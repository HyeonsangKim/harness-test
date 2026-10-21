"""Public benchmarks for the tool-free harness: TAT-QA (arithmetic) and GSM-Hard, 100 questions each.

Data files live in bench/ext/ (not committed): tatqa_dataset_dev.json from next-tat/TAT-QA (CC-BY-4.0) and
gsmhardv2.jsonl from reasoning-machines/gsm-hard (MIT). TAT-QA is graded with the official TAT-QA metric
(tatqa_metric.py, MIT, needs numpy/pandas/scipy), so this file runs only on the outside machine.
"""
import json
import random
import sys
from pathlib import Path

import grade

EXT = Path(__file__).resolve().parent / "ext"
sys.path.insert(0, str(EXT))
N, SEED = 100, 0
SCALES = ["", "thousand", "million", "billion", "percent"]


def _tatqa_tasks():
    from tatqa_metric import TaTQAEmAndF1   # official metric

    docs = json.loads((EXT / "tatqa_dev.json").read_text(encoding="utf-8"))
    pool = [(doc, q) for doc in docs for q in doc["questions"] if q["answer_type"] == "arithmetic"]
    pool.sort(key=lambda dq: dq[1]["uid"])
    picked = random.Random(SEED).sample(pool, N)
    tasks = []
    for doc, q in picked:
        table = "\n".join("\t".join(str(c) for c in row) for row in doc["table"]["table"])
        paras = "\n".join(p["text"] for p in sorted(doc["paragraphs"], key=lambda p: p["order"]))
        prompt = (f"Below is a table (tab-separated) and text from a company's financial report.\n\n"
                  f"{table}\n\n{paras}\n\nQuestion: {q['question']}\n\n"
                  'Answer with one JSON line only: {"answer": number, "scale": one of "", "thousand", '
                  '"million", "billion", "percent"}. Keep the unit the report uses for those numbers; do not '
                  'convert it. If the table says "in thousands", answer in thousands with "scale": "thousand" '
                  '(e.g. 1234 with "thousand", not 1.234 with "million"). For a percentage, give the percent '
                  'value with "scale": "percent" (e.g. 12.5 for 12.5%). Otherwise use "scale": "".')

        def check(answer, parsed, ws, q=q):
            if not parsed or "answer" not in parsed:
                return False
            scale = str(parsed.get("scale", "") or "").strip().lower()
            scale = scale if scale in SCALES else ""
            metric = TaTQAEmAndF1()
            metric(q, [str(parsed["answer"])], scale)
            return metric.get_overall_metric()[0] == 1.0

        tasks.append({"id": f"tatqa_{q['uid'][:8]}", "split": "bench", "domain": "tatqa", "prompt": prompt,
                      "tools": "none", "contract": {"type": "json", "keys": {"answer": "float", "scale": "str"}},
                      "check": check})
    return tasks


def _gsmhard_tasks():
    rows = [json.loads(l) for l in (EXT / "gsmhard.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    idx = random.Random(SEED).sample(range(len(rows)), N)
    tasks = []
    for i in idx:
        r = rows[i]
        target = float(r["target"])
        prompt = (f"{r['input']}\n\nAnswer with one JSON line only: {{\"answer\": number}}")

        def check(answer, parsed, ws, target=target):
            if not parsed:
                return False
            got = grade.num(parsed.get("answer"))
            return got is not None and abs(float(got) - target) <= max(1e-2, abs(target) * 1e-6)

        tasks.append({"id": f"gsmh_{i:04d}", "split": "bench", "domain": "gsmhard", "prompt": prompt,
                      "tools": "none", "contract": {"type": "json", "keys": {"answer": "float"}}, "check": check})
    return tasks


TASKS = _tatqa_tasks() + _gsmhard_tasks()
