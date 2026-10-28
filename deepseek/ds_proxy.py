"""Anthropic Messages -> OpenAI chat/completions proxy so Claude Code can use the in-house gateway.
Standard library only. Listens on 127.0.0.1 only.

usage: ds_proxy.py [--port 8787]
Then point Claude Code at http://127.0.0.1:8787 (DEEPSEEK_SETUP_KO.md 5절).

- The gateway key is read here (LLM_API_KEY or prompt). Claude Code gets a dummy token.
- Every model id Claude Code sends (main, haiku, subagent) is replaced with LLM_MODEL.
- LLM_EXTRA is merged into every request, so reasoning effort is set here, not in Claude Code.
- Reasoning text is not passed to Claude Code; its length is logged.
- One log line per request: timing, tokens, cache hits. Lines also go to runs/ds_proxy/<time>.log.
"""
import argparse
import json
import os
import pathlib
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import llm

MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "0"))   # 0 = pass Claude Code's value through
LOCK = threading.Lock()
COUNT = [0]
DUMP = [False]
LOG = pathlib.Path(__file__).parent / "runs" / "ds_proxy" / (time.strftime("%Y%m%d-%H%M%S") + ".log")
STOP = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use", "function_call": "tool_use",
        "content_filter": "end_turn"}
ERROR_TYPE = {400: "invalid_request_error", 401: "authentication_error", 403: "permission_error",
              404: "not_found_error", 413: "request_too_large", 429: "rate_limit_error",
              503: "overloaded_error", 529: "overloaded_error"}


def log(text):
    with LOCK:
        print(text, flush=True)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(text + "\n")


# ---------- request: Anthropic -> OpenAI ----------

def text_of(content):
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif block.get("type") == "image":
            parts.append("[image]")
    return "\n".join(parts)


def image_part(block):
    src = block.get("source") or {}
    if src.get("type") == "base64":
        url = f"data:{src.get('media_type', 'image/png')};base64,{src.get('data', '')}"
    else:
        url = src.get("url", "")
    return {"type": "image_url", "image_url": {"url": url}}


def system_text(system):
    text = text_of(system) if system else ""
    keep = [ln for ln in text.split("\n") if not ln.startswith("x-anthropic-billing-header")]
    return "\n".join(keep).strip()


def convert_messages(body):
    out = []
    system = system_text(body.get("system"))
    if system:
        out.append({"role": "system", "content": system})
    for m in body.get("messages", []):
        content = m.get("content")
        if m["role"] == "system":
            # Claude Code puts context notes mid-conversation as system entries; open-model chat
            # templates expect system only first, so they ride along as user text.
            text = text_of(content)
            if text.strip():
                out.append({"role": "user", "content": text})
            continue
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
            continue
        if m["role"] == "assistant":
            texts, calls = [], []
            for b in content:
                if b.get("type") == "text":
                    texts.append(b.get("text", ""))
                elif b.get("type") == "tool_use":
                    calls.append({"id": b["id"], "type": "function", "function": {
                        "name": b["name"], "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False)}})
            msg = {"role": "assistant", "content": "\n".join(texts) if texts or not calls else None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
            continue
        parts, images_from_tools = [], []
        for b in content:
            kind = b.get("type")
            if kind == "tool_result":
                inner = b.get("content")
                result = text_of(inner)
                if isinstance(inner, list):
                    images_from_tools += [image_part(x) for x in inner if x.get("type") == "image"]
                if b.get("is_error"):
                    result = "ERROR: " + result
                out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": result})
            elif kind == "text":
                parts.append({"type": "text", "text": b.get("text", "")})
            elif kind == "image":
                parts.append(image_part(b))
        parts += images_from_tools
        if parts:
            if all(p["type"] == "text" for p in parts):
                out.append({"role": "user", "content": "\n".join(p["text"] for p in parts)})
            else:
                out.append({"role": "user", "content": parts})
    return merge_users(out)


def merge_users(msgs):
    """Join back-to-back user messages; some chat templates reject two in a row."""
    out = []
    for m in msgs:
        prev = out[-1] if out else None
        if prev and prev["role"] == "user" and m["role"] == "user":
            a, b = prev["content"], m["content"]
            if isinstance(a, str) and isinstance(b, str):
                prev["content"] = a + "\n\n" + b
            else:
                as_parts = lambda c: [{"type": "text", "text": c}] if isinstance(c, str) else c
                prev["content"] = as_parts(a) + as_parts(b)
            continue
        out.append(dict(m))
    return out


def convert_tools(tools):
    out = []
    for t in tools or []:
        if "input_schema" not in t:          # server tools such as web_search have no schema
            continue
        out.append({"type": "function", "function": {
            "name": t["name"], "description": t.get("description", ""), "parameters": t["input_schema"]}})
    return out


def convert_tool_choice(choice):
    kind = (choice or {}).get("type")
    if kind == "any":
        return "required"
    if kind == "tool":
        return {"type": "function", "function": {"name": choice["name"]}}
    if kind == "none":
        return "none"
    return None


def to_openai(body):
    req = {"model": llm.MODEL, "messages": convert_messages(body)}
    max_tokens = body.get("max_tokens")
    if max_tokens:
        req["max_tokens"] = min(max_tokens, MAX_TOKENS) if MAX_TOKENS else max_tokens
    for src, dst in (("temperature", "temperature"), ("top_p", "top_p"), ("stop_sequences", "stop")):
        if body.get(src) is not None:
            req[dst] = body[src]
    tools = convert_tools(body.get("tools"))
    if tools:
        req["tools"] = tools
        choice = convert_tool_choice(body.get("tool_choice"))
        if choice:
            req["tool_choice"] = choice
    req.update(llm.EXTRA)
    return req


# ---------- response: OpenAI -> Anthropic ----------

def usage_block(usage):
    prompt, cached, out, _ = llm.usage_numbers(usage)
    return {"input_tokens": max(prompt - cached, 0), "output_tokens": out,
            "cache_read_input_tokens": cached, "cache_creation_input_tokens": 0}


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def to_anthropic(data, model):
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = []
    if msg.get("content"):
        content.append({"type": "text", "text": msg["content"]})
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {"_raw": fn.get("arguments")}
        content.append({"type": "tool_use", "id": tc.get("id") or new_id("toolu"), "name": fn.get("name"),
                        "input": args})
    stop = "tool_use" if msg.get("tool_calls") else STOP.get(choice.get("finish_reason"), "end_turn")
    return {"id": new_id("msg"), "type": "message", "role": "assistant", "model": model, "content": content,
            "stop_reason": stop, "stop_sequence": None, "usage": usage_block(data.get("usage"))}, \
        len(llm.reasoning_of(msg))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def send_json(self, status, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, status, message):
        self.send_json(status, {"type": "error", "error": {
            "type": ERROR_TYPE.get(status, "api_error"), "message": message[:2000]}})

    def do_GET(self):
        if self.path.split("?")[0] in ("/v1/models", "/models"):
            self.send_json(200, {"data": [{"type": "model", "id": llm.MODEL, "display_name": llm.MODEL}],
                                 "has_more": False, "first_id": llm.MODEL, "last_id": llm.MODEL})
        else:
            self.send_json(200, {"status": "ok"})

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        path = self.path.split("?")[0]
        size = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(size) or b"{}")
        except json.JSONDecodeError:
            return self.send_error_json(400, "body is not JSON")
        if path.endswith("/messages/count_tokens"):
            chars = len(json.dumps(body, ensure_ascii=False))
            return self.send_json(200, {"input_tokens": chars // 3})
        if not path.endswith("/messages"):
            return self.send_error_json(404, f"unknown path {path}")
        with LOCK:
            COUNT[0] += 1
            n = COUNT[0]
        req = to_openai(body)
        if DUMP[0]:
            (LOG.parent / "last_request.json").write_text(json.dumps(
                {"anthropic": body, "openai": req}, ensure_ascii=False, indent=1), encoding="utf-8")
        head = (f"#{n} {time.strftime('%H:%M:%S')} {body.get('model', '?')}→{llm.MODEL} "
                f"msgs {len(req['messages'])} tools {len(req.get('tools', []))}")
        if body.get("stream"):
            self.stream(req, body.get("model") or llm.MODEL, head)
        else:
            self.once(req, body.get("model") or llm.MODEL, head)

    def once(self, req, model, head):
        start = time.monotonic()
        status, resp = llm.open_url(llm.URL, req)
        if status != 200:
            log(f"{head} | 실패 {status} {str(resp)[:300]}")
            return self.send_error_json(status or 502, str(resp))
        with resp:
            data = json.load(resp)
        msg, think = to_anthropic(data, model)
        p, c, o, r = llm.usage_numbers(data.get("usage"))
        log(f"{head} | {time.monotonic() - start:.1f}s | 입력 {p}(캐시 {c}) 출력 {o}(사고 {r}, "
            f"사고글자 {think}) | {msg['stop_reason']}")
        self.send_json(200, msg)

    def event(self, name, obj):
        self.wfile.write(f"event: {name}\ndata: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.flush()

    def stream(self, req, model, head):
        req = dict(req, stream=True, stream_options={"include_usage": True})
        start = time.monotonic()
        status, resp = llm.open_url(llm.URL, req)
        if status == 400 and "stream_options" in str(resp):
            req.pop("stream_options")
            status, resp = llm.open_url(llm.URL, req)
        if status != 200:
            log(f"{head} | 실패 {status} {str(resp)[:300]}")
            return self.send_error_json(status or 502, str(resp))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.event("message_start", {"type": "message_start", "message": {
            "id": new_id("msg"), "type": "message", "role": "assistant", "model": model, "content": [],
            "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0}}})
        index, open_kind, tools, usage = -1, None, {}, {}
        finish, think, ttft, last_ping = None, 0, None, time.monotonic()

        def close_block():
            nonlocal open_kind
            if open_kind:
                self.event("content_block_stop", {"type": "content_block_stop", "index": index})
                open_kind = None

        try:
            with resp:
                for chunk in llm.iter_sse(resp):
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        reasoning = llm.reasoning_of(delta)
                        if (reasoning or delta.get("content") or delta.get("tool_calls")) and ttft is None:
                            ttft = time.monotonic() - start
                        if reasoning:
                            think += len(reasoning)
                            if time.monotonic() - last_ping > 5:
                                self.event("ping", {"type": "ping"})
                                last_ping = time.monotonic()
                        if delta.get("content"):
                            if open_kind != "text":
                                close_block()
                                index += 1
                                open_kind = "text"
                                self.event("content_block_start", {"type": "content_block_start", "index": index,
                                                                   "content_block": {"type": "text", "text": ""}})
                            self.event("content_block_delta", {"type": "content_block_delta", "index": index,
                                                               "delta": {"type": "text_delta",
                                                                         "text": delta["content"]}})
                        for tc in delta.get("tool_calls") or []:
                            key = tc.get("index", 0)
                            fn = tc.get("function") or {}
                            if key not in tools:
                                close_block()
                                index += 1
                                open_kind = "tool"
                                tools[key] = index
                                self.event("content_block_start", {
                                    "type": "content_block_start", "index": index, "content_block": {
                                        "type": "tool_use", "id": tc.get("id") or new_id("toolu"),
                                        "name": fn.get("name") or "", "input": {}}})
                            if fn.get("arguments"):
                                self.event("content_block_delta", {
                                    "type": "content_block_delta", "index": tools[key],
                                    "delta": {"type": "input_json_delta", "partial_json": fn["arguments"]}})
                        if choice.get("finish_reason"):
                            finish = choice["finish_reason"]
            close_block()
            stop = "tool_use" if tools else STOP.get(finish, "end_turn")
            self.event("message_delta", {"type": "message_delta",
                                         "delta": {"stop_reason": stop, "stop_sequence": None},
                                         "usage": usage_block(usage)})
            self.event("message_stop", {"type": "message_stop"})
        except (BrokenPipeError, ConnectionResetError):
            log(f"{head} | Claude Code가 연결을 끊음(취소)")
            return
        p, c, o, r = llm.usage_numbers(usage)
        first = f"{ttft:.1f}s" if ttft is not None else "-"
        log(f"{head} | 첫토큰 {first} 전체 {time.monotonic() - start:.1f}s | 입력 {p}(캐시 {c}) "
            f"출력 {o}(사고 {r}, 사고글자 {think}) | {stop}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--dump", action="store_true", help="마지막 요청을 runs/ds_proxy/last_request.json에 저장")
    args = ap.parse_args()
    DUMP[0] = args.dump
    llm.key()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"프록시 http://127.0.0.1:{args.port} → {llm.URL} ({llm.MODEL})")
    print(f"LLM_EXTRA={json.dumps(llm.EXTRA, ensure_ascii=False)}  기록 {LOG}")
    print("Ctrl+C로 끕니다.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
