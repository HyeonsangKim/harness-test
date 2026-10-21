"""Ask one question with the tool-free harness. Standard library only.

    python ask.py question.txt                     # free-text answer
    python ask.py question.txt --json answer:float # answer as one JSON line with these keys
    type question.txt | python ask.py -            # question from stdin

Free-form writing (no JSON answer, table, numbers or code asked for) is answered directly, without the harness.
The question file holds the whole request, with any tables or documents pasted in. The model gets one
action, run_python: tables in the question are saved as table_N.csv, the whole question as input.txt, and
the model computes the answer in code. With --json, the last printed line of a program that already has
the requested keys becomes the answer.

env: LLM_URL, LLM_MODEL, optional LLM_API_KEY (asked for if missing), LLM_CA_FILE, LLM_EXTRA, LLM_MAX_TOKENS.
The model's code runs on this PC in a fresh folder under --workdir, without environment variables (so no keys)
and with a time limit. This prevents accidents; it is not a security sandbox. Do not run it in a folder with
important files.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import env
import hx

TYPES = ("str", "int", "float", "bool", "list", "dict")


def parse_keys(spec):
    keys = {}
    for part in filter(None, (p.strip() for p in spec.split(","))):
        name, _, typ = part.partition(":")
        typ = typ or "str"
        if typ not in TYPES:
            sys.exit(f"--json: unknown type {typ!r} for {name!r}; use one of {', '.join(TYPES)}")
        keys[name] = typ
    return keys


def main():
    ap = argparse.ArgumentParser(description="Ask one question with the tool-free harness.")
    ap.add_argument("question", help="text file with the question and pasted data, or - for stdin")
    ap.add_argument("--json", default="", help="answer keys, e.g. answer:float,unit:str")
    ap.add_argument("--workdir", default="runs/ask", help="folder for the model's code and the trace")
    ap.add_argument("--max-turns", type=int, default=12)
    a = ap.parse_args()

    text = sys.stdin.read() if a.question == "-" else Path(a.question).read_text(encoding="utf-8")
    contract = None
    if a.json:
        keys = parse_keys(a.json)
        contract = {"type": "json", "keys": keys}
        example = ", ".join(f'"{k}": <{t}>' for k, t in keys.items())
        text += f"\n\nAnswer with one JSON line only: {{{example}}}"

    run_dir = Path(a.workdir) / time.strftime("%Y%m%d-%H%M%S")
    if hx.wants_harness(text, contract):    # structured answer, table, numbers or code: use the harness
        tools = env.python_tool(run_dir / "ws", input_text=text, finish_hint=contract is not None,
                                clean_tables="keep")
        system = hx.SYSTEM + "\n\n# How to work with these tools\n" + (
            Path(__file__).with_name("skills") / "python_v3.md").read_text(encoding="utf-8").strip()
    else:                                   # free-form writing: answer directly (the code rules only distract)
        tools, system = {}, hx.SYSTEM
    client = hx.client_from_env(extra=json.loads(os.getenv("LLM_EXTRA", "{}")))
    res = hx.run(client, text, tools, features=hx.FEATURES_NT7 if tools else (), contract=contract,
                 trace=run_dir / "trace.json", system=system, max_turns=a.max_turns)
    print(res["answer"] or "")
    print(f"[harness] turns={res['turns']} tokens={res.get('tokens')} events={res['events']} "
          f"error={res['error']} trace={run_dir / 'trace.json'}", file=sys.stderr)
    return 0 if res["answer"] and not res["error"] else 1


if __name__ == "__main__":
    sys.exit(main())
