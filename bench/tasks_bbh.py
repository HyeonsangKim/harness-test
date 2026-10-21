"""BIG-Bench Hard (BBH): reasoning questions where code is not obviously needed. 108 questions.

Data: bench/ext/bbh/<task>.json (not committed) from suzgunmirac/BIG-Bench-Hard, directory bbh/ (MIT,
bench/ext/BBH_LICENSE). 4 questions per task across the 27 tasks: random.Random(0).sample on each task's
sorted index list. The chosen ids are listed in bench/bbh_ids.txt.

The answer form note in each prompt is derived from that task's targets (option letter, a fixed word pair,
an integer, closing brackets, a sorted word list). Grading is exact match after light normalization only:
strip, case-insensitive; option letters as "(A)" or "A"; integers by numeric equality; bracket sequences
ignoring spaces; word lists word by word. An answer that merely contains the target among other text fails.
Standard library only.
"""
import json
import random
import re
from pathlib import Path

import grade

EXT = Path(__file__).resolve().parent / "ext" / "bbh"
PER_TASK, SEED = 4, 0
JSON_RULE = 'Answer with one JSON line only: {"answer": "..."}'
_MC = re.compile(r"\(([A-Z])\)")
_BRACKETS = set("()[]{}<>")


def _form(targets):
    """Answer form of a task from all its targets: (kind, note for the prompt)."""
    mc = sum(1 for t in targets if _MC.fullmatch(t))
    if mc >= 0.95 * len(targets):
        return "mc", 'The answer is the letter of the correct option in parentheses, e.g. "(A)".'
    distinct = sorted(set(targets))
    if len(distinct) == 2 and all(re.fullmatch(r"[A-Za-z]+", t) for t in distinct):
        a, b = distinct
        return "word", f'The answer is "{a}" or "{b}".'
    if all(re.fullmatch(r"-?\d+", t) for t in targets):
        return "int", 'The answer is an integer, written as a JSON string, e.g. "-12".'
    if all(t.split() and set(t.split()) <= _BRACKETS for t in targets):
        return "brackets", ('The answer is only the closing brackets that complete the sequence (not the part '
                            'already given), separated by spaces, e.g. ") ] }".')
    return "words", ('The answer is all the given words in the requested order, separated by single spaces, '
                     'e.g. "apple banana cherry".')


def _text(v):
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, list):
        return " ".join(str(x) for x in v)
    return "" if v is None else str(v)


def _match(kind, target, value):
    s = _text(value).strip()
    if kind == "mc":
        m = re.fullmatch(r"\(?([A-Za-z])\)?", s)
        return bool(m) and m.group(1).upper() == _MC.fullmatch(target).group(1)
    if kind == "word":
        return s.casefold() == target.casefold()
    if kind == "int":
        got = grade.num(value) if not isinstance(value, bool) else None
        return got is not None and got == int(target)
    if kind == "brackets":
        return re.sub(r"\s+", "", s) == target.replace(" ", "")
    return [w.casefold() for w in re.split(r"[\s,]+", s) if w] == target.casefold().split()


def _first_json(text):
    """First JSON object with an "answer" key, read with a real JSON decoder (braces inside strings are fine).
    grade.parse_json counts braces without looking at strings, so it misses e.g. {"answer": "} ]"}."""
    text = re.sub(r"```(?:json)?", "", text or "")
    dec, start = json.JSONDecoder(), text.find("{")
    while start != -1:
        try:
            value, _ = dec.raw_decode(text, start)
            if isinstance(value, dict) and "answer" in value:
                return value
        except ValueError:
            pass
        start = text.find("{", start + 1)
    return None


def _tasks():
    tasks = []
    for path in sorted(EXT.glob("*.json")):
        name = path.stem
        examples = json.loads(path.read_text(encoding="utf-8"))["examples"]
        kind, note = _form([e["target"] for e in examples])
        for i in random.Random(SEED).sample(sorted(range(len(examples))), PER_TASK):
            target = examples[i]["target"]
            if kind == "mc" and not _MC.fullmatch(target):
                raise ValueError(f"bbh {name} #{i}: target {target!r} is not an option letter")
            prompt = f"{examples[i]['input']}\n\n{JSON_RULE}\n{note}"

            def check(answer, parsed, ws, kind=kind, target=target):
                p = parsed if parsed and "answer" in parsed else _first_json(answer)
                return bool(p) and _match(kind, target, p["answer"])

            tasks.append({"id": f"bbh_{name}_{i}", "split": "bbh", "domain": "bbh", "prompt": prompt,
                          "tools": "none", "contract": {"type": "json", "keys": {"answer": "any"}},
                          "check": check})
    return tasks


TASKS = _tasks()
