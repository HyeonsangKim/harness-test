"""Hard public benchmark for the tool-free harness: MultiHiertt (ACL 2022), 150 numeric questions over several tables.

Data: bench/ext/multihiertt_dev.json (not committed), the dev split from
https://huggingface.co/datasets/yilunzhao/MultiHiertt (multihiertt_data/dev.json, MIT; code and license at
https://github.com/psunlpgroup/MultiHiertt, copied to bench/ext/MULTIHIERTT_LICENSE). Test labels are hidden
(CodaLab leaderboard), so the dev split is used. Each document has 2-7 tables (HTML) and about 1,600 words of text;
"## Table k ##" lines in the text mark where each table sits.

Questions: only "arithmetic" questions (gold reasoning program, numeric gold answer). Among them, a question is
hard if its gold table evidence ("table-row-col" ids) spans 2+ tables, or one of its evidence tables has 15+ rows.
Questions whose prompt is over MAX_CHARS characters are left out (local context: 64k tokens shared by 6 slots).
150 are sampled with random.Random(0) from that pool sorted by uid; the chosen ids are in bench/hard_ids.txt.

Prompt: the text in order, each table in place as tab-separated rows (every row padded to the same number of
cells, colspan/rowspan cells written once and padded with empty cells) under its line "Table k", then the question
and a one-line JSON answer instruction. The dataset stores percentages and ratios as decimal fractions (0.18136
for 18.1%), so the instruction asks for that form.

Grading: the official evaluate.py (https://github.com/psunlpgroup/MultiHiertt/blob/main/evaluate.py,
evaluate_span_program_result) compares a predicted number with a gold program answer by
    math.isclose(gold, pred, abs_tol=min(abs(min(gold, pred) / 1000), 0.1))       # rel_tol default 1e-9
i.e. within 0.1% of the smaller value, at most 0.1 absolute. Implemented as is, with one difference: the
official str_to_num drops every "-" from the predicted text, so a negative gold answer could never match; here
the sign is kept.
"""
import json
import math
import random
from html.parser import HTMLParser
from pathlib import Path

import grade

EXT = Path(__file__).resolve().parent / "ext"
N, SEED, MAX_CHARS, MIN_ROWS = 150, 0, 30000, 15


class _Rows(HTMLParser):
    """<table> HTML to a grid of cell strings; colspan/rowspan cells are written once, padded with empty cells."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.cell, self.span, self.down = [], None, (1, 1), {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self.rows.append([])
        elif tag == "td":
            def n(k):
                try:
                    return max(1, int(a.get(k) or 1))
                except ValueError:
                    return 1
            self.cell, self.span = [], (n("colspan"), n("rowspan"))

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            row, r = self.rows[-1], len(self.rows) - 1
            while (r, len(row)) in self.down:          # columns taken by a rowspan cell from above
                row.append("")
            text = " ".join("".join(self.cell).replace("\t", " ").split())
            cs, rs = self.span
            for k in range(rs):
                for j in range(cs):
                    if k:
                        self.down[(r + k, len(row) + j)] = True
            row.extend([text] + [""] * (cs - 1))
            self.cell = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def table_rows(html):
    p = _Rows()
    p.feed(html)
    p.close()
    rows = [r for r in p.rows if any(c for c in r)]
    width = max((len(r) for r in rows), default=0)
    return [r + [""] * (width - len(r)) for r in rows]


def _evidence_tables(q):
    return sorted({int(x.split("-")[0]) for x in q.get("table_evidence") or []})


def is_hard(doc):
    tabs = _evidence_tables(doc["qa"])
    return len(tabs) >= 2 or any(len(table_rows(doc["tables"][t])) >= MIN_ROWS for t in tabs if t < len(doc["tables"]))


def make_prompt(doc):
    parts, tables = [], [table_rows(t) for t in doc["tables"]]
    for p in doc["paragraphs"]:
        s = p.strip()
        if s.startswith("## Table ") and s.endswith(" ##"):
            k = int(s[9:-3])
            parts.append(f"Table {k}\n" + "\n".join("\t".join(r) for r in tables[k]))
        elif s:
            parts.append(s)
    body = "\n\n".join(parts)
    return (f"Below is text from a company's annual report, with its tables (tab-separated) in place.\n\n{body}\n\n"
            f"Question: {doc['qa']['question']}\n\n"
            'Answer with one JSON line only: {"answer": number}. Give amounts in the unit the question or the table '
            'uses (e.g. "in millions" means 1234 for $1,234 million). Give a percentage, ratio or growth rate as a '
            'decimal fraction, not a percent value (e.g. 0.1814 for 18.14%). Do not round: keep at least 4 '
            'significant digits.')


def official_match(pred, gold):
    """evaluate_span_program_result in the official evaluate.py (sign kept)."""
    return math.isclose(gold, pred, abs_tol=min(abs(min(gold, pred) / 1000), 0.1))


def _pool():
    docs = json.loads((EXT / "multihiertt_dev.json").read_text(encoding="utf-8"))
    pool = [d for d in docs if d["qa"]["question_type"] == "arithmetic" and d["qa"]["program"]
            and isinstance(d["qa"]["answer"], (int, float)) and is_hard(d)]
    pool.sort(key=lambda d: d["uid"])
    long = [d["uid"] for d in pool if len(make_prompt(d)) > MAX_CHARS]
    return [d for d in pool if len(make_prompt(d)) <= MAX_CHARS], long


def _tasks():
    pool, _ = _pool()
    tasks = []
    for doc in random.Random(SEED).sample(pool, N):
        gold = float(doc["qa"]["answer"])

        def check(answer, parsed, ws, gold=gold):
            if not parsed:
                return False
            got = grade.num(parsed.get("answer"))
            return got is not None and official_match(float(got), gold)

        tasks.append({"id": f"mhiertt_{doc['uid'][:12]}", "split": "hard", "domain": "multihiertt",
                      "prompt": make_prompt(doc), "tools": "none",
                      "contract": {"type": "json", "keys": {"answer": "float"}}, "check": check})
    return tasks


TASKS = _tasks()
