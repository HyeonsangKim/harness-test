"""IFEval (Google, instruction following): 150 prompts that need no computation, graded by the official checker.

Used to show the harness does not hurt tasks that need no tool. Run with `--taskfile tasks_ifeval --split ifeval`.

Data and code live in bench/ext/ (not committed), taken from google-research/google-research
instruction_following_eval (Apache-2.0):
  ext/instruction_following_eval/  instructions.py, instructions_registry.py, instructions_util.py, evaluation_lib.py
                                   (unchanged) + empty __init__.py; data/input_data.jsonl (541 prompts)
  ext/nltk_data/                   nltk punkt + punkt_tab, downloaded once so grading runs offline
Needs absl-py, langdetect, nltk, immutabledict, so this file runs only on the outside machine.

Grading: official strict, prompt-level accuracy -- evaluation_lib.test_instruction_following_strict on the reply as is;
the task passes only if every instruction of the prompt is followed. The prompt is the IFEval prompt unchanged.
Sample: random.Random(0).sample(sorted keys, 150); the chosen keys are fixed in bench/ifeval_ids.txt.
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXT = HERE / "ext"
DATA = EXT / "instruction_following_eval" / "data" / "input_data.jsonl"
IDS = HERE / "ifeval_ids.txt"
N, SEED = 150, 0

sys.path.insert(0, str(EXT))
import nltk                                                     # noqa: E402
nltk.data.path.insert(0, str(EXT / "nltk_data"))
import langdetect                                               # noqa: E402
langdetect.DetectorFactory.seed = 0                             # langdetect is random otherwise
from instruction_following_eval import evaluation_lib           # noqa: E402  official checker


def _tasks():
    rows = {r["key"]: r for r in map(json.loads, DATA.read_text(encoding="utf-8").splitlines()) if r}
    keys = [int(k) for k in IDS.read_text(encoding="utf-8").strip().split(",")]
    assert keys == random.Random(SEED).sample(sorted(rows), N), "ifeval_ids.txt does not match the seeded sample"
    tasks = []
    for k in keys:
        r = rows[k]
        inp = evaluation_lib.InputExample(key=r["key"], instruction_id_list=r["instruction_id_list"],
                                          prompt=r["prompt"], kwargs=r["kwargs"])

        def check(answer, parsed, ws, inp=inp):
            out = evaluation_lib.test_instruction_following_strict(inp, {inp.prompt: answer or ""})
            return bool(out.follow_all_instructions)

        tasks.append({"id": f"ifeval_{k:04d}", "split": "ifeval", "domain": "ifeval", "prompt": r["prompt"],
                      "tools": "none", "contract": {"type": "text"}, "check": check,
                      "instructions": list(r["instruction_id_list"])})
    return tasks


TASKS = _tasks()
