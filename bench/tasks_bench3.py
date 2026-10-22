"""TAT-QA / GSM-Hard tasks for bench_ids_heldout3.txt (100 + 100 ids never used before), built by tasks_bench2.build."""
from pathlib import Path

import tasks_bench2

IDS_FILE = Path(__file__).resolve().parent / "bench_ids_heldout3.txt"
TASKS = tasks_bench2.build(i.strip() for i in IDS_FILE.read_text(encoding="utf-8").split(",") if i.strip())
