"""Contract clause extraction from CUAD v1 (Hendrycks et al., NeurIPS 2021 Datasets and Benchmarks), 40 items.

Data: bench/ext/cuad/data/test.json (not committed), the test split of CUAD v1 as served by the Hugging Face loader
https://huggingface.co/datasets/theatticusproject/cuad-qa (cuad-qa.py downloads
https://github.com/TheAtticusProject/cuad/raw/main/data.zip and reads test.json for the test split). CC BY 4.0 (the
dataset card's "Licensing Information"; copied to bench/ext/cuad/LICENSE). Paper: arXiv 2103.06268. The test split
is 102 contracts (the paper: a random 80/20 split of the 510 contracts by contract). Each contract has one context
(the full contract text) and 41 questions, one per category, with expert-labeled answer spans (text + char offset).

Item = one contract window + 5 clause categories asked at once. The model returns one JSON object
{category: quoted clause text | list of quoted texts | null}.

Selection (deterministic, run at import; the chosen titles are in bench/cuad_ids.txt):
  1. Categories: POOL, 22 of the 41 that matter in business contract review (names as in category_descriptions.csv;
     dataset ids use str.title() of them, as the official evaluate.py does). Not used: Document Name, Parties,
     dates, and rare license sub-types.
  2. Window: a contract of at most WINDOW (12,000) characters is used whole. Otherwise every line start s is a
     candidate; the window is [s, e) with e the last line break at or before s + WINDOW (or the end of the text). A
     category is "inside" a window if it has at least one labeled span and every span that overlaps the window lies
     fully inside it; it "straddles" if some span crosses a window edge. The chosen window maximises the number of
     POOL categories inside; ties go to the earliest s.
  3. Asked categories, with random.Random(f"{SEED}:{title}"): up to 3 present (inside) categories, chosen so that no
     span of one matches (Jaccard >= 0.5) a span of another (a clause labeled under two asked categories would make
     a swap undetectable); then absent categories fill up to K = 5: POOL categories with no span overlapping the
     window (gold null). Straddling categories are never asked. Keys are shuffled.
  4. Eligible contracts have at least 2 present categories. Contract type is read from the title by keyword
     (TYPES, first match; "Other" if none; the dataset has no type field). Within each type the eligible contracts
     are shuffled with random.Random(SEED); types are visited in a shuffled order, one contract per type per round,
     until N = 40.

Prompt: the window between <contract> tags with its character range, the asked categories each with the official
description (the "Details:" part of the CUAD question), and the JSON answer instruction. At most about 14k chars.

Grading follows evaluate.py of https://github.com/TheAtticusProject/cuad (the paper, Sec. 4: "We use the threshold
0.5 <= J(A, B) for determining matches", J = word-set Jaccard after removing punctuation and lower-casing):
  get_jaccard: remove . , ; : ; lower-case; "/" -> space; split into a word set; |A & B| / |A | B|.
  One difference: words are split on any whitespace (evaluate.py splits on " " only, so a quote with a line break
  re-flowed into a space would lose words). Parties' substring rule is not needed (Parties is not asked).
Per category, gold = labeled spans inside the window, pred = the non-empty quoted strings:
  gold empty: correct iff pred is empty (null, "", [], or "none"/"null"/"n/a").
  gold non-empty: correct iff pred is non-empty, every pred string matches some gold span (no false positive) and
  at least one gold span is matched. (The paper scores every span; requiring one match per category is a
  deviation, since the answer format allows one quote per clause and CUAD often labels a clause in pieces.)
Item pass = every asked category correct. score(task_id, answer) also returns per-category tp/fp/fn counted the
evaluate.py way (each gold span matched by some pred is a tp, else fn; each pred matching no gold span is a fp),
so precision/recall/F1 can be summed over items later.
"""
import json
import random
import re
from pathlib import Path

import grade

EXT = Path(__file__).resolve().parent / "ext" / "cuad"
N, K, SEED, WINDOW, MAX_PRESENT, MIN_PRESENT, IOU = 40, 5, 0, 12000, 3, 2, 0.5

POOL = ["Governing Law", "Expiration Date", "Renewal Term", "Notice Period to Terminate Renewal",
        "Termination for Convenience", "Change of Control", "Anti-Assignment", "Exclusivity", "Non-Compete",
        "No-Solicit of Employees", "Minimum Commitment", "Revenue/Profit Sharing", "License Grant",
        "IP Ownership Assignment", "Audit Rights", "Cap on Liability", "Uncapped Liability", "Liquidated Damages",
        "Warranty Duration", "Insurance", "Post-Termination Services", "Rofr/Rofo/Rofn"]

TYPES = [("Co-Branding", ("CO-BRANDING", "CO BRANDING")), ("Endorsement", ("ENDORSEMENT",)),
         ("Sponsorship", ("SPONSORSHIP",)), ("Franchise", ("FRANCHISE",)), ("Hosting", ("HOSTING",)),
         ("Joint Venture", ("JOINT VENTURE",)), ("Strategic Alliance", ("STRATEGIC ALLIANCE",)),
         ("Non-Compete", ("NON-COMPETITION", "NON COMPETITION", "NON-COMPETE")),
         ("Outsourcing", ("OUTSOURCING",)), ("Transportation", ("TRANSPORTATION",)),
         ("Manufacturing", ("MANUFACTURING",)), ("Supply", ("SUPPLY",)), ("Maintenance", ("MAINTENANCE",)),
         ("Development", ("DEVELOPMENT",)), ("Distributor", ("DISTRIBUT",)), ("Reseller", ("RESELLER", "REMARKETING")),
         ("Promotion", ("PROMOTION",)), ("Marketing", ("MARKETING",)), ("Agency", ("AGENCY",)),
         ("Consulting", ("CONSULTING",)), ("Service", ("SERVICE",)), ("Collaboration/Cooperation", ("COOPERATION", "COLLABORATION")),
         ("IP", ("INTELLECTUAL PROPERTY", "TRADEMARK")), ("License", ("LICENS",)), ("Affiliate", ("AFFILIATE",))]


def contract_type(title):
    t = title.upper()
    for name, keys in TYPES:
        if any(k in t for k in keys):
            return name
    return "Other"


# ---------------------------------------------------------------- matching (evaluate.py get_jaccard)

def _words(s):
    for tok in (".", ",", ";", ":"):
        s = s.replace(tok, "")
    return set(s.lower().replace("/", " ").split())


def jaccard(gt, pred):
    a, b = _words(gt), _words(pred)
    return len(a & b) / len(a | b) if a | b else 0.0


def _preds(value):
    """The quoted strings of one answer value; empty list for null / '' / 'none'."""
    items = value if isinstance(value, list) else [value]
    out = []
    for v in items:
        if v is None or isinstance(v, (bool, dict)):
            continue
        s = str(v).strip()
        if s and s.lower().strip(".") not in ("none", "null", "n/a", "na", "not found", "not applicable"):
            out.append(s)
    return out


def score_category(gold, value):
    preds = _preds(value)
    tp = sum(any(jaccard(g, p) >= IOU for p in preds) for g in gold)
    fp = sum(not any(jaccard(g, p) >= IOU for g in gold) for p in preds)
    correct = (not preds) if not gold else (bool(preds) and fp == 0 and tp >= 1)
    return {"correct": correct, "tp": tp, "fp": fp, "fn": len(gold) - tp, "n_gold": len(gold), "n_pred": len(preds)}


def _score(gold_map, answer):
    parsed = grade.parse_json(answer) if isinstance(answer, str) else answer
    parsed = parsed if isinstance(parsed, dict) else {}
    cats = {c: score_category(g, parsed.get(c)) for c, g in gold_map.items()}
    return {"pass": bool(parsed) and all(v["correct"] for v in cats.values()), "categories": cats}


# ---------------------------------------------------------------- items

def _spans(contract):
    """{dataset category: [(start, end, text)]} and {dataset category: description}."""
    spans, desc = {}, {}
    for q in contract["paragraphs"][0]["qas"]:
        cat = q["id"].split("__", 1)[1]
        desc[cat] = q["question"].split("Details:", 1)[1].strip()
        spans[cat] = [(a["answer_start"], a["answer_start"] + len(a["text"]), a["text"]) for a in q["answers"]]
    return spans, desc


def _classify(spans, s, e):
    """POOL categories inside / straddling / absent for the window [s, e)."""
    inside, straddle, absent = [], [], []
    for c in POOL:
        sp = spans.get(c.title(), [])
        over = [(a, b) for a, b, _ in sp if a < e and b > s]
        if any(a < s or b > e for a, b in over):
            straddle.append(c)
        elif over:
            inside.append(c)
        else:
            absent.append(c)
    return inside, straddle, absent


def best_window(text, spans):
    if len(text) <= WINDOW:
        return 0, len(text)
    best = None
    starts = [0] + [m.end() for m in re.finditer(r"\n", text)]
    for s in starts:
        if s >= len(text):
            break
        if s + WINDOW >= len(text):
            e = len(text)
        else:
            e = text.rfind("\n", s, s + WINDOW) + 1
            if e <= s:
                e = s + WINDOW
        n = len(_classify(spans, s, e)[0])
        if best is None or n > best[0]:
            best = (n, s, e)
    return best[1], best[2]


def _distinct(a, b, gold):
    return not any(jaccard(x, y) >= IOU for x in gold[a] for y in gold[b])


def build_item(contract):
    text = contract["paragraphs"][0]["context"]
    spans, desc = _spans(contract)
    s, e = best_window(text, spans)
    inside, _, absent = _classify(spans, s, e)
    gold = {c: [t for a, b, t in spans[c.title()] if a >= s and b <= e] for c in inside}
    rng = random.Random(f"{SEED}:{contract['title']}")
    present = []
    for c in rng.sample(inside, len(inside)):
        if len(present) < MAX_PRESENT and all(_distinct(c, p, gold) for p in present):
            present.append(c)
    if len(present) < MIN_PRESENT:
        return None
    asked = present + rng.sample(absent, K - len(present))
    rng.shuffle(asked)
    return {"title": contract["title"], "type": contract_type(contract["title"]), "start": s, "end": e,
            "length": len(text), "window": text[s:e], "asked": asked,
            "gold": {c: (gold[c] if c in present else []) for c in asked},
            "desc": {c: desc[c.title()] for c in asked}}


def make_prompt(item):
    cats = "\n".join(f"- {c}: {item['desc'][c]}" for c in item["asked"])
    keys = ", ".join(json.dumps(c) for c in item["asked"])
    return ("Below is part of a commercial contract filed with the SEC (characters "
            f"{item['start']:,}-{item['end']:,} of {item['length']:,}).\n\n<contract>\n{item['window']}\n</contract>\n\n"
            "A lawyer reviewing this contract wants the clauses that belong to each category below.\n"
            f"{cats}\n\n"
            "For each category, quote the clause from the contract text above exactly as written (the relevant "
            "sentence or sentences, not a whole section and not a summary). If the category appears in several "
            "separate places, give a list of quotes. If the text above has no clause for the category, give null.\n"
            f"Answer with one JSON object only, with exactly these keys: {keys}.")


def _select():
    data = json.loads((EXT / "data" / "test.json").read_text(encoding="utf-8"))["data"]
    items = [it for it in (build_item(c) for c in sorted(data, key=lambda c: c["title"])) if it]
    by_type = {}
    for it in items:
        by_type.setdefault(it["type"], []).append(it)
    rng = random.Random(SEED)
    types = sorted(by_type)
    rng.shuffle(types)
    for t in types:
        rng.shuffle(by_type[t])
    chosen = []
    while len(chosen) < N and any(by_type[t] for t in types):
        for t in types:
            if by_type[t] and len(chosen) < N:
                chosen.append(by_type[t].pop(0))
    return chosen, len(data), len(items)


def _tasks():
    chosen, _, _ = _select()
    tasks = []
    for k, it in enumerate(chosen):
        gold = it["gold"]

        def check(answer, parsed, ws, gold=gold):
            return _score(gold, parsed if parsed is not None else answer)["pass"]

        tasks.append({"id": f"cuad_{k:02d}", "split": "cuad", "domain": f"cuad/{it['type']}",
                      "prompt": make_prompt(it), "tools": "none",
                      "contract": {"type": "json", "keys": {c: "any" for c in it["asked"]}},
                      "check": check, "gold": gold, "title": it["title"]})
    return tasks


TASKS = _tasks()
_BY_ID = {t["id"]: t for t in TASKS}


def score(task_id, answer):
    """{'pass': bool, 'categories': {category: {correct, tp, fp, fn, n_gold, n_pred}}} for one answer text."""
    return _score(_BY_ID[task_id]["gold"], answer)


def _selftest():
    import statistics
    chosen, n_all, n_elig = _select()
    print(f"contracts in test split {n_all} -> eligible (>= {MIN_PRESENT} present POOL categories) {n_elig} "
          f"-> chosen {len(chosen)}")
    lens = sorted(len(t["prompt"]) for t in TASKS)
    print(f"prompt chars: min {lens[0]} median {statistics.median(lens):.0f} max {lens[-1]}")
    fails = []
    for t in TASKS:
        g = t["gold"]
        good = json.dumps({c: (v[0] if len(v) == 1 else v) if v else None for c, v in g.items()})
        if not t["check"](good, grade.parse_json(good), None):
            fails.append((t["id"], "gold"))
        if t["check"]("", None, None) or t["check"]("{}", {}, None):
            fails.append((t["id"], "empty"))
        present = [c for c, v in g.items() if v]
        absent = [c for c, v in g.items() if not v]
        a, b = present[0], present[1]
        swap = {c: (v[0] if v else None) for c, v in g.items()}
        swap[a], swap[b] = g[b][0], g[a][0]
        if t["check"](json.dumps(swap), swap, None):
            fails.append((t["id"], "swap"))
        fill = {c: (v[0] if v else None) for c, v in g.items()}
        fill[absent[0]] = g[a][0]
        if t["check"](json.dumps(fill), fill, None):
            fails.append((t["id"], "null filled"))
        drop = {c: (v[0] if v else None) for c, v in g.items()}
        drop[a] = None
        if t["check"](json.dumps(drop), drop, None):
            fails.append((t["id"], "present dropped"))
        whole = {c: t["prompt"] for c in g}
        if t["check"](json.dumps(whole), whole, None):
            fails.append((t["id"], "whole window quoted"))
    print("self-test failures:", fails or "none")
    (Path(__file__).resolve().parent / "cuad_ids.txt").write_text(
        "".join(f"{t['id']}\t{t['title']}\n" for t in TASKS), encoding="utf-8")


if __name__ == "__main__":
    _selftest()
