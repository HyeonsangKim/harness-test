"""Minimal coding agent: two tools (shell, edit), the shape that scored best for DeepSeek-V4.1-Flash
(mini-SWE, DSH Minimal). Standard library only.

usage: ds_agent.py "작업 설명" [--dir 작업폴더] [--yes] [--steps 40]
       ds_agent.py --task-file task.txt --dir 작업폴더

Every shell command and edit is shown and asked before it runs unless --yes is given.
The trace goes to runs/ds_agent/<time>.json (no API key).
"""
import argparse
import json
import os
import pathlib
import platform
import subprocess
import time

import llm

WINDOWS = platform.system() == "Windows"
SHELL_NAME = "PowerShell" if WINDOWS else "bash"
OUT_LIMIT = int(os.getenv("AGENT_OUTPUT_CHARS", "10000"))
SHELL_TIMEOUT = int(os.getenv("AGENT_SHELL_TIMEOUT", "120"))

SYSTEM = f"""You are a careful software agent working in the folder {{root}} on {platform.system()} ({SHELL_NAME}).
Tools:
- shell: run one {SHELL_NAME} command in that folder. Use it to look around, read files, run tests.
- edit: replace an exact, unique piece of text in a file, or create a new file when old is empty.
Work in small steps: inspect, change, then run something that checks the change.
Read only the part of a large file you need. Never print secrets or environment variables.
When the task is done, reply without a tool call: what you changed and how you checked it,
in the user's language."""

TOOLS = [
    {"type": "function", "function": {
        "name": "shell", "description": f"Run one {SHELL_NAME} command in the work folder. Returns exit code and output.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "edit",
        "description": "Replace the exact text `old` with `new` in a file. `old` must appear exactly once. "
                       "With empty `old`, create a new file whose content is `new`.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "path relative to the work folder"},
            "old": {"type": "string"}, "new": {"type": "string"}}, "required": ["path", "old", "new"]}}},
]


def clip(text):
    if len(text) <= OUT_LIMIT:
        return text
    head, tail = OUT_LIMIT * 2 // 5, OUT_LIMIT * 3 // 5
    return f"{text[:head]}\n...[{len(text) - head - tail}자 생략]...\n{text[-tail:]}"


def clean_env():
    return {k: v for k, v in os.environ.items()
            if not (k.startswith("LLM_") or k.startswith("ANTHROPIC_") or "KEY" in k or "TOKEN" in k)}


def run_shell(command, root):
    if WINDOWS:
        argv = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + command]
    else:
        argv = ["bash", "-c", command]
    try:
        p = subprocess.run(argv, cwd=root, env=clean_env(), capture_output=True, timeout=SHELL_TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"timeout after {SHELL_TIMEOUT}s"
    out = (p.stdout + p.stderr).decode("utf-8", "replace")
    return f"exit {p.returncode}\n{clip(out)}"


def run_edit(path, old, new, root):
    target = (root / path).resolve()
    if root not in target.parents:
        return "error: path is outside the work folder"
    if not old:
        if target.exists() and target.read_text(encoding="utf-8", errors="replace").strip():
            return "error: file already exists; give the exact old text to replace"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new, encoding="utf-8")
        return f"created {path} ({len(new)} chars)"
    if not target.exists():
        return "error: file not found"
    text = target.read_text(encoding="utf-8", errors="replace")
    count = text.count(old)
    if count != 1:
        return f"error: old text found {count} times; it must be exactly once. Read the file and copy it exactly."
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    return f"edited {path}"


class Gate:
    def __init__(self, yes):
        self.all = yes

    def ok(self, what):
        if self.all:
            return True
        answer = input(f"  실행할까요? [y=예 / n=아니오 / a=이후 모두] ").strip().lower()
        if answer == "a":
            self.all = True
        return answer in ("y", "a")


def act(call, root, gate):
    fn = call["function"]
    try:
        args = json.loads(fn["arguments"] or "{}")
    except json.JSONDecodeError:
        return "error: arguments were not valid JSON"
    if fn["name"] == "shell":
        command = args.get("command", "")
        print(f"  $ {command}")
        return run_shell(command, root) if gate.ok("shell") else "the user declined this command"
    if fn["name"] == "edit":
        path, old, new = args.get("path", ""), args.get("old", ""), args.get("new", "")
        print(f"  edit {path}: {old[:80]!r} → {new[:80]!r}")
        return run_edit(path, old, new, root) if gate.ok("edit") else "the user declined this edit"
    return f"error: unknown tool {fn['name']}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?")
    ap.add_argument("--task-file")
    ap.add_argument("--dir", default=".")
    ap.add_argument("--yes", action="store_true", help="묻지 않고 모두 실행")
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--max-tokens", type=int, default=32768)
    args = ap.parse_args()
    task = pathlib.Path(args.task_file).read_text(encoding="utf-8") if args.task_file else args.task
    if not task:
        ap.error("작업 설명이나 --task-file을 주세요")
    root = pathlib.Path(args.dir).resolve()
    llm.key()
    messages = [{"role": "system", "content": SYSTEM.format(root=root)}, {"role": "user", "content": task}]
    gate, keep_reasoning, trace = Gate(args.yes), True, []
    start, model_time = time.monotonic(), 0.0
    totals = [0, 0, 0, 0]
    print(f"모델 {llm.MODEL}  폴더 {root}  LLM_EXTRA={json.dumps(llm.EXTRA, ensure_ascii=False)}")
    for step in range(1, args.steps + 1):
        rec = llm.chat(messages, tools=TOOLS, max_tokens=args.max_tokens)
        if rec["status"] == 400 and keep_reasoning and any("reasoning_content" in m for m in messages):
            keep_reasoning = False
            for m in messages:
                m.pop("reasoning_content", None)
            rec = llm.chat(messages, tools=TOOLS, max_tokens=args.max_tokens)
        trace.append({k: v for k, v in rec.items() if k != "request"})
        if rec["status"] != 200:
            print(f"[{step}] 모델 호출 실패 {rec['status']}: {str(rec.get('error'))[:500]}")
            break
        model_time += rec["seconds"]
        nums = llm.usage_numbers(rec["usage"])
        totals = [a + b for a, b in zip(totals, nums)]
        print(f"[{step}] {rec['seconds']}초 (첫토큰 {rec['ttft']}초) 입력 {nums[0]}(캐시 {nums[1]}) "
              f"출력 {nums[2]}(사고 {nums[3]}, 사고글자 {len(rec['reasoning'])})")
        msg = {"role": "assistant", "content": rec["text"] or None}
        if keep_reasoning and rec["reasoning"]:
            msg["reasoning_content"] = rec["reasoning"]
        calls = [dict(c, id=c["id"] or f"call_{step}_{i}") for i, c in enumerate(rec["tool_calls"])]
        if calls:
            msg["tool_calls"] = calls
        messages.append(msg)
        if rec["text"].strip():
            print("  " + rec["text"].strip().replace("\n", "\n  "))
        if not calls:
            break
        for call in calls:
            result = act(call, root, gate)
            print("  → " + result[:300].replace("\n", "\n    "))
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
    else:
        print(f"단계 상한({args.steps})에 닿아 멈췄습니다.")
    wall = time.monotonic() - start
    out = pathlib.Path(__file__).parent / "runs" / "ds_agent"
    out.mkdir(parents=True, exist_ok=True)
    path = out / (time.strftime("%Y%m%d-%H%M%S") + ".json")
    path.write_text(json.dumps({"task": task, "dir": str(root), "extra": llm.EXTRA, "steps": trace,
                                "messages": messages}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n요약: 호출 {len(trace)}회, 전체 {wall:.0f}초 중 모델 {model_time:.0f}초, "
          f"입력 {totals[0]}(캐시 {totals[1]}) 출력 {totals[2]}(사고 {totals[3]})")
    print(f"기록: {path}")


if __name__ == "__main__":
    main()
