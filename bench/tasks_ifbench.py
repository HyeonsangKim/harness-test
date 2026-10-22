"""IFBench (AllenAI, NeurIPS 2025 D&B, arXiv 2507.02833): 50 constrained-writing prompts, graded by the official checker.

Used to check that the harness does not hurt constrained writing and that the router (hx.wants_harness) sends these
free-writing requests to a plain answer. Run with `--taskfile tasks_ifbench --split ifbench`.

Source: 300 single-turn prompts, each a held-out WildChat request plus 1-2 of 58 new verifiable constraints
(count, ratio, words, sentence, format, custom, copy) that are not in IFEval.
  Data:  HF allenai/IFBench_test @ 2e8a48de (ODC-BY-1.0), data/train-00000-of-00001.parquet, converted to
         ext/ifbench_hf/IFBench_test_hf.jsonl (float kwargs that are whole numbers written as int, NaN as null).
         The same 300 prompts ship in the GitHub repo; two prompts there (keys 13, 19) differ only by trailing spaces.
  Code:  github.com/allenai/IFBench @ 1c40f0c1 (Apache-2.0), copied unchanged to ext/IFBench/
         (ifbench/ package: instructions, classic_instructions, instructions_registry, instructions_util;
         evaluation_lib.py). License in ext/IFBENCH_LICENSE, commits in ext/IFBENCH_SOURCE.txt.
  NLTK:  punkt, punkt_tab, stopwords, averaged_perceptron_tagger_eng in ext/nltk_data, so grading runs offline
         (ifbench.instructions_util downloads them at import time if they are missing).
Needs absl-py, langdetect, nltk, immutabledict, emoji, syllapy, so this file runs only on the outside machine:
    uv run --no-project --python 3.12 --with absl-py,langdetect,nltk,immutabledict,emoji,syllapy python ...

Selection: random.Random(0).sample(keys sorted as integers, 50); the chosen keys are fixed in bench/ifbench_ids.txt.
The prompt is the IFBench prompt unchanged.

Grading: official prompt-level loose accuracy, as reported in the paper (Sec. 3, "We report the prompt-level loose
accuracy for both IFEval and IFBENCH") -- evaluation_lib.test_instruction_following_loose; the task passes only if
every instruction of the prompt is followed by at least one of 8 variants of the reply (as is, first line removed,
last line removed, both removed, each also with every "*" removed). An empty reply fails.
check_strict() gives the strict variant (reply as is). One detail of the official run_eval.py is kept: it runs strict
first, and strict drops None-valued kwargs in place, so loose then sees the cleaned kwargs; here both get them cleaned.

Published scores (paper v3, IFBench single-turn, prompt-level loose, all 300 prompts, temperature 0):
  Qwen2.5-7B-Instruct 31.3, Tulu-3-DPO 8B 25.2 (Table 6); Tulu-3-8B 28.9 (Table 3);
  Qwen3-8B 35.0, Qwen3-32B 37.3, Claude 4 Sonnet 42.3, Gemini 2.5 Pro 52.3, o3 69.3 (Figure 1).
  GPT-4.1 has no number in the paper, only "leading models such as GPT-4.1 or Claude 3.7 Sonnet score below 50%".
"""
import copy
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXT = HERE / "ext"
DATA = EXT / "ifbench_hf" / "IFBench_test_hf.jsonl"
IDS = HERE / "ifbench_ids.txt"
N, SEED = 50, 0

sys.path.insert(0, str(EXT / "IFBench"))
import nltk                                                     # noqa: E402
nltk.data.path.insert(0, str(EXT / "nltk_data"))
import langdetect                                               # noqa: E402
langdetect.DetectorFactory.seed = 0                             # langdetect is random otherwise
import evaluation_lib                                           # noqa: E402  official checker (ext/IFBench)


def _example(r):
    """A fresh InputExample per call: the official strict test edits kwargs in place."""
    kwargs = [{k: v for k, v in kw.items() if v is not None} for kw in r["kwargs"]]
    return evaluation_lib.InputExample(key=r["key"], instruction_id_list=list(r["instruction_id_list"]),
                                       prompt=r["prompt"], kwargs=copy.deepcopy(kwargs))


def check_loose(r, answer):
    """Official prompt-level loose: every instruction followed under the loose rules."""
    inp = _example(r)
    return bool(evaluation_lib.test_instruction_following_loose(inp, {inp.prompt: answer or ""})
                .follow_all_instructions)


def check_strict(r, answer):
    """Official prompt-level strict: every instruction followed by the reply as is."""
    inp = _example(r)
    return bool(evaluation_lib.test_instruction_following_strict(inp, {inp.prompt: answer or ""})
                .follow_all_instructions)


def rows():
    return {int(r["key"]): r for r in map(json.loads, DATA.read_text(encoding="utf-8").splitlines()) if r}


def _tasks():
    data = rows()
    keys = [int(k) for k in IDS.read_text(encoding="utf-8").strip().split(",")]
    assert keys == random.Random(SEED).sample(sorted(data), N), "ifbench_ids.txt does not match the seeded sample"
    tasks = []
    for k in keys:
        r = data[k]

        def check(answer, parsed, ws, r=r):
            return check_loose(r, answer)

        def check_s(answer, parsed, ws, r=r):
            return check_strict(r, answer)

        tasks.append({"id": f"ifbench_{k:03d}", "split": "ifbench", "domain": "ifbench", "prompt": r["prompt"],
                      "tools": "none", "contract": {"type": "text"}, "check": check, "check_strict": check_s,
                      "instructions": list(r["instruction_id_list"])})
    return tasks


TASKS = _tasks()
