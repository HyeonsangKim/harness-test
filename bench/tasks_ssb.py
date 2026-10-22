"""SpreadsheetBench Verified: 100 real Excel-forum questions, answered as the values of the target cells.

Data: bench/ext/ssb/<id>.json (not committed), written once by bench/prep_ssb.py from
spreadsheetbench_verified_400.tar.gz in https://huggingface.co/datasets/KAKA22/SpreadsheetBench (CC BY-SA 4.0,
bench/ext/SSB_LICENSE; paper arXiv 2406.14991, code https://github.com/RUCKBReasoning/SpreadsheetBench). Each of
the 400 instances has an instruction, an instruction_type ("Cell-Level Manipulation" or "Sheet-Level
Manipulation"), an answer_position (cell ranges, optionally with a sheet name) and one input workbook with its
golden (answer) workbook. See prep_ssb.py for how cells are read and how formulas are handled: a cell shows the
value Excel cached for it, and no formula is evaluated.

The original task is writing formulas into the workbook; here the model returns the target cell values. A model
may therefore compute the values once for the workbook it sees, instead of writing a solution that would also
work on other data.

Test cases: the paper's OJ-style metric applies one solution to several test cases (the 912-question release has
2,729 test cases, about three per instruction; the "hard" score counts an instruction only if all pass). Every
Verified folder holds a single input/golden pair, so each instance is one task on that pair and nothing is merged
or dropped; on Verified the official score is that single comparison. (The official evaluation.py still loops over
three files named <n>_<id>_input.xlsx / _answer.xlsx, the 912-release names.)

Selection, in this order (instances left after each step, as printed by `python tasks_ssb.py`):
  1. not marked "exclude" in dataset.json (the dataset marks 2)                                     398
  2. instruction_type "Cell-Level Manipulation"                                                    273
  3. answer_position parses to bounded ranges on existing sheets (prep_ssb.parse_position; the two
     that fail, "A:G" and "BD2:308", are sheet-level)                                              273
  4. the instruction matches none of DROP (case-insensitive): VBA or macros, charts, colours, fonts, borders,
     gridlines, hiding, formatting cells, merged cells, recreating a sheet, adding rows, columns or sheets. These
     ask for work that cell values cannot show, or depend on formatting the grid below does not show. The rule is
     deliberately broad and also drops a few that only mention such a word (e.g. "without VBA")    234
  5. every golden answer cell has a value (no formula without a cached value), the answer sheet exists in the
     input workbook, no input formula is left without a value, and no sheet has over 40,000 cells   184
  6. no input formula or golden answer formula calls TODAY, NOW or RAND*                          178
  7. at least one answer cell is non-empty in the golden file, and the input file does not already pass  178
  8. the prompt is at most MAX_CHARS (16,000) characters                                          168
The pool is sorted by id (as text) and 100 are drawn with random.Random(0).sample; the ids are in
bench/ssb_ids.txt.

Prompt: the instruction unchanged; every sheet of the input workbook as a tab-separated grid from A1 to its last
non-empty cell, whose first line is "row" and the column letters and whose rows start with their row numbers
(cell text has tabs and line breaks replaced by spaces); then the answer position and a one-line JSON answer format
{"cells": {"D2": ..., "D3": ...}} (keys "Sheet!D2" when the answer spans several sheets).

Grading: cell by cell over the whole answer position, all cells must match (the official cell_level_compare).
A cell missing from the answer counts as empty; cells outside the answer position are ignored; keys may carry "$"
and a sheet name, and an answer without a "cells" object is read from its top-level cell keys. Based on
compare_cell_value / transform_value in the official evaluation/evaluation.py, with these differences:
  - numbers: official rounds both to 2 decimals and tests equality; here a cell also matches when
    math.isclose(rel_tol=1e-6, abs_tol=1e-9) holds. A numeric string counts as a number (as officially); here
    thousands commas and a trailing "%" (value / 100) are also read;
  - text: official is exact; here both sides are stripped, inner whitespace collapsed, and case ignored;
  - empty: official treats only None and "" as empty; here whitespace-only text is empty too;
  - dates: official compares the Excel serial number rounded to whole days; here both sides are normalized to
    ISO "YYYY-MM-DD" (plus "THH:MM" when the time is not midnight). The answer may also give the serial number;
  - times: as officially, "HH:MM" (seconds dropped); the answer may also give "H:MM:SS", "H:MM AM" or a fraction
    of a day;
  - booleans: official turns TRUE into 1.0; here true, 1 and the text "TRUE" all match TRUE;
  - durations ([h]:mm cells, read by openpyxl as timedelta; official compares timedelta objects): the answer may
    give "H:MM[:SS]" or a number of days.
The paper's own check of its metric (Appendix D.3: 50 instructions sampled from the original benchmark, three test
cases each, GPT-4o outputs) found no false positives, and "Among all instructions, 4% instructions contain at least
one correct sample prediction that fails to pass our automatic metric" (3.8% of failed test cases were judged
correct), because generated code wrote content beyond the intended answer.
Standard library only.
"""
import datetime
import json
import math
import random
import re
from pathlib import Path

import grade

HERE = Path(__file__).resolve().parent
EXT = HERE / "ext" / "ssb"
IDS = HERE / "ssb_ids.txt"
N, SEED, MAX_CHARS = 100, 0, 16000
DROP = re.compile(
    r"\bVBA\b|\bmacros?\b|\bcharts?\b|highlight|colou?r|\bfont\b|\bbold|italic|border|gridline|"
    r"conditional format|\bhid(?:e|den)\b|\bformat (?:the )?(?:cells?|col)|unmerge|recreate|wrap text|\bshade|"
    r"(?:insert|add) (?:a |an |new |the )?(?:new )?(?:rows?|columns?|tabs?|sheets?|worksheets?)\b|"
    r"new (?:tab|sheet|worksheet)\b", re.IGNORECASE)
_NUMTEXT = re.compile(r"\s*[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?\s*")
_CELL = re.compile(r"^([A-Z]{1,3})(\d+)$")
_EXCEL0 = datetime.datetime(1899, 12, 30)


# ---------------------------------------------------------------- rendering

def col_name(n):
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _iso(dt):
    return dt.strftime("%Y-%m-%d") if dt.time() == datetime.time() else dt.strftime("%Y-%m-%dT%H:%M")


def _hms(seconds):
    s = int(round(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def show(v):
    """A stored cell value as grid text."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else format(v, ".15g")
    if isinstance(v, dict):
        if "date" in v:
            return _iso(datetime.datetime.fromisoformat(v["date"])).replace("T", " ")
        if "time" in v:
            return v["time"]
        if "duration_s" in v:
            return _hms(v["duration_s"])
    return " ".join(str(v).replace("\t", " ").splitlines())


def grid(sheet):
    head = f'Sheet "{sheet["name"]}"' + (" (hidden)" if sheet["hidden"] else "")
    if not sheet["max_row"]:
        return head + ": empty"
    rows = sheet["rows"]
    lines = [f'{head}, A1:{col_name(sheet["max_col"])}{sheet["max_row"]}',
             "row\t" + "\t".join(col_name(c) for c in range(1, sheet["max_col"] + 1))]
    lines += [f"{r + 1}\t" + "\t".join(show(v) for v in row) for r, row in enumerate(rows)]
    return "\n".join(lines)


def _multi(rec):
    return len({s for s, _ in rec["answer"]}) > 1


def position_text(rec):
    if _multi(rec):
        return "cells " + ", ".join(f"'{s}'!{r}" for s, r in rec["answer"])
    return f'sheet "{rec["answer"][0][0]}", cells ' + ", ".join(r for _, r in rec["answer"])


def make_prompt(rec, tc=0):
    case = rec["test_cases"][tc]
    keys = list(case["expected"])[:2]
    ex = [k if _multi(rec) else k.split("!", 1)[1] for k in keys]
    more = ", ..." if len(case["expected"]) > 2 else ""
    example = '{"cells": {' + ", ".join(f'"{k}": ...' for k in ex) + more + "}}"
    n = len(case["sheets"])
    shown = "1 sheet, shown" if n == 1 else f"{n} sheets, each shown"
    sheets = "\n\n".join(grid(s) for s in case["sheets"])
    return (f"{rec['instruction']}\n\n"
            f"The workbook has {shown} below as a tab-separated grid. The first "
            "line of a grid holds the column letters and each row starts with its row number, so D2 is column D, "
            "row 2. A formula cell shows the value it gives. Empty rows at the bottom and empty columns at the "
            f"right are not shown.\n\n{sheets}\n\n"
            f"Give the values that should appear in {position_text(rec)} once the request above is carried out "
            f"(values, not formulas). Answer with one JSON line only: {example}, one entry per cell, keyed by cell "
            "reference" + (' with its sheet ("Sheet!D2")' if _multi(rec) else "") + ". Use a number for a number, "
            'text for text, "YYYY-MM-DD" for a date ("YYYY-MM-DD HH:MM" with a time), "HH:MM" for a time, '
            "true/false for TRUE/FALSE. Leave out a cell, or give \"\", if it should be empty.")


# ---------------------------------------------------------------- grading

def _num(x):
    """A JSON value as a number: numbers, booleans, numeric text (commas allowed, "12%" is 0.12). Else None."""
    if isinstance(x, bool):
        return float(x)
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.strip().replace(",", "")
        pct = s.endswith("%")
        try:
            f = float(s[:-1] if pct else s)
        except ValueError:
            return None
        return f / 100 if pct else f
    return None


def _norm_text(x):
    return " ".join(str(x).split()).casefold()


def _empty(x):
    return x is None or (isinstance(x, str) and not x.strip())


def _as_datetime(x):
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return _EXCEL0 + datetime.timedelta(days=float(x))
    if isinstance(x, str):
        s = x.strip().replace("/", "-")
        for f in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
            try:
                return datetime.datetime.strptime(s, f)
            except ValueError:
                pass
    return None


def _minutes(dt):
    return dt.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1 if dt.second >= 30 else 0)


def _as_hhmm(x):
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        m = round((float(x) % 1) * 1440)
        return f"{m // 60 % 24:02d}:{m % 60:02d}"
    if isinstance(x, str):
        s = x.strip().upper()
        for f in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p", "%I:%M:%S%p", "%I:%M%p"):
            try:
                return datetime.datetime.strptime(s, f).strftime("%H:%M")
            except ValueError:
                pass
    return None


def _as_seconds(x):
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x) * 86400
    if isinstance(x, str):
        m = re.fullmatch(r"\s*(-?\d+):(\d{1,2})(?::(\d{1,2}))?\s*", x)
        if m:
            sign = -1 if m[1].startswith("-") else 1
            return sign * (abs(int(m[1])) * 3600 + int(m[2]) * 60 + int(m[3] or 0))
    return None


def cell_match(gold, pred):
    """gold: a stored golden value (prep_ssb encoding); pred: a JSON value from the answer (missing = None)."""
    if _empty(gold):
        return _empty(pred)
    if _empty(pred):
        return False
    if isinstance(gold, dict):
        if "date" in gold:
            p = _as_datetime(pred)
            g = datetime.datetime.fromisoformat(gold["date"])
            return p is not None and _iso(_minutes(p)) == _iso(_minutes(g))
        if "time" in gold:
            return _as_hhmm(pred) == gold["time"][:5]
        if "duration_s" in gold:
            p = _as_seconds(pred)
            return p is not None and abs(p - gold["duration_s"]) < 0.5
        return False
    if isinstance(gold, bool):
        if isinstance(pred, str):
            return pred.strip().casefold() == str(gold).casefold()
        return _num(pred) == float(gold)
    if isinstance(gold, (int, float)) or _NUMTEXT.fullmatch(gold):      # official: float(text) if it parses
        g, p = float(gold), _num(pred)
        return p is not None and (round(g, 2) == round(p, 2) or math.isclose(g, p, rel_tol=1e-6, abs_tol=1e-9))
    if isinstance(pred, (dict, list)):
        return False
    if isinstance(pred, bool):
        pred = "TRUE" if pred else "FALSE"
    elif isinstance(pred, float) and pred.is_integer():
        pred = int(pred)
    return _norm_text(pred) == _norm_text(gold)


def _norm_key(k, sheets):
    """'$d$2' / "'Data'!D2" / 'data!D2' -> 'Data!D2' (sheet matched without case); None if not a cell."""
    k = str(k).strip().replace("$", "")
    sheet = None
    if "!" in k:
        sheet, k = k.rsplit("!", 1)
        sheet = sheet.strip().strip("'").strip().casefold()
    m = _CELL.match(k.strip().upper())
    if not m:
        return None
    ref = m[0]
    names = {s.casefold(): s for s in sheets}
    if sheet is not None:
        return f"{names[sheet]}!{ref}" if sheet in names else None
    return ref


def answer_cells(parsed, expected):
    """The answer's {"cells": {...}} keyed like expected ("Sheet!D2"). A bare reference goes to the one answer
    sheet that has that cell. Without a "cells" object, top-level keys that are cell references are used."""
    if not isinstance(parsed, dict):
        return None
    cells = parsed.get("cells")
    if not isinstance(cells, dict):
        cells = {k: v for k, v in parsed.items() if _CELL.match(str(k).replace("$", "").split("!")[-1].strip().upper())}
        if not cells:
            return None
    sheets = sorted({k.split("!", 1)[0] for k in expected})
    by_ref = {}
    for k in expected:
        by_ref.setdefault(k.split("!", 1)[1], []).append(k)
    out = {}
    for k, v in cells.items():
        nk = _norm_key(k, sheets)
        if nk is None:
            continue
        if "!" not in nk:
            owners = by_ref.get(nk, [])
            if len(owners) != 1:
                continue
            nk = owners[0]
        out[nk] = v
    return out


def check_cells(parsed, expected):
    got = answer_cells(parsed, expected)
    if got is None:
        return False
    return all(cell_match(g, got.get(k)) for k, g in expected.items())


# ---------------------------------------------------------------- selection

def _load():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(EXT.glob("*.json"))]


def _filters():
    def nonempty(case):
        return any(not _empty(v) for v in case["expected"].values())

    def init_passes(case):
        return all(cell_match(g, case["init_answer"].get(k)) for k, g in case["expected"].items())

    def resolved(rec):
        return all(not c.get("answer_too_large") and not c["expected_uncached"] and not c["answer_sheet_missing"]
                   and not c["uncached"] and not any(s.get("too_large") for s in c["sheets"])
                   for c in rec["test_cases"])

    return [
        ("not marked exclude", lambda r: "exclude" not in r),
        ("Cell-Level Manipulation", lambda r: r["instruction_type"] == "Cell-Level Manipulation"),
        ("answer position parses", lambda r: "answer" in r and "test_cases" in r),
        ("no VBA/chart/format/structure words", lambda r: not DROP.search(r["instruction"])),
        ("all formula values cached", resolved),
        ("no TODAY/NOW/RAND", lambda r: not any(c["volatile"] for c in r["test_cases"])),
        ("non-empty answer, input not already passing",
         lambda r: all(nonempty(c) and not init_passes(c) for c in r["test_cases"])),
        (f"prompt <= {MAX_CHARS} chars",
         lambda r: all(len(make_prompt(r, i)) <= MAX_CHARS for i in range(len(r["test_cases"])))),
    ]


def select(verbose=False):
    pool = _load()
    if verbose:
        print(f"{'all instances':45s} {len(pool)}")
    for name, keep in _filters():
        pool = [r for r in pool if keep(r)]
        if verbose:
            print(f"{name:45s} {len(pool)}")
    pool.sort(key=lambda r: r["id"])
    return random.Random(SEED).sample(pool, N)


def _tasks():
    tasks = []
    for rec in select():
        expected = rec["test_cases"][0]["expected"]

        def check(answer, parsed, ws, expected=expected):
            return check_cells(parsed if parsed is not None else grade.parse_json(answer or ""), expected)

        tasks.append({"id": f"ssb_{rec['id']}", "split": "ssb", "domain": "spreadsheetbench",
                      "prompt": make_prompt(rec), "tools": "none",
                      "contract": {"type": "json", "keys": {"cells": "dict"}}, "check": check,
                      "instruction_type": rec["instruction_type"]})
    return tasks


TASKS = _tasks() if EXT.exists() else []


# ---------------------------------------------------------------- self-test

def _gold_json(v):
    if isinstance(v, dict):
        if "date" in v:
            return _iso(datetime.datetime.fromisoformat(v["date"])).replace("T", " ")
        if "time" in v:
            return v["time"][:5]
        if "duration_s" in v:
            return _hms(v["duration_s"])
    return v


def _perturb(v):
    if isinstance(v, bool):
        return not v
    if isinstance(v, (int, float)):
        return v + 1
    if isinstance(v, dict):
        if "date" in v:
            return _iso(datetime.datetime.fromisoformat(v["date"]) + datetime.timedelta(days=1)).replace("T", " ")
        if "time" in v:
            h, m = int(v["time"][:2]), v["time"][3:5]
            return f"{(h + 1) % 24:02d}:{m}"
        if "duration_s" in v:
            return _hms(v["duration_s"] + 3600)
    n = _num(v)
    return n + 1 if n is not None else str(v) + " x"


def _self_test():
    import collections
    import statistics
    chosen = select(verbose=True)
    IDS.write_text("\n".join(r["id"] for r in chosen) + "\n", encoding="utf-8")
    print(f"wrote {IDS.name}: {len(chosen)} ids")
    by_task = {t["id"]: t for t in TASKS}
    bad = []
    for rec in chosen:
        t = by_task[f"ssb_{rec['id']}"]
        exp = rec["test_cases"][0]["expected"]
        multi = _multi(rec)
        key = (lambda k: k) if multi else (lambda k: k.split("!", 1)[1])
        gold = {key(k): _gold_json(v) for k, v in exp.items() if not _empty(v)}
        text = json.dumps({"cells": gold}, ensure_ascii=False)
        if not t["check"](text, grade.parse_json(text), None):
            bad.append((t["id"], "gold fails"))
        for empty in ('{"cells": {}}', "", "no answer"):
            if t["check"](empty, grade.parse_json(empty), None):
                bad.append((t["id"], f"empty passes: {empty!r}"))
        first = next(k for k, v in exp.items() if not _empty(v))
        wrong = dict(gold)
        wrong[key(first)] = _perturb(exp[first])
        text = json.dumps({"cells": wrong}, ensure_ascii=False)
        if t["check"](text, grade.parse_json(text), None):
            bad.append((t["id"], f"perturbed passes at {first}: {exp[first]!r} -> {wrong[key(first)]!r}"))
    lens = sorted(len(t["prompt"]) for t in TASKS)
    cells = sorted(sum(not _empty(v) for v in r["test_cases"][0]["expected"].values()) for r in chosen)
    print("instruction_type:", dict(collections.Counter(r["instruction_type"] for r in chosen)))
    print("multi-sheet answers:", sum(_multi(r) for r in chosen),
          "| workbooks with 2+ sheets:", sum(len(r["test_cases"][0]["sheets"]) > 1 for r in chosen))
    print(f"prompt chars: min {lens[0]}, p25 {lens[len(lens) // 4]}, median {statistics.median(lens):.0f}, "
          f"p75 {lens[3 * len(lens) // 4]}, max {lens[-1]}")
    print(f"non-empty answer cells: min {cells[0]}, median {statistics.median(cells):.0f}, max {cells[-1]}")
    print(f"self-test: {len(chosen) - len({b[0] for b in bad})}/{len(chosen)} clean")
    for b in bad:
        print("  FAIL", *b)
    return not bad


if __name__ == "__main__":
    raise SystemExit(0 if _self_test() else 1)
