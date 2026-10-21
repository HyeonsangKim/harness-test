"""GLM gateway probe -> model profile. Python 3.12, standard library only.
env: LLM_URL (full .../chat/completions), LLM_MODEL, optional LLM_API_KEY, LLM_CA_FILE
run: python probe.py --n 10
"""
import argparse
import concurrent.futures as cf
import getpass
import json
import os
import re
import ssl
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

URL, MODEL = os.environ["LLM_URL"], os.environ["LLM_MODEL"]
KEY = os.getenv("LLM_API_KEY") or getpass.getpass("API key: ")
CTX = ssl.create_default_context(cafile=os.getenv("LLM_CA_FILE"))
OUT = Path("probe_out") / time.strftime("%Y%m%d-%H%M%S")
RETRIES = int(os.getenv("LLM_RETRIES", "5"))   # retries on 429
GAP = float(os.getenv("LLM_GAP", "0"))          # seconds to pause before every call
RL = {"hits": 0, "retries": 0, "waited": 0, "gave_up": 0, "skipped": 0, "body": "", "headers": {}}
GIVE_UP = 3   # after this many calls still 429 after retries, skip the rest


def retry_after(hdrs, attempt):
    try:
        return min(max(float(hdrs.get("retry-after")), 1), 120)
    except (TypeError, ValueError):
        return min(5 * 2 ** attempt, 60)


def redact(text):
    """Hide the key, key hashes, tokens and addresses before anything is printed."""
    if KEY:
        text = text.replace(KEY, "***")
    text = re.sub(r"(sk-|Bearer )\S+", r"\1***", text)
    text = re.sub(r"\b[0-9a-fA-F]{24,}\b", "<hash>", text)
    return re.sub(r"https?://\S+|\b\d{1,3}(\.\d{1,3}){3}(:\d+)?\b", "<addr>", text)


def note_429(data, hdrs):
    RL["hits"] += 1
    if not RL["body"]:
        try:
            err = json.loads(data).get("error", data)
            data = err.get("message", err) if isinstance(err, dict) else err
        except (ValueError, AttributeError, TypeError):
            pass
        RL["body"] = redact(" ".join(str(data).split()))[:160]
        RL["headers"] = {k.lower(): v for k, v in hdrs.items()
                         if "ratelimit" in k.lower() or k.lower() == "retry-after"}


FN = {"name": "get_weather", "description": "Get the current weather for a city.",
      "parameters": {"type": "object", "properties": {"city": {"type": "string"}},
                     "required": ["city"], "additionalProperties": False}}
TOOL = {"type": "function", "function": FN}
ASK = {"en": "What is the weather in Seoul right now? Use the tool.",
       "ko": "지금 서울 날씨 어때? 도구를 사용해서 알려줘."}
CALIB = {
    "ko": "회의록에 따르면 다음 분기 예산은 조금 늘어나며, 각 팀은 금요일까지 계획서를 내야 한다. " * 20,
    "en": "According to the notes, next quarter's budget rises slightly and plans are due Friday. " * 20,
    "json": json.dumps([{"id": f"R{i}", "group": "A", "amount": i * 10, "approved": True}
                        for i in range(40)]),
}
CHECKS = {
    "plain": {},
    "auto": {"tools": [TOOL], "tool_choice": "auto"},
    "required": {"tools": [TOOL], "tool_choice": "required"},
    "named": {"tools": [TOOL], "tool_choice": {"type": "function", "function": {"name": "get_weather"}}},
    "strict": {"tools": [{"type": "function", "function": {**FN, "strict": True}}]},
    "no_parallel": {"tools": [TOOL], "parallel_tool_calls": False},
    "effort_top": {"tools": [TOOL], "reasoning_effort": "low"},
    "effort_kwargs": {"tools": [TOOL], "chat_template_kwargs": {"reasoning_effort": "low"}},
    "thinking_obj": {"tools": [TOOL], "thinking": {"type": "enabled", "clear_thinking": False}},
}


def call(name, extra, prompt=ASK["en"], messages=None, max_tokens=4096, timeout=180):
    body = {"model": MODEL, "max_tokens": max_tokens,
            "messages": messages or [{"role": "user", "content": prompt}], **extra}
    req = urllib.request.Request(URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Authorization": "Bearer " + KEY,
                                          "Content-Type": "application/json"})
    if RL["gave_up"] >= GIVE_UP:
        RL["skipped"] += 1
        return {"name": name, "request": body, "status": 429, "waited": 0, "seconds": 0,
                "response": "skipped: still rate-limited", "headers": {}}
    if GAP:
        time.sleep(GAP)
    start, waited = time.monotonic(), 0
    for attempt in range(RETRIES + 1):
        hdrs = {}
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                status, data, hdrs = r.status, json.load(r), r.headers
        except urllib.error.HTTPError as e:
            status, data, hdrs = e.code, e.read().decode("utf-8", "replace")[:3000], e.headers
        except Exception as e:
            status, data = 0, f"{type(e).__name__}: {e}"
        if status != 429:
            break
        note_429(data, hdrs)
        if attempt == RETRIES:
            RL["gave_up"] += 1
            if RL["gave_up"] == GIVE_UP:
                print(f"  still 429 after retries on {GIVE_UP} calls; skipping the remaining calls")
            break
        wait = retry_after(hdrs, attempt)
        print(f"  429 on {name}, waiting {wait}s (retry {attempt + 1}/{RETRIES})")
        time.sleep(wait)
        waited += wait
        RL["retries"] += 1
    RL["waited"] += waited
    rec = {"name": name, "request": body, "status": status, "waited": waited,
           "seconds": round(time.monotonic() - start - waited, 2), "response": data,
           "headers": {k.lower(): v for k, v in hdrs.items() if k.lower() != "set-cookie"}}
    (OUT / f"{name}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def message(rec):
    try:
        return rec["response"]["choices"][0]["message"] or {}
    except (KeyError, IndexError, TypeError):
        return None


def kind(rec):
    if rec["status"] != 200:
        return f"http_{rec['status']}"
    msg = message(rec)
    if msg is None:
        return "bad_shape"
    if rec["response"]["choices"][0].get("finish_reason") == "length":
        return "length"
    calls = msg.get("tool_calls") or []
    if calls:
        fn = calls[0].get("function") or {}
        args = fn.get("arguments")
        try:
            args = json.loads(args) if isinstance(args, str) else args
        except json.JSONDecodeError:
            return "native_bad_json"
        if not calls[0].get("id"):
            return "native_no_id"
        ok = fn.get("name") == "get_weather" and isinstance(args, dict) and args.get("city")
        return "native_ok" if ok else "native_bad_args"
    text = msg.get("content") or ""
    return "text_tool_call" if "<tool_call>" in text or "get_weather" in text else "no_tool_call"


def info(rec):
    msg = message(rec)
    if msg is None:
        return str(rec["response"])[:300].replace("\n", " ")
    usage = rec["response"].get("usage") or {}
    think = msg.get("reasoning_content") or msg.get("reasoning") or ""
    think_tok = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    keys = sorted(set(msg) - {"role", "content", "tool_calls"})
    text = "" if msg.get("tool_calls") else f" text={(msg.get('content') or '')[:60]!r}"
    return (f"keys={keys} in_tok={usage.get('prompt_tokens')} cached={cached} "
            f"think_chars={len(think)} out_tok={usage.get('completion_tokens')} think_tok={think_tok}{text}")


def prompt_tokens(rec):
    usage = rec["response"].get("usage") if isinstance(rec["response"], dict) else None
    return (usage or {}).get("prompt_tokens")


def server_hints(rec):
    resp = rec["response"] if isinstance(rec["response"], dict) else {}
    choice = (resp.get("choices") or [{}])[0]
    hdrs = rec["headers"]
    hints = {"server": hdrs.get("server"), "via": hdrs.get("via"),
             "x_headers": sorted(k for k in hdrs if k.startswith("x-")),
             "body_keys": sorted(resp), "choice_keys": sorted(choice), "id": str(resp.get("id"))[:16]}
    models = get_json("/models", "models")
    hints["models"] = models if isinstance(models, str) else [
        {k: m[k] for k in ("id", "owned_by", "root", "max_model_len") if k in m}
        for m in models.get("data", [])][:5]
    info = get_json("/model/info", "model_info")
    hints["model_info"] = info if isinstance(info, str) else [
        {"name": d.get("model_name"), "max_input": (d.get("model_info") or {}).get("max_input_tokens"),
         "max_output": (d.get("model_info") or {}).get("max_output_tokens")}
        for d in info.get("data", []) if d.get("model_name") == MODEL][:3]
    return hints

def get_json(path, name):
    req = urllib.request.Request(URL.rsplit("/chat/completions", 1)[0] + path,
                                 headers={"Authorization": "Bearer " + KEY})
    try:
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            data = json.load(r)
        (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return data if isinstance(data, dict) else {"data": data}
    except Exception as e:
        return f"{type(e).__name__}: {e}"[:120]

def roundtrip(base):
    first = call("rt_1", base)
    if kind(first) != "native_ok":
        return f"skipped (first call: {kind(first)})"
    msg = message(first)
    result = {"role": "tool", "tool_call_id": msg["tool_calls"][0]["id"],
              "content": json.dumps({"temp_c": 17, "sky": "clear"})}
    out = []
    variants = {"keep_reasoning": (True, False), "drop_reasoning": (False, False),
                "user_after_tool": (True, True)}
    for label, (keep, extra_user) in variants.items():
        asst = {k: v for k, v in msg.items() if keep or k not in ("reasoning_content", "reasoning")}
        asst["role"] = "assistant"
        messages = [{"role": "user", "content": ASK["en"]}, asst, result]
        if extra_user:
            messages.append({"role": "user", "content": "Status: tool result received. Answer now."})
        rec = call(f"rt_2_{label}", base, messages=messages)
        used = "17" in str((message(rec) or {}).get("content"))
        out.append(f"{label}: http_{rec['status']} {'uses_result' if used else 'NO_RESULT'}")
    return "; ".join(out)


PUZZLE = ("How many integers from 1 to 1000 are divisible by 3 or by 5, but not by 15? "
          "Reply with only the final number.")
EFFORTS = {"default": {}, "top_low": {"reasoning_effort": "low"}, "top_high": {"reasoning_effort": "high"},
           "kw_low": {"chat_template_kwargs": {"reasoning_effort": "low"}},
           "kw_high": {"chat_template_kwargs": {"reasoning_effort": "high"}}}

SHORT = {"native_ok": "ok", "text_tool_call": "txt", "no_tool_call": "none", "length": "len",
         "native_bad_json": "badjson", "native_bad_args": "badargs", "native_no_id": "noid",
         "bad_shape": "shape"}

def short(k):
    return SHORT.get(k, k.replace("http_", ""))

def summary(rep):
    c, h = rep["checks"], rep["server"]
    models = h["models"] if isinstance(h["models"], list) else []
    names = [n for n, hit in (("litellm", any(k.startswith("x-litellm") for k in h["x_headers"])),
                              ("vllm", any(m.get("owned_by") == "vllm" for m in models)
                               or "stop_reason" in h["choice_keys"]),
                              ("sglang", "matched_stop" in h["choice_keys"])) if hit]
    infos = h["model_info"] if isinstance(h["model_info"], list) else []
    ctx = next((m["max_model_len"] for m in models if "max_model_len" in m), None) \
        or next((i["max_input"] for i in infos if i["max_input"]), "?")
    rt = rep["roundtrip"]
    for a, b in ((": http_200 uses_result", "=Y"), (": http_200 NO_RESULT", "=N"), ("; ", " "),
                 ("keep_reasoning", "keep"), ("drop_reasoning", "drop"), ("user_after_tool", "user")):
        rt = rt.replace(a, b)
    rate = " ".join(f"{lang}={v.get('native_ok', 0)}/{sum(v.values())}"
                    + "".join(f",{short(k)}:{n}" for k, n in v.items() if k != "native_ok")
                    for lang, v in rep["rate"].items())
    lat = rep.get("latency_s") or {}
    sample = rep.get("text_sample", "")
    fmt = "glm" if "<arg_key>" in sample else "json" if "{" in sample else "other" if sample else "-"
    burst = [b.split()[0] for b in rep["burst"]]
    return [
        "S1 " + " ".join(f"{n}={short(v['kind'])}" for n, v in c.items()),
        "T1 think auto={} top={} kw={}".format(*(c[n]["think_chars"] for n in ("auto", "effort_top", "effort_kwargs"))),
        f"SV {'+'.join(names) or '?'} ctx={ctx} models={'ok' if models else 'x'} info={'ok' if infos else 'x'}",
        "S2 " + rt,
        f"S3 {rate} txtfmt={fmt} p50={round(lat.get('p50', 0), 1)} p90={round(lat.get('p90', 0), 1)}",
        "S4 " + " ".join(f"{short(k)}:{burst.count(k)}" for k in sorted(set(burst))),
        "S5 " + " ".join(f"{k}={v}" for k, v in rep["chars_per_token"].items()),
        "T2 " + " ".join(f"{n}={v['think']}c/{v['seconds']}s/{v['answer']}" for n, v in rep["effort"].items()),
        "ER " + next((f"{n}: {v['error']}" for n, v in c.items() if "error" in v), "-"),
        rl_line(),
    ]


def rl_line():
    """429 count, retries, total wait, rate-limit headers, first 429 body."""
    if not RL["hits"]:
        return "RL -"
    hdr = " ".join(f"{k.replace('x-ratelimit-', '')}={v}" for k, v in RL["headers"].items())
    return (f"RL hits={RL['hits']} retries={RL['retries']} waited={round(RL['waited'])}s "
            f"skipped={RL['skipped']} {hdr} | {RL['body'][:100]}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=10, help="tool calls per language")
    parser.add_argument("--burst", type=int, default=4, help="simultaneous requests")
    parser.add_argument("--effort", default="low", help="low/high/max, or none")
    args = parser.parse_args()
    OUT.mkdir(parents=True)
    report = {"model": MODEL, "checks": {}}
    print("== 1. options (status, result, details)")
    for name, extra in CHECKS.items():
        rec = call(name, extra, prompt="Reply with OK." if name == "plain" else ASK["en"])
        if name == "plain":
            report["server"] = server_hints(rec)
        think = (message(rec) or {}).get("reasoning_content") or ""
        report["checks"][name] = {"status": rec["status"], "kind": kind(rec),
                                  "seconds": rec["seconds"], "think_chars": len(think)}
        if rec["status"] != 200:
            report["checks"][name]["error"] = redact(" ".join(str(rec["response"]).split()))[:70]
        print(f"{name:14} {kind(rec):16} {rec['seconds']:6}s  {info(rec)}")
    print("server", json.dumps(report["server"], ensure_ascii=False))
    ok = {n for n, c in report["checks"].items() if c["status"] == 200}
    base = {"tools": [TOOL], "tool_choice": "auto"}
    if args.effort != "none" and "effort_top" in ok:
        base["reasoning_effort"] = args.effort
    elif args.effort != "none" and "effort_kwargs" in ok:
        base["chat_template_kwargs"] = {"reasoning_effort": args.effort}
    report["base"] = base
    print("base for 2-4:", json.dumps({k: v for k, v in base.items() if k != "tools"}))
    print("== 2. tool round trip")
    report["roundtrip"] = roundtrip(base)
    print(report["roundtrip"])
    print(f"== 3. reliability: {args.n} x en + {args.n} x ko, one at a time")
    recs = [call(f"rate_{lang}_{i:02d}", base, prompt=ASK[lang])
            for i in range(args.n) for lang in ASK]
    report["rate"] = {}
    for lang in ASK:
        kinds = [kind(r) for r in recs if r["name"].startswith(f"rate_{lang}")]
        report["rate"][lang] = {k: kinds.count(k) for k in sorted(set(kinds))}
        print(lang, report["rate"][lang])
    leak = next((r for r in recs if kind(r) == "text_tool_call"), None)
    if leak:
        report["text_sample"] = (message(leak).get("content") or "")[:120]
        print("text sample", repr(report["text_sample"]))
    secs = sorted(r["seconds"] for r in recs if r["status"] == 200)
    if len(secs) >= 2:
        report["latency_s"] = {"p50": statistics.median(secs),
                               "p90": statistics.quantiles(secs, n=10, method="inclusive")[8], "max": secs[-1]}
        print("latency", report["latency_s"])
    print(f"== 4. burst: {args.burst} requests at once")
    with cf.ThreadPoolExecutor(args.burst) as pool:
        burst = list(pool.map(lambda i: call(f"burst_{i}", base), range(args.burst)))
    report["burst"] = [f"{kind(r)} {r['seconds']}s" for r in burst]
    print(report["burst"])
    print("== 5. token calibration (characters per token)")
    empty = prompt_tokens(call("calib_base", {}, prompt=".", max_tokens=16))
    report["chars_per_token"] = {}
    for name, text in CALIB.items():
        used = prompt_tokens(call(f"calib_{name}", {}, prompt=text, max_tokens=16))
        if isinstance(used, int) and isinstance(empty, int) and used > empty:
            report["chars_per_token"][name] = round((len(text) - 1) / (used - empty), 2)
    print(report["chars_per_token"])
    print("== 6. thinking effort on a harder question (answer should be 401)")
    report["effort"] = {}
    for name, extra in EFFORTS.items():
        rec = call(f"effort_{name}", extra, prompt=PUZZLE, max_tokens=16000, timeout=600)
        msg = message(rec) or {}
        if rec["status"] != 200 or not msg:
            report["effort"][name] = {"think": 0, "seconds": rec["seconds"], "answer": f"http_{rec['status']}"}
        else:
            report["effort"][name] = {"think": len(msg.get("reasoning_content") or ""), "seconds": rec["seconds"],
                                      "answer": "Y" if "401" in (msg.get("content") or "") else "N"}
        print(f"{name:10} {report['effort'][name]}  {info(rec)}")
    (OUT / "profile.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = summary(report)
    (OUT / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("saved:", OUT.resolve())
    print("== copy these lines")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
