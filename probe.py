"""GLM gateway probe -> model profile. Python 3.12, standard library only.
env: LLM_URL (full .../chat/completions), LLM_MODEL, optional LLM_API_KEY, LLM_CA_FILE
run: python probe.py --n 10
"""
import argparse
import concurrent.futures as cf
import getpass
import json
import os
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


def call(name, extra, prompt=ASK["en"], messages=None, max_tokens=4096):
    body = {"model": MODEL, "max_tokens": max_tokens,
            "messages": messages or [{"role": "user", "content": prompt}], **extra}
    req = urllib.request.Request(URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Authorization": "Bearer " + KEY,
                                          "Content-Type": "application/json"})
    start, hdrs = time.monotonic(), {}
    try:
        with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
            status, data, hdrs = r.status, json.load(r), r.headers
    except urllib.error.HTTPError as e:
        status, data, hdrs = e.code, e.read().decode("utf-8", "replace")[:3000], e.headers
    except Exception as e:
        status, data = 0, f"{type(e).__name__}: {e}"
    rec = {"name": name, "request": body, "status": status,
           "seconds": round(time.monotonic() - start, 2), "response": data,
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
    req = urllib.request.Request(URL.rsplit("/chat/completions", 1)[0] + "/models",
                                 headers={"Authorization": "Bearer " + KEY})
    try:
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            models = json.load(r)
        (OUT / "models.json").write_text(json.dumps(models, ensure_ascii=False, indent=1), encoding="utf-8")
        hints["models"] = [{k: m[k] for k in ("id", "owned_by", "root", "max_model_len") if k in m}
                           for m in models.get("data", [])][:5]
    except Exception as e:
        hints["models"] = f"{type(e).__name__}: {e}"[:120]
    return hints

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
        report["checks"][name] = {"status": rec["status"], "kind": kind(rec), "seconds": rec["seconds"]}
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
    (OUT / "profile.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved:", OUT.resolve())


if __name__ == "__main__":
    main()
