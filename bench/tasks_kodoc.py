"""Korean document QA from the Allganize RAG Leaderboard data (allganize/RAG-Evaluation-Dataset-KO), 60 items.

Data: https://huggingface.co/datasets/allganize/RAG-Evaluation-Dataset-KO (license: MIT on the dataset card; copied to
bench/ext/kodoc/LICENSE). rag_evaluation_result.csv has 300 questions, 60 in each of five domains (finance, public,
medical, law, commerce), each with target_answer, target_file_name, target_page_no and context_type (paragraph,
table, image; the medical domain writes "text" for paragraph). documents.csv gives each PDF's page count and a
source URL (often a landing page). The PDFs are not in the dataset; they were downloaded from those URLs (or the
same file elsewhere when a link was dead) into bench/ext/kodoc/pdf/{row:02d}.pdf (row = 0-based row of
documents.csv) and turned into per-page text by bench/kodoc_extract.py (PyMuPDF, NFC) in bench/ext/kodoc/text/.
None of this is committed. Rows 14, 25, 50, 61, 63 could not be downloaded (dead
links, no archive copy); rows 18 and 60 exist only in an edition with a different page count. Row 22 (KDCA press
release) came from KDCA's current board, rows 28, 38, 56, 57 from Wayback Machine copies of the listed URLs. The original leaderboard is a full RAG test (parse, retrieve, generate) graded by a vote
of four LLM judges; here the evidence pages are given and grading is a fixed key-fact check (below).

Selection, per domain, run at import:
  1. Questions with context_type paragraph or text (not table/image) and a target_page_no (one law question has none).
  2. Their PDF was downloaded and has the page count documents.csv states (a different page count means a different
     edition, so the page number could point elsewhere).
  3. The evidence page has extracted text with at least MIN_HANGUL Hangul syllables (no garbled or image-only page).
  4. The pool, in CSV order, is shuffled with random.Random(f"{SEED}:{domain}"), then walked in that order: an item
     is kept if it has a checklist in CHECKLIST whose facts all appear in its prompt text; otherwise it is dropped
     with the reason in DROPPED. The walk stops at N_PER = 12 kept items. Every item the walk reaches must be in
     exactly one of CHECKLIST or DROPPED (checked at import).

Prompt: the text of the evidence page and the pages before and after it (those that exist), each under a
"[p. N]" line, then the question and a one-line JSON answer instruction {"answer": "..."}. If the pages exceed
MAX_DOC characters, the neighbouring pages are cut (the earlier page from its start, the later page from its end);
the evidence page is never cut.

Grading: CHECKLIST holds, per item, 1-4 key facts taken from the gold answer only (numbers, names, dates, short
phrases), not facts that the question itself states. Each fact is a list of acceptable variants. A few facts are
computed from the page (e.g. a growth multiple from two values); they are marked "~" and DERIVED lists the source
values, which must be in the page text. Pass = every
fact has a variant present in the answer value. Matching is on normalised text: NFC, case-folded, all whitespace
removed, commas between digits removed, "퍼센트" -> "%". A variant written "#<number>" is numeric: it matches if any
number in the answer, read with Korean units (e.g. 1,000억원, 천억 원, 2억 6천만), equals it. A variant written
"re:<pattern>" is a regular expression on the normalised answer (used so that "4%" does not match inside "34%").
The checklists were written by Claude (the coding assistant) from the gold answers before any model output for this
set existed; the walk checks automatically that every fact is in the prompt text, and the 6 SPOT_CHECKED items were
also read against the evidence page by hand. Facts are short, so a long answer that happens to contain a generic
fact word (e.g. "데이터") can pass it; most items have 2-3 facts to limit this.
"""
import csv
import json
import random
import re
import unicodedata
from pathlib import Path

import grade

EXT = Path(__file__).resolve().parent / "ext" / "kodoc"
DOMAINS = ("finance", "public", "medical", "law", "commerce")
N_PER, SEED, MAX_DOC, MIN_HANGUL = 12, 0, 15000, 50

# item id -> list of facts; a fact is a list of acceptable variants
CHECKLIST = {
    # ---- finance
    "finance_003": [["본인가 요건", "본인가의 요건", "본인가 시 요건"]],
    "finance_035": [["#0.6"], ["#4.7"], ["#4.1"]],
    "finance_033": [["규모가 큰 증권부터", "큰 증권부터", "규모가 큰 순", "규모가 큰 증권 순", "규모 순", "규모순"]],
    "finance_046": [["re:(?<![\\d.])0\\.5%"], ["1년", "12개월"]],
    "finance_051": [["1961"], ["퇴직금"]],
    "finance_038": [["re:(?<![\\d.])2%"], ["3월"]],
    "finance_047": [["~", "re:(?<![\\d.])3\\.(3|29)\\d*배"], ["~", "re:(?<![\\d.])(23|22\\.[89]\\d*)배"],
                    ["~", "re:(?<![\\d.])1\\.5\\d*배"]],
    "finance_029": [["온실가스", "탄소배출", "탄소 배출"], ["6가지", "6개", "여섯", "6종"], ["모기지"], ["상업용 부동산"]],
    "finance_000": [["#100000000000"], ["#25000000000"], ["re:(?<![\\d.])4%"], ["re:(?<![\\d.])34%"]],
    "finance_036": [["#882"], ["re:(?<![\\d.])22%"]],
    "finance_039": [["호주"], ["캐나다"], ["스웨덴"]],
    "finance_041": [["불필요한 투자", "불필요한 투자를 방지", "투자를 방지"]],
    # ---- public
    "public_080": [["re:4월?(~|∼|～|-|–|부터)(20)?(23년)?8월"], ["9월1일", "9.1", "9/1"]],
    "public_093": [["#2496"], ["8차"], ["민주화운동기념관"]],
    "public_091": [["#7172"], ["1만", "#10000"], ["#2000000"]],
    "public_086": [["#20000000"], ["법인"], ["거주지"]],
    "public_092": [["re:(2023년|'23\\.?|’23\\.?|23년)?12월|'23\\.12|’23\\.12"], ["추석"]],
    "public_107": [["인도"], ["E-7"]],
    "public_081": [["중장기 재무관리계획"], ["국회"]],
    "public_089": [["#110"], ["2026", "'26", "’26", "26년"]],
    "public_103": [["10.5조"], ["4개", "4곳", "네 개"], ["하나금융"]],
    "public_094": [["#5.5"], ["#39.9"], ["re:(?<![\\d.])3%"]],
    "public_095": [["대출"], ["독서공간", "독서 공간"], ["미래형"]],
    "public_097": [["텍사스"], ["STAAR", "학업성취도"], ["진단검사", "진단 검사", "진단평가"]],
    # ---- medical
    "medical_144": [["눈물결핍", "눈물 결핍", "눈물 분비 부족", "눈물분비부족", "aqueous tear deficiency", "수성눈물결핍"],
                    ["증발"]],
    "medical_149": [["44주"], ["#28.3"]],
    "medical_171": [["2년"], ["#96"], ["#71"]],
    "medical_173": [["손상"], ["re:80%?(~|∼|-|–|～|에서)90%"], ["재발"]],
    "medical_168": [["고리", "올가미", "스네어", "snare"], ["칼", "나이프", "knife"]],
    "medical_155": [["대장내시경"], ["혈액", "피"]],
    "medical_146": [["re:(?<![\\d.])20명"]],
    "medical_152": [["#214.1"], ["#361.9"]],
    "medical_148": [["re:(?<![\\d.])50명"], ["re:(?<![\\d.])30명"]],
    "medical_178": [["PPI", "양성자"], ["H2RA", "H2 수용체", "H2수용체", "히스타민"]],
    "medical_172": [["내시경"], ["복강경"]],
    "medical_166": [["1cm", "1 센티", "10mm", "1센티"], ["3개", "세 개"], ["톱니"]],
    # ---- law
    "law_207": [["부분품"], ["원재료"], ["구현"]],
    "law_227": [["기각"], ["상고"]],
    "law_208": [["노하우"], ["영업비밀"], ["디자인"]],
    "law_228": [["관통"], ["기름배출공"]],
    "law_195": [["5년"], ["#10000000"]],
    "law_212": [["re:2022(\\.|년|-)0?1(\\.|월|-)28"], ["re:2023(\\.|년|-)0?1(\\.|월|-)12"], ["기각"]],
    "law_193": [["금고 이상", "금고이상"], ["고의"]],
    "law_190": [["2012"], ["5월"], ["영입"]],
    "law_186": [["위해"], ["거래조건", "거래방법"], ["정확"], ["배상"]],
    "law_192": [["기여금"], ["불성실"]],
    "law_196": [["대화의 내용", "대화 내용"], ["장소"], ["종합"]],
    "law_187": [["불균형", "비대칭"], ["제조업자", "제조사", "제조자"]],
    # ---- commerce
    "commerce_275": [["SaaS"], ["데이터"]],
    "commerce_265": [["후기"], ["프로모션", "할인", "1+1"], ["온라인 쇼핑몰", "쇼핑몰"]],
    "commerce_249": [["퍼스트파티", "퍼스트 파티", "1st party", "1st-party", "first-party", "first party", "자사 데이터"],
                     ["서드파티", "써드파티", "3rd party", "3rd-party", "third-party", "third party", "제3자"]],
    "commerce_241": [["코로나"], ["러시아", "우크라이나"], ["빅스텝", "금리"]],
    "commerce_262": [["라스트마일", "라스트 마일", "last mile", "last-mile"], ["lock-in", "락인", "록인", "유입"]],
    "commerce_240": [["체리슈머", "cherrysumer"]],
    "commerce_242": [["re:(?<![\\d.])20%"], ["간편결제", "간편 결제"], ["배송"]],
    "commerce_267": [["네이버"], ["포털"]],
    "commerce_289": [["Watch Together"], ["채팅"]],
    "commerce_250": [["4.8배"]],
    "commerce_290": [["saks", "삭스"], ["소매점", "매장", "리테일"]],
    "commerce_279": [["상담"], ["예약"], ["구매"]],
}

# item id -> facts the answer is computed from; they must be in the document text (the computed facts in CHECKLIST,
# marked by a first variant "~", are not)
DERIVED = {
    "finance_047": [["850억"], ["2,800억"], ["65억"], ["1,486억"], ["480억"], ["720억"]],
}

# item id -> reason it was dropped during the walk
DROPPED = {
    "medical_145": "extraction: the PDF's text layer splits numbers with spaces ('6 2 . 5 %', '1 6예'), so the gold "
                   "numbers are not readable as written",
}

SPOT_CHECKED = ["finance_035", "finance_047", "public_080", "public_092", "public_093", "public_095"]


# ---------------------------------------------------------------- matching

_SMALL = {"천": 1000, "백": 100, "십": 10}
_BIG = {"조": 10 ** 12, "억": 10 ** 8, "만": 10 ** 4}


def norm(s):
    s = unicodedata.normalize("NFC", str(s if s is not None else "")).casefold()
    s = s.replace("퍼센트", "%")
    s = re.sub(r"\s+", "", s)
    return re.sub(r"(?<=\d),(?=\d)", "", s)


def _korean_number(tok):
    """'1000억' -> 1e11, '2억6천만' -> 260000000, '천억' -> 1e11, '3.5' -> 3.5."""
    total, section, cur = 0, 0, None
    for m in re.finditer(r"\d+(?:\.\d+)?|[조억만천백십]", tok):
        t = m.group()
        if t[0].isdigit():
            cur = float(t)
        elif t in _SMALL:
            section += (1 if cur is None else cur) * _SMALL[t]
            cur = None
        else:
            section += 0 if cur is None else cur
            total += (section or 1) * _BIG[t]
            section, cur = 0, None
    return total + section + (0 if cur is None else cur)


def numbers(text):
    """Every number written in the text, with Korean units read. Spaces split numbers, except between a digit and a unit."""
    s = unicodedata.normalize("NFC", str(text if text is not None else ""))
    s = re.sub(r"(?<=\d),(?=\d{3})", "", s)
    s = re.sub(r"(?<=\d)\s+(?=[조억만천백십])", "", s)                              # 1000 억
    for big, smaller in (("조", "억만천백십"), ("억", "만천백십"), ("만", "천백십")):               # 2억 6천만
        s = re.sub(rf"(?<={big})\s+(?=\d+(?:\.\d+)?[{smaller}])", "", s)
    out = []
    for m in re.finditer(r"(?:\d+(?:\.\d+)?|[천백십])(?:[조억만천백십]|\d+(?:\.\d+)?)*", s):
        tok = m.group()
        if not re.search(r"\d", tok) and not re.search(r"[조억만]", tok):
            continue
        try:
            out.append(_korean_number(tok))
        except (ValueError, KeyError):
            pass
    return out


def fact_ok(fact, answer):
    a = norm(answer)
    nums = None
    for v in fact:
        if v == "~":
            continue
        if v.startswith("#"):
            nums = numbers(answer) if nums is None else nums
            if any(abs(x - float(v[1:])) < 1e-9 * max(1.0, abs(x)) for x in nums):
                return True
        elif v.startswith("re:"):
            if re.search(v[3:], a):
                return True
        elif norm(v) in a:
            return True
    return False


def passes(facts, answer):
    return bool(answer) and all(fact_ok(f, answer) for f in facts)


# ---------------------------------------------------------------- items

def _load():
    docs = list(csv.DictReader((EXT / "documents.csv").open(encoding="utf-8")))
    row_of = {(d["domain"], d["file_name"]): i for i, d in enumerate(docs)}
    qs = list(csv.DictReader((EXT / "rag_evaluation_result.csv").open(encoding="utf-8")))
    return docs, row_of, qs


def _pages(row):
    p = EXT / "text" / f"{row:02d}.json"
    if not p.exists():
        return None
    t = json.loads(p.read_text(encoding="utf-8"))
    return t["pages"] if len(t["pages"]) == t["pages_expected"] else None


def make_doc(pages, page):
    """Evidence page `page` (1-based) with its neighbours, cut to MAX_DOC characters."""
    lo, hi = max(1, page - 1), min(len(pages), page + 1)
    parts = {k: pages[k - 1].strip() for k in range(lo, hi + 1)}
    over = sum(len(v) for v in parts.values()) - MAX_DOC
    if over > 0:
        sides = [k for k in (page - 1, page + 1) if k in parts]
        for k in sides:
            cut = min(len(parts[k]), -(-over // len(sides)))
            parts[k] = parts[k][cut:] if k < page else parts[k][:len(parts[k]) - cut]
    return "\n\n".join(f"[p. {k}]\n{v}" for k, v in parts.items())


def make_prompt(doc, question):
    return ("다음은 PDF 문서에서 뽑은 본문입니다(쪽 번호 표시).\n\n<document>\n" + doc + "\n</document>\n\n"
            f"질문: {question}\n\n"
            '위 문서를 근거로 답하세요. 답은 다른 설명 없이 JSON 한 줄로만 주세요: {"answer": "답"}')


def walk():
    """Per domain: (pool sizes after each filter, the walk as a list of (item id, question row, prompt))."""
    docs, row_of, qs = _load()
    out = {}
    for dom in DOMAINS:
        sizes, pool = {}, []
        typed = [(k, q) for k, q in enumerate(qs) if q["domain"] == dom and q["context_type"] in ("paragraph", "text")]
        sizes["paragraph/text"] = len(typed)
        typed = [(k, q) for k, q in typed if q["target_page_no"].strip().isdigit()]
        sizes["page no. given"] = len(typed)
        have = [(k, q, _pages(row_of[(dom, q["target_file_name"])])) for k, q in typed]
        have = [(k, q, p) for k, q, p in have if p is not None]
        sizes["pdf ok"] = len(have)
        for k, q, p in have:
            page = int(q["target_page_no"])
            if 1 <= page <= len(p) and len(re.findall("[가-힣]", p[page - 1])) >= MIN_HANGUL:
                pool.append((f"{dom}_{k:03d}", q, make_prompt(make_doc(p, page), q["question"])))
        sizes["page text ok"] = len(pool)
        random.Random(f"{SEED}:{dom}").shuffle(pool)
        out[dom] = (sizes, pool)
    return out


def _tasks():
    tasks, problems, stats = [], [], {}
    for dom, (sizes, pool) in walk().items():
        kept, walked, dropped = 0, 0, []
        for iid, q, prompt in pool:
            if kept == N_PER:
                break
            walked += 1
            if iid in DROPPED:
                dropped.append(iid)
                continue
            facts = CHECKLIST.get(iid)
            if facts is None:
                problems.append(f"{iid}: no checklist and not dropped")
                continue
            doc = prompt.split("</document>")[0]
            missing = [f for f in facts + DERIVED.get(iid, []) if f[0] != "~" and not fact_ok(f, doc)]
            if missing:
                problems.append(f"{iid}: facts not in the document text: {missing}")
                continue

            def check(answer, parsed, ws, facts=facts):
                value = parsed.get("answer") if isinstance(parsed, dict) else None
                return isinstance(value, (str, int, float)) and not isinstance(value, bool) and passes(facts, str(value))

            tasks.append({"id": f"kodoc_{iid}", "split": "kodoc", "domain": f"kodoc/{dom}", "prompt": prompt,
                          "tools": "none", "contract": {"type": "json", "keys": {"answer": "str"}}, "check": check,
                          "facts": facts, "gold": q["target_answer"]})
            kept += 1
        stats[dom] = dict(sizes, walked=walked, dropped=len(dropped), kept=kept)
    return tasks, problems, stats


TASKS, PROBLEMS, STATS = _tasks()


def _selftest():
    import statistics
    for dom, st in STATS.items():
        print(f"{dom:9s} " + ", ".join(f"{k} {v}" for k, v in st.items()))
    lens = sorted(len(t["prompt"]) for t in TASKS)
    print(f"items {len(TASKS)}; prompt chars: min {lens[0]} median {statistics.median(lens):.0f} max {lens[-1]}")
    print("facts per item:", {k: sum(len(t['facts']) == k for t in TASKS) for k in range(1, 5)})
    fails = list(PROBLEMS)
    for t in TASKS:
        def ok(v):
            return t["check"](json.dumps({"answer": v}, ensure_ascii=False), {"answer": v}, None)
        if not ok(t["gold"]) and not any(f[0] == "~" for f in t["facts"]):
            fails.append((t["id"], "gold answer fails"))
        if ok("") or t["check"]("", None, None) or ok(None):
            fails.append((t["id"], "empty passes"))
        if ok(t["prompt"].split("질문:")[1]):
            fails.append((t["id"], "question echo passes"))
        # perturb: shift every digit of the gold answer by one and delete the first fact's text variants
        g = t["gold"]
        bad = re.sub(r"\d", lambda m: str((int(m.group()) + 1) % 10), g) if re.search(r"\d", g) else g
        for v in t["facts"][0]:
            if not v.startswith(("#", "re:", "~")):
                bad = re.sub(r"\s*".join(map(re.escape, re.sub(r"\s+", "", v))), "", bad, flags=re.I)
        if ok(bad):
            fails.append((t["id"], "perturbed gold passes"))
    print("self-test failures:", fails or "none")
    (Path(__file__).resolve().parent / "kodoc_ids.txt").write_text("".join(t["id"] + "\n" for t in TASKS),
                                                                    encoding="utf-8")


if __name__ == "__main__":
    _selftest()
