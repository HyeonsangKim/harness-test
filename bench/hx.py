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


def finish_line(tool_output, contract):
    """Last non-empty stdout line of a run_python result, if it already is a valid answer."""
    if not contract or contract.get("type") != "json":
        return None
    try:
        res = json.loads(tool_output)
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
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504) or attempt == 5:
                    body = " ".join(e.read().decode("utf-8", "replace").split())[:200]
                    raise RuntimeError(self.redact(f"http_{e.code}: {body}"))
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as e:
                if attempt == 5:
                    raise RuntimeError(self.redact(f"connection: {e}"))
            time.sleep(min(5 * 2 ** attempt, 60))


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

_PY = {"str": str, "int": int, "float": (int, float), "list": list, "bool": bool, "dict": dict}


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
        max_turns=12, trace=None, history=None, system=SYSTEM, resume=False):
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
    for turn in range(used, max_turns):
        save(False)
        try:
            resp = client.chat(messages, specs)
        except RuntimeError as e:
            error = str(e)
            break
        usage = resp.get("usage") or {}
        tokens["prompt"] += usage.get("prompt_tokens") or 0
        tokens["completion"] += usage.get("completion_tokens") or 0
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
                if "budget" in feats and left == 2 and i == len(tcalls) - 1:
                    events.append("budget_warning")
                    out += "\n[harness] Only 2 turns are left. Finish now and give the final answer in the required format."
                messages.append({"role": "tool", "tool_call_id": tc.get("id") or f"call_{turn}_{i}", "content": out})
                if "autofinish" in feats and finished is None:
                    finished = finish_line(out, contract)
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
        if "evidence" in feats and calls == 0 and not rechecks["evidence"]:
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
    return Client(url, os.environ["LLM_MODEL"], key, os.getenv("LLM_CA_FILE"), extra=extra,
                  gap=float(os.getenv("LLM_GAP", "0")))
