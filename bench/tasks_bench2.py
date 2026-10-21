"""TAT-QA / GSM-Hard tasks for an explicit id list (default: bench_ids_heldout2.txt).

tasks_bench.py builds tasks only for its own seed-0 sample. This module reuses tasks_bench's builders unchanged
(same prompt text, check functions, split "bench") and only swaps the sampling step for "pick these ids", so ids
that tasks_bench.py already has get identical prompts and checks. Needs numpy/pandas like tasks_bench.py.
"""
from pathlib import Path

import tasks_bench

IDS_FILE = Path(__file__).resolve().parent / "bench_ids_heldout2.txt"


class _PickRandom:
    """Stands in for random.Random inside tasks_bench: sample() returns the wanted items in id-list order."""

    def __init__(self, ids):
        self.ids = ids

    def __call__(self, seed=None):
        return self

    def sample(self, population, k):
        if isinstance(population, range):
            by_id = {f"gsmh_{i:04d}": i for i in population}
        else:
            by_id = {f"tatqa_{q['uid'][:8]}": (doc, q) for doc, q in population}
        return [by_id[i] for i in self.ids if i in by_id]


def build(ids):
    ids = list(ids)
    real = tasks_bench.random
    tasks_bench.random = type("R", (), {"Random": _PickRandom(ids)})
    try:
        tasks = tasks_bench._tatqa_tasks() + tasks_bench._gsmhard_tasks()
    finally:
        tasks_bench.random = real
    missing = set(ids) - {t["id"] for t in tasks}
    if missing:
        raise KeyError(f"ids not found in the data: {sorted(missing)}")
    order = {i: n for n, i in enumerate(ids)}
    return sorted(tasks, key=lambda t: order[t["id"]])


TASKS = build(i.strip() for i in IDS_FILE.read_text(encoding="utf-8").split(",") if i.strip())
