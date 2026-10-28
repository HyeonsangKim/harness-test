"""Find out why the in-house model is slow and which options work.

usage: ds_check.py [--only connect,effort,speed,cache,tools,anthropic] [--cache-chars 40000]
Raw records go to runs/ds_check/<time>/ (no API key). Copy only the summary at the end.
"""
import argparse
import json
import pathlib
import sys
import time

import llm

STEPS = ["connect", "effort", "speed", "cache", "tools", "anthropic"]
OUT = pathlib.Path(__file__).parent / "runs" / "ds_check" / time.strftime("%Y%m%d-%H%M%S")
SUMMARY = []
STREAM = [True]

MATH = "What is 17 * 23 + 48? Reply with the number only."
EFFORTS = [
    ("기본", {}),
    ("effort=low", {"reasoning_effort": "low"}),
    ("effort=high", {"reasoning_effort": "high"}),
    ("effort=10", {"reasoning_effort": 10}),
    ("thinking off", {"thinking": {"type": "disabled"}}),
    ("tmpl thinking=false", {"chat_template_kwargs": {"thinking": False}}),
    ("tmpl enable_thinking=false", {"chat_template_kwargs": {"enable_thinking": False}}),
]


def save(name, rec):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")


def ask(name, messages, extra=None, **fields):
    rec = llm.chat(messages, extra, stream=STREAM[0], **fields)
    save(name, rec)
    return rec


def tokens(rec):
    p, c, o, r = llm.usage_numbers(rec["usage"])
    return f"입력 {p}(캐시 {c}) 출력 {o}(사고 {r}) 사고글자 {len(rec['reasoning'])}"


def line(text):
    print(text)
    SUMMARY.append(text)


def connect():
    msgs = [{"role": "user", "content": "Reply with OK."}]
    rec = ask("connect", msgs, max_tokens=4096)
    if rec["status"] != 200:
        print(f"  스트리밍 실패({rec['status']}), 스트리밍 없이 다시 시도: {str(rec.get('error'))[:300]}")
        STREAM[0] = False
        rec = ask("connect_nostream", msgs, max_tokens=4096)
    if rec["status"] != 200:
        line(f"연결: 실패 {rec['status']} {str(rec.get('error'))[:300]}")
        sys.exit(1)
    line(f"연결: 200 스트리밍={'Y' if STREAM[0] else 'N'} {rec['seconds']}초 첫토큰 {rec['ttft']}초 "
         f"답={rec['text'].strip()[:20]!r} {tokens(rec)}")


def effort():
    print("추론 강도 옵션별 시간 (같은 계산 문제, 정답 439)")
    for label, extra in EFFORTS:
        rec = ask("effort_" + label.replace(" ", "_").replace("=", "-"),
                  [{"role": "user", "content": MATH}], extra, max_tokens=16384)
        if rec["status"] != 200:
            line(f"  {label:<28} {rec['status']} {str(rec.get('error'))[:120]}")
            continue
        ok = "439" in rec["text"]
        line(f"  {label:<28} 200 {rec['seconds']:>6}초 정답 {'Y' if ok else 'N'} {tokens(rec)}")


def speed():
    rec = ask("speed", [{"role": "user", "content":
                         "Write about 300 words on how a warehouse counts inventory. Plain text."}],
              max_tokens=16384)
    if rec["status"] != 200:
        line(f"생성 속도: 실패 {rec['status']}")
        return
    _, _, out, _ = llm.usage_numbers(rec["usage"])
    gen = rec["seconds"] - (rec["ttft"] or 0)
    rate = f"{out / gen:.1f} 토큰/초" if out and gen > 0 and STREAM[0] else "측정 불가(스트리밍 아님)"
    line(f"생성 속도: {rate}, 첫토큰 {rec['ttft']}초 전체 {rec['seconds']}초 {tokens(rec)}")


def filler(chars):
    rows, i = [], 0
    while sum(len(r) for r in rows) < chars:
        i += 1
        rows.append(f"기록 {i:05d}: 창고 {i % 7 + 1}번, 품목 P-{(i * 37) % 1000:03d}, 수량 {(i * 13) % 97}개, "
                    f"담당 {['김', '이', '박', '최'][i % 4]}, 비고 정상 입고 확인.\n")
    return "".join(rows)


def cache(chars):
    doc = filler(chars)
    recs = []
    for n, q in enumerate(["기록 00010의 수량은? 숫자만.", "기록 00020의 담당은? 한 글자만."]):
        rec = ask(f"cache_{n + 1}", [{"role": "system", "content": "아래 기록을 참고해 답한다.\n" + doc},
                                    {"role": "user", "content": q}], max_tokens=8192)
        if rec["status"] != 200:
            line(f"캐시: 실패 {rec['status']}")
            return
        recs.append(rec)
    a, second = recs
    p, _, _, _ = llm.usage_numbers(a["usage"])
    _, c2, _, _ = llm.usage_numbers(second["usage"])
    t1, t2 = a["ttft"] or a["seconds"], second["ttft"] or second["seconds"]
    works = c2 > p * 0.5 or (t1 > 2 and t2 < t1 * 0.5)
    rate = f" 입력 처리 약 {p / t1:.0f} 토큰/초(1회 기준)." if p and t1 else ""
    line(f"캐시: {'동작' if works else '안 됨'} — 입력 {p}토큰, 첫토큰 1회 {t1}초 → 2회 {t2}초, "
         f"2회 캐시토큰 {c2}.{rate}")


TOOL = [{"type": "function", "function": {
    "name": "read_file", "description": "Read a text file and return its content.",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}]


def tools():
    msgs = [{"role": "user", "content": "notes.txt 파일을 읽고 회의 날짜만 알려줘."}]
    rec = ask("tools_1", msgs, tools=TOOL, max_tokens=8192)
    calls = rec["tool_calls"]
    if rec["status"] != 200 or not calls:
        line(f"도구 호출: 실패 status={rec['status']} 본문={rec['text'][:120]!r}")
        return
    call = calls[0]
    msgs += [{"role": "assistant", "content": rec["text"] or None, "tool_calls": [
        {"id": call["id"] or "call_0", "type": "function", "function": call["function"]}]},
        {"role": "tool", "tool_call_id": call["id"] or "call_0",
         "content": "주간 회의: 2026-11-04(수) 14시, 3층 대회의실"}]
    rec2 = ask("tools_2", msgs, tools=TOOL, max_tokens=8192)
    ok = rec2["status"] == 200 and "11" in rec2["text"] and "04" in rec2["text"].replace("4일", "04")
    line(f"도구 호출: 호출 Y({call['function']['name']} {call['function']['arguments'][:60]}) "
         f"왕복 {'Y' if ok else 'N'} 답={rec2['text'].strip()[:40]!r} {rec['seconds']}+{rec2['seconds']}초")


def anthropic():
    url = llm.root() + "/v1/messages"
    body = {"model": llm.MODEL, "max_tokens": 1024, "messages": [{"role": "user", "content": "Reply with OK."}]}
    status, resp = llm.open_url(url, body, 300, {"x-api-key": llm.key(), "anthropic-version": "2023-06-01"})
    if status == 200:
        with resp:
            text = resp.read().decode("utf-8", "replace")[:200]
    else:
        text = str(resp)[:200]
    line(f"Anthropic 형식({url}): {status} {'→ Claude Code 직접 연결 가능' if status == 200 else '→ ds_proxy.py 사용'}"
         f" {text!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(STEPS))
    ap.add_argument("--cache-chars", type=int, default=40000, help="캐시 시험 문서 길이(글자)")
    args = ap.parse_args()
    steps = args.only.split(",")
    llm.key()
    print(f"모델 {llm.MODEL} @ {llm.URL}  LLM_EXTRA={json.dumps(llm.EXTRA, ensure_ascii=False)}")
    connect()
    for step in steps:
        if step == "connect":
            continue
        print(f"\n== {step} ==")
        if step == "cache":
            cache(args.cache_chars)
        else:
            globals()[step]()
    print("\n===== 옮길 것 (여기부터) =====")
    print(f"모델 {llm.MODEL}  LLM_EXTRA={json.dumps(llm.EXTRA, ensure_ascii=False)}")
    for text in SUMMARY:
        print(text)
    print("===== (여기까지) =====")
    print(f"원본 기록: {OUT}")


if __name__ == "__main__":
    main()
