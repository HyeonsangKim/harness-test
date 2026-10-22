"""Harness v0: one tool loop, harness features switched by flags. Standard library only.

Conditions compared by ab.py:
  B  plain tool loop (what most quick agent scripts do)
  C  B + one generic "double-check your answer" turn (control: same extra turn, no specific feedback)
  H  B + harness features below

Harness features (each is generic: none knows about a specific task):
  recover   tool calls written as text (Qwen XML, GLM arg_key, JSON) are parsed and executed
  validate  arguments are checked against the tool schema before running; errors carry the schema
  repeat    the same call with the same arguments is flagged, the third time it is not run
  budget    the model is told when two turns are left
  contract  the final answer is checked against the required format; specific fix-up request
  verify    the task adapter's own check (for code: the project's tests) runs before accepting
  evidence  an answer given before any tool call is sent back once
"""
import difflib
import getpass
import http.client
import json
import math
import os
import re
import ssl
import time
import urllib.error
import urllib.request

import grade

FEATURES = ("recover", "validate", "repeat", "budget", "contract", "verify", "evidence")
# v1: "repeat" (flags and blocks identical calls) is replaced by "stall": a note only when the same call
# returns exactly the same result again, never blocking. Found on BFCL: in stateful tools (cd, then ls)
# identical calls are legitimate and the v0 note "result is unchanged" was false.
FEATURES_V1 = ("recover", "validate", "stall", "budget", "contract", "verify", "evidence")
# tool-free harness v2: v1 + "autofinish" (the last printed line of a program that already matches the
# answer format becomes the reply, saving the final model turn).
FEATURES_NT2 = FEATURES_V1 + ("autofinish",)
# RT2: autofinish only when a second, independent program prints the same answer (conditional offloading)
FEATURES_NT3 = FEATURES_NT2 + ("crosscheck",)
# v6: before autofinish, numbers written into the program that the request never mentions are pointed out once
# (a small model tends to use a constant it knows, e.g. 7.48 gallons per cubic foot, instead of the given one)
FEATURES_NT6 = FEATURES_NT2 + ("numcheck",)
# v7: the "answered without code" check only when a number is asked for or a table is given (general tasks:
# writing, choices, yes/no are not pushed into code)
FEATURES_NT7 = FEATURES_NT2 + ("evidence_auto",)
FEATURES_NT7C = FEATURES_NT6 + ("evidence_auto",)
# v9: before autofinish, a text field of the answer left empty is pointed out once (a program fills the numbers
# carefully but tends to leave a unit or label field blank, which the model would have read off the data)
FEATURES_NT9 = FEATURES_NT7 + ("emptycheck",)
# v10: + no autofinish when the request states cleanup rules (the model checks the output against them),
# + later turns see the pasted data shortened (it is in input.txt and table files)
FEATURES_NT10 = FEATURES_NT9 + ("rulegate", "compact")
# v11: NT9 + thinking only when reading is hard or the run shows trouble (fast on simple requests)
FEATURES_NT11 = FEATURES_NT9 + ("adaptive_think",)
# v12 (RT21): RT19 + cleanup-rule review + shortened data in later turns (helpers and turn budget set by ab.py)
FEATURES_NT12 = FEATURES_NT9 + ("rulegate", "compact", "errgate")
# v13 (RT22): RT21 + rule checklist before an answer is accepted + a second independent program for hard requests
FEATURES_NT13 = FEATURES_NT12 + ("rulecheck", "crosshard")
# v3b: tables as files but no autofinish (the model reviews the program output before answering)


def _norm_answer(line):
    """Answer JSON with numbers normalized (rounded to 6 places) and lists sorted, for comparing two programs."""
    parsed = grade.parse_json(line) or {}
    out = {}
    for k, v in parsed.items():
        n = grade.num(v)
        if n is not None:
            out[k] = round(float(n), 6)
        elif isinstance(v, list):
            out[k] = sorted(" ".join(str(x).split()) for x in v)
        else:
            out[k] = " ".join(str(v).split())
    return out


_COMMON = {0.25, 0.5, 0.75, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 24, 28, 29, 30, 31, 52, 60, 100, 365, 366, 1000, 1440, 3600}


def _numbers_in_text(text):
    found = set()
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", text or ""):
        tok = m.group().rstrip(",")
        try:
            v = float(tok.replace(",", ""))
        except ValueError:
            continue
        found.update({v, v / 100, v * 100})          # 12.5% may be written as 0.125, 0.125 as 12.5
        if "," in tok:                               # "1,234" could also be read as two numbers
            for part in tok.split(","):
                if part:
                    found.add(float(part))
    return found


def foreign_numbers(code, request):
    """Number literals in the program (not in comments or strings) that the request does not contain.
    Small integers, powers of ten and common calendar/clock constants are allowed."""
    import io
    import tokenize
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(code or "").readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []
    given = _numbers_in_text(request)
    out = []
    for t in toks:
        if t.type != tokenize.NUMBER:
            continue
        try:
            v = float(t.string.replace("_", "").rstrip("jJ"))
        except ValueError:
            continue
        if v in _COMMON or (v > 0 and abs(math.log10(v) - round(math.log10(v))) < 1e-9):
            continue
        if not any(math.isclose(v, g, rel_tol=1e-9, abs_tol=1e-12) for g in given):
            out.append(t.string)
    return sorted(set(out), key=out.index)


def needs_code(request, contract):
    """The request asks for a number, or carries a table: an answer without running code is likely a guess.
    Writing, rewriting, choosing an option or answering yes/no does not need code."""
    keys = (contract or {}).get("keys") or {}
    if any(t in ("int", "float") for t in keys.values()):
        return True
    for d in ("\t", "|", ","):
        rows = [l for l in (request or "").splitlines() if l.count(d) >= 2]
        if len(rows) >= 3:
            return True
    return False


_CODE_ASK = re.compile(r"```python|\bdef \w+\(|파이썬|python 함수|python function|write a (python )?function|"
                       r"함수를? 작성", re.IGNORECASE)


def wants_harness(request, contract):
    """Route a request: the harness (run_python, its working rules, checks) is for requests with a structured
    answer (JSON), a pasted table, or a request for code. Free-form writing goes to the model directly, because
    the working rules for code distract a small model from writing instructions (IFEval)."""
    if (contract or {}).get("type") == "json":
        return True
    return needs_code(request, contract) or bool(_CODE_ASK.search(request or "")) or asks_for_number(request)


_CALC_ASK = re.compile(r"합계|평균|총액|몇 (?:명|개|건|일|시간|번)|얼마|비율|증가율|감소율|차이는|계산|"
                       r"how many|how much|in total|average|percentage|what is the (?:sum|total|difference)",
                       re.IGNORECASE)


def asks_for_number(request):
    """A free-text question that asks for a computed number from figures it gives (at least three numbers)."""
    text = request or ""
    return bool(_CALC_ASK.search(text)) and len(re.findall(r"\d[\d,]*(?:\.\d+)?", text)) >= 3


_RULE_CUES = re.compile(r"무시|한 번만|같은 (?:것|사람|품목|거래처|입고)|중복|제외하|빼고|세지 (?:않|마)|합계 행|소계|메모|"
                        r"\bignore\b|only once|\bexclude|duplicate|do not count|treat .{0,30} as the same", re.IGNORECASE)


def has_cleanup_rules(request):
    """The request states rules for cleaning the data (duplicates, notes, rows not to count). A program's first
    output often misses one of them, so the model should look at the output before answering."""
    return len(_RULE_CUES.findall(request or "")) >= 2


def _compact(messages, keep=1200):
    """After the first reply, send the request with its pasted data shortened: the data is in input.txt and the
    table files, so later turns do not need to read it again. The trace keeps the full text."""
    if not any(m.get("role") == "assistant" for m in messages):
        return messages
    out, done = [], False
    for m in messages:
        c = m.get("content")
        if not done and m.get("role") == "user" and isinstance(c, str) and len(c) > 3 * keep:
            m = dict(m, content=c[:keep] + f"\n[harness] ... {len(c) - 2 * keep} characters of the pasted data are "
                     "left out here; the full request is in input.txt and its tables in the table files ...\n" + c[-keep:])
            done = True
        out.append(m)
    return out


def wants_thinking(request):
    """Reading is the hard part: a pasted table, a long request, or data-cleanup rules."""
    text = request or ""
    return needs_code(text, None) or len(text) > 4000 or has_cleanup_rules(text)


# only words that mean the program failed on some input; "skipped"/"제외" are normal reports of applied rules
_OUTPUT_TROUBLE = re.compile(r"\berror\b|could not|cannot (?:parse|convert|read)|failed|invalid literal|unparsed|"
                             r"traceback|실패|오류|에러|파싱 불가|읽지 못|변환 불가", re.IGNORECASE)


def output_reports_trouble(tool_output):
    """The program itself printed that something went wrong (a row it could not read, a skipped value).
    Its last line may still look like an answer, but the total is likely missing those rows."""
    try:
        res, _ = json.JSONDecoder().raw_decode(tool_output)
    except ValueError:
        return False
    lines = [l for l in str(res.get("stdout", "")).splitlines() if l.strip()][:-1]   # not the answer line itself
    return any(_OUTPUT_TROUBLE.search(l) for l in lines)


_RULE_WORDS = re.compile(r"규칙|제외|중복|무시|한 번만|단위|환산|우선|정정|반올림|버림|절사|올림|기준|포함하지|빼고|"
                         r"만 (?:집계|계산|센|인정)|면세|비과세|한도|상한|하한|가산|할인|초과|미만|이상|이하|"
                         r"\bexcept\b|\bexclude|\bignore\b|only|round|treat|unless|at most|at least", re.IGNORECASE)


def rule_lines(request, limit=12):
    """Sentences of the request that state a rule (exclusions, duplicates, units, precedence, limits, rounding).
    Data rows are skipped: lines with many digits or table delimiters."""
    out, seen = [], set()
    for line in (request or "").splitlines():
        if line.count("\t") >= 1 or line.count("|") >= 2 or line.count(",") >= 3:
            continue
        for part in re.split(r"(?<=[.。])\s+|(?<=다\.)|(?<=요\.)", line):
            part = part.strip(" -*•")
            if len(part) < 8 or not _RULE_WORDS.search(part):
                continue
            if sum(ch.isdigit() for ch in part) > 0.3 * len(part):
                continue
            key = part[:60]
            if key not in seen:
                seen.add(key)
                out.append(part[:200])
    return out[:limit]


def is_hard_request(request):
    """Long data or many stated rules: worth a second, independent program before an answer is accepted."""
    return len(request or "") > 6000 or len(rule_lines(request)) >= 4


def finish_line(tool_output, contract):
    """Last non-empty stdout line of a run_python result, if it already is a valid answer."""
    if not contract or contract.get("type") != "json":
        return None
    try:
        res, _ = json.JSONDecoder().raw_decode(tool_output)   # ignore harness notes appended after the result
    except ValueError:
        return None
    if not isinstance(res, dict) or res.get("exit_code") != 0:
        return None
    lines = [l.strip() for l in str(res.get("stdout", "")).splitlines() if l.strip()]
    if lines and grade.parse_json(lines[-1]) is not None and not contract_problems(lines[-1], contract):
        return lines[-1]
    return None
SYSTEM = ("You are a work assistant for a Korean company. Use the tools to find facts; do not guess "
          "numbers or names. When you are done, reply with the final answer in exactly the format the user asked for.")


# ---------------------------------------------------------------- model client

class Client:
    def __init__(self, url, model, key="", ca_file=None, extra=None, timeout=600, gap=0.0):
        self.url, self.model, self.key, self.extra, self.timeout = url, model, key, extra or {}, timeout
        self.gap = gap   # seconds to pause before every request (gateway rate limits)
        self.ctx = ssl.create_default_context(cafile=ca_file)

    def redact(self, text):
        """Hide the key, key hashes and addresses in error text that may be copied by hand."""
        text = str(text)
        if self.key:
            text = text.replace(self.key, "***")
        text = re.sub(r"(sk-|Bearer )\S+", r"\1***", text)
        text = re.sub(r"\b[0-9a-fA-F]{24,}\b", "<hash>", text)
        return re.sub(r"https?://\S+|\b\d{1,3}(\.\d{1,3}){3}(:\d+)?\b", "<addr>", text)

    def chat(self, messages, tools, max_tokens=None):
        body = {"model": self.model, "messages": messages,
                "max_tokens": max_tokens or getattr(self, "max_tokens", 4096), **self.extra}
        if tools:   # some servers reject an empty tools list, so plain chat sends none
            body.update(tools=[{"type": "function", "function": t} for t in tools], tool_choice="auto")
        # LLM_STREAM=1: receive the reply as it is written. The timeout then only fires when nothing arrives for
        # that long (a slow, long-thinking model is not cut off), and a reply that loops can be stopped early.
        stream = os.getenv("LLM_STREAM") == "1"
        if stream:
            body.update(stream=True, stream_options={"include_usage": True})
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        for attempt in range(6):
            if self.gap:
                time.sleep(self.gap)
            req = urllib.request.Request(self.url, data=data, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
                    return self._read_stream(r) if stream else json.load(r)
            except urllib.error.HTTPError as e:
                body = " ".join(e.read().decode("utf-8", "replace").split())[:200]
                if e.code == 500 and "parse tool call" in body:
                    # the server could not read the model's tool call (seen when the model writes the same
                    # code over and over until max_tokens cuts it): resending the same request does not help
                    raise RuntimeError(self.redact(f"bad_tool_call: {body}"))
                if e.code not in (429, 500, 502, 503, 504) or attempt == 5:
                    raise RuntimeError(self.redact(f"http_{e.code}: {body}"))
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as e:
                if attempt == 5:
                    raise RuntimeError(self.redact(f"connection: {e}"))
            time.sleep(min(5 * 2 ** attempt, 60))


    @staticmethod
    def _looping(text, span=80, times=6, window=4000):
        """The reply keeps writing the same text: its last `span` characters already occur `times` times in the
        last `window` characters."""
        if len(text) < span * times:
            return False
        return text[-window:].count(text[-span:]) >= times

    def _read_stream(self, r):
        """Collect a server-sent-events reply into the same shape as a non-streamed one."""
        content, reasoning, calls, finish, usage = [], [], {}, None, None
        written = 0
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            usage = chunk.get("usage") or usage
            for ch in chunk.get("choices") or []:
                d = ch.get("delta") or {}
                content.append(d.get("content") or "")
                reasoning.append(d.get("reasoning_content") or "")
                for tc in d.get("tool_calls") or []:
                    slot = calls.setdefault(tc.get("index", 0), {"id": None, "type": "function",
                                                                 "function": {"name": "", "arguments": ""}})
                    slot["id"] = tc.get("id") or slot["id"]
                    fn = tc.get("function") or {}
                    slot["function"]["name"] += fn.get("name") or ""
                    slot["function"]["arguments"] += fn.get("arguments") or ""
                finish = ch.get("finish_reason") or finish
            text = "".join(content) + "".join(c["function"]["arguments"] for c in calls.values())
            if len(text) - written >= 500:      # check now and then, not on every token
                written = len(text)
                args = "".join(c["function"]["arguments"] for c in calls.values())
                # a long program that is mostly comments weighing readings ("But wait, ...") does not converge;
                # normal programs, even well-commented ones, stay far below 8000 characters
                lines = args.count("\\n") + 1
                comments = len(re.findall(r"\\n\s*#", args))
                if self._looping(text) or (len(args) > 8000 and comments > 0.5 * lines):
                    finish = "loop"
                    break
        msg = {"role": "assistant", "content": "".join(content) or None}
        if any(reasoning):
            msg["reasoning_content"] = "".join(reasoning)
        if calls and finish != "loop":
            msg["tool_calls"] = [calls[i] for i in sorted(calls)]
        return {"choices": [{"message": msg, "finish_reason": finish}], "usage": usage or {}}


# ---------------------------------------------------------------- text tool-call recovery

def _coerce(v):
    try:
        return json.loads(v)
    except ValueError:
        return v


def parse_text_calls(text):
    """Tool calls that the model wrote into the message text instead of the tool_calls field."""
    calls = []
    for name, body in re.findall(r"<function=([\w.-]+)>(.*?)</function>", text or "", re.S):        # Qwen3 XML
        args = {k: _coerce(v.strip()) for k, v in re.findall(r"<parameter=([\w.-]+)>(.*?)</parameter>", body, re.S)}
        calls.append((name, args))
    if calls:
        return calls
    for block in re.findall(r"<tool_call>(.*?)</tool_call>", text or "", re.S):
        block = block.strip()
        if "<arg_key>" in block:                                                                     # GLM
            name = block.split("<arg_key>")[0].strip()
            keys = re.findall(r"<arg_key>(.*?)</arg_key>", block, re.S)
            vals = re.findall(r"<arg_value>(.*?)</arg_value>", block, re.S)
            calls.append((name, {k.strip(): _coerce(v.strip()) for k, v in zip(keys, vals)}))
        else:                                                                                        # JSON
            try:
                obj = json.loads(block)
                calls.append((obj["name"], obj.get("arguments") or {}))
            except (ValueError, KeyError, TypeError):
                pass
    return calls


# ---------------------------------------------------------------- argument validation

_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}


def _check_value(v, schema, path):
    t = schema.get("type")
    if t and not isinstance(v, _TYPES[t]) or (t in ("integer", "number") and isinstance(v, bool)):
        return [f"{path} must be {t}, got {type(v).__name__} {json.dumps(v, ensure_ascii=False)[:40]}"]
    if "enum" in schema and v not in schema["enum"]:
        return [f"{path} must be one of {schema['enum']}, got {v!r}"]
    errs = []
    if t == "array" and "items" in schema:
        for i, item in enumerate(v):
            errs += _check_value(item, schema["items"], f"{path}[{i}]")
    if t == "object" and "properties" in schema:
        errs += _check_object(v, schema, path)
    return errs


def _check_object(args, schema, path="arguments"):
    props, errs = schema.get("properties", {}), []
    for k in schema.get("required", []):
        if k not in args:
            errs.append(f"missing required {path}.{k}")
    for k, v in args.items():
        if k not in props:
            near = difflib.get_close_matches(k, props, 1)
            errs.append(f"unknown parameter {path}.{k}" + (f" (did you mean {near[0]!r}?)" if near else ""))
        else:
            errs += _check_value(v, props[k], f"{path}.{k}")
    return errs


def validate(name, args, tools):
    if name not in tools:
        near = difflib.get_close_matches(name, tools, 1)
        return [f"unknown tool {name!r}" + (f" (did you mean {near[0]!r}?)" if near else "") + f". Tools: {sorted(tools)}"]
    if not isinstance(args, dict):
        return ["arguments must be a JSON object"]
    return _check_object(args, tools[name][0]["parameters"])


# ---------------------------------------------------------------- answer contract

_PY = {"str": str, "int": int, "float": (int, float), "list": list, "bool": bool, "dict": dict, "any": object}


def contract_problems(answer, contract):
    if not contract or contract.get("type") != "json":
        return []
    parsed = grade.parse_json(answer)
    if parsed is None:
        return ["the answer must contain one JSON object"]
    errs = []
    for k, t in contract.get("keys", {}).items():
        if k not in parsed:
            errs.append(f"missing key {k!r}")
            continue
        v = parsed[k]
        if t in ("int", "float") and isinstance(v, str) and grade.num(v) is not None:
            errs.append(f"key {k!r} must be a plain number, not the text {v!r}")
        elif not isinstance(v, _PY[t]) or (t in ("int", "float") and isinstance(v, bool)):
            errs.append(f"key {k!r} must be {t}, got {type(v).__name__}")
    return errs


# ---------------------------------------------------------------- the loop

def _result_text(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text[:8000]


def run(client, task_prompt, tools, features=(), control=False, contract=None, verify=None,
        max_turns=12, trace=None, history=None, system=SYSTEM, resume=False, think_client=None):
    """tools: {name: (spec, fn)}. verify: callable() -> (ok, message) or None.
    history: messages of earlier turns of the same conversation (multi-turn tasks).
    trace: file written after every turn (a checkpoint). resume=True continues an unfinished trace.
    Returns dict(answer, turns, calls, events, error, messages, executed, tokens)."""
    feats = set(features)
    specs = [spec for spec, _ in tools.values()]
    messages = list(history) if history else [{"role": "system", "content": system}]
    messages.append({"role": "user", "content": task_prompt})
    executed = []
    seen, calls, events = {}, 0, []
    results, stalls = {}, {}
    rechecks = {"contract": 0, "verify": 0, "evidence": 0, "control": 0}
    answer, error, finished = None, None, None
    cross = {"first": None, "off": False, "code": None}
    tokens = {"prompt": 0, "completion": 0}
    if resume and trace is not None and trace.exists():
        saved = json.loads(trace.read_text(encoding="utf-8"))
        if not saved.get("done", True):
            messages, events = saved["messages"], saved["events"]
            seen, calls, rechecks = saved["state"]["seen"], saved["state"]["calls"], saved["state"]["rechecks"]
            tokens = saved.get("tokens", tokens)
            events.append("resumed")

    def save(done):
        if trace is not None:
            trace.write_text(json.dumps({"done": done, "messages": messages, "events": events, "error": error,
                                         "tokens": tokens,
                                         "state": {"seen": seen, "calls": calls, "rechecks": rechecks}},
                                        ensure_ascii=False, indent=1), encoding="utf-8")

    def execute(name, args):
        nonlocal calls
        calls += 1
        executed.append((name, args))
        key = name + json.dumps(args, sort_keys=True, ensure_ascii=False)
        seen[key] = seen.get(key, 0) + 1
        prefix = ""
        if "repeat" in feats and seen[key] >= 2:
            events.append("repeat")
            if seen[key] >= 3:
                return ("[harness] You already made this exact call twice and got the same result. "
                        "It was not run again. Try different arguments or a different tool, or give the answer.")
            prefix = "[harness] Note: you already made this exact call; the result is unchanged.\n"
        if "validate" in feats:
            problems = validate(name, args, tools)
            if problems:
                events.append("invalid_args")
                schema = json.dumps(tools[name][0]["parameters"], ensure_ascii=False) if name in tools else ""
                return ("[harness] The call was not run because the arguments are invalid:\n- " + "\n- ".join(problems)
                        + (f"\nParameter schema: {schema}" if schema else "") + "\nFix the arguments and call again.")
        if name not in tools:
            return f"Error: unknown tool {name}"
        try:
            out = prefix + _result_text(tools[name][1](**args))
        except Exception as e:  # noqa: BLE001 - tools raise ordinary exceptions by design
            out = f"Error: {type(e).__name__}: {e}"
            if "validate" in feats:
                events.append("tool_error")
                out += ("\n[harness] The tool failed with these arguments. Check names and values "
                        "(list/describe tools can show valid ones), fix them and call again.")
            out = prefix + out
        if "stall" in feats:
            same = results.get(key) == out
            results[key] = out
            if same:
                stalls[key] = stalls.get(key, 0) + 1
                events.append("stall")
                out += ("\n[harness] This exact call already returned exactly this result. "
                        "Repeating it will not change anything: try a different step, or give the answer.")
        return out

    used = sum(1 for m in messages if m["role"] == "assistant")
    bad_calls, room = 0, None
    numchecked, last_code = False, ""
    emptychecked = False
    gate = {"rules": rule_lines(task_prompt) if "rulecheck" in feats else [], "rules_done": False,
            "hard": "crosshard" in feats and is_hard_request(task_prompt), "stage": None, "first": None}

    def final_gate(candidate):
        """Checks before an answer is accepted: the stated rules one by one, then (for hard requests) a second,
        independent program that must reach the same answer. Returns a message for the model, or None."""
        if gate["rules"] and not gate["rules_done"]:
            gate["rules_done"] = True
            events.append("rulecheck")
            return ("[harness] Before this answer is accepted, check it against every rule in the request:\n"
                    + "\n".join(f"{i}. {r}" for i, r in enumerate(gate["rules"], 1))
                    + "\nFor each rule, say in one line where your program applies it. If one is missing or wrong, "
                    "fix the program and run it again. Then give the final answer in the required format.")
        if gate["hard"] and gate["stage"] is None:
            gate["stage"], gate["first"] = "asked", _norm_answer(candidate)
            events.append("crosshard_ask")
            return ("[harness] This request has a lot of data or many rules. Before the answer is accepted, write a "
                    "second, independent program that computes the same answer another way (do not copy the first "
                    "program), and print its answer as the last line in the required format.")
        if gate["hard"] and gate["stage"] == "asked":
            gate["stage"] = "done"
            second = _norm_answer(candidate)
            if second == gate["first"]:
                events.append("crosshard_agree")
                return None
            events.append("crosshard_disagree")
            return ("[harness] The two programs disagree:\n- first: " + json.dumps(gate["first"], ensure_ascii=False)
                    + "\n- second: " + json.dumps(second, ensure_ascii=False)
                    + "\nFind which one follows every rule in the request, fix it if needed, and give the final answer "
                    "in the required format.")
        return None
    # with the rule checklist (rulecheck) the review happens at the answer gate, so autofinish stays on: turning it
    # off made the model print answer lines turn after turn that were never taken (the tool says printing answers)
    rule_review = "rulegate" in feats and "rulecheck" not in feats and has_cleanup_rules(task_prompt)
    if rule_review:
        events.append("rule_review")
    # adaptive thinking: the model's own long thinking only when reading is hard (a table, a long request, cleanup
    # rules) or when the run shows trouble (repeated code errors, a stall, an empty answer field, a loop)
    thinking = "adaptive_think" in feats and think_client is not None and wants_thinking(task_prompt)
    if thinking:
        events.append("think_start")
    code_errors = 0
    for turn in range(used, max_turns):
        save(False)
        if "adaptive_think" in feats and think_client is not None and not thinking and (
                code_errors >= 2 or any(e in events for e in ("stall", "emptycheck", "loop", "bad_call"))):
            thinking = True
            events.append("think_on")
        chat_client = think_client if thinking else client
        try:
            resp = chat_client.chat(_compact(messages) if "compact" in feats else messages, specs, max_tokens=room)
        except RuntimeError as e:
            if str(e).startswith("bad_tool_call") and "recover" in feats and bad_calls < 2:
                # a tool call cut off by the output limit: give the next reply twice the room, like length_retry
                bad_calls += 1
                room = min((room or getattr(client, "max_tokens", 4096)) * 2, 32768)
                events.append("bad_call")
                messages.append({"role": "user", "content": (
                    "[harness] Your last reply could not be read: the tool call was cut off or malformed, "
                    "probably because the code was too long or repeated itself. Send a short program "
                    "(about 60 lines at most) that reads the data from the files instead of writing it out.")})
                continue
            error = str(e)
            break
        cap = getattr(client, "max_tokens", 4096)
        while True:   # the model ran out of output room before saying anything: give it more, up to 32k
            ch = (resp.get("choices") or [{}])[0]
            m0 = ch.get("message") or {}
            if not (ch.get("finish_reason") == "length" and not m0.get("content") and not m0.get("tool_calls")
                    and cap < 32768):
                break
            cap = min(cap * 2, 32768)
            events.append("length_retry")
            u0 = resp.get("usage") or {}
            tokens["prompt"] += u0.get("prompt_tokens") or 0
            tokens["completion"] += u0.get("completion_tokens") or 0
            try:
                resp = chat_client.chat(_compact(messages) if "compact" in feats else messages, specs, max_tokens=cap)
            except RuntimeError as e:
                error = str(e)
                resp = {}
                break
        if not resp:
            break
        usage = resp.get("usage") or {}
        tokens["prompt"] += usage.get("prompt_tokens") or 0
        tokens["completion"] += usage.get("completion_tokens") or 0
        if (resp.get("choices") or [{}])[0].get("finish_reason") == "loop" and "recover" in feats and bad_calls < 2:
            bad_calls += 1      # stopped while writing the same text over and over: more room would not help
            events.append("loop")
            messages.append({"role": "user", "content": (
                "[harness] Your last reply was stopped because it kept repeating the same text. Do not weigh "
                "readings in comments: pick the most likely reading of the question, state it in one comment "
                "line, and send a short program.")})
            continue
        msg = (resp.get("choices") or [{}])[0].get("message") or {}
        content = msg.get("content") or ""
        tcalls = msg.get("tool_calls") or []
        if not tcalls and "recover" in feats:
            found = parse_text_calls(content)
            if found:
                events.append("recovered_text_call")
                tcalls = [{"id": f"rec_{turn}_{i}", "type": "function",
                           "function": {"name": n, "arguments": json.dumps(a, ensure_ascii=False)}}
                          for i, (n, a) in enumerate(found)]
                content = ""
        asst = {"role": "assistant", "content": content}
        if tcalls:
            asst["tool_calls"] = tcalls
        messages.append(asst)
        left = max_turns - turn - 1
        if tcalls:
            for i, tc in enumerate(tcalls):
                fn = tc.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args, out = None, "Error: arguments are not valid JSON"
                if args is not None:
                    out = execute(fn.get("name", ""), args if isinstance(args, dict) else {"_": args})
                    if '"exit_code": 0' not in out[:40]:
                        code_errors += 1
                    if isinstance(args, dict):
                        last_code = str(args.get("code", ""))
                if "budget" in feats and left == 2 and i == len(tcalls) - 1:
                    events.append("budget_warning")
                    out += "\n[harness] Only 2 turns are left. Finish now and give the final answer in the required format."
                messages.append({"role": "tool", "tool_call_id": tc.get("id") or f"call_{turn}_{i}", "content": out})
                if "autofinish" in feats and finished is None and not cross["off"] and not rule_review:
                    finished = finish_line(out, contract)
                    if finished is not None and "errgate" in feats and output_reports_trouble(out):
                        finished = None             # the model sees its own warnings before answering
                        events.append("errgate")
                    code_now = json.dumps(args, sort_keys=True) if args is not None else ""
                    if finished is not None and "crosscheck" in feats and cross["first"] is not None \
                            and code_now == cross["code"]:
                        finished = None                # same program again is not an independent check
                        events.append("crosscheck_same_code")
                        messages.append({"role": "user", "content": (
                            "[harness] That is the same program. Write a different, independent program "
                            "(another method) and print its answer as the last line.")})
                    elif finished is not None and cross["first"] is None:
                        cross["code"] = code_now
            if finished is not None and "crosscheck" in feats:
                key = _norm_answer(finished)
                if cross["first"] is None:            # first candidate: ask for an independent second program
                    cross["first"], finished = key, None
                    events.append("crosscheck_ask")
                    messages.append({"role": "user", "content": (
                        "[harness] Before this answer is accepted, write a second, independent program that "
                        "computes the same result a different way (do not copy the first program). "
                        "Print its answer as the last line in the same format.")})
                    continue
                if key == cross["first"]:
                    events.append("crosscheck_agree")
                else:                                  # disagreement: show both, let the model decide
                    events.append("crosscheck_disagree")
                    cross["off"], finished = True, None
                    messages.append({"role": "user", "content": (
                        "[harness] The two programs disagree:\n- first: " + json.dumps(cross["first"], ensure_ascii=False)
                        + "\n- second: " + json.dumps(key, ensure_ascii=False)
                        + "\nFind which one follows the rules in the request (check each rule), fix it if needed, "
                        "and reply with the final answer in the required format.")})
                    continue
            if finished is not None and "emptycheck" in feats and not emptychecked:
                parsed = grade.parse_json(finished) or {}
                blank = [k for k, t in ((contract or {}).get("keys") or {}).items()
                         if t in ("str", "any") and str(parsed.get(k, "")).strip() == ""]
                if blank:
                    emptychecked, finished = True, None
                    events.append("emptycheck")
                    messages.append({"role": "user", "content": (
                        "[harness] Before this answer is accepted: the field(s) " + ", ".join(blank) + " are empty. "
                        "Decide what belongs there from the request's own instructions for that field. A unit field "
                        "is the unit of the answer itself: a ratio, share or rate of change is a percentage; an "
                        "amount keeps the unit the data uses for it. Leave it empty only if the request says so for "
                        "this kind of answer. Then print the answer line again.")})
                    continue
            if finished is not None and "numcheck" in feats and not numchecked:
                extra = foreign_numbers(last_code, task_prompt)
                if extra:
                    numchecked, finished = True, None
                    events.append("numcheck")
                    messages.append({"role": "user", "content": (
                        "[harness] Before this answer is accepted: your program uses numbers that do not appear "
                        "in the request: " + ", ".join(extra[:8]) + ". If the request gives a value or a rule "
                        "for any of them, use the request's value instead. If a number really follows from the "
                        "wording (for example a unit conversion the request implies), keep it. Then run the "
                        "program again.")})
                    continue
            if finished is not None and ("rulecheck" in feats or "crosshard" in feats):
                note = final_gate(finished)
                if note:
                    finished = None
                    messages.append({"role": "user", "content": note})
                    continue
            if finished is not None:
                answer = finished
                events.append("autofinish")
                break
            continue
        # no tool call: a candidate final answer
        answer = content
        if left == 0:
            break
        feedback = None
        if "evidence" in feats and calls == 0 and not rechecks["evidence"] and (
                "evidence_auto" not in feats or needs_code(task_prompt, contract)):
            rechecks["evidence"] = 1
            kind = "recheck_evidence"
            feedback = "[harness] You answered without using any tool. Look the facts up with the tools first, then answer."
        if feedback is None and "contract" in feats and rechecks["contract"] < 2:
            problems = contract_problems(content, contract)
            if problems:
                rechecks["contract"] += 1
                kind = "recheck_contract"
                feedback = ("[harness] The answer does not match the required format:\n- " + "\n- ".join(problems)
                            + "\nReply again with only the answer in the required format.")
        if feedback is None and "verify" in feats and verify and rechecks["verify"] < 2:
            ok, detail = verify()
            if not ok:
                rechecks["verify"] += 1
                kind = "recheck_verify"
                feedback = f"[harness] Automatic check failed, so the task is not done yet:\n{detail}\nFix it, then answer again."
        if feedback is None and ("rulecheck" in feats or "crosshard" in feats) \
                and not contract_problems(content, contract):
            note = final_gate(content)
            if note:
                feedback, kind = note, "final_gate"
        if feedback is None and control and not rechecks["control"]:
            rechecks["control"] = 1
            kind = "recheck_control"
            feedback = "Please double-check your work and then reply again with the final answer in the required format."
        if feedback is None:
            break
        events.append(kind)
        messages.append({"role": "user", "content": feedback})
    else:
        error = error or "max_turns"
    save(True)
    return {"answer": answer, "turns": sum(1 for m in messages if m["role"] == "assistant"),
            "calls": calls, "events": events, "error": error, "messages": messages, "executed": executed,
            "tokens": tokens}


def client_from_env(extra=None):
    url = os.environ["LLM_URL"]
    key = os.getenv("LLM_API_KEY")
    if key is None:
        local = "://127.0.0.1" in url or "://localhost" in url
        key = "" if local else getpass.getpass("API key: ")
    client = Client(url, os.environ["LLM_MODEL"], key, os.getenv("LLM_CA_FILE"), extra=extra,
                    gap=float(os.getenv("LLM_GAP", "0")))
    client.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))   # raise for models that think by default
    return client
