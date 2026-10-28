"""OpenAI-compatible client shared by ds_check, ds_agent and ds_proxy (standard library only).

env:
  LLM_URL      full .../chat/completions address
  LLM_MODEL    model id
  LLM_API_KEY  optional; asked at start when missing
  LLM_CA_FILE  optional company CA bundle (TLS verification stays on)
  LLM_EXTRA    optional JSON merged into every request, e.g. {"reasoning_effort":"low"}
  LLM_RETRIES  retries on 429/502/503/504 (default 4)
"""
import getpass
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

RETRY_STATUS = {429, 502, 503, 504}


def _need(name):
    value = os.getenv(name)
    if not value:
        sys.exit(f"환경변수 {name}가 없습니다. DEEPSEEK_SETUP_KO.md 1절을 보세요.")
    return value


URL = _need("LLM_URL")
MODEL = _need("LLM_MODEL")
CTX = ssl.create_default_context(cafile=os.getenv("LLM_CA_FILE"))
RETRIES = int(os.getenv("LLM_RETRIES", "4"))
try:
    EXTRA = json.loads(os.getenv("LLM_EXTRA") or "{}")
except json.JSONDecodeError as e:
    sys.exit(f"LLM_EXTRA가 JSON이 아닙니다: {e}")
_KEY = []


def key():
    if not _KEY:
        _KEY.append(os.getenv("LLM_API_KEY") or getpass.getpass("API key: "))
    return _KEY[0]


def root():
    """Gateway root without /v1/chat/completions."""
    for tail in ("/v1/chat/completions", "/chat/completions"):
        if URL.endswith(tail):
            return URL[: -len(tail)]
    return URL.rsplit("/", 1)[0]


def _request(url, body, headers=None):
    hdrs = {"Authorization": "Bearer " + key(), "Content-Type": "application/json"}
    hdrs.update(headers or {})
    return urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                  headers=hdrs)


def open_url(url, body, timeout=900, headers=None):
    """POST with retries. Returns (status, response or error text). A 200 response is left open."""
    for attempt in range(RETRIES + 1):
        try:
            return 200, urllib.request.urlopen(_request(url, body, headers), timeout=timeout, context=CTX)
        except urllib.error.HTTPError as e:
            status, text = e.code, e.read().decode("utf-8", "replace")[:3000]
            wait = e.headers.get("retry-after")
        except Exception as e:
            status, text, wait = 0, f"{type(e).__name__}: {e}", None
        if status not in RETRY_STATUS or attempt == RETRIES:
            return status, text
        try:
            wait = min(float(wait), 60)
        except (TypeError, ValueError):
            wait = min(2 ** attempt * 3, 60)
        print(f"  [{status}] {wait:.0f}초 후 다시 시도 ({attempt + 1}/{RETRIES})", file=sys.stderr)
        time.sleep(wait)


def body_for(messages, extra=None, **fields):
    return {"model": MODEL, "messages": messages, **fields, **EXTRA, **(extra or {})}


def iter_sse(resp):
    """Yield parsed JSON chunks from an OpenAI-style SSE stream."""
    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


def reasoning_of(obj):
    return obj.get("reasoning_content") or obj.get("reasoning") or ""


def usage_numbers(usage):
    """(prompt, cached, completion, reasoning) from any of the usual usage shapes."""
    usage = usage or {}
    details = usage.get("prompt_tokens_details") or {}
    cached = (details.get("cached_tokens") or usage.get("prompt_cache_hit_tokens")
              or usage.get("cache_read_input_tokens") or 0)
    out_details = usage.get("completion_tokens_details") or {}
    return (usage.get("prompt_tokens") or 0, cached, usage.get("completion_tokens") or 0,
            out_details.get("reasoning_tokens") or 0)


def chat(messages, extra=None, stream=True, timeout=900, **fields):
    """One call. Returns a record with status, timing, text, reasoning, tool_calls and usage."""
    body = body_for(messages, extra, **fields)
    if stream:
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
    start = time.monotonic()
    status, resp = open_url(URL, body, timeout)
    rec = {"status": status, "request": body, "ttft": None, "text": "", "reasoning": "",
           "tool_calls": [], "usage": {}, "finish": None}
    if status != 200:
        rec.update(seconds=round(time.monotonic() - start, 2), error=resp)
        return rec
    with resp:
        if not stream:
            data = json.load(resp)
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            rec.update(text=msg.get("content") or "", reasoning=reasoning_of(msg),
                       tool_calls=msg.get("tool_calls") or [], usage=data.get("usage") or {},
                       finish=choice.get("finish_reason"))
        else:
            calls = {}
            for chunk in iter_sse(resp):
                if chunk.get("usage"):
                    rec["usage"] = chunk["usage"]
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    piece = (delta.get("content") or "") + reasoning_of(delta)
                    if (piece or delta.get("tool_calls")) and rec["ttft"] is None:
                        rec["ttft"] = round(time.monotonic() - start, 2)
                    rec["text"] += delta.get("content") or ""
                    rec["reasoning"] += reasoning_of(delta)
                    for tc in delta.get("tool_calls") or []:
                        slot = calls.setdefault(tc.get("index", 0),
                                                {"id": "", "type": "function",
                                                 "function": {"name": "", "arguments": ""}})
                        slot["id"] = tc.get("id") or slot["id"]
                        fn = tc.get("function") or {}
                        slot["function"]["name"] += fn.get("name") or ""
                        slot["function"]["arguments"] += fn.get("arguments") or ""
                    if choice.get("finish_reason"):
                        rec["finish"] = choice["finish_reason"]
            rec["tool_calls"] = [calls[i] for i in sorted(calls)]
    rec["seconds"] = round(time.monotonic() - start, 2)
    return rec
