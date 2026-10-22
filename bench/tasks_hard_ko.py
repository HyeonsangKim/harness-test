"""Hard Korean office tasks: long tables, several tables to join, multi-step rules with exceptions, mess.

Sixty tasks across 회계, 인사·급여, 구매·재고, 영업, 총무, 법무. Each prompt embeds 100-500 data rows
(one or more tables, mixed formats), states every rule it needs, and asks for one JSON line with 1-4
keys. Data comes from random.Random(seed) per task. Ground truth is computed by a solver that reads
the rows as they appear in the prompt (duplicates, memo lines, subtotal rows, mixed units included)
and applies the stated rules; every rendered amount and date is round-trip checked against its parser.
SELFTEST holds, per task, the oracle answer and "plausible wrong" answers (rule skipped, wrong unit,
exception missed). META holds rows/tables/rule steps/mess types. Run this file to self-check.
Standard library only. No tools.
"""
import csv as _d_csv
import random
import re
from datetime import date, timedelta
from fractions import Fraction as _F

import grade

JSON_RULE = "답은 다른 설명 없이 JSON 한 줄로만 주세요: "

TASKS = []
SELFTEST = {}
META = {}

# ================================================================= checking


def _norm(s):
    s = str(s if s is not None else "")
    for t in ("주식회사", "(주)", "㈜", "（주）"):
        s = s.replace(t, "")
    return re.sub(r"\s+", "", s).lower()


def _get(p, k):
    return p.get(k) if isinstance(p, dict) else None


def _match(kind, got, exp, tol):
    if kind == "int":
        v = grade.num(got)
        return v is not None and not isinstance(v, float) and v == exp
    if kind == "float":
        v = grade.num(got)
        return v is not None and abs(float(v) - float(exp)) <= tol + 1e-9
    if kind == "str":
        return isinstance(got, (str, int)) and _norm(got) == _norm(exp)
    if kind == "list":
        if not isinstance(got, list) or len(got) != len(exp):
            return False
        for g, e in zip(got, exp):
            if isinstance(e, (int, float)) and not isinstance(e, bool):
                v = grade.num(g)
                if v is None or abs(float(v) - float(e)) > (tol or 0) + 1e-9:
                    return False
            elif _norm(g) != _norm(e):
                return False
        return True
    raise ValueError(kind)


def _make_check(keys, truth, tol):
    def check(answer, parsed, ws):
        if not isinstance(parsed, dict):
            return False
        try:
            return all(_match(kind, _get(parsed, k), truth[k], tol.get(k, 0)) for k, kind in keys.items())
        except Exception:
            return False
    return check


def _add(n, domain, prompt, keys, truth, wrong, meta, tol=None):
    """Register task hk_<n>. truth: solver answer. wrong: list of plausible wrong answer dicts.
    meta: {"rows": int, "tables": int, "steps": int, "mess": [str, ...]}. tol: {key: abs tolerance} for floats."""
    tid = f"hk_{n:02d}"
    tol = tol or {}
    assert 1 <= len(keys) <= 4 and set(keys) == set(truth), tid
    assert len(prompt) <= 25000, (tid, len(prompt))
    assert len(wrong) >= 2, tid
    TASKS.append(dict(id=tid, split="hard_ko", domain=domain, prompt=prompt, tools="none",
                      contract={"type": "json", "keys": dict(keys)}, check=_make_check(keys, truth, tol)))
    SELFTEST[tid] = {"oracle": dict(truth), "wrong": [dict(w) for w in wrong]}
    META[tid] = dict(meta, chars=len(prompt))


def _argmax(d):
    items = sorted(d.items(), key=lambda x: -x[1])
    assert len(items) < 2 or items[0][1] != items[1][1], "tie"
    return items[0]


def _argmin(d):
    items = sorted(d.items(), key=lambda x: x[1])
    assert len(items) < 2 or items[0][1] != items[1][1], "tie"
    return items[0]


def _floor10(x):
    """원 단위 절사: 10원 미만 버림 (x >= 0)."""
    return int(x) // 10 * 10


def _rhalf(x, nd=0):
    """사사오입(반올림, .5는 올림). Avoids banker's rounding of round()."""
    m = 10 ** nd
    v = int(abs(x) * m + 0.5 + 1e-9) / m
    v = v if x >= 0 else -v
    return int(v) if nd == 0 else v


# ================================================================= amounts


def _k4(x, words):
    """1..9999 -> '3천2백50' (words) or '3,250'."""
    if not words:
        return f"{x:,}"
    s = ""
    if x // 1000:
        s += f"{x // 1000}천"
    if x // 100 % 10:
        s += f"{x // 100 % 10}백"
    if x % 100:
        s += str(x % 100)
    return s


def _ko(n, rng, won="원"):
    """320000000 -> '3억 2천만원' / '3억2,000만원', digits and Korean units mixed."""
    groups = ((n // 10**8, "억"), (n // 10**4 % 10**4, "만"), (n % 10**4, ""))
    parts = []
    for g, u in groups:
        if g:
            parts.append(_k4(g, rng.random() < 0.5) + u)
    sep = rng.choice(["", " "])
    return sep.join(parts) + won


_HD = "영일이삼사오육칠팔구"


def _h4(x):
    s = ""
    for unit, val in (("천", 1000), ("백", 100), ("십", 10), ("", 1)):
        d = x // val % 10
        if d:
            s += ("" if d == 1 and unit else _HD[d]) + unit
    return s


def _hangul(n, won="원"):
    """123000000 -> '일억이천삼백만원'."""
    eok, man, rest = n // 10**8, n // 10**4 % 10**4, n % 10**4
    s = ""
    if eok:
        s += ("일" if eok == 1 else _h4(eok)) + "억"
    if man:
        s += ("일" if man == 1 else _h4(man)) + "만"
    if rest:
        s += _h4(rest)
    return s + won


def _parse_k4(s):
    """'3천2백50' / '3,250' / '삼천이백오십' -> 3250."""
    s = s.replace(",", "").strip()
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    total, cur = 0, ""
    for ch in s:
        if ch.isdigit():
            cur += ch
        elif ch in _HD:
            cur = str(_HD.index(ch))
        elif ch in "천백십":
            total += (int(cur) if cur else 1) * {"천": 1000, "백": 100, "십": 10}[ch]
            cur = ""
        else:
            raise ValueError(s)
    return total + (int(cur) if cur else 0)


def _parse_amt(s):
    """Parse every amount style _amt renders, back to won (int). Raises on anything else."""
    t = str(s).strip().replace(" ", "")
    neg = t.startswith("-") or t.startswith("△") or t.startswith("▲") or (t.startswith("(") and t.endswith(")"))
    t = t.strip("-△▲()").replace("₩", "").replace("KRW", "")
    if t.endswith("원"):
        t = t[:-1]
    m = re.fullmatch(r"([\d,]+(?:\.\d+)?)(천|만|백만|억)?", t)
    if m:
        mul = {None: 1, "천": 1000, "만": 10**4, "백만": 10**6, "억": 10**8}[m.group(2)]
        v = float(m.group(1).replace(",", "")) * mul
        assert abs(v - round(v)) < 1e-6, s
        v = int(round(v))
    else:
        v, rest = 0, t
        for unit, mul in (("억", 10**8), ("만", 10**4)):
            if unit in rest:
                a, rest = rest.split(unit, 1)
                v += (_parse_k4(a) if a else 1) * mul
        v += _parse_k4(rest)
    return -v if neg else v


AMT_STYLES = ("plain", "won", "krw", "chun", "man", "ko", "hangul")


def _amt(n, style, rng=None):
    """Render won amount n in a pasted style; asserts it parses back exactly.
    plain '1,234,000'  won '1,234,000원'  krw '₩1,234,000'  chun '1,234천원'  man '123.4만원'
    ko '1억2,340만원'/'1억 2천3백40만원'  hangul '일억이천삼백사십만원'  neg: '-' prefix."""
    rng = rng or random.Random(n)
    a = abs(n)
    if style == "plain":
        s = f"{a:,}"
    elif style == "won":
        s = f"{a:,}원"
    elif style == "krw":
        s = f"₩{a:,}"
    elif style == "chun":
        assert a % 1000 == 0, (n, style)
        s = f"{a // 1000:,}천원"
    elif style == "man":
        assert a % 1000 == 0, (n, style)
        q = a / 10**4
        s = (f"{a // 10**4:,}" if a % 10**4 == 0 else f"{q:,.1f}") + "만원"
    elif style == "ko":
        s = _ko(a, rng)
    elif style == "hangul":
        s = _hangul(a)
    else:
        raise ValueError(style)
    s = ("-" + s) if n < 0 else s
    assert _parse_amt(s) == n, (n, style, s)
    return s


# ================================================================= dates

DATE_STYLES = ("iso", "dot", "dots", "slash", "compact", "kor")


def _dt(d, style):
    """iso 2026-03-05 / dot 2026.03.05 / dots 2026.3.5 / slash 2026/03/05 / compact 20260305 / kor 2026년 3월 5일
    / md 3/5 (year must be stated in the prompt) / mdk 3월 5일."""
    s = {"iso": f"{d:%Y-%m-%d}", "dot": f"{d:%Y.%m.%d}", "dots": f"{d.year}.{d.month}.{d.day}",
         "slash": f"{d:%Y/%m/%d}", "compact": f"{d:%Y%m%d}", "kor": f"{d.year}년 {d.month}월 {d.day}일",
         "md": f"{d.month}/{d.day}", "mdk": f"{d.month}월 {d.day}일"}[style]
    assert _parse_dt(s, d.year) == d, (d, style, s)
    return s


def _parse_dt(s, year=None):
    s = s.strip()
    m = re.fullmatch(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})\.?", s) or re.fullmatch(r"(\d{4})(\d{2})(\d{2})", s) \
        or re.fullmatch(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", s) or re.fullmatch(r"(\d{1,2})월\s*(\d{1,2})일", s)
    if m and year:
        return date(year, int(m.group(1)), int(m.group(2)))
    raise ValueError(s)


def _days(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# 2026 공휴일 (prompts that need holidays list them explicitly; this is just the generator's list).
HOLIDAYS_2026 = [date(2026, 1, 1), date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18), date(2026, 3, 2),
                 date(2026, 5, 5), date(2026, 5, 25), date(2026, 6, 3), date(2026, 8, 17), date(2026, 9, 24),
                 date(2026, 9, 25), date(2026, 9, 26), date(2026, 10, 5), date(2026, 10, 9), date(2026, 12, 25)]


def _is_biz(d, hol):
    return d.weekday() < 5 and d not in hol


def _add_biz(d, n, hol):
    """n business days after d (d itself not counted)."""
    while n > 0:
        d += timedelta(days=1)
        if _is_biz(d, hol):
            n -= 1
    return d


# ================================================================= names and rendering

PEOPLE = ["김민수", "이서연", "박지훈", "최유진", "정다은", "강현우", "조수아", "윤도현", "장하린", "임재원",
          "한소희", "오세훈", "서지민", "신동욱", "권나래", "황보람", "안태준", "송예린", "류건우", "배수빈",
          "문가영", "남궁현", "제갈민", "백승호", "유하늘", "노은지", "하준서", "곽민재", "성유리", "탁재훈",
          "전소미", "홍길동", "구본혁", "엄지원", "채수빈", "차은우", "주현영", "우도윤", "명세빈", "변우석"]

COMPANIES = ["한빛상사", "대성산업", "미래테크", "동양물산", "세진전자", "청솔유통", "태영정밀", "우리식품", "가람물류",
             "누리소프트", "새한화학", "보람기계", "한결건설", "다온상회", "초록에너지", "신성금속", "정우플라스틱",
             "하나포장", "온누리무역", "백두철강"]

LATIN_CO = ["Acme Supply", "Blue Ocean Ltd", "Nordic Parts", "Sunrise Trading", "Kobe Metals", "Pacific Freight",
            "Delta Components", "Orion Labs"]


def _co_var(name, rng):
    """Company name as people type it: (주)/㈜/주식회사 prefix or suffix, inner space, case."""
    v = rng.randrange(7)
    if re.fullmatch(r"[A-Za-z .]+", name):
        return [name, name.upper(), name.lower(), " " + name, name + " ", name.replace(" ", "  "), name][v]
    return [name, f"(주){name}", f"㈜{name}", f"{name} 주식회사", f"주식회사 {name}",
            name[:2] + " " + name[2:], f" {name}"][v]


def _person_var(name, rng):
    v = rng.randrange(4)
    return [name, name[0] + " " + name[1:], " " + name, name + " "][v]


def _tsv(header, rows):
    return "\n".join("\t".join(str(c) for c in r) for r in [header] + list(rows))


def _csv_cell(c):
    c = str(c)
    return '"' + c.replace('"', '""') + '"' if ("," in c or '"' in c) else c


def _csv(header, rows):
    return "\n".join(",".join(_csv_cell(c) for c in r) for r in [header] + list(rows))


def _md(header, rows):
    out = ["| " + " | ".join(str(h) for h in header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _eun(word):
    """Topic particle 은/는."""
    w = re.sub(r"\([^)]*\)$", "", word.strip()) or word
    ch = w[-1]
    if "가" <= ch <= "힣":
        final = (ord(ch) - 0xAC00) % 28 != 0
    elif ch.isdigit():
        final = ch in "013678"
    else:
        final = ch.upper() in "LMNR"
    return word + ("은" if final else "는")


# ================================================================= part A: 회계 (hk_01-hk_10), 인사·급여 (hk_11-hk_15)


def _a_wrongs(solve, truth, *flagsets):
    out = []
    for f in flagsets:
        w = solve(**f)
        assert w != truth, f
        out.append(w)
    return out


def _a_fx(s):
    """'12,345.67' -> 1234567 (cents)."""
    return int(round(float(s.replace(",", "")) * 100))


def _a_cells(block, sep="\t"):
    return [ln.split(sep) for ln in block.split("\n")[1:]]


def _a_csv_rows(block):
    out = []
    for ln in block.split("\n")[1:]:
        row, cur, q, i = [], "", False, 0
        while i < len(ln):
            ch = ln[i]
            if q:
                if ch == '"' and i + 1 < len(ln) and ln[i + 1] == '"':
                    cur += '"'
                    i += 1
                elif ch == '"':
                    q = False
                else:
                    cur += ch
            elif ch == '"':
                q = True
            elif ch == ",":
                row.append(cur)
                cur = ""
            else:
                cur += ch
            i += 1
        row.append(cur)
        out.append(row)
    return out


def _a_md_rows(block):
    return [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in block.split("\n")[2:]]


def _a_shuffle_insert(rng, lines, extra):
    """Insert extra lines at random positions (after index 0) deterministically."""
    lines = list(lines)
    for e in extra:
        lines.insert(rng.randrange(1, len(lines) + 1), e)
    return lines


# ----------------------------------------------------------------- hk_01 외화 매입 전표 원화 환산


def _hk01():
    rng = random.Random(1001)
    vend = [("Acme Supply", "미국", "USD"), ("Blue Ocean Ltd", "싱가포르", "USD"), ("Sunrise Trading", "미국", "USD"),
            ("Kobe Metals", "일본", "JPY"), ("Pacific Freight", "미국", "USD"), ("Delta Components", "독일", "EUR"),
            ("Orion Labs", "프랑스", "EUR"), ("Tokyo Seiki", "일본", "JPY"), ("Berlin Tools", "독일", "EUR"),
            ("Lyon Chimie", "프랑스", "EUR"), ("Osaka Denki", "일본", "JPY"), ("Nordic Parts", "미국", "USD")]
    master = []
    for nm, ct, cu in vend:
        if nm == "Nordic Parts":
            master.append((nm, "스웨덴", "EUR", date(2025, 11, 2)))
        master.append((nm, ct, cu, date(2025, rng.randrange(1, 13), rng.randrange(1, 28))
                       if nm != "Nordic Parts" else date(2026, 2, 10)))
    m_tbl = _md(["거래처명", "국가", "결제통화", "수정일"], [(a, b, c, _dt(d, "iso")) for a, b, c, d in master])
    hol = {date(2026, 3, 2)}
    rdays = [d for d in _days(date(2026, 2, 23), date(2026, 3, 31)) if _is_biz(d, hol)]
    rate, cur = {}, {"USD": 145230, "EUR": 158110, "JPY": 96840}
    for d in rdays:
        cur = {k: v + rng.randrange(-600, 601) for k, v in cur.items()}
        rate[d] = dict(cur)
    r_tbl = _csv(["고시일", "USD", "EUR", "JPY(100엔)"],
                 [(_dt(d, "iso"), *(f"{rate[d][k] / 100:,.2f}" for k in ("USD", "EUR", "JPY"))) for d in rdays])
    curmap = {nm: cu for nm, _, cu in vend}
    vouchers = []
    for i in range(168):
        nm = vend[rng.randrange(len(vend))][0]
        d = date(2026, 2, 25) + timedelta(days=rng.randrange(0, 35))
        c = curmap[nm]
        amt = f"{rng.randrange(50, 3000) * 1000:,}" if c == "JPY" else f"{rng.randrange(30000, 3000000) / 100:,.2f}"
        memo = rng.choice(["원자재", "부품", "운송료", "샘플", "", "금형", "포장재"])
        vouchers.append([f"FV-{3001 + i}", _dt(d, rng.choice(DATE_STYLES)), _co_var(nm, rng), amt, memo])
    lines = ["\t".join(v) for v in vouchers]
    dups = rng.sample(range(len(lines)), 6)
    cancels = rng.sample([i for i in range(len(vouchers)) if i not in dups], 4)
    extra = [lines[i] for i in dups]
    extra += [f"※ {vouchers[i][0]} 반품으로 전표 취소" for i in cancels]
    extra += ["3월 1~15일 소계\t\t\t" + f"{rng.randrange(10**6, 10**7):,}.00\t(시스템 자동 합산)"]
    lines = _a_shuffle_insert(rng, lines, extra)
    v_tbl = "\n".join(["전표번호\t거래일\t거래처\t외화금액\t적요"] + lines)

    def solve(dedupe=True, cancel=True, latest=True, jpy100=True, prev=True):
        mrows = _a_md_rows(m_tbl)
        mm = {}
        for nm, ct, cu, md in mrows:
            k = _norm(nm)
            d = _parse_dt(md)
            if k not in mm or (latest and d > mm[k][2]):
                mm[k] = (nm, cu, d)
        rates = {}
        for r in _a_csv_rows(r_tbl):
            rates[_parse_dt(r[0])] = {"USD": _a_fx(r[1]), "EUR": _a_fx(r[2]), "JPY": _a_fx(r[3])}
        rds = sorted(rates)
        rows, seen, canc = [], set(), set()
        for c in _a_cells(v_tbl):
            if c[0].startswith("※"):
                canc.add(re.search(r"FV-\d+", c[0]).group())
                continue
            if "소계" in c[0]:
                continue
            if dedupe and c[0] in seen:
                continue
            seen.add(c[0])
            rows.append(c)
        tot, by, usd = 0, {}, 0
        for no, ds, vn, amt, _ in rows:
            d = _parse_dt(ds)
            if d.month != 3 or (cancel and no in canc):
                continue
            nm, cu, _ = mm[_norm(vn)]
            if prev:
                rd = max(x for x in rds if x <= d)
            else:
                rd = min(x for x in rds if x >= d)
            rt = rates[rd][cu]
            if cu == "JPY":
                y = int(amt.replace(",", ""))
                krw = y * rt // 10000 if jpy100 else y * rt // 100
            else:
                krw = _a_fx(amt) * rt // 10000
            tot += krw
            by[nm] = by.get(nm, 0) + krw
            usd += cu == "USD"
        return {"total_krw": tot, "top_vendor": _argmax(by)[0], "usd_count": usd}

    truth = solve()
    wrong = _a_wrongs(solve, truth, {"dedupe": False}, {"cancel": False}, {"latest": False},
                      {"jpy100": False}, {"prev": False})
    prompt = ("해외 매입 전표를 원화로 환산해서 3월 수입 매입액을 확정하려고 합니다. ERP 전표 목록(탭 구분), 거래처 마스터(마크다운 표), "
              "외환 고시 환율표(CSV) 세 가지를 붙입니다. 전표에는 통화가 없고, 통화는 거래처 마스터의 결제통화를 따릅니다.\n\n"
              "[전표 목록]\n" + v_tbl + "\n\n[거래처 마스터]\n" + m_tbl + "\n\n[고시 환율표] (USD·EUR는 1단위당 원, JPY는 100엔당 원)\n"
              + r_tbl + "\n\n규칙:\n"
              "1. 거래일이 2026년 3월(3/1~3/31)인 전표만 집계합니다. 거래일 표기 형식은 섞여 있습니다.\n"
              "2. 같은 전표번호가 두 번 이상 나오면 중복 전송된 것이니 한 번만 셉니다.\n"
              "3. '※ ... 취소' 메모 줄에 적힌 전표번호는 집계에서 뺍니다. '소계' 줄은 자동 합산 줄이라 무시합니다.\n"
              "4. 거래처명은 (주)·공백·대소문자 차이를 무시하고 마스터와 맞춥니다. 마스터에 같은 거래처가 두 줄 있으면 수정일이 늦은 줄을 따릅니다.\n"
              "5. 환율은 거래일의 고시 환율을 씁니다. 거래일이 환율표에 없으면(주말·공휴일) 거래일보다 앞선 가장 가까운 고시일의 환율을 씁니다.\n"
              "6. JPY는 100엔당 환율이므로 원화 = 엔화 금액 ÷ 100 × 환율입니다.\n"
              "7. 전표별 원화 금액은 원 미만을 버린 뒤 합산합니다.\n\n"
              "3월 원화 환산 매입 합계, 3월 원화 합계가 가장 큰 거래처(마스터 표기), 3월에 집계된 USD 결제 전표 수를 알려주세요. "
              + JSON_RULE + '{"total_krw": 원(정수), "top_vendor": 거래처명, "usd_count": 건수(정수)}')
    _add(1, "acct_fx", prompt, {"total_krw": "int", "top_vendor": "str", "usd_count": "int"}, truth, wrong,
         {"rows": len(vouchers) + len(master) + len(rdays), "tables": 3, "steps": 7,
          "mess": ["duplicates", "memo_cancel", "subtotal", "date_formats", "name_variants", "contradiction_master"]})


# ----------------------------------------------------------------- hk_02 1분기 부가세


def _hk02():
    rng = random.Random(1002)
    items = [("사무용가구", "과세"), ("노트북", "과세"), ("포장재", "과세"), ("소프트웨어 라이선스", "과세"), ("생수", "과세"),
             ("승용차(비영업용)", "과세·불공제"), ("접대용 선물세트", "과세·불공제"), ("쌀", "면세"), ("신선채소", "면세"),
             ("도서", "면세"), ("수산물", "면세"), ("교육용역", "면세"), ("수출용부품", "영세율"), ("수출 완제품", "영세율")]
    kind = dict(items)
    i_tbl = _md(["품목", "과세유형"], items)
    sales_items = ["사무용가구", "노트북", "포장재", "소프트웨어 라이선스", "쌀", "도서", "수출용부품", "수출 완제품", "신선채소"]
    buy_items = [x for x, _ in items if x not in ("수출 완제품",)]
    rows = []
    n = 0
    for _ in range(232):
        n += 1
        sale = rng.random() < 0.55
        it = rng.choice(sales_items if sale else buy_items)
        sup = rng.randrange(20, 3000) * 1000 if sale else rng.randrange(10, 1500) * 1000
        if rng.random() < 0.03:
            d = date(2026, 4, rng.randrange(1, 15))
        else:
            d = date(2026, 1, 1) + timedelta(days=rng.randrange(0, 90))
        ev = "세금계산서" if sale else rng.choices(["세금계산서", "카드", "없음"], [6, 3, 1])[0]
        tax = sup // 10 if kind[it].startswith("과세") else 0
        incl = rng.random() < 0.12 and kind[it].startswith("과세")
        rows.append(dict(no=f"T{26000 + n}", d=d, g="매출" if sale else "매입", co=rng.choice(COMPANIES), it=it,
                         sup=sup, tax=tax, ev=ev, incl=incl))
    bad = next(r for r in rows if r["g"] == "매출" and kind[r["it"]] == "과세" and not r["incl"] and r["d"].month < 4)
    bad_tax = bad["tax"] + 90000
    lines = []
    for r in rows:
        if r["incl"]:
            supc, taxc, memo = "", "", f"합계금액 {_amt(r['sup'] + r['tax'], rng.choice(['won', 'plain']))}(VAT포함)"
        else:
            supc = _amt(r["sup"], rng.choice(["plain", "won", "chun", "man", "plain"]), rng)
            taxc = f"{(bad_tax if r is bad else r['tax']):,}"
            memo = rng.choice(["", "", "", "정기", "긴급"])
        lines.append([r["no"], _dt(r["d"], rng.choice(DATE_STYLES)), r["g"], _co_var(r["co"], rng), r["it"], supc, taxc,
                      r["ev"], memo])
    dups = [lines[i] for i in rng.sample(range(len(lines)), 7)]
    body = [",".join(_csv_cell(c) for c in ln) for ln in lines]
    body = _a_shuffle_insert(rng, body, [",".join(_csv_cell(c) for c in ln) for ln in dups])
    for m in (1, 2, 3):
        body.insert(rng.randrange(1, len(body)), f"{m}월 월계,,,,,{rng.randrange(10**7, 10**8):,},,,")
    t_tbl = "전표번호,일자,구분,거래처,품목,공급가액,세액,증빙,비고\n" + "\n".join(body)

    def solve(dedupe=True, evid=True, nonded=True, recompute=True, zero_rate=True):
        km = {r[0]: r[1] for r in _a_md_rows(i_tbl)}
        seen, out_v, in_v = set(), 0, 0
        for c in _a_csv_rows(t_tbl):
            if "월계" in c[0]:
                continue
            if dedupe and c[0] in seen:
                continue
            seen.add(c[0])
            no, ds, g, co, it, supc, taxc, ev, memo = c
            if _parse_dt(ds).month > 3:
                continue
            k = km[it]
            if supc == "":
                tot = _parse_amt(re.search(r"합계금액 ([^()]+)\(", memo).group(1))
                sup = tot * 10 // 11
                tax = tot - sup
            else:
                sup = _parse_amt(supc)
                tax = sup // 10 if recompute else _parse_amt(taxc)
            if not k.startswith("과세"):
                tax = 0 if (zero_rate or k == "면세") else sup // 10
            if g == "매출":
                out_v += tax
            else:
                if evid and ev == "없음":
                    continue
                if nonded and k == "과세·불공제":
                    continue
                in_v += tax
        return {"output_vat": out_v, "input_vat": in_v, "payable": out_v - in_v}

    truth = solve()
    assert truth["payable"] > 0
    wrong = _a_wrongs(solve, truth, {"dedupe": False}, {"evid": False}, {"nonded": False}, {"recompute": False},
                      {"zero_rate": False})
    prompt = ("2026년 1기 예정(1~3월) 부가가치세 신고용으로 매출·매입 전표를 정리해 주세요. 전표는 ERP에서 CSV로 내보낸 것이고, "
              "품목별 과세유형표를 함께 붙입니다.\n\n[전표]\n" + t_tbl + "\n\n[품목별 과세유형]\n" + i_tbl + "\n\n규칙:\n"
              "1. 일자가 2026년 1~3월인 전표만 대상입니다. 4월 전표는 빼세요. 'n월 월계' 줄은 합계 줄이라 무시합니다.\n"
              "2. 같은 전표번호가 두 번 이상 나오면 한 번만 셉니다.\n"
              "3. 공급가액 단위가 섞여 있습니다(원, 천원, 만원 등). 공급가액이 비어 있고 비고에 '합계금액 …(VAT포함)'이 있으면 "
              "공급가액 = 합계금액 × 10 ÷ 11, 세액 = 합계금액 − 공급가액입니다.\n"
              "4. 그 밖의 과세 품목 세액은 공급가액 × 10%(원 미만 버림)로 계산합니다. 세액 칸 숫자가 이 계산과 다른 행이 하나 섞여 있는데, "
              "그 경우에도 공급가액으로 계산한 세액을 씁니다.\n"
              "5. 면세 품목은 세액이 없고, 영세율 품목은 세율 0%라 세액 0원입니다.\n"
              "6. 매출세액 = 매출 전표 세액 합계. 매입세액 공제액 = 매입 전표 세액 합계에서 다음을 뺀 것: 증빙이 '없음'인 전표, "
              "과세유형이 '과세·불공제'인 품목의 전표.\n"
              "7. 납부세액 = 매출세액 − 매입세액 공제액.\n\n"
              "매출세액, 매입세액 공제액, 납부세액을 알려주세요. "
              + JSON_RULE + '{"output_vat": 원(정수), "input_vat": 원(정수), "payable": 원(정수)}')
    _add(2, "acct_vat", prompt, {"output_vat": "int", "input_vat": "int", "payable": "int"}, truth, wrong,
         {"rows": len(rows) + len(items), "tables": 2, "steps": 7,
          "mess": ["duplicates", "subtotal", "unit_mix", "vat_inclusive", "date_formats", "name_variants",
                   "contradiction_tax_cell"]})


# ----------------------------------------------------------------- hk_03 감가상각


def _hk03():
    rng = random.Random(1003)
    cls = [("비품", "정액법", 5, None), ("공구기구", "정액법", 4, None), ("소프트웨어", "정액법", 5, None),
           ("시설장치", "정액법", 10, None), ("차량운반구", "정률법", 5, 451), ("기계장치", "정률법", 8, 313)]
    c_tbl = _md(["분류", "상각방법", "내용연수(년)", "상각률(정률법)"],
                [(a, b, c, f"0.{d}" if d else "-") for a, b, c, d in cls])
    names = {"비품": ["사무용 책상", "회의 테이블", "복합기", "냉난방기", "서랍장", "노트북"],
             "공구기구": ["전동공구 세트", "측정기", "용접기", "지그"], "소프트웨어": ["ERP 모듈", "CAD 라이선스", "그룹웨어"],
             "시설장치": ["사무실 인테리어", "방음 공사", "전기 증설"], "차량운반구": ["업무용 화물차", "지게차", "승합차"],
             "기계장치": ["CNC 선반", "사출기", "컨베이어", "프레스"]}
    assets = []
    for i in range(128):
        cn = cls[rng.randrange(len(cls))][0]
        acq = date(rng.randrange(2021, 2027), 1, 1)
        acq = date(acq.year, rng.randrange(1, 12 if acq.year == 2026 else 13), rng.randrange(1, 29))
        cost = rng.randrange(30, 99) * 10000 if rng.random() < 0.12 else rng.randrange(100, 8000) * 10000
        disp = None
        if cost >= 10**6 and acq < date(2026, 1, 1) and rng.random() < 0.08:
            disp = date(2026, rng.randrange(2, 12), rng.randrange(1, 28))
        assets.append(dict(code=f"FA-{i + 101:04d}", nm=rng.choice(names[cn]), cn=cn, acq=acq, cost=cost, disp=disp,
                           memo=""))
    # contradiction: same code twice with different cost; '정정' row wins
    tgt = next(a for a in assets if a["cn"] == "기계장치" and a["cost"] >= 10**6 and a["disp"] is None
               and a["acq"].year < 2025)
    fix = dict(tgt, cost=tgt["cost"] + 12_000_000, memo="정정(세금계산서 재확인)")
    rows = []
    for a in assets:
        rows.append(a)
        if a is tgt:
            rows.append(fix)
    styles = ["won", "plain", "chun", "man", "ko"]
    lines = []
    for a in rows:
        lines.append([a["code"], a["nm"], a["cn"], _dt(a["acq"], rng.choice(DATE_STYLES)),
                      _amt(a["cost"], rng.choice(styles), rng), _dt(a["disp"], "iso") if a["disp"] else "", a["memo"]])
    dup = [lines[i] for i in rng.sample(range(len(lines)), 4) if lines[i][0] != tgt["code"]]
    lines += dup
    rng.shuffle(lines)
    lines.append(["합계", "", "", "", _amt(sum(a["cost"] for a in assets), "won"), "", ""])
    a_tbl = _md(["자산코드", "자산명", "분류", "취득일", "취득가액", "처분일", "비고"], lines)

    def solve(immed=True, keep1000=True, fixrow=True, disp_months=True):
        cm = {r[0]: (r[1], int(r[2]), int(r[3][2:]) if r[3] != "-" else None) for r in _a_md_rows(c_tbl)}
        recs = {}
        for r in _a_md_rows(a_tbl):
            if r[0] == "합계":
                continue
            rec = (r[0], r[2], _parse_dt(r[3]), _parse_amt(r[4]), _parse_dt(r[5]) if r[5] else None, r[6])
            if r[0] in recs and recs[r[0]] != rec:
                if fixrow == ("정정" in rec[5]):
                    recs[r[0]] = rec
            else:
                recs[r[0]] = rec
        dep26, book, byc = 0, 0, {}
        for code in sorted(recs):
            _, cn, acq, cost, disp, _ = recs[code]
            meth, life, rate = cm[cn]
            floor_v = 1000 if keep1000 else 0
            if immed and cost < 10**6:
                d26 = cost if acq.year == 2026 else 0
                bv = 0
            else:
                bv, used, d26 = cost, 0, 0
                for y in range(acq.year, 2027):
                    m0 = acq.month if y == acq.year else 1
                    m1 = 12
                    if y == 2026 and disp:
                        m1 = disp.month - 1 if disp_months else 12
                    months = max(0, m1 - m0 + 1)
                    rem = life * 12 - used
                    m = min(months, rem)
                    if m <= 0:
                        dep = 0
                    elif m == rem:
                        dep = bv - floor_v
                    elif meth == "정액법":
                        dep = min(cost * m // (life * 12), bv - floor_v)
                    else:
                        dep = min(bv * rate * m // 12000, bv - floor_v)
                    used += m
                    bv -= dep
                    if y == 2026:
                        d26 = dep
            dep26 += d26
            byc[cn] = byc.get(cn, 0) + d26
            if not disp:
                book += bv
        return {"dep_2026": dep26, "book_end": book, "top_class": _argmax(byc)[0]}

    truth = solve()
    wrong = _a_wrongs(solve, truth, {"immed": False}, {"keep1000": False}, {"fixrow": False}, {"disp_months": False})
    prompt = ("고정자산 대장으로 2026년 감가상각비와 2026년 말 장부가액을 계산해 주세요. 자산 대장과 분류별 상각 기준표를 붙입니다.\n\n"
              "[고정자산 대장]\n" + a_tbl + "\n\n[분류별 상각 기준]\n" + c_tbl + "\n\n규칙:\n"
              "1. 맨 아래 '합계' 줄은 대장 합계라 자산이 아닙니다. 취득가액 단위(원·천원·만원·한글 금액)와 날짜 형식이 섞여 있습니다.\n"
              "2. 같은 자산코드가 두 번 이상 나오면, 내용이 완전히 같으면 한 번만 셉니다. 내용이 다르면 비고에 '정정'이 있는 줄만 씁니다.\n"
              "3. 상각은 월할입니다. 취득한 달은 한 달로 치고(1일 취득이든 말일 취득이든), 처분한 달은 상각하지 않습니다. "
              "그래서 처분 자산의 2026년 상각월수는 1월부터 처분월 전달까지입니다.\n"
              "4. 정액법: 연도별 상각비 = 취득가액 × 그 해 상각월수 ÷ (내용연수×12), 원 미만 버림. 잔존가치는 0원으로 봅니다.\n"
              "5. 정률법: 연도별 상각비 = 그 해 초 장부가액 × 상각률 × 그 해 상각월수 ÷ 12, 원 미만 버림.\n"
              "6. 누적 상각월수가 내용연수×12개월에 닿는 해에는 장부가액이 정확히 1,000원(비망가액)이 되도록 상각하고, 그 뒤로는 상각하지 않습니다. "
              "어느 해든 상각 후 장부가액이 1,000원보다 낮아지게 상각하지 않습니다.\n"
              "7. 예외: 취득가액 100만원 미만 자산은 취득한 해에 전액 비용 처리(즉시상각)하고 장부가액은 0원입니다(비망가액 없음).\n"
              "8. 2026년 말 장부가액 합계에는 2026년에 처분한 자산을 넣지 않습니다.\n\n"
              "2026년 감가상각비 합계, 2026년 12월 31일 장부가액 합계, 2026년 감가상각비 합이 가장 큰 분류를 알려주세요. "
              + JSON_RULE + '{"dep_2026": 원(정수), "book_end": 원(정수), "top_class": 분류명}')
    _add(3, "acct_depr", prompt, {"dep_2026": "int", "book_end": "int", "top_class": "str"}, truth, wrong,
         {"rows": len(lines) + len(cls), "tables": 2, "steps": 8,
          "mess": ["duplicates", "total_row", "unit_mix", "korean_amount", "date_formats", "contradiction_correction"]})


# ----------------------------------------------------------------- hk_04 매출채권 연령분석


def _hk04():
    rng = random.Random(1004)
    base = date(2026, 6, 30)
    custs = COMPANIES[:16] + ["Acme Supply", "Orion Labs"]
    ctype = {c: "일반" for c in custs}
    for c in ("대성산업", "누리소프트"):
        ctype[c] = "분쟁"
    for c in ("한결건설", "초록에너지"):
        ctype[c] = "공공"
    cm_tbl = _tsv(["고객명", "유형"], [(c, ctype[c]) for c in custs])
    invs = []
    for i in range(158):
        c = custs[rng.randrange(len(custs))]
        iss = date(2025, 9, 1) + timedelta(days=rng.randrange(0, 312))
        due = iss + timedelta(days=rng.choice([30, 45, 60]))
        invs.append(dict(no=f"INV-{5001 + i}", c=c, iss=iss, due=due, amt=rng.randrange(50, 5000) * 10000))
    contra = invs[40]
    contra_due = contra["iss"] - timedelta(days=14)
    pays = []
    for c in custs:
        mine = sorted([v for v in invs if v["c"] == c], key=lambda v: v["due"])
        for v in mine:
            r = rng.random()
            if r < 0.55:
                pd_ = v["due"] + timedelta(days=rng.randrange(-10, 40))
                pays.append([c, pd_, v["amt"] if rng.random() < 0.7 else v["amt"] // 20000 * 10000])
    pays.append(["가람물류", date(2026, 7, 3), 30_000_000])
    pays.append(["한빛상사", date(2026, 7, 8), 20_000_000])
    pays.sort(key=lambda p: p[1])
    p_lines = []
    for i, (c, d, a) in enumerate(pays):
        p_lines.append([f"RC-{701 + i}", _dt(d, rng.choice(DATE_STYLES)), _co_var(c, rng), _amt(a, rng.choice(AMT_STYLES[:5]), rng)])
    dups = [p_lines[i] for i in rng.sample(range(len(p_lines)), 5)]
    p_body = _a_shuffle_insert(rng, ["\t".join(x) for x in p_lines], ["\t".join(x) for x in dups])
    p_tbl = "입금번호\t입금일\t고객명\t금액\n" + "\n".join(p_body)
    i_lines = []
    for v in invs:
        due = contra_due if v is contra else v["due"]
        i_lines.append([v["no"], _co_var(v["c"], rng), _dt(v["iss"], rng.choice(DATE_STYLES)),
                        _dt(due, rng.choice(DATE_STYLES)), _amt(v["amt"], rng.choice(["won", "plain", "man", "ko"]), rng)])
    late = [[f"INV-{5200 + k}", _co_var(custs[k], rng), _dt(date(2026, 7, 2 + k), "iso"),
             _dt(date(2026, 8, 1 + k), "iso"), _amt(rng.randrange(100, 900) * 10000, "won")] for k in range(3)]
    i_tbl = _csv(["송장번호", "고객명", "발행일", "만기일", "금액"], i_lines + late)

    def solve(dedupe=True, cutoff=True, by_due=True, ctypes=True, fix_due=True):
        ty = {_norm(r[0]): r[1] for r in _a_cells(cm_tbl)}
        inv = []
        for no, cn, iss, due, amt in _a_csv_rows(i_tbl):
            iss, due = _parse_dt(iss), _parse_dt(due)
            if iss > base:
                continue
            if fix_due and due < iss:
                due = iss + timedelta(days=30)
            inv.append([no, _norm(cn), iss, due, _parse_amt(amt)])
        inv.sort(key=lambda v: ((v[3] if by_due else v[2]), v[0]))
        seen = set()
        for c in _a_cells(p_tbl):
            if dedupe and c[0] in seen:
                continue
            seen.add(c[0])
            d = _parse_dt(c[1])
            if cutoff and d > base:
                continue
            k, a = _norm(c[2]), _parse_amt(c[3])
            for v in inv:
                if v[1] == k and a > 0 and v[4] > 0:
                    t = min(a, v[4])
                    v[4] -= t
                    a -= t
        tot, allow, o90 = 0, 0, 0
        for no, k, iss, due, bal in inv:
            if bal <= 0:
                continue
            age = (base - due).days
            pct = 1 if age <= 0 else 3 if age <= 30 else 10 if age <= 90 else 30 if age <= 180 else 70
            if ctypes:
                pct = {"분쟁": 100, "공공": 0}.get(ty[k], pct)
            tot += bal
            allow += bal * pct // 100
            o90 += bal if age > 90 else 0
        return {"total_open": tot, "allowance": allow, "over90_balance": o90}

    truth = solve()
    wrong = _a_wrongs(solve, truth, {"dedupe": False}, {"cutoff": False}, {"ctypes": False}, {"fix_due": False})
    prompt = ("6월 말 결산용 매출채권 연령분석과 대손충당금을 계산해 주세요. 송장 목록(CSV), 입금 내역(탭 구분), 고객 유형표(탭 구분)를 붙입니다.\n\n"
              "[송장 목록]\n" + i_tbl + "\n\n[입금 내역]\n" + p_tbl + "\n\n[고객 유형]\n" + cm_tbl + "\n\n규칙 (기준일 2026-06-30):\n"
              "1. 발행일이 기준일 이후인 송장과 입금일이 기준일 이후인 입금은 반영하지 않습니다.\n"
              "2. 입금 내역에 같은 입금번호가 두 번 이상 있으면 한 번만 반영합니다. 고객명은 (주)·공백·대소문자 차이를 무시합니다.\n"
              "3. 송장의 만기일이 발행일보다 앞선 행이 하나 있는데 입력 오류입니다. 그 송장의 만기일은 발행일 + 30일로 봅니다.\n"
              "4. 입금은 입금일 순서대로, 같은 고객의 아직 남은 송장 중 만기일이 가장 이른 것부터(만기일이 같으면 송장번호가 작은 것부터) 충당합니다. "
              "한 입금이 여러 송장에 나뉘어 충당될 수 있고, 모든 송장을 갚고 남는 돈은 선수금이라 다른 고객에 쓰지 않습니다.\n"
              "5. 남은 잔액의 연령 = 기준일 − 만기일(일수). 충당률: 0일 이하(만기 미도래) 1%, 1~30일 3%, 31~90일 10%, 91~180일 30%, 180일 초과 70%.\n"
              "6. 예외: 고객 유형이 '분쟁'이면 연령과 무관하게 100%, '공공'이면 0%.\n"
              "7. 대손충당금은 송장별로 잔액 × 충당률을 원 미만 버림한 뒤 합산합니다.\n\n"
              "기준일 미수 잔액 합계, 대손충당금 합계, 연령 90일 초과 잔액 합계(고객 유형 무관)를 알려주세요. "
              + JSON_RULE + '{"total_open": 원(정수), "allowance": 원(정수), "over90_balance": 원(정수)}')
    _add(4, "acct_ar_aging", prompt, {"total_open": "int", "allowance": "int", "over90_balance": "int"}, truth, wrong,
         {"rows": len(i_lines) + 3 + len(p_body) + len(custs), "tables": 3, "steps": 7,
          "mess": ["duplicates", "unit_mix", "korean_amount", "date_formats", "name_variants", "cutoff_rows",
                   "contradiction_due_date"]})


# ----------------------------------------------------------------- hk_05 은행 잔액 대사


def _hk05():
    rng = random.Random(1005)
    descs_in = ["매출대금 입금", "카드매출 정산", "외상대 회수", "임대료 수입"]
    descs_out = ["원재료 대금", "급여 이체", "임차료", "관리비", "운반비", "수수료 지급", "소모품 구입", "보험료"]
    common = []
    for i in range(118):
        inn = rng.random() < 0.45
        a = rng.randrange(10, 3000) * 1000 if inn else -rng.randrange(5, 2500) * 1000
        d = date(2026, 3, 1) + timedelta(days=rng.randrange(0, 27))
        common.append(dict(d=d, a=a, ds=rng.choice(descs_in if inn else descs_out), lag=rng.choice([0, 0, 0, 1, 1, 2, 3])))
    # two same-amount rents to test tie rules
    common.append(dict(d=date(2026, 3, 10), a=-1_100_000, ds="임차료(창고)", lag=2))
    common.append(dict(d=date(2026, 3, 11), a=-1_100_000, ds="임차료(사무실)", lag=0))
    book_only = [dict(d=date(2026, 3, rng.randrange(27, 32)), a=(rng.randrange(10, 900) * 1000) * rng.choice([1, -1]),
                      ds=rng.choice(["발행수표", "타행 송금 대기", "미착 입금"]), lag=None) for _ in range(9)]
    bank_only = [dict(d=date(2026, 3, rng.randrange(1, 32)), a=a, ds=ds, lag=0) for a, ds in
                 [(18_420, "예금이자"), (-3_300, "이체수수료"), (-5_500, "이체수수료"), (-412_000, "자동이체 보험료"),
                  (1_250_000, "미확인 입금"), (-88_000, "카드 연회비"), (-2_200, "이체수수료"), (27_910, "예금이자"),
                  (-650_000, "자동이체 리스료"), (3_480_000, "거래처 직접입금")]]
    book = sorted(common + book_only, key=lambda x: x["d"])
    b_lines = []
    for i, e in enumerate(book):
        a = e["a"]
        if a < 0:
            s = ("△" if rng.random() < 0.6 else "-") + f"{-a:,}"
        else:
            s = _amt(a, rng.choice(["plain", "won"]))
        assert _parse_amt(s) == a
        b_lines.append(f"{i + 1}\t{_dt(e['d'], rng.choice(['iso', 'dot', 'dots', 'md']))}\t{e['ds']}\t{s}")
    b_lines = _a_shuffle_insert(rng, b_lines, ["※ 3/15 이후 분은 회계팀 수기 입력"])
    b_lines.append(f"월계\t\t\t{sum(e['a'] for e in book):,}")
    opening_typo, opening = 52_340_000, 52_430_000
    bk_tbl = "순번\t일자\t적요\t금액(출금은 △ 또는 -)\n" + "\n".join(b_lines)
    bank = sorted([dict(e, bd=e["d"] + timedelta(days=e["lag"])) for e in common if e["d"] + timedelta(days=e["lag"]) <= date(2026, 3, 31)]
                  + [dict(e, bd=e["d"]) for e in bank_only], key=lambda x: x["bd"])
    late_common = [e for e in common if e["d"] + timedelta(days=e["lag"]) > date(2026, 3, 31)]
    bal = 61_200_000
    k_rows = []
    for i, e in enumerate(bank):
        bal += e["a"]
        t = f"{rng.randrange(8, 18):02d}:{rng.randrange(60):02d}"
        k_rows.append([f"B{260300 + i}", f"{e['bd']:%Y-%m-%d} {t}", e["ds"],
                       f"{-e['a']:,}" if e["a"] < 0 else "", f"{e['a']:,}" if e["a"] > 0 else "", f"{bal:,}"])
    dups = [k_rows[i] for i in rng.sample(range(len(k_rows)), 3)]
    k_body = [",".join(_csv_cell(c) for c in r) for r in k_rows]
    for dd in dups:
        idx = k_body.index(",".join(_csv_cell(c) for c in dd))
        k_body.insert(idx + 1, ",".join(_csv_cell(c) for c in dd))
    bk_csv = "거래번호,거래일시,적요,출금,입금,잔액\n" + "\n".join(k_body)

    def solve(dedupe=True, tol=3, right_open=True):
        ops = opening if right_open else opening_typo
        books = []
        for c in _a_cells(bk_tbl):
            if c[0].startswith("※") or c[0] == "월계":
                continue
            books.append((int(c[0]), _parse_dt(c[1], 2026), _parse_amt(c[3])))
        banks, seen = [], set()
        for r in _a_csv_rows(bk_csv):
            if dedupe and r[0] in seen:
                continue
            seen.add(r[0])
            a = -_parse_amt(r[3]) if r[3] else _parse_amt(r[4])
            banks.append([r[0], _parse_dt(r[1].split()[0]), a, False])
        b_only = []
        for no, d, a in sorted(books):
            cands = [b for b in banks if not b[3] and b[2] == a and abs((b[1] - d).days) <= tol]
            if not cands:
                b_only.append(a)
                continue
            best = min(cands, key=lambda b: (abs((b[1] - d).days), b[0]))
            best[3] = True
        k_only = sum(b[2] for b in banks if not b[3])
        end = ops + sum(a for _, _, a in books)
        return {"book_only_count": len(b_only), "book_only_net": sum(b_only), "bank_only_net": k_only,
                "adjusted_book_balance": end + k_only}

    truth = solve()
    assert truth["book_only_count"] == len(book_only) + len(late_common), truth
    wrong = _a_wrongs(solve, truth, {"dedupe": False}, {"tol": 0}, {"right_open": False})
    prompt = ("3월 보통예금 잔액 대사를 부탁합니다. 회사 장부(탭 구분)와 은행 거래내역(CSV 내보내기)을 붙입니다. "
              f"장부 머리에는 3월 기초잔액이 {opening_typo:,}원으로 적혀 있지만, 회계팀 메모에 따르면 '전월 결산 확정 기초잔액은 "
              f"{_amt(opening, 'ko', rng)}이며 장부 머리 금액은 오타'라고 합니다. 두 금액이 다르면 결산 확정 금액을 씁니다.\n\n"
              f"[장부] 3월 기초잔액 {opening_typo:,}원\n" + bk_tbl + "\n\n[은행 거래내역]\n" + bk_csv + "\n\n규칙:\n"
              "1. 장부의 '※' 메모 줄과 '월계' 줄은 거래가 아닙니다. 장부 일자는 모두 2026년입니다.\n"
              "2. 은행 내역은 내보내기 오류로 같은 거래번호가 연달아 두 번 나온 줄이 있습니다. 같은 거래번호는 한 번만 셉니다.\n"
              "3. 매칭: 장부 거래를 순번 순서대로 하나씩 보면서, 아직 매칭되지 않은 은행 거래 중 금액과 방향(입금/출금)이 같고 날짜 차이가 "
              "3일 이내(앞뒤 모두)인 것과 짝짓습니다. 후보가 여럿이면 날짜 차이가 가장 작은 것, 그래도 같으면 거래번호가 작은 것을 고릅니다. "
              "은행 거래 하나는 장부 거래 하나와만 짝지어집니다.\n"
              "4. 짝이 없는 장부 거래 = 은행 미반영(장부에만 있음), 짝이 없는 은행 거래 = 장부 미반영(은행에만 있음)입니다.\n"
              "5. 장부 기말잔액 = 결산 확정 기초잔액 + 장부 거래 금액 합계(입금 +, 출금 −). "
              "조정 후 장부잔액 = 장부 기말잔액 + 은행에만 있는 거래의 순액(입금 +, 출금 −).\n\n"
              "은행 미반영 장부 거래 건수와 그 순액(입금 +, 출금 −), 장부 미반영 은행 거래의 순액, 조정 후 장부잔액을 알려주세요. "
              + JSON_RULE + '{"book_only_count": 건수(정수), "book_only_net": 원(정수, 음수 가능), "bank_only_net": 원(정수, 음수 가능), '
              '"adjusted_book_balance": 원(정수)}')
    _add(5, "acct_bankrec", prompt, {"book_only_count": "int", "book_only_net": "int", "bank_only_net": "int",
                                     "adjusted_book_balance": "int"}, truth, wrong,
         {"rows": len(book) + len(k_body), "tables": 2, "steps": 5,
          "mess": ["duplicates", "memo_line", "subtotal", "sign_styles", "date_formats", "korean_amount",
                   "contradiction_opening_balance"]})


# ----------------------------------------------------------------- hk_06 원천징수 (사업·기타·일용)


def _hk06():
    rng = random.Random(1006)
    ppl = PEOPLE[:34]
    kinds = {p: rng.choices(["사업소득", "기타소득", "일용근로"], [5, 4, 3])[0] for p in ppl}
    contra = ppl[7]
    kinds[contra] = "기타소득"
    reg = [(p, kinds[p], date(2025, rng.randrange(1, 13), rng.randrange(1, 28))) for p in ppl]
    ci = next(i for i, r in enumerate(reg) if r[0] == contra)
    reg[ci] = (contra, "기타소득", date(2026, 3, 20))
    reg.insert(ci + 3, (contra, "사업소득", date(2025, 6, 2)))
    r_tbl = _md(["성명", "소득구분", "등록일"], [(a, b, _dt(c, "iso")) for a, b, c in reg])
    item = {"사업소득": ["강의료", "디자인 용역비", "번역료", "촬영 용역비"], "기타소득": ["원고료", "자문료", "심사위원 수당"],
            "일용근로": ["일당(행사 보조)", "일당(물류 지원)"]}
    pays = []
    for i in range(196):
        p = ppl[rng.randrange(len(ppl))] if i % 28 else contra
        k = kinds[p]
        if k == "일용근로":
            a = rng.randrange(10, 26) * 10000
        elif k == "기타소득":
            a = rng.randrange(5, 200) * 10000 if rng.random() < 0.8 else rng.randrange(5, 13) * 10000
        else:
            a = rng.randrange(3, 300) * 10000 if rng.random() < 0.9 else rng.randrange(1, 4) * 10000
        if rng.random() < 0.04:
            d = rng.choice([date(2026, 3, rng.randrange(20, 32)), date(2026, 7, rng.randrange(1, 10))])
        else:
            d = date(2026, 4, 1) + timedelta(days=rng.randrange(0, 91))
        pays.append(dict(no=f"P-{4001 + i}", d=d, p=p, it=rng.choice(item[k]), a=a))
    pays.sort(key=lambda x: x["d"])
    lines, prev_m = [], None
    for x in pays + [None]:
        m = x["d"].month if x else None
        if prev_m in (4, 5, 6) and m != prev_m:
            lines.append(f"— {prev_m}월 소계 {_amt(sum(y['a'] for y in pays if y['d'].month == prev_m), 'won')}")
        prev_m = m
        if x:
            lines.append(f"- {_dt(x['d'], rng.choice(DATE_STYLES))} {_person_var(x['p'], rng)} {x['it']} "
                         f"{_amt(x['a'], rng.choice(['won', 'man', 'ko', 'plain', 'won']), rng)} (지급번호 {x['no']})")
    pl = [i for i, ln in enumerate(lines) if ln.startswith("- ")]
    extra = [lines[i] + " (재전송)" for i in rng.sample(pl, 6)]
    extra += [f"※ {pays[i]['no']} 지급 취소(계좌 오류로 반송)" for i in rng.sample(range(len(pays)), 4)]
    lines = _a_shuffle_insert(rng, lines, extra)
    body = "\n".join(lines)
    all_items = sorted({i for v in item.values() for i in v}, key=len, reverse=True)

    def parse(ln):
        m = re.fullmatch(r"- (.*) \(지급번호 (P-\d+)\)( \(재전송\))?", ln)
        if not m:
            return None
        core, no = m.group(1), m.group(2)
        it = next(i for i in all_items if f" {i} " in core)
        pre, amt = core.split(f" {it} ", 1)
        tok = pre.split(" ")
        nd = 3 if tok[0].endswith("년") else 1
        return no, _parse_dt(" ".join(tok[:nd])), "".join(tok[nd:]), _parse_amt(amt)

    def solve(dedupe=True, latest=True, minimum=True, cancel=True):
        km = {}
        for nm, k, d in _a_md_rows(r_tbl):
            d = _parse_dt(d)
            if nm not in km or not latest or d > km[nm][1]:
                km[nm] = (k, d)
        canc = set(re.findall(r"※ (P-\d+)", body))
        seen, it_, lt, zero = set(), 0, 0, 0
        for ln in body.split("\n"):
            r = parse(ln)
            if not r:
                continue
            no, d, nm, a = r
            if dedupe and no in seen:
                continue
            seen.add(no)
            if cancel and no in canc:
                continue
            if d.month not in (4, 5, 6):
                continue
            k = km[nm][0]
            if k == "사업소득":
                tax = _floor10(a * 3 // 100)
                if minimum and tax < 1000:
                    tax = 0
            elif k == "기타소득":
                inc = a * 40 // 100
                tax = 0 if (minimum and inc <= 50000) else _floor10(inc * 20 // 100)
            else:
                tax = _floor10(max(0, a - 150000) * 6 * 45 // 10000)
                if minimum and tax < 1000:
                    tax = 0
            it_ += tax
            lt += _floor10(tax // 10)
            zero += tax == 0
        return {"income_tax": it_, "local_tax": lt, "zero_count": zero}

    clean = [x for x in pays if x["d"].month in (4, 5, 6)]
    assert all(parse(ln) is not None for ln in lines if ln.startswith("- "))
    truth = solve()
    wrong = _a_wrongs(solve, truth, {"dedupe": False}, {"latest": False}, {"minimum": False}, {"cancel": False})
    prompt = ("2분기(4~6월) 외부 인력 지급분의 원천징수 세액을 집계해 주세요. 지급 내역은 메신저로 받은 목록이고, 소득구분은 인력 등록부를 따릅니다.\n\n"
              "[지급 내역]\n" + body + "\n\n[인력 등록부]\n" + r_tbl + "\n\n규칙:\n"
              "1. 지급일이 2026년 4~6월인 건만 대상입니다. '— n월 소계' 줄은 합계라 무시합니다. 이름의 공백 차이는 무시합니다.\n"
              "2. 같은 지급번호가 '(재전송)'으로 다시 나온 줄은 한 번만 셉니다. '※ … 지급 취소' 줄에 있는 지급번호는 빼고 셉니다.\n"
              "3. 소득구분은 등록부 기준입니다. 등록부에 같은 사람이 두 줄 있으면 등록일이 늦은 줄을 따릅니다.\n"
              "4. 사업소득: 소득세 = 지급액 × 3%. 소득세가 1,000원 미만이면 0원(소액부징수).\n"
              "5. 기타소득: 필요경비 60%를 빼서 기타소득금액 = 지급액 × 40%. 건별 기타소득금액이 50,000원 이하이면 소득세 0원(과세최저한), "
              "아니면 소득세 = 기타소득금액 × 20%.\n"
              "6. 일용근로: 지급 1건이 하루 일당입니다. 소득세 = (일당 − 150,000원, 음수면 0) × 6% × 45%(세액공제 55% 반영). "
              "1,000원 미만이면 0원(소액부징수).\n"
              "7. 소득세는 건별로 원 미만 버리고 10원 미만도 버립니다. 지방소득세 = 건별 소득세 × 10%에서 10원 미만 버림.\n\n"
              "소득세 합계, 지방소득세 합계, 대상 지급 건 중 소득세가 0원인 건수를 알려주세요. "
              + JSON_RULE + '{"income_tax": 원(정수), "local_tax": 원(정수), "zero_count": 건수(정수)}')
    _add(6, "acct_wht", prompt, {"income_tax": "int", "local_tax": "int", "zero_count": "int"}, truth, wrong,
         {"rows": len(pays) + len(reg), "tables": 2, "steps": 7,
          "mess": ["prose_list", "duplicates", "memo_cancel", "subtotal", "unit_mix", "korean_amount", "date_formats",
                   "name_variants", "contradiction_registry"]})


# ----------------------------------------------------------------- hk_07 법인카드 경비 정산


def _hk07():
    rng = random.Random(1007)
    depts = ["영업1팀", "영업2팀", "마케팅팀", "구매팀", "경영지원팀", "연구소"]
    cards = [f"{rng.randrange(1000, 10000)}" for _ in range(14)]
    assert len(set(cards)) == 14
    own = [(c, PEOPLE[i + 10], depts[i % 6], "") for i, c in enumerate(cards)]
    swap = cards[3]
    own.insert(4, (swap, PEOPLE[30], "연구소", "5/16 재발급, 이날부터 이 사람이 사용"))
    o_tbl = _tsv(["카드끝4자리", "사용자", "부서", "비고"], own)
    acc = [("일반음식점", "복리후생비"), ("편의점", "복리후생비"), ("주점", "접대비"), ("한정식", "접대비"), ("골프장", "접대비"),
           ("택시", "여비교통비"), ("숙박", "여비교통비"), ("주유소", "차량유지비"), ("문구", "소모품비"), ("온라인몰", "소모품비")]
    accm = dict(acc)
    m_tbl = _md(["업종", "계정"], acc)
    shops = {"일반음식점": ["김밥천국", "본가설렁탕", "청담국수", "한솥도시락"], "편의점": ["GS25", "CU", "세븐일레븐"],
             "주점": ["달빛포차", "하이볼바"], "한정식": ["수라원", "가온정"], "골프장": ["레이크CC"], "택시": ["카카오T"],
             "숙박": ["신라스테이", "토요코인"], "주유소": ["SK에너지", "S-OIL"], "문구": ["알파문구"], "온라인몰": ["쿠팡", "11번가"]}
    hol = {date(2026, 5, 5), date(2026, 5, 25)}
    holis = [d for d in _days(date(2026, 5, 1), date(2026, 5, 31)) if not _is_biz(d, hol)]
    tx = []
    for i in range(214):
        cat = rng.choices([a for a, _ in acc], [9, 4, 3, 3, 1, 5, 2, 3, 2, 2])[0]
        a = {"주점": rng.randrange(80, 700), "한정식": rng.randrange(150, 900), "골프장": rng.randrange(300, 900),
             "숙박": rng.randrange(60, 200)}.get(cat, rng.randrange(5, 120)) * 1000 + rng.choice([0, 500, 300])
        d = date(2026, 5, 1) + timedelta(days=rng.randrange(0, 31))
        memo = ""
        if accm[cat] == "복리후생비" and d in holis and rng.random() < 0.4:
            memo = "주말 특근 식대"
        elif accm[cat] == "접대비":
            memo = rng.choice(["거래처 미팅", "고객 접대", ""])
        tx.append(dict(no=f"A{rng.randrange(10**7, 10**8)}", d=d, t=f"{rng.randrange(7, 23):02d}:{rng.randrange(60):02d}",
                       c=cards[rng.randrange(14)], sh=rng.choice(shops[cat]), cat=cat, a=a, memo=memo))
    tx.sort(key=lambda x: (x["d"], x["t"]))
    rows = []
    for x in tx:
        rows.append([x["no"], f"{_dt(x['d'], rng.choice(['iso', 'dot', 'slash']))} {x['t']}", x["c"], x["sh"], x["cat"],
                     _amt(x["a"], rng.choice(["plain", "won"])), "승인", x["memo"]])
    cxl = rng.sample(range(len(tx)), 6)
    for i in cxl:
        x = tx[i]
        rows.append([x["no"], f"{_dt(x['d'] + timedelta(days=rng.randrange(0, 3)), 'iso')} 10:00", x["c"], x["sh"], x["cat"],
                     "-" + f"{x['a']:,}", "취소", "승인 취소"])
    for i in rng.sample([j for j in range(len(tx)) if j not in cxl], 5):
        rows.append(list(rows[i]))
    rng.shuffle(rows)
    t_csv = _csv(["승인번호", "승인일시", "카드", "가맹점", "업종", "금액", "구분", "적요"], rows)
    nosub = sorted(rng.sample([x["no"] for i, x in enumerate(tx) if i not in cxl], 7))

    def solve(dedupe=True, cancel=True, swap_rule=True, holiday=True, cap=True):
        om = {}
        for c, nm, dp, memo in _a_cells(o_tbl):
            if memo and swap_rule:
                om[c] = (om[c], (date(2026, 5, 16), dp))
            elif not memo:
                om[c] = dp
        recs, seen = {}, set()
        cancelled = set()
        for r in _a_csv_rows(t_csv):
            key = (r[0], r[6])
            if dedupe and key in seen:
                continue
            seen.add(key)
            if r[6] == "취소":
                cancelled.add(r[0])
                continue
            recs.setdefault(r[0], []).append(r)
        personal, ent, byd = 0, 0, {}
        holiday_s = {(d.month, d.day) for d in holis}
        for no in sorted(recs):
            for r in recs[no]:
                if cancel and no in cancelled:
                    continue
                d = _parse_dt(r[1].split()[0])
                a = _parse_amt(r[5])
                ac = accm[r[4]]
                pers = 0
                if no in nosub or r[4] == "골프장":
                    pers = a
                elif holiday and ac == "복리후생비" and (d.month, d.day) in holiday_s and "특근" not in r[7]:
                    pers = a
                elif cap and ac == "접대비" and a > 300000:
                    pers = a - 300000
                ok = a - pers
                personal += pers
                if ac == "접대비":
                    ent += ok
                o = om[r[2]]
                dp = (o[1][1] if d >= o[1][0] else o[0]) if isinstance(o, tuple) else o
                byd[dp] = byd.get(dp, 0) + ok
        return {"personal_total": personal, "entertain_allowed": ent, "top_dept": _argmax(byd)[0]}

    truth = solve()
    wrong = _a_wrongs(solve, truth, {"dedupe": False}, {"cancel": False}, {"holiday": False}, {"cap": False})
    prompt = ("5월 법인카드 사용분 정산을 해 주세요. 카드사 승인 내역(CSV), 카드 사용자표(탭 구분), 업종별 계정표를 붙입니다.\n\n"
              "[승인 내역] (모두 2026년 5월)\n" + t_csv + "\n\n[카드 사용자]\n" + o_tbl + "\n\n[업종별 계정]\n" + m_tbl + "\n\n"
              "[영수증 미제출 승인번호] " + ", ".join(nosub) + "\n\n"
              "[5월 휴일(주말·공휴일)] " + ", ".join(f"{d.month}/{d.day}" for d in holis) + "\n\n규칙:\n"
              "1. 같은 승인번호·같은 구분(승인/취소) 줄이 두 번 이상 있으면 한 번만 셉니다.\n"
              "2. 구분이 '취소'인 줄은 같은 승인번호의 승인을 전액 취소합니다. 취소된 승인은 아예 정산에서 뺍니다.\n"
              "3. 계정은 업종별 계정표를 따릅니다.\n"
              "4. 개인부담(회사 불인정) 판정은 다음 순서로 하나만 적용합니다. (가) 영수증 미제출 승인번호이거나 업종이 골프장이면 전액 개인부담. "
              "(나) 그렇지 않고 사용일이 휴일이며 계정이 복리후생비인데 적요에 '특근'이 없으면 전액 개인부담. "
              "(다) 그렇지 않고 계정이 접대비이면 건당 300,000원을 넘는 부분만 개인부담.\n"
              "5. 회사 인정액 = 금액 − 개인부담. 부서는 사용일 기준 카드 사용자의 부서입니다. 사용자표에 같은 카드가 두 줄이면 "
              "비고에 적힌 날짜(그날 포함)부터는 비고가 있는 줄의 사람·부서가 사용한 것으로 봅니다.\n\n"
              "개인부담 합계, 회사가 인정한 접대비 합계, 회사 인정액 합계가 가장 큰 부서를 알려주세요. "
              + JSON_RULE + '{"personal_total": 원(정수), "entertain_allowed": 원(정수), "top_dept": 부서명}')
    _add(7, "acct_card", prompt, {"personal_total": "int", "entertain_allowed": "int", "top_dept": "str"}, truth, wrong,
         {"rows": len(rows) + len(own) + len(acc), "tables": 3, "steps": 5,
          "mess": ["duplicates", "cancellations", "date_formats", "exception_list", "contradiction_card_owner"]})


# ----------------------------------------------------------------- hk_08 하반기 예산 대비 실적


def _hk08():
    rng = random.Random(1008)
    depts = [("D210", "영업기획팀"), ("D220", "영업운영팀"), ("D230", "마케팅팀"), ("D310", "구매팀"), ("D320", "물류팀"),
             ("D410", "인사팀"), ("D420", "총무팀"), ("D510", "연구1팀"), ("D520", "연구2팀"), ("D610", "재무팀")]
    dn = dict(depts)
    remap = [("D110", "D210"), ("D120", "D210"), ("D130", "D230"), ("D300", "D310"), ("D400", "D420"), ("D500", "D510")]
    old_of = {}
    for o, n in remap:
        old_of.setdefault(n, []).append(o)
    accts = ["복리후생비", "여비교통비", "접대비", "소모품비", "지급수수료", "광고선전비", "교육훈련비", "감가상각비"]
    rows = []
    for i in range(262):
        c, nm = depts[rng.randrange(len(depts))]
        code = rng.choice(old_of[c]) if c in old_of and rng.random() < 0.35 else c
        d = date(2026, 6, 1) + timedelta(days=rng.randrange(0, 214))
        ac = rng.choices(accts, [4, 4, 2, 4, 3, 2, 2, 2])[0]
        a = rng.randrange(10, 2500) * 1000
        rows.append([f"JV{26700 + i}", d, code, nm, ac, a, ""])
    for i in rng.sample(range(len(rows)), 8):
        r = list(rows[i])
        r[0] = r[0] + "R"
        r[5] = -(r[5] // 2000 * 1000)
        r[6] = "역분개(일부 취소)"
        rows.append(r)
    contra = next(r for r in rows if r[2] == "D320" and r[1].month >= 7 and r[4] != "감가상각비")
    contra[3] = "마케팅팀"
    lines = []
    for r in rows:
        lines.append([r[0], _dt(r[1], rng.choice(DATE_STYLES)), r[2], r[3], r[4],
                      _amt(r[5], rng.choice(["plain", "won", "chun", "man"]), rng), r[6]])
    dups = [lines[i] for i in rng.sample(range(len(lines)), 6)]
    body = _a_shuffle_insert(rng, ["\t".join(x) for x in lines], ["\t".join(x) for x in dups])
    body.insert(len(body) // 2, "\t\t\t\t소계\t" + f"{rng.randrange(10**8, 3 * 10**8):,}\t(중간 집계)")
    v_tbl = "전표번호\t일자\t부서코드\t부서명\t계정\t금액\t비고\n" + "\n".join(body)

    def actual_clean():
        act = {}
        for r in rows:
            if r[1].month >= 7 and r[4] != "감가상각비":
                n = dict(remap).get(r[2], r[2])
                act[n] = act.get(n, 0) + r[5]
        return act

    act0 = actual_clean()
    bud_rows = []
    facs = [0.86, 0.93, 0.97, 1.06, 1.12, 1.18, 1.25, 1.09, 1.3, 1.15]
    rng.shuffle(facs)
    for (c, nm), f in zip(depts, facs):
        b = int(act0[c] * f) // 1000 + 1
        if rng.random() < 0.4:
            bud_rows.append((c, nm, "본예산", f"{int(b * rng.choice([0.85, 1.25])):,}"))
            bud_rows.append((c, nm, "추경", f"{b:,}"))
        else:
            bud_rows.append((c, nm, "본예산", f"{b:,}"))
    b_tbl = _md(["부서코드", "부서명", "구분", "하반기 예산(천원)"], bud_rows)
    r_tbl = "\n".join(f"- {o} → {n} ({dn[n]})" for o, n in remap)

    def solve(dedupe=True, mapping=True, excl=True, supp=True, unit=1000):
        bud = {}
        for c, nm, g, b in _a_md_rows(b_tbl):
            if g == "추경" and supp or c not in bud:
                bud[c] = int(b.replace(",", "")) * unit
        mp = dict(re.findall(r"- (D\d+) → (D\d+)", r_tbl))
        seen, act = set(), {}
        for c in _a_cells(v_tbl):
            if c[4] == "소계":
                continue
            if dedupe and c[0] in seen:
                continue
            seen.add(c[0])
            if _parse_dt(c[1]).month < 7 or (excl and c[4] == "감가상각비"):
                continue
            code = mp.get(c[2], c[2]) if mapping else c[2]
            act[code] = act.get(code, 0) + _parse_amt(c[5])
        tot = sum(v for k, v in act.items() if k in bud)
        over = sorted(k for k in bud if act.get(k, 0) > bud[k])
        worst = _argmax({k: act.get(k, 0) / bud[k] for k in bud})[0]
        return {"overrun_depts": over, "total_actual": tot, "worst_dept": worst}

    truth = solve()
    assert truth["total_actual"] == sum(act0.values()) and 2 <= len(truth["overrun_depts"]) <= 6, truth
    wrong = _a_wrongs(solve, truth, {"dedupe": False}, {"mapping": False}, {"excl": False}, {"supp": False})
    prompt = ("하반기(7~12월) 부서별 예산 대비 실적을 점검해 주세요. 7월 1일 조직개편으로 부서코드가 바뀌었는데 일부 전표는 아직 옛 코드로 입력되어 있습니다.\n\n"
              "[전표] (2026년, 금액 단위 섞임, 음수는 역분개)\n" + v_tbl + "\n\n[하반기 부서 예산]\n" + b_tbl +
              "\n\n[부서코드 변경(구 → 신)]\n" + r_tbl + "\n\n규칙:\n"
              "1. 일자가 7월 1일~12월 31일인 전표만 하반기 실적입니다. '소계' 줄은 무시합니다.\n"
              "2. 같은 전표번호는 한 번만 셉니다. 역분개 전표(번호 끝 R, 음수 금액)는 실적에서 빼는 금액으로 그대로 반영합니다.\n"
              "3. 옛 부서코드는 변경표에 따라 새 코드로 바꿔 합칩니다. 부서코드와 부서명이 서로 안 맞는 전표가 하나 있는데, 이때는 부서코드를 따릅니다.\n"
              "4. 계정이 '감가상각비'인 전표는 예산 통제 대상이 아니라 실적에서 뺍니다.\n"
              "5. 예산표는 천원 단위입니다. 한 부서에 본예산과 추경이 함께 있으면 추경 금액이 최종 예산입니다.\n"
              "6. 실적이 예산보다 크면(같으면 아님) 초과 부서입니다. 실행률 = 실적 ÷ 예산.\n\n"
              "초과 부서 코드 목록(코드 오름차순), 예산표에 있는 부서들의 하반기 실적 합계(원), 실행률이 가장 높은 부서 코드를 알려주세요. "
              + JSON_RULE + '{"overrun_depts": [부서코드, ...], "total_actual": 원(정수), "worst_dept": 부서코드}')
    _add(8, "acct_budget", prompt, {"overrun_depts": "list", "total_actual": "int", "worst_dept": "str"}, truth, wrong,
         {"rows": len(body) + len(bud_rows) + len(remap), "tables": 3, "steps": 6,
          "mess": ["duplicates", "subtotal", "unit_mix", "negative_reversal", "date_formats", "code_remap",
                   "contradiction_code_name"]})


# ----------------------------------------------------------------- hk_09 할부 차입 이자


def _a_addm(d, k):
    m = d.month - 1 + k
    return date(d.year + m // 12, m % 12 + 1, d.day)


def _hk09():
    rng = random.Random(1009)
    cons = []
    for i in range(118):
        st = date(2022, 1, 1) + timedelta(days=rng.randrange(0, 1760))
        st = date(st.year, st.month, min(st.day, 28))
        cons.append(dict(no=f"L-{i + 1:03d}", st=st, p=rng.randrange(100, 3000) * 100000,
                         bp=rng.randrange(320, 790), n=rng.choice([12, 24, 36, 36, 48, 60]),
                         way=rng.choice(["원금균등", "원금균등", "만기일시"])))
    early = {}
    for c in rng.sample(cons, 9):
        last = _a_addm(c["st"], c["n"])
        if date(2026, 1, 10) < last and c["st"] < date(2025, 12, 1):
            early[c["no"]] = date(2026, rng.randrange(2, 12), rng.randrange(1, 28))
    early = {k: v for k, v in sorted(early.items())}
    fixc = next(c for c in cons if c["n"] == 36 and c["st"].year == 2024 and c["no"] not in early)
    voidc = next(c for c in cons if c["st"].year == 2025 and c["no"] not in early and c is not fixc)
    lines = []
    for c in cons:
        rate = rng.choice([f"{c['bp'] / 100:.2f}%", f"연 {c['bp'] / 100:.2f}%", f"{c['bp'] / 100:.3f}"])
        lines.append([c["no"], _dt(c["st"], rng.choice(DATE_STYLES)), _amt(c["p"], rng.choice(["won", "plain", "man", "ko", "chun"]), rng),
                      rate, str(c["n"]), c["way"]])
    dups = [lines[i] for i in rng.sample(range(len(lines)), 4)]
    rows = lines + dups
    rng.shuffle(rows)
    c_tbl = _csv(["계약번호", "실행일", "원금", "연이율", "기간(개월)", "상환방식"], rows)
    memo = ["※ 조기상환(잔액 전액 상환): " + ", ".join(f"{k} {_dt(v, 'kor')}" for k, v in early.items()),
            f"※ {voidc['no']}는 계약만 하고 실행되지 않음(대장 삭제 예정) — 집계에서 제외.",
            f"※ {fixc['no']}의 기간은 계약서상 48개월입니다. 표의 36은 입력 오류이니 계약서를 따르세요."]

    def solve(dedupe=True, prepay=True, fix=True, void=True):
        txt = "\n".join(memo)
        ear = {k: _parse_dt(f"{y}년 {m}월 {d}일") for k, y, m, d in re.findall(r"(L-\d+) (\d{4})년 (\d+)월 (\d+)일", txt)}
        seen, interest, bal_end, closed = set(), 0, 0, 0
        for r in _a_csv_rows(c_tbl):
            if dedupe and r[0] in seen:
                continue
            seen.add(r[0])
            if void and r[0] == voidc["no"]:
                continue
            st, p = _parse_dt(r[1]), _parse_amt(r[2])
            bp = int(round(float(re.sub(r"[연%\s]", "", r[3])) * 100))
            n = int(r[4])
            if fix and r[0] == fixc["no"]:
                n = 48
            e = ear.get(r[0]) if prepay else None
            bal, end_on = p, None
            for k in range(1, n + 1):
                pdt = _a_addm(st, k)
                if pdt > date(2026, 12, 31) or (e and pdt > e):
                    break
                it = bal * bp // 120000
                pr = (p // n if k < n else bal) if r[5] == "원금균등" else (bal if k == n else 0)
                if pdt.year == 2026:
                    interest += it
                bal -= pr
                if bal == 0:
                    end_on = pdt
            if e and e <= date(2026, 12, 31) and bal > 0:
                bal, end_on = 0, e
            bal_end += bal
            closed += bool(end_on and end_on.year == 2026)
        return {"interest_2026": interest, "balance_end_2026": bal_end, "closed_2026": closed}

    truth = solve()
    wrong = _a_wrongs(solve, truth, {"dedupe": False}, {"prepay": False}, {"fix": False}, {"void": False})
    prompt = ("설비 할부 차입금 대장으로 2026년 이자비용과 연말 잔액을 계산해 주세요. 대장은 CSV이고 아래에 담당자 메모가 있습니다.\n\n"
              "[차입금 대장]\n" + c_tbl + "\n\n[메모]\n" + "\n".join(memo) + "\n\n규칙:\n"
              "1. 같은 계약번호 줄이 두 번 이상 있으면 한 번만 셉니다. 원금 단위와 날짜 형식, 이율 표기('4.85%', '연 4.85%', '4.850')가 섞여 있습니다.\n"
              "2. 상환일은 실행일로부터 매달 같은 날짜입니다(1회차 = 실행일의 1개월 뒤, n회차 = n개월 뒤).\n"
              "3. 회차별 이자 = 직전 잔액 × 연이율 ÷ 12, 원 미만 버림. 이자는 상환일이 속한 해의 비용입니다.\n"
              "4. 원금균등: 1~(n−1)회차 원금 = 원금 ÷ 기간(원 미만 버림), 마지막 회차에 남은 잔액 전부. 만기일시: 마지막 회차에 원금 전부, 그 전에는 이자만.\n"
              "5. 조기상환일에는 그날까지의 정기 회차(그날이 상환일이면 그 회차 포함)를 마친 뒤 남은 잔액을 모두 갚고, 그 뒤로는 이자가 없습니다. "
              "조기상환 자체에는 추가 이자가 없습니다.\n"
              "6. 메모의 실행 제외 계약은 빼고, 기간 정정은 계약서 기간을 씁니다.\n\n"
              "2026년 이자비용 합계(상환일이 2026년인 회차), 2026년 12월 31일 현재 잔액 합계, 2026년 중에 잔액이 0이 된 계약 수(조기상환 포함)를 알려주세요. "
              + JSON_RULE + '{"interest_2026": 원(정수), "balance_end_2026": 원(정수), "closed_2026": 건수(정수)}')
    _add(9, "acct_loan", prompt, {"interest_2026": "int", "balance_end_2026": "int", "closed_2026": "int"}, truth, wrong,
         {"rows": len(rows), "tables": 2, "steps": 6,
          "mess": ["duplicates", "unit_mix", "korean_amount", "rate_formats", "date_formats", "memo_exclusion",
                   "contradiction_term"]})


# ----------------------------------------------------------------- hk_10 외화 채권·채무 기말 평가


def _hk10():
    rng = random.Random(1010)
    end_rate = {"USD": 138420, "EUR": 151275, "JPY": 91890, "CNY": 19214}
    kinds = ["외화매출채권", "외화매출채권", "외화매입채무", "외화매입채무", "외화선급금", "외화선수금"]
    items = []
    for i in range(132):
        cu = rng.choices(["USD", "EUR", "JPY", "CNY"], [5, 3, 2, 2])[0]
        amt = rng.randrange(500, 200000) * 100 if cu != "JPY" else rng.randrange(100, 20000) * 1000
        d = date(2026, 1, 1) + timedelta(days=rng.randrange(0, 364))
        br = end_rate[cu] + rng.randrange(-9000, 9000) * end_rate[cu] // 140000
        items.append(dict(no=f"FX{i + 1:03d}", k=rng.choice(kinds), co=rng.choice(LATIN_CO), cu=cu, amt=amt, d=d, br=br))
    rows = []
    for x in items:
        a = f"{x['amt']:,}" if x["cu"] == "JPY" else f"{x['amt'] / 100:,.2f}"
        rows.append([x["no"], x["k"], _co_var(x["co"], rng), x["cu"], a, _dt(x["d"], rng.choice(DATE_STYLES)),
                     f"{x['br'] / 100:,.2f}"])
    i_tbl = _tsv(["관리번호", "구분", "거래처", "통화", "외화금액", "발생일", "장부환율"], rows)
    sets = []
    for x in rng.sample(items, 52):
        frac = rng.choice([1, 1, 0.5, 0.3])
        a = x["amt"] if frac == 1 else int(x["amt"] * frac) // 100 * 100
        d = x["d"] + timedelta(days=rng.randrange(5, 120))
        sets.append([x["no"], d, a, x["cu"]])
    sets.sort(key=lambda s: s[1])
    s_rows = [[f"S-{i + 1:03d}", s[0], _dt(s[1], rng.choice(DATE_STYLES)),
               f"{s[2]:,}" if s[3] == "JPY" else f"{s[2] / 100:,.2f}"] for i, s in enumerate(sets)]
    s_rows += [s_rows[i] for i in rng.sample(range(len(s_rows)), 4)]
    s_csv = _csv(["정산번호", "관리번호", "회수·지급일", "외화금액"], s_rows)
    r_tbl = _md(["통화", "기말 매매기준율(원)"], [("USD", "1,384.20"), ("EUR", "1,512.75"), ("JPY(100엔)", "918.90"),
                                             ("CNY", "192.14")])
    notice = "[자금팀 공지] 연말 USD 기준율은 1,348.20원입니다. (표와 다르면 표 숫자가 은행 확인값이니 표를 쓰세요.)"

    def solve(dedupe=True, cutoff=True, nonmon=True, notice_rate=False, jpy100=True):
        rt = {}
        for c, v in _a_md_rows(r_tbl):
            rt[c[:3]] = _a_fx(v)
        if notice_rate:
            rt["USD"] = 134820
        st, seen = {}, set()
        for r in _a_csv_rows(s_csv):
            if dedupe and r[0] in seen:
                continue
            seen.add(r[0])
            if cutoff and _parse_dt(r[2]) > date(2026, 12, 31):
                continue
            st[r[1]] = st.get(r[1], 0) + _a_fx(r[3])
        gain = loss = 0
        for no, k, co, cu, a, d, br in _a_cells(i_tbl):
            if nonmon and k in ("외화선급금", "외화선수금"):
                continue
            rem = _a_fx(a) - st.get(no, 0)
            if rem <= 0:
                continue
            mul = 1 if (cu != "JPY" or jpy100) else 100
            bk = rem * _a_fx(br) * mul // 10000
            en = rem * rt[cu] * mul // 10000
            diff = en - bk if "채권" in k or "선급" in k else bk - en
            if diff > 0:
                gain += diff
            else:
                loss -= diff
        return {"gain_total": gain, "loss_total": loss, "net_gain": gain - loss}

    truth = solve()
    wrong = _a_wrongs(solve, truth, {"dedupe": False}, {"cutoff": False}, {"nonmon": False}, {"notice_rate": True},
                      {"jpy100": False})
    prompt = ("2026년 결산 외화환산 평가를 부탁합니다. 외화 채권·채무 원장(탭 구분), 회수·지급 정산 내역(CSV), 기말 환율표를 붙입니다.\n\n"
              "[외화 원장] (JPY 금액은 엔, 나머지는 소수 둘째 자리까지. 장부환율은 USD·EUR·CNY 1단위당 원, JPY 100엔당 원)\n" + i_tbl +
              "\n\n[회수·지급 정산 내역]\n" + s_csv + "\n\n[기말 환율표]\n" + r_tbl + "\n\n" + notice + "\n\n규칙:\n"
              "1. 정산 내역에 같은 정산번호가 두 번 이상 있으면 한 번만 반영합니다. 정산일이 2026-12-31보다 늦은 정산은 기말 잔액에 반영하지 않습니다.\n"
              "2. 기말 외화잔액 = 원장 외화금액 − 반영할 정산 외화금액 합계. 잔액이 0 이하인 항목은 평가하지 않습니다.\n"
              "3. 외화선급금·외화선수금은 비화폐성 항목이라 평가하지 않습니다.\n"
              "4. 항목별로 장부 원화 = 외화잔액 × 장부환율, 기말 원화 = 외화잔액 × 기말환율을 각각 원 미만 버림으로 구합니다(JPY는 ÷100 후 곱함).\n"
              "5. 외화매출채권은 (기말 원화 − 장부 원화), 외화매입채무는 (장부 원화 − 기말 원화)가 항목별 평가손익입니다. 양수는 이익, 음수는 손실.\n"
              "6. 기말환율이 두 곳에서 다르게 나오면 공지 안내대로 환율표 숫자를 씁니다.\n\n"
              "외화환산이익 합계, 외화환산손실 합계(양수로), 순이익(이익 − 손실, 음수 가능)을 알려주세요. "
              + JSON_RULE + '{"gain_total": 원(정수), "loss_total": 원(정수), "net_gain": 원(정수)}')
    _add(10, "acct_fxeval", prompt, {"gain_total": "int", "loss_total": "int", "net_gain": "int"}, truth, wrong,
         {"rows": len(rows) + len(s_rows) + 4, "tables": 3, "steps": 6,
          "mess": ["duplicates", "cutoff_rows", "date_formats", "name_variants", "currency_units",
                   "contradiction_rate_notice"]})


# ----------------------------------------------------------------- 인사·급여 helpers


def _a_names(rng, n):
    sur = "김이박최정강조윤장임한오서신권황안송류홍"
    syl = "민서지현우준도하윤수아은재영호성진혜원태유나"
    out, seen = [], set()
    while len(out) < n:
        nm = rng.choice(sur) + rng.choice(syl) + rng.choice(syl)
        if nm not in seen and nm[1] != nm[2]:
            seen.add(nm)
            out.append(nm)
    return out


def _a_hm(m, style):
    """Minutes since midnight -> '08:35' / '8:35' / '오후 7:35' / '19시35분'."""
    h, mi = divmod(m, 60)
    if style == 0:
        s = f"{h:02d}:{mi:02d}"
    elif style == 1:
        s = f"{h}:{mi:02d}"
    elif style == 2:
        s = (f"오전 {h if h else 12}:{mi:02d}" if h < 12 else f"오후 {h - 12 if h > 12 else 12}:{mi:02d}")
    else:
        s = f"{h}시{mi:02d}분"
    assert _a_parse_hm(s) == m, (m, s)
    return s


def _a_parse_hm(s):
    s = s.strip()
    m = re.fullmatch(r"(오전|오후) (\d{1,2}):(\d{2})", s)
    if m:
        h = int(m.group(2)) % 12 + (12 if m.group(1) == "오후" else 0)
        return h * 60 + int(m.group(3))
    m = re.fullmatch(r"(\d{1,2})(?::|시)(\d{2})분?", s)
    return int(m.group(1)) * 60 + int(m.group(2))


# ----------------------------------------------------------------- hk_11 연장·야간·휴일 근로수당


def _hk11():
    rng = random.Random(1011)
    names = _a_names(rng, 12)
    emps = [(f"E{2101 + i}", names[i], rng.randrange(1003, 2600) * 10, rng.choice([0, 30, 60, 120, 180, 210, 240])) for i in range(12)]
    contra = emps[5]
    e_rows = []
    for no, nm, w, _ in emps:
        if no == contra[0]:
            e_rows.append((no, nm, f"{w - 870:,}", "2026-03-01"))
            e_rows.append((no, nm, f"{w:,}", "2026-08-01"))
        else:
            e_rows.append((no, nm, f"{w:,}", "2026-01-01"))
    e_tbl = _md(["사번", "성명", "통상시급(원)", "적용일"], e_rows)
    hol = set(d for d in HOLIDAYS_2026 if d.month == 9)
    offs = [d for d in _days(date(2026, 9, 1), date(2026, 9, 30)) if not _is_biz(d, hol)]
    recs = []
    for d in _days(date(2026, 9, 1), date(2026, 9, 30)):
        biz = _is_biz(d, hol)
        for no, nm, w, late in emps:
            if biz:
                if rng.random() < 0.06:
                    recs.append([d, no, nm, None, None, "연차"])
                    continue
                if rng.random() < 0.06:
                    continue
                s = rng.randrange(90, 115) * 5
                e = s + 9 * 60 + rng.randrange(0, late + 40) // 5 * 5 + (rng.randrange(60, 240) if rng.random() < 0.08 else 0)
            else:
                if rng.random() > 0.16:
                    continue
                s = rng.randrange(108, 156) * 5
                e = s + rng.randrange(36, 132) * 5
            e = min(e, 1440 + 110)
            recs.append([d, no, nm, s, e, ""])
    lines = []
    for d, no, nm, s, e, memo in recs:
        ss = _a_hm(s, rng.randrange(4)) if s is not None else ""
        es = _a_hm(e % 1440, rng.randrange(4)) if e is not None else ""
        lines.append("\t".join([_dt(d, rng.choice(["md", "iso", "dots", "mdk"])), no, _person_var(nm, rng), ss, es, memo]))
    extra = [lines[i] for i in rng.sample(range(len(lines)), 6)]
    extra += ["# 9/15 근태 시스템 점검 — 이날 기록은 수기 입력분", "# 9/24~9/26 추석 연휴"]
    lines = _a_shuffle_insert(rng, lines, extra)
    a_tbl = "날짜\t사번\t성명\t출근\t퇴근\t비고\n" + "\n".join(lines)

    def solve(dedupe=True, cap=True, brk=True, holiday=True, latest=True):
        rate = {}
        for no, nm, w, ad in _a_md_rows(e_tbl):
            ad = _parse_dt(ad)
            if no not in rate or (ad > rate[no][1]) == latest:
                rate[no] = (int(w.replace(",", "")), ad, nm)
        offset = {(d.month, d.day) for d in offs}
        seen, st = set(), {}
        for ln in a_tbl.split("\n")[1:]:
            if ln.startswith("#"):
                continue
            c = ln.split("\t")
            key = (c[0], c[1], c[3], c[4])
            if dedupe and key in seen:
                continue
            seen.add(key)
            if not c[3]:
                continue
            d = _parse_dt(c[0], 2026)
            s, e = _a_parse_hm(c[3]), _a_parse_hm(c[4])
            if e < s:
                e += 1440
            stay = e - s
            b = (60 if stay >= 540 else 30 if stay >= 240 else 0) if brk else 0
            work = stay - b
            night = max(0, min(e, 1800) - max(s, 1320))
            x = st.setdefault(c[1], [0, 0, 0, 0])
            if holiday and (d.month, d.day) in offset:
                x[1] += min(work, 480)
                x[2] += max(0, work - 480)
            else:
                x[0] += max(0, work - 480)
            x[3] += night
        pay, tot, nm_all = {}, 0, 0
        for no in sorted(st):
            ot, h8, hx, ni = st[no]
            if cap:
                ot = min(ot, 2400)
            p = rate[no][0] * (3 * ot + 3 * h8 + 4 * hx + ni) // 120
            pay[rate[no][2]] = p
            tot += p
            nm_all += ni
        return {"total_allowance": tot, "top_employee": _argmax(pay)[0], "night_minutes": nm_all}

    truth = solve()
    wrong = _a_wrongs(solve, truth, {"dedupe": False}, {"cap": False}, {"brk": False}, {"holiday": False},
                      {"latest": False})
    prompt = ("9월 근로수당(연장·야간·휴일)을 계산해 주세요. 출퇴근 기록(탭 구분, 날짜는 모두 2026년)과 직원 시급표를 붙입니다.\n\n"
              "[출퇴근 기록]\n" + a_tbl + "\n\n[직원 시급표]\n" + e_tbl + "\n\n"
              "[9월 휴일(주말·공휴일)] " + ", ".join(f"9/{d.day}" for d in offs) + "\n\n규칙:\n"
              "1. '#'으로 시작하는 줄은 메모입니다. 날짜·사번·출근·퇴근이 모두 같은 줄이 두 번 이상 있으면 한 번만 셉니다. "
              "출퇴근 시각이 없는 줄(연차 등)은 근무가 없는 날입니다.\n"
              "2. 시각 표기가 섞여 있습니다('08:35', '8:35', '오후 7:35', '19시35분'). 퇴근 시각이 출근 시각보다 이르면 다음 날 새벽 퇴근입니다.\n"
              "3. 체류시간 = 퇴근 − 출근. 휴게: 체류 9시간 이상이면 60분, 4시간 이상 9시간 미만이면 30분, 4시간 미만이면 0분. "
              "실근로 = 체류 − 휴게.\n"
              "4. 평일: 실근로 중 8시간(480분)을 넘는 부분이 연장근로이고 1.5배를 지급합니다(8시간까지는 월급에 포함). "
              "휴일: 실근로 중 8시간까지는 1.5배, 8시간을 넘는 부분은 2.0배를 지급합니다.\n"
              "5. 야간: 22:00~다음 날 06:00 사이에 걸친 체류 분은 평일·휴일 상관없이 0.5배를 추가로 지급합니다(휴게는 야간이 아닌 시간에 쓴 것으로 봅니다).\n"
              "6. 상한: 평일 연장근로는 1인당 월 40시간(2,400분)까지만 수당을 지급하고 넘는 분은 지급하지 않습니다. 휴일·야간은 상한이 없습니다.\n"
              "7. 1인 수당 = 통상시급 × (1.5×평일연장분 + 1.5×휴일 8시간 이내분 + 2.0×휴일 8시간 초과분 + 0.5×야간분) ÷ 60, 원 미만 버림. "
              "시급표에 같은 사번이 두 줄이면 적용일이 늦은 줄의 시급을 씁니다.\n\n"
              "전 직원 수당 합계, 수당이 가장 많은 직원 성명, 전 직원 야간 근로 분 합계를 알려주세요. "
              + JSON_RULE + '{"total_allowance": 원(정수), "top_employee": 성명, "night_minutes": 분(정수)}')
    _add(11, "hr_overtime", prompt, {"total_allowance": "int", "top_employee": "str", "night_minutes": "int"}, truth, wrong,
         {"rows": len(lines) + len(e_rows), "tables": 2, "steps": 7,
          "mess": ["duplicates", "memo_line", "time_formats", "date_formats", "name_variants", "overnight",
                   "contradiction_rate_rows"]})


# ----------------------------------------------------------------- hk_12 급여 공제 계산


def _hk12():
    rng = random.Random(1012)
    names = _a_names(rng, 132)
    emps = []
    for i in range(132):
        job = rng.choice(["사무", "사무", "생산"])
        base = rng.randrange(180, 650) * 10000 if job == "사무" else rng.randrange(170, 320) * 10000
        emps.append(dict(no=f"S{3001 + i}", nm=names[i], job=job, base=base,
                         pos=rng.choice([0, 0, 100000, 300000, 500000]) if job == "사무" else rng.choice([0, 0, 50000]),
                         meal=rng.choice([100000, 150000, 200000, 200000, 250000, 300000]),
                         car=rng.choice([0, 0, 200000, 300000]), ot=rng.randrange(0, 80) * 10000 if job == "생산" else
                         rng.choice([0, rng.randrange(0, 40) * 10000]), veh=rng.choice(["Y", "N"]),
                         fam=rng.randrange(1, 6)))
    quit_ = rng.sample(emps, 2)
    bal = [e for e in emps if e not in quit_]
    order_ = [e for e in emps if e["job"] == "사무"] + [e for e in emps if e["job"] == "생산"]
    order_d = rng.sample(bal, 3)
    contra = order_d[0]
    new_base = {e["no"]: (e["base"] + 250000 if e is contra else e["base"]) for e in order_d}
    lines = []
    for grp in ("사무", "생산"):
        sub = 0
        for e in [x for x in order_ if x["job"] == grp]:
            vals = [e["base"], e["pos"], e["meal"], e["car"], e["ot"]]
            sub += sum(vals)
            cells = [e["no"], _person_var(e["nm"], rng), e["job"]]
            cells += [_amt(v, rng.choice(["plain", "won", "man"]), rng) if v else "0" for v in vals]
            cells += [e["veh"], str(e["fam"])]
            lines.append(cells)
        lines.append(["", f"{grp}직 소계", "", _amt(sub, "plain"), "", "", "", "", "", ""])
    dups = [lines[i] for i in rng.sample([j for j, l in enumerate(lines) if l[0]], 4)]
    body = [",".join(_csv_cell(c) for c in l) for l in lines]
    body = _a_shuffle_insert(rng, body, [",".join(_csv_cell(c) for c in l) for l in dups])
    p_tbl = "사번,성명,직군,기본급,직책수당,식대,자가운전보조금,연장수당,차량보유,부양가족수(본인포함)\n" + "\n".join(body)
    memo = ([f"※ {e['no']} {e['nm']}: 9월 20일 퇴사, 이번 달 급여는 별도 정산하므로 대장 계산에서 제외." for e in quit_] +
            [f"※ 인사발령: {e['no']} {e['nm']} 9월 1일부로 기본급 {_amt(new_base[e['no']], 'man')}" for e in order_d])

    def solve(dedupe=True, meal_cap=True, car_veh=True, pcap=True, order=True):
        txt = "\n".join(memo)
        q = set(re.findall(r"※ (S\d+) \S+: 9월 20일 퇴사", txt))
        nb = {k: _parse_amt(v) for k, v in re.findall(r"인사발령: (S\d+) \S+ 9월 1일부로 기본급 (\S+)", txt)}
        seen = set()
        tnet = ttax = tpen = 0
        for c in _a_csv_rows(p_tbl):
            if not c[0]:
                continue
            if dedupe and c[0] in seen:
                continue
            seen.add(c[0])
            if c[0] in q:
                continue
            base, pos, meal, car, ot = (_parse_amt(x) for x in c[3:8])
            if order and c[0] in nb:
                base = nb[c[0]]
            gross = base + pos + meal + car + ot
            nt = min(meal, 200000) if meal_cap else meal
            nt += (min(car, 200000) if (c[8] == "Y" or not car_veh) else 0)
            if c[2] == "생산" and base + pos <= 2100000:
                nt += ot
            tx = gross - nt
            pen = _floor10((min(max(tx, 400000), 6370000) if pcap else tx) * 475 // 10000)
            hl = _floor10(tx * 3595 // 100000)
            lt = _floor10(hl * 1314 // 10000)
            em = _floor10(tx * 9 // 1000)
            if tx <= 1500000:
                it = 0
            elif tx <= 3000000:
                it = (tx - 1500000) * 6 // 100
            elif tx <= 5000000:
                it = 90000 + (tx - 3000000) * 15 // 100
            else:
                it = 390000 + (tx - 5000000) * 24 // 100
            it = _floor10(max(0, it - 12500 * (int(c[9]) - 1)))
            lc = _floor10(it // 10)
            tnet += gross - pen - hl - lt - em - it - lc
            ttax += it
            tpen += pen
        return {"total_net_pay": tnet, "total_income_tax": ttax, "total_pension": tpen}

    truth = solve()
    wrong = _a_wrongs(solve, truth, {"dedupe": False}, {"meal_cap": False}, {"car_veh": False}, {"pcap": False},
                      {"order": False})
    prompt = ("9월 급여 대장으로 공제액과 실지급액을 계산해 주세요. 대장(CSV)과 인사팀 메모를 붙입니다. 금액 단위는 칸마다 섞여 있습니다(원, 만원).\n\n"
              "[급여 대장]\n" + p_tbl + "\n\n[메모]\n" + "\n".join(memo) + "\n\n규칙:\n"
              "1. '소계' 줄은 합계 줄이라 무시합니다. 같은 사번 줄이 두 번 이상 있으면 한 번만 셉니다. 메모의 퇴사자는 계산에서 뺍니다.\n"
              "2. 인사발령 기본급이 대장과 다르면 발령 금액을 씁니다.\n"
              "3. 총지급 = 기본급 + 직책수당 + 식대 + 자가운전보조금 + 연장수당.\n"
              "4. 비과세: 식대는 월 200,000원까지. 자가운전보조금은 차량보유가 Y인 사람만 월 200,000원까지(N이면 전액 과세). "
              "연장수당은 직군이 생산이고 (기본급 + 직책수당)이 2,100,000원 이하인 사람만 전액 비과세.\n"
              "5. 과세급여 = 총지급 − 비과세.\n"
              "6. 국민연금 = 과세급여 × 4.75%. 단 과세급여가 6,370,000원을 넘으면 6,370,000원, 400,000원 미만이면 400,000원으로 보고 계산. "
              "건강보험 = 과세급여 × 3.595%. 장기요양 = 건강보험료 × 13.14%. 고용보험 = 과세급여 × 0.9%.\n"
              "7. 소득세(간이 기준): 과세급여 150만원 이하 0원 / 300만원 이하 (과세급여−150만원)×6% / 500만원 이하 9만원+(과세급여−300만원)×15% / "
              "500만원 초과 39만원+(과세급여−500만원)×24%. 여기서 본인 외 부양가족 1명당 12,500원을 빼고, 음수면 0원. 지방소득세 = 소득세 × 10%.\n"
              "8. 모든 보험료·세금은 사람별로 계산해 원 미만과 10원 미만을 버립니다(장기요양은 버림한 건강보험료로 계산).\n"
              "9. 실지급 = 총지급 − 국민연금 − 건강보험 − 장기요양 − 고용보험 − 소득세 − 지방소득세.\n\n"
              "실지급액 합계, 소득세 합계, 국민연금 합계를 알려주세요. "
              + JSON_RULE + '{"total_net_pay": 원(정수), "total_income_tax": 원(정수), "total_pension": 원(정수)}')
    _add(12, "hr_payroll", prompt, {"total_net_pay": "int", "total_income_tax": "int", "total_pension": "int"}, truth, wrong,
         {"rows": len(body), "tables": 2, "steps": 9,
          "mess": ["duplicates", "subtotal", "unit_mix", "name_variants", "memo_exclusion", "contradiction_order"]})


# ----------------------------------------------------------------- hk_13 연차 잔여


def _hk13():
    rng = random.Random(1013)
    names = _a_names(rng, 90)
    emps = []
    for i in range(90):
        y = rng.choices([2026, 2025, 2024, 2022, 2020, 2017, 2014, 2010, 2005], [2, 2, 2, 2, 2, 2, 1, 1, 1])[0]
        h = date(y, rng.randrange(1, 13 if y < 2026 else 10), rng.randrange(1, 29))
        if i == 3:
            h = date(2025, 1, 1)
        emps.append(dict(no=f"H{1101 + i}", nm=names[i], h=h, co=rng.choice([0, 0, 1, 2, 3.5, 5, 6, 8, 2.5])))
    e_tbl = _md(["사번", "성명", "입사일", "2025년 이월(일)"],
                [(e["no"], e["nm"], _dt(e["h"], rng.choice(DATE_STYLES)), f"{e['co']:g}") for e in emps])
    hol = set(HOLIDAYS_2026)
    uses, n = [], 0
    for e in emps:
        k = rng.randrange(0, 5) if e["no"] not in ("H1110", "H1125", "H1170") else rng.randrange(24, 30)
        for _ in range(k):
            n += 1
            while True:
                d = date(2026, 1, 1) + timedelta(days=rng.randrange(0, 365))
                if d.weekday() < 5 and d >= e["h"]:
                    break
            uses.append([f"LV-{6000 + n}", e["no"], _person_var(e["nm"], rng), d,
                         rng.choices(["연차", "반차", "반반차"], [6, 3, 1])[0], rng.choices(["승인", "반려", "취소"], [12, 1, 1])[0]])
    for u in rng.sample(uses, 5):
        u[3] = rng.choice([x for x in sorted(hol) if x.weekday() < 5])
        u[5] = "승인"
    rows = [[u[0], u[1], u[2], _dt(u[3], rng.choice(DATE_STYLES)), u[4], u[5]] for u in uses]
    ctr = next(r for r in rows if r[4] == "연차" and r[5] == "승인")
    dups = [list(rows[i]) for i in rng.sample(range(len(rows)), 5)]
    c2 = list(ctr)
    c2[4] = "반차"
    rows += dups + [c2]
    rows.sort(key=lambda r: r[0])
    u_tbl = _tsv(["신청번호", "사번", "성명", "사용일", "종류", "상태"], rows)
    hol_txt = ", ".join(f"{d.month}/{d.day}" for d in sorted(hol))

    def solve(later=True, carry_cap=True, hol_rule=True, status=True, dedupe=True, strict=False):
        base = date(2026, 1, 1)
        grant = {}
        for no, nm, hd, co in _a_md_rows(e_tbl):
            h = _parse_dt(hd)
            if h.year == 2026:
                g = sum(1 for k in range(1, 12) if _a_addm(h, k) <= date(2026, 12, 31))
            else:
                y = base.year - h.year - (1 if (h.month, h.day) > (base.month, base.day) else 0)
                g = 11 if y < 1 else min(25, 15 + (y - 1) // 2)
            grant[no] = [nm, g + (min(float(co), 5) if carry_cap else float(co))]
        hs = {(int(a), int(b)) for a, b in (x.split("/") for x in hol_txt.split(", "))}
        req = {}
        seen = set()
        for c in _a_cells(u_tbl):
            if not dedupe:
                req[(c[0], len(seen))] = c
                seen.add(len(seen))
                continue
            if c[0] in req and not later:
                continue
            req[c[0]] = c
        used = {}
        for k in sorted(req, key=str):
            no_, sab, nm, ds, kd, stt = req[k]
            if status and stt != "승인":
                continue
            d = _parse_dt(ds)
            if hol_rule and (d.month, d.day) in hs:
                continue
            used[sab] = used.get(sab, 0) + {"연차": 1, "반차": 0.5, "반반차": 0.25}[kd]
        rem = {no: (v[0], v[1] - used.get(no, 0)) for no, v in grant.items()}
        tot = round(sum(r for _, r in rem.values()), 2)
        neg = sorted(nm for nm, r in rem.values() if r < 0)
        rd = {nm: r for nm, r in rem.values()}
        top = _argmax(rd)[0] if strict else sorted(rd.items(), key=lambda x: (-x[1], x[0]))[0][0]
        return {"total_remaining": tot, "negative_names": neg, "top_remaining": top}

    truth = solve(strict=True)
    assert truth["negative_names"], truth
    wrong = _a_wrongs(solve, truth, {"carry_cap": False}, {"hol_rule": False}, {"status": False}, {"dedupe": False},
                      {"later": False})
    prompt = ("2026년 연차 잔여일수를 정리해 주세요. 직원 명부(마크다운 표)와 2026년 휴가 신청 내역(탭 구분)을 붙입니다.\n\n"
              "[직원 명부]\n" + e_tbl + "\n\n[휴가 신청 내역]\n" + u_tbl + "\n\n[2026년 공휴일] " + hol_txt + "\n\n규칙:\n"
              "1. 2026년 부여일수: (가) 2026년 입사자는 입사일로부터 1개월이 될 때마다 1일씩, 2026-12-31까지 발생한 만큼(최대 11일). "
              "(나) 2026-01-01 기준 근속 만 1년 미만(2025-01-02 이후 입사)은 11일. "
              "(다) 2026-01-01 기준 근속 만 1년 이상은 15일 + (만 근속연수 − 1) ÷ 2의 몫, 최대 25일. 입사일이 1월 1일이면 그날 만 1년이 찬 것으로 봅니다.\n"
              "2. 2025년 이월은 5일까지만 인정합니다(넘는 부분 소멸).\n"
              "3. 사용일수: 상태가 '승인'인 신청만 차감합니다. 연차 1일, 반차 0.5일, 반반차 0.25일. "
              "사용일이 공휴일 목록에 있으면 원래 쉬는 날이라 차감하지 않습니다.\n"
              "4. 같은 신청번호가 완전히 같은 내용으로 두 번 나오면 한 번만 셉니다. 같은 신청번호가 내용이 다르게 두 번 나오면 표에서 아래쪽 줄(나중 수정본)을 따릅니다.\n"
              "5. 잔여 = 부여일수 + 인정 이월 − 사용일수 (음수 가능). 성명은 명부 기준이며 신청 내역의 성명 공백 차이는 무시하고 사번으로 맞춥니다.\n\n"
              "전 직원 잔여일수 합계, 잔여가 음수인 직원 성명 목록(가나다순), 잔여가 가장 많은 직원 성명을 알려주세요. "
              + JSON_RULE + '{"total_remaining": 일수(숫자, 소수 가능), "negative_names": [성명, ...], "top_remaining": 성명}')
    _add(13, "hr_leave", prompt, {"total_remaining": "float", "negative_names": "list", "top_remaining": "str"}, truth, wrong,
         {"rows": len(emps) + len(rows), "tables": 2, "steps": 5,
          "mess": ["duplicates", "date_formats", "name_variants", "status_filter", "holiday_exception",
                   "contradiction_request_rows"]}, tol={"total_remaining": 0.001})


# ----------------------------------------------------------------- hk_14 성과급


def _hk14():
    rng = random.Random(1014)
    names = _a_names(rng, 152)
    depts = ["영업1팀", "영업2팀", "마케팅팀", "생산팀", "품질팀", "연구소", "경영지원팀"]
    ach = {"영업1팀": (1200, 1351), "영업2팀": (950, 902), "마케팅팀": (300, 279), "생산팀": (2100, 2163),
           "품질팀": (180, 151), "연구소": (420, 470), "경영지원팀": (90, 92)}
    a_rows = []
    for dp in depts:
        t, r = ach[dp]
        rs = rng.choice([f"{r}억원", f"{r * 100:,}백만원", _ko(r * 10**8, rng)])
        assert _parse_amt(rs) == r * 10**8
        a_rows.append((dp, f"{t}억원", rs))
    a_tbl = _md(["부서", "목표 매출", "실적 매출"], a_rows)
    ranks = [("사원", 5_000_000), ("대리", 7_000_000), ("과장", 10_000_000), ("차장", 13_000_000), ("부장", 15_000_000)]
    capm = dict(ranks)
    sal = {"사원": (3200, 4200), "대리": (4000, 5200), "과장": (5000, 6600), "차장": (6200, 8000), "부장": (7500, 10000)}
    emps = []
    for i in range(152):
        rk = rng.choices([r for r, _ in ranks], [5, 4, 3, 2, 1])[0]
        y = rng.choices([2026, 2025, 2020], [2, 2, 8])[0]
        h = date(y, rng.randrange(1, 13), rng.randrange(1, 29))
        emps.append(dict(no=f"P{4001 + i}", nm=names[i], dp=rng.choice(depts), rk=rk,
                         sal=rng.randrange(*sal[rk]) * 10000, h=h, lv=rng.choices([0, 0, 0, 0, 2, 3, 6], k=1)[0],
                         gr=rng.choices("SABCD", [1, 3, 5, 2, 1])[0]))
    appeal = rng.sample([e for e in emps if e["gr"] in "BC" and e["h"].year < 2026], 3)
    newg = {e["no"]: {"B": "A", "C": "B"}[e["gr"]] for e in appeal}
    retired = rng.sample([e for e in emps if e not in appeal and e["gr"] in "SAB"], 3)
    lines = []
    for e in emps:
        lines.append([e["no"], _person_var(e["nm"], rng), e["dp"], e["rk"],
                      _amt(e["sal"], rng.choice(["won", "plain", "man", "ko"]), rng), _dt(e["h"], rng.choice(DATE_STYLES)),
                      str(e["lv"]), e["gr"]])
    lines += [list(lines[i]) for i in rng.sample(range(len(lines)), 4)]
    rng.shuffle(lines)
    e_tbl = _tsv(["사번", "성명", "부서", "직급", "연봉", "입사일", "휴직개월", "평가등급"], lines)
    notes = ("[이의신청 결과] " + "; ".join(f"{e['no']} 등급 {e['gr']}→{newg[e['no']]} 조정" for e in appeal) +
             "\n[퇴직 예정(지급일 전 퇴직)] " + ", ".join(f"{e['no']}" for e in retired))

    def solve(appeal_rule=True, cap=True, prorate=True, retire=True, mult=True, dedupe=True):
        am = {}
        for dp, t, r in _a_md_rows(a_tbl):
            ratio = _parse_amt(r) * 1000 // _parse_amt(t)
            am[dp] = 12 if ratio >= 1100 else 10 if ratio >= 1000 else 8 if ratio >= 900 else 5
        ng = dict(re.findall(r"(P\d+) 등급 [A-D]→([A-S]) 조정", notes))
        ret = set(re.findall(r"P\d+", notes.split("[퇴직 예정")[1]))
        seen, tot, byd, capped = set(), 0, {}, 0
        for c in _a_cells(e_tbl):
            if dedupe and c[0] in seen:
                continue
            seen.add(c[0])
            no, nm, dp, rk, sl, hd, lv, gr = c
            h = _parse_dt(hd)
            if (retire and no in ret) or h >= date(2026, 10, 1):
                continue
            if appeal_rule and no in ng:
                gr = ng[no]
            pct = {"S": 200, "A": 150, "B": 100, "C": 50, "D": 0}[gr]
            months = max(0, 12 - int(lv) - ((h.month - 1) if h.year == 2026 else 0))
            if not prorate:
                months = 12
            amt = (_parse_amt(sl) // 12) * pct * (am[dp] if mult else 10) * months // (100 * 10 * 12)
            if cap and amt > capm[rk]:
                amt = capm[rk]
                capped += 1
            amt = amt // 1000 * 1000
            tot += amt
            byd[dp] = byd.get(dp, 0) + amt
        return {"total_bonus": tot, "top_dept": _argmax(byd)[0], "capped_count": capped}

    truth = solve()
    wrong = _a_wrongs(solve, truth, {"appeal_rule": False}, {"cap": False}, {"prorate": False}, {"retire": False},
                      {"mult": False})
    prompt = ("2026년 성과급 지급액을 계산해 주세요. 직원 평가표(탭 구분), 부서 실적표, 인사팀 공지를 붙입니다.\n\n"
              "[직원 평가표]\n" + e_tbl + "\n\n[부서 실적]\n" + a_tbl + "\n\n" + notes + "\n\n규칙:\n"
              "1. 같은 사번 줄이 두 번 이상 있으면 한 번만 셉니다. 연봉 단위(원·만원·한글 금액)와 날짜 형식이 섞여 있습니다.\n"
              "2. 지급 제외: 퇴직 예정자, 입사일이 2026-10-01 이후인 사람(평가 대상 기간 3개월 미만).\n"
              "3. 이의신청 결과가 있으면 평가표 등급 대신 조정된 등급을 씁니다.\n"
              "4. 월 기본급 = 연봉 ÷ 12 (원 미만 버림). 등급별 지급률: S 200%, A 150%, B 100%, C 50%, D 0%.\n"
              "5. 부서 달성률 = 실적 ÷ 목표. 부서 배수: 110% 이상 1.2, 100% 이상 110% 미만 1.0, 90% 이상 100% 미만 0.8, 90% 미만 0.5.\n"
              "6. 근무월수 = 12 − 휴직개월 − (2026년 입사자는 입사월 − 1), 음수면 0. 산정액 = 월 기본급 × 지급률 × 부서 배수 × 근무월수 ÷ 12, 원 미만 버림.\n"
              "7. 직급별 상한: 사원 500만원, 대리 700만원, 과장 1,000만원, 차장 1,300만원, 부장 1,500만원. 산정액이 상한을 넘으면 상한액을 지급합니다.\n"
              "8. 최종 지급액은 1,000원 미만을 버립니다.\n\n"
              "성과급 총액, 지급 총액이 가장 큰 부서, 상한이 적용된 인원 수를 알려주세요. "
              + JSON_RULE + '{"total_bonus": 원(정수), "top_dept": 부서명, "capped_count": 명(정수)}')
    _add(14, "hr_bonus", prompt, {"total_bonus": "int", "top_dept": "str", "capped_count": "int"}, truth, wrong,
         {"rows": len(lines) + len(a_rows), "tables": 2, "steps": 8,
          "mess": ["duplicates", "unit_mix", "korean_amount", "date_formats", "name_variants", "exclusion_list",
                   "contradiction_appeal"]})


# ----------------------------------------------------------------- hk_15 퇴직금


def _hk15():
    rng = random.Random(1015)
    names = _a_names(rng, 28)
    ppl = []
    for i in range(28):
        q = date(2026, rng.randrange(3, 12), rng.randrange(1, 29))
        h = date(rng.randrange(2012, 2025), rng.randrange(1, 13), rng.randrange(1, 29)) if i % 9 else \
            q - timedelta(days=rng.randrange(120, 360))
        monthly = rng.randrange(250, 700) * 10000
        ppl.append(dict(no=f"R{701 + i}", nm=names[i], h=h, q=q, m=monthly, ord=monthly * rng.randrange(80, 95) // 100 // 1000 * 1000,
                        lv=rng.choice([0, 0, rng.randrange(20, 120) * 10000])))
    low = [ppl[2], ppl[13]]
    l_rows = [(p["no"], p["nm"], _dt(p["h"], rng.choice(DATE_STYLES)), _dt(p["q"], rng.choice(DATE_STYLES)),
               _amt(p["ord"], rng.choice(["won", "man"])), _amt(p["lv"], "won") if p["lv"] else "0") for p in ppl]
    l_tbl = _md(["사번", "성명", "입사일", "퇴직일", "월 통상임금", "전년도 연차수당"], l_rows)
    w_rows = []
    contra = ppl[5]
    for p in ppl:
        for back in (4, 3, 2, 1, 0):
            mm = p["q"].month - back
            y = 2026
            if mm <= 0:
                mm += 12
                y -= 1
            amt = p["m"] + rng.randrange(0, 60) * 10000
            if p in low and back in (1, 2):
                amt = p["m"] // 5 // 10000 * 10000
            memo = "퇴직월 일할" if back == 0 else ""
            if back == 0:
                amt = amt * p["q"].day // 30 // 10 * 10
            w_rows.append([p["no"], f"{y}-{mm:02d}", _amt(amt, rng.choice(["won", "plain", "man"]) if amt % 1000 == 0 else "won"), memo])
            if p is contra and back == 2:
                w_rows.append([p["no"], f"{y}-{mm:02d}", _amt(amt + 1_200_000, "won"), "정정(소급분 반영)"])
    w_rows += [list(w_rows[i]) for i in rng.sample(range(len(w_rows)), 3)]
    rng.shuffle(w_rows)
    w_tbl = _tsv(["사번", "귀속월", "지급액", "비고"], w_rows)
    b_rows = []
    for p in ppl:
        for _ in range(rng.randrange(2, 5)):
            d = p["q"] - timedelta(days=rng.randrange(10, 540))
            b_rows.append([p["no"], _dt(d, rng.choice(DATE_STYLES)), _amt(rng.randrange(50, 400) * 10000,
                                                                           rng.choice(["won", "man", "ko"]), rng)])
    b_rows.sort(key=lambda r: r[0])
    b_csv = _csv(["사번", "지급일", "상여금"], b_rows)

    def solve(window=3, bonus_q=True, floor_ord=True, fix=True, dedupe=True, bonus_window=True):
        info = {}
        for no, nm, hd, qd, od, lv in _a_md_rows(l_tbl):
            info[no] = dict(nm=nm, h=_parse_dt(hd), q=_parse_dt(qd), o=_parse_amt(od), lv=_parse_amt(lv))
        wages = {}
        seen = set()
        for no, ym, a, memo in _a_cells(w_tbl):
            key = (no, ym, a, memo)
            if dedupe and key in seen:
                continue
            seen.add(key)
            k = (no, ym)
            if k in wages and dedupe:
                if fix == ("정정" in memo):
                    wages[k] = _parse_amt(a)
            elif k in wages:
                wages[k] += _parse_amt(a)
            else:
                wages[k] = _parse_amt(a)
        bon = {}
        for no, d, a in _a_csv_rows(b_csv):
            d = _parse_dt(d)
            q = info[no]["q"]
            if not bonus_window or (date(q.year - 1, q.month, q.day) < d < q):
                bon[no] = bon.get(no, 0) + _parse_amt(a)
        tot, inel, pay = 0, 0, {}
        for no in sorted(info):
            x = info[no]
            q = x["q"]
            ms = []
            for back in range(1, window + 1):
                mm, y = q.month - back, q.year
                if mm <= 0:
                    mm, y = mm + 12, y - 1
                ms.append((y, mm))
            days = sum(((date(y + (m == 12), m % 12 + 1, 1)) - date(y, m, 1)).days for y, m in ms)
            W = sum(wages[(no, f"{y}-{m:02d}")] for y, m in ms)
            B, L = bon.get(no, 0), x["lv"]
            avg = (W * 12 + ((B + L) * 3 if bonus_q else (B + L) * 12)) // (12 * days)
            od = x["o"] * 8 // 209
            if floor_ord and avg < od:
                avg = od
            served = (q - x["h"]).days
            if served < 365:
                inel += 1
                continue
            s = avg * 30 * served // 365
            tot += s
            pay[x["nm"]] = s
        return {"total_severance": tot, "ineligible_count": inel, "top_person": _argmax(pay)[0]}

    truth = solve()
    wrong = _a_wrongs(solve, truth, {"window": 4}, {"bonus_q": False}, {"floor_ord": False}, {"fix": False},
                      {"bonus_window": False})
    prompt = ("2026년 퇴직자들의 퇴직금을 계산해 주세요. 퇴직자 명단(마크다운), 월별 급여 지급 내역(탭 구분), 상여금 지급 내역(CSV)을 붙입니다.\n\n"
              "[퇴직자 명단]\n" + l_tbl + "\n\n[급여 지급 내역]\n" + w_tbl + "\n\n[상여금 지급 내역]\n" + b_csv + "\n\n규칙:\n"
              "1. 급여 내역에서 사번·귀속월·지급액·비고가 모두 같은 줄은 한 번만 셉니다. 같은 사번·귀속월에 금액이 다른 줄이 두 개 있으면 비고에 '정정'이 있는 줄만 씁니다.\n"
              "2. 3개월 임금총액 = 퇴직일이 속한 달의 직전 3개 귀속월(예: 8월 퇴직이면 5·6·7월) 지급액 합계. 퇴직월 일할분과 그보다 앞선 달은 넣지 않습니다. "
              "산정 일수 = 그 3개 달의 달력 일수 합계.\n"
              "3. 상여금은 지급일이 퇴직일 전 1년 이내(퇴직일 1년 전 같은 날짜보다 뒤이고 퇴직일보다 앞)인 것만 합산하고, 그 합계의 3/12를 더합니다. "
              "전년도 연차수당도 3/12을 더합니다.\n"
              "4. 1일 평균임금 = (3개월 임금총액 + 상여 합계×3/12 + 연차수당×3/12) ÷ 산정 일수, 원 미만 버림.\n"
              "5. 1일 통상임금 = 월 통상임금 × 8 ÷ 209, 원 미만 버림. 평균임금이 통상임금보다 적으면 통상임금을 평균임금으로 씁니다.\n"
              "6. 재직일수 = 퇴직일 − 입사일(일수). 재직일수가 365일 미만이면 퇴직금이 없습니다.\n"
              "7. 퇴직금 = 1일 평균임금 × 30 × 재직일수 ÷ 365, 원 미만 버림.\n\n"
              "퇴직금 총액, 퇴직금이 없는 인원 수, 퇴직금이 가장 많은 사람 성명을 알려주세요. "
              + JSON_RULE + '{"total_severance": 원(정수), "ineligible_count": 명(정수), "top_person": 성명}')
    _add(15, "hr_severance", prompt, {"total_severance": "int", "ineligible_count": "int", "top_person": "str"}, truth, wrong,
         {"rows": len(l_rows) + len(w_rows) + len(b_rows), "tables": 3, "steps": 7,
          "mess": ["duplicates", "unit_mix", "korean_amount", "date_formats", "noise_months", "window_filter",
                   "contradiction_correction"]})


# ================================================================= part B: 인사·급여 (16-20), 구매·재고 (21-30)


class _BRetry(Exception):
    pass


def _b_build(n, fn):
    """Run fn(rng) with seed 1000+n; on a tie or a non-discriminating wrong answer, retry with a fixed next seed."""
    for k in range(60):
        try:
            return fn(random.Random(1000 + n + 7919 * k))
        except _BRetry:
            continue
        except AssertionError as e:
            if e.args != ("tie",):
                raise
    raise RuntimeError(f"hk_{n}: no seed")


def _b_need(cond):
    if not cond:
        raise _BRetry()


def _b_wrongs(truth, cands):
    """Keep candidates that differ from truth on some key; need at least two."""
    out = []
    for c in cands:
        if any(c[k] != truth[k] for k in truth) and c not in out:
            out.append(c)
    _b_need(len(out) >= 2)
    return out


def _b_ceil(a, b):
    return -(-a // b)


def _b_insert(rng, lines, extra):
    """Insert extra lines at random positions (deterministic)."""
    lines = list(lines)
    for x in extra:
        lines.insert(rng.randrange(1, len(lines) + 1), x)
    return lines


def _b_dup(rng, rows, k):
    """Copy k random rows to random later positions (identical duplicates)."""
    rows = list(rows)
    for _ in range(k):
        i = rng.randrange(len(rows) - 1)
        j = rng.randrange(i + 1, len(rows) + 1)
        rows.insert(j, list(rows[i]))
    return rows


_B_SUR = "김이박최정강조윤장임한오서신권황안송류배문남백유노하곽성탁전홍구엄채차주우명변"
_B_GIV = ["민수", "서연", "지훈", "유진", "다은", "현우", "수아", "도현", "하린", "재원", "소희", "세훈", "지민", "동욱",
          "나래", "보람", "태준", "예린", "건우", "수빈", "가영", "승호", "하늘", "은지", "준서", "민재", "유리", "재훈",
          "소미", "본혁", "지원", "은우", "현영", "도윤", "세빈", "우석", "정민", "상우", "혜진", "영수"]


def _b_names(rng, k):
    pool = sorted({s + g for s in _B_SUR for g in _B_GIV})
    return rng.sample(pool, k)


def _b_time(h):
    return f"{h:02d}:00" if h < 24 else f"{h - 24:02d}:00(익일)"


def _b_ptime(s):
    m = re.fullmatch(r"(\d{2}):00(\(익일\))?", s.strip())
    return int(m.group(1)) + (24 if m.group(2) else 0)


# ---------------------------------------------------------------- hk_16 교대근무: 휴식시간 위반 + 야간수당


def _hk16():
    def build(rng):
        emps = rng.sample(PEOPLE, 12)
        prob = sorted(rng.sample(emps, 2))
        wage = {e: rng.randrange(100, 160) * 100 for e in emps}
        base = {"주간": (9, 18), "오후": (14, 23), "야간": (22, 31)}
        start = date(2026, 3, 2)
        raw = []
        for i in range(21):
            d = start + timedelta(days=i)
            for e in emps:
                if rng.random() < 0.27:
                    continue
                sh = rng.choice(["주간", "주간", "오후", "야간"])
                s, t = base[sh]
                if rng.random() < 0.12:
                    t += rng.choice([1, 2])
                raw.append([d, e, sh, s, t])
        rows = [[_dt(r[0], rng.choice(["iso", "dot", "dots", "md"])), _person_var(r[1], rng), r[2],
                 _b_time(r[3]), _b_time(r[4])] for r in raw]
        rows = _b_dup(rng, rows, 7)
        # contradiction: an 오후 row of a non-probation employee re-entered later with a corrected 퇴근
        cands = [i for i, r in enumerate(raw) if r[2] == "오후" and r[1] not in prob and r[4] == 23]
        ci = rng.choice(cands)
        c = raw[ci]
        fixed = [_dt(c[0], "iso"), c[1], "오후", _b_time(14), _b_time(25)]
        pos = next(i for i, r in enumerate(rows) if _parse_dt(r[0], 2026) == c[0] and _norm(r[1]) == _norm(c[1]))
        rows.insert(rng.randrange(pos + 1, len(rows) + 1), fixed)
        lines = ["\t".join(r) for r in rows]
        memos = ["※ 3/9 주간조 교육으로 일부 인원 오후조 전환", "※ 근무표 원본은 인사팀 공유폴더", "3월 2주차 소계\t\t\t근무 64건\t",
                 "※ 퇴근 (익일)은 다음날 시각"]
        lines = _b_insert(rng, lines, memos)
        table = "일자\t성명\t근무조\t출근\t퇴근\n" + "\n".join(lines)
        wtab = _md(["성명", "시급", "구분"], [[_person_var(e, rng), _amt(wage[e], rng.choice(["won", "plain", "krw"])),
                                         "수습" if e in prob else "정규"] for e in sorted(emps)])

        def solve(dedupe=True, later=True, probation=True, night_end=30):
            recs = {}
            order = []
            for ln in lines:
                cells = ln.split("\t")
                if len(cells) != 5 or "소계" in ln or ln.startswith("※"):
                    continue
                d = _parse_dt(cells[0], 2026)
                key = (d, _norm(cells[1]))
                val = (_b_ptime(cells[3]), _b_ptime(cells[4]))
                if key in recs and dedupe:
                    if recs[key] != val and later:
                        recs[key] = val
                    continue
                recs.setdefault(key, val)
                order.append((key, val))
            if dedupe:
                order = [(k, recs[k]) for k, _ in order]
            info = {}
            for ln in wtab.split("\n")[2:]:
                c = [x.strip() for x in ln.strip("|").split("|")]
                info[_norm(c[0])] = (_parse_amt(c[1]), c[2] == "수습")
            viol = {}
            pay = 0
            byemp = {}
            for (d, nm), (s, t) in order:
                off = (d - start).days * 24
                byemp.setdefault(nm, []).append((off + s, off + t))
            for nm in sorted(byemp):
                sh = sorted(byemp[nm])
                v = sum(1 for a, b in zip(sh, sh[1:]) if b[0] - a[1] < 11)
                viol[nm] = v
                nh = sum(max(0, min(t, 24 * k + night_end) - max(s, 24 * k + 22)) for s, t in sh for k in range(-1, 23))
                w, pr = info[nm]
                if not (pr and probation):
                    pay += _floor10(nh * w * 5 // 10)
            top = _argmax(viol)[0]
            name = next(e for e in emps if _norm(e) == top)
            return {"rest_violations": sum(viol.values()), "night_pay_total": pay, "top_violator": name}

        truth = solve()
        wrong = _b_wrongs(truth, [solve(dedupe=False), solve(later=False), solve(probation=False),
                                  solve(night_end=31)])
        prompt = ("3월 교대근무 기록을 엑셀에서 복사했습니다(탭 구분, 연도는 모두 2026년). 휴식시간 위반과 야간수당을 점검해 주세요.\n\n"
                  "[근무 기록]\n" + table + "\n\n[직원별 시급]\n" + wtab + "\n\n"
                  "규칙:\n"
                  "1. '※'로 시작하는 줄과 '소계' 줄은 기록이 아닙니다. 성명의 공백 차이는 같은 사람입니다.\n"
                  "2. 같은 직원·같은 일자에 내용이 똑같은 행이 여러 번 있으면 한 번만 셉니다. 같은 직원·같은 일자인데 출퇴근 시각이 "
                  "다른 행이 있으면, 표에서 더 아래에 있는 행(정정 입력)만 적용합니다.\n"
                  "3. 휴식시간 위반: 한 직원의 근무를 시작 시각 순으로 늘어놓았을 때, 앞 근무의 퇴근 시각부터 다음 근무의 출근 시각까지가 "
                  "11시간 미만이면 위반 1건입니다. '(익일)'은 다음날 시각입니다.\n"
                  "4. 야간시간은 22:00부터 다음날 06:00까지 사이에 근무한 시간입니다. 야간수당 = 야간시간 × 시급 × 0.5이고, 직원별 "
                  "월 합계에서 10원 미만을 버립니다.\n"
                  "5. 예외: 시급표에서 구분이 '수습'인 직원은 야간수당을 지급하지 않습니다(휴식시간 위반은 셉니다).\n\n"
                  "전체 휴식시간 위반 건수, 야간수당 지급 총액(원), 위반 건수가 가장 많은 직원 이름을 알려주세요. "
                  + JSON_RULE + '{"rest_violations": 정수, "night_pay_total": 정수, "top_violator": "이름"}')
        nrows = len(lines) + len(emps)
        _add(16, "hr_shift", prompt, {"rest_violations": "int", "night_pay_total": "int", "top_violator": "str"},
             truth, wrong, {"rows": nrows, "tables": 2, "steps": 5,
                            "mess": ["dup_rows", "contradiction_later_row", "memo", "subtotal", "date_mixed",
                                     "name_space", "overnight_time", "unit_mixed"]})
    _b_build(16, build)


# ---------------------------------------------------------------- hk_17 국내 출장비 정산


def _hk17():
    def build(rng):
        names = rng.sample(PEOPLE, 36)
        depts = ["영업1팀", "영업2팀", "생산관리팀", "품질팀", "구매팀", "기술연구소"]
        ranks = ["사원", "대리", "과장", "차장", "부장"]
        emp = []
        for i, nm in enumerate(names):
            emp.append((f"E{2100 + i * 7}", nm, rng.choice(depts), rng.choices(ranks, [5, 5, 4, 2, 1])[0]))
        per_diem = {"사원": 25000, "대리": 25000, "과장": 30000, "차장": 30000, "부장": 40000}
        lodge = {"사원": 70000, "대리": 70000, "과장": 80000, "차장": 80000, "부장": 100000}
        cities = ["서울", "부산", "대전", "광주", "울산", "창원", "전주", "강릉", "포항", "청주", "여수", "제주"]
        trips = []
        for k in range(125):
            e = rng.choice(emp)
            d0 = date(2026, 4, 1) + timedelta(days=rng.randrange(0, 85))
            nd = rng.choices([0, 1, 2, 3, 4], [3, 4, 3, 2, 1])[0]
            d1 = d0 + timedelta(days=nd)
            city = rng.choice(cities)
            lim = lodge[e[3]] * (12 if city in ("서울", "부산") else 10) // 10
            if nd == 0:
                lod = 0
            else:
                lod = nd * rng.randrange(lim // 1000 - 25, lim // 1000 + 18) * 1000
            if rng.random() < 0.3:
                trans = ("km", rng.randrange(40, 480))
            else:
                trans = ("won", rng.randrange(8, 160) * 1000)
            state = "반려" if rng.random() < 0.06 else "승인"
            trips.append([f"T-{3000 + k}", e, city, d0, d1, nd + 1, lod, trans, state])
        # contradiction: the 일수 column of one multi-day trip disagrees with the dates
        ct = rng.choice([t for t in trips if t[5] >= 2 and t[8] == "승인"])
        ct[5] = ct[5] + 1
        rows = []
        for t in trips:
            tr = f"자가 {t[7][1]}km" if t[7][0] == "km" else _amt(t[7][1], rng.choice(["won", "plain", "man", "chun"]), rng)
            rows.append([t[0], t[1][0], _person_var(t[1][1], rng), t[2], _dt(t[3], rng.choice(["iso", "dot", "kor", "compact"])),
                         _dt(t[4], rng.choice(["iso", "dot", "kor", "compact"])), str(t[5]),
                         _amt(t[6], rng.choice(["won", "plain", "man", "ko"]), rng) if t[6] else "0", tr, t[8]])
        rows = _b_dup(rng, rows, 5)
        csv_lines = _csv(["신청번호", "사번", "성명", "출장지", "출발일", "복귀일", "일수", "숙박비(실비)", "교통비", "상태"], rows).split("\n")
        csv_lines = _b_insert(rng, csv_lines, ["# 6월분 일부는 다음 달 정산", "# 숙박 영수증 원본은 총무팀 제출"])
        mtab = _md(["사번", "성명", "부서", "직급"], [[e[0], e[1], e[2], e[3]] for e in emp])

        def solve(dedupe=True, use_days_col=False, big_city=True, skip_reject=True):
            info = {}
            for ln in mtab.split("\n")[2:]:
                c = [x.strip() for x in ln.strip("|").split("|")]
                info[c[0]] = (c[2], c[3])
            seen = set()
            total, capped, bydept = 0, 0, {}
            for ln in csv_lines[1:]:
                if ln.startswith("#"):
                    continue
                c = _b_csv_split(ln)
                if dedupe and c[0] in seen:
                    continue
                seen.add(c[0])
                if skip_reject and c[9] == "반려":
                    continue
                dept, rank = info[c[1]]
                d0, d1 = _parse_dt(c[4]), _parse_dt(c[5])
                days = int(c[6]) if use_days_col else (d1 - d0).days + 1
                nights = days - 1
                pd = per_diem[rank] * days if days > 1 else per_diem[rank] // 2
                lim = lodge[rank] * (12 if (big_city and c[3] in ("서울", "부산")) else 10) // 10 * nights
                lod = _parse_amt(c[7])
                if lod > lim:
                    capped += 1
                    lod = lim
                m = re.fullmatch(r"자가 (\d+)km", c[8])
                tr = int(m.group(1)) * 250 if m else _parse_amt(c[8])
                amt = pd + lod + tr
                total += amt
                bydept[dept] = bydept.get(dept, 0) + amt
            return {"total_reimburse": total, "top_dept": _argmax(bydept)[0], "capped_count": capped}

        truth = solve()
        wrong = _b_wrongs(truth, [solve(dedupe=False), solve(use_days_col=True), solve(big_city=False),
                                  solve(skip_reject=False)])
        rule = ("규정(국내 출장비):\n"
                "- 출장일수 = 출발일부터 복귀일까지 달력 날짜 수(양끝 포함), 숙박일수 = 출장일수 − 1. 표의 '일수' 칸이 날짜와 맞지 않으면 "
                "날짜를 기준으로 계산합니다.\n"
                "- 일비 = 직급별 일비 × 출장일수. 사원·대리 25,000원, 과장·차장 30,000원, 부장 40,000원. 예외: 당일 출장(출발일=복귀일)은 "
                "일비의 50%만 지급하고 숙박비는 없습니다.\n"
                "- 숙박비 = 실비, 단 1박 한도 × 숙박일수를 넘으면 한도까지만 지급. 1박 한도: 사원·대리 70,000원, 과장·차장 80,000원, "
                "부장 100,000원. 출장지가 서울 또는 부산이면 1박 한도를 1.2배로 봅니다.\n"
                "- 교통비 = 실비 전액. '자가 NNNkm'로 적힌 건은 자가용 이용이라 km당 250원으로 계산합니다.\n"
                "- 상태가 '반려'인 신청은 지급하지 않습니다. 같은 신청번호가 여러 번 있으면 한 번만 계산합니다. '#'으로 시작하는 줄은 메모입니다.\n"
                "- 금액 표기(원, 만원, 천원, 한글 섞인 금액)는 모두 원으로 환산합니다. 직원의 부서·직급은 사번으로 직원 명부에서 찾습니다.")
        prompt = ("2분기 국내 출장비 정산을 해야 합니다. 출장 신청 내역(CSV)과 직원 명부(마크다운 표)를 붙입니다.\n\n[출장 신청 내역]\n"
                  + "\n".join(csv_lines) + "\n\n[직원 명부]\n" + mtab + "\n\n" + rule + "\n\n"
                  "지급 총액(원), 지급액 합계가 가장 큰 부서, 숙박비가 한도에 걸려 깎인 신청 건수를 알려주세요. "
                  + JSON_RULE + '{"total_reimburse": 정수, "top_dept": "부서명", "capped_count": 정수}')
        _add(17, "hr_travel", prompt, {"total_reimburse": "int", "top_dept": "str", "capped_count": "int"}, truth, wrong,
             {"rows": len(csv_lines) - 1 + len(emp), "tables": 2, "steps": 6,
              "mess": ["dup_rows", "contradiction_days_col", "memo", "unit_mixed", "korean_amount", "date_mixed",
                       "name_space", "status_filter"]})
    _b_build(17, build)


def _b_csv_split(line):
    out, cur, q = [], "", False
    i = 0
    while i < len(line):
        ch = line[i]
        if q:
            if ch == '"' and i + 1 < len(line) and line[i + 1] == '"':
                cur += '"'
                i += 1
            elif ch == '"':
                q = False
            else:
                cur += ch
        elif ch == '"':
            q = True
        elif ch == ",":
            out.append(cur)
            cur = ""
        else:
            cur += ch
        i += 1
    out.append(cur)
    return out


def _b_md_rows(text):
    return [[x.strip() for x in ln.strip().strip("|").split("|")] for ln in text.split("\n")[2:]]


# ---------------------------------------------------------------- hk_18 교육비 지원


def _hk18():
    def build(rng):
        names = rng.sample(PEOPLE, 40)
        depts = ["경영지원팀", "영업팀", "개발팀", "디자인팀", "물류팀"]
        ranks = ["사원", "대리", "과장", "차장", "부장"]
        limit = {"사원": 1000000, "대리": 1200000, "과장": 1500000, "차장": 2000000, "부장": 2000000}
        emp = {nm: (rng.choice(depts), rng.choices(ranks, [5, 4, 3, 2, 1])[0]) for nm in names}
        rate = {"직무": 100, "어학": 50, "자기계발": 30}
        courses = []
        pref = {"직무": "JOB", "어학": "LANG", "자기계발": "SELF"}
        cnt = {"직무": 0, "어학": 0, "자기계발": 0}
        titles = {"직무": ["재무제표 분석", "SQL 실무", "원가관리", "협상 스킬", "품질경영", "물류 최적화", "엑셀 고급", "프로젝트 관리",
                         "데이터 시각화", "노무 실무"],
                  "어학": ["비즈니스 영어", "중국어 회화", "일본어 기초", "영어 프레젠테이션", "토익 스피킹", "베트남어 입문"],
                  "자기계발": ["리더십 코칭", "스피치", "시간관리", "글쓰기", "마인드풀니스", "재테크 기초"]}
        for typ in ("직무", "어학", "자기계발"):
            for t in titles[typ]:
                cnt[typ] += 1
                fee = rng.randrange(15, 90) * 10000
                ref = rng.choice([0, 0, fee * rng.randrange(20, 50) // 100 // 1000 * 1000]) if typ == "직무" else 0
                courses.append([f"{pref[typ]}-{cnt[typ]:02d}", t, typ, fee, ref])
        # contradiction: one 자기계발 course listed again as 직무 (개정)
        rev = rng.choice([c for c in courses if c[2] == "자기계발"])
        crows = [[c[0], c[1], c[2], "Y" if c[4] else "N", _amt(c[4], "won") if c[4] else "-", ""] for c in courses]
        crows.insert(rng.randrange(len(crows) + 1), [rev[0], rev[1], "직무", "N", "-", "(개정) 직무 연관 과정으로 재분류"])
        ctab = _md(["과정코드", "과정명", "유형", "고용보험 환급", "환급액", "비고"], crows)
        apps = []
        for k in range(160):
            nm = rng.choice(names)
            c = rng.choice(courses)
            st = rng.choices(["수료", "중도포기", "취소"], [8, 2, 1])[0]
            pct = rng.randrange(80, 101) if st == "수료" else (rng.randrange(20, 79) if st == "중도포기" else 0)
            if st == "수료" and rng.random() < 0.1:
                pct = rng.randrange(70, 80)
            apps.append([f"A{5000 + k}", nm, c[0], c[3], pct, st])
        rows = []
        for a in apps:
            code = rng.choice([a[2], a[2].lower(), " " + a[2], a[2] + " "])
            rows.append([a[0], _person_var(a[1], rng), code, _amt(a[3], rng.choice(["won", "plain", "man", "ko", "krw"]), rng),
                         f"{a[4]}%", a[5]])
        rows = _b_dup(rng, rows, 6)
        lines = _csv(["신청번호", "성명", "과정코드", "수강료", "이수율", "상태"], rows).split("\n")
        lines = _b_insert(rng, lines, ["# 하반기 신청분은 별도 시트", "# 이수율은 LMS 기준 9/30 추출"])
        etab = _tsv(["성명", "부서", "직급"], [[nm, emp[nm][0], emp[nm][1]] for nm in names])

        def solve(dedupe=True, revised=True, refund=True, cap=True, min_pct=80):
            cinfo = {}
            for c in _b_md_rows(ctab):
                key = _norm(c[0])
                if key in cinfo and not revised:
                    continue
                if key in cinfo and "(개정)" not in c[5]:
                    continue
                cinfo[key] = (c[2], 0 if c[4] == "-" else _parse_amt(c[4]))
            einfo = {}
            for ln in etab.split("\n")[1:]:
                c = ln.split("\t")
                einfo[_norm(c[0])] = (c[1], c[2])
            seen, per = set(), {}
            for ln in lines[1:]:
                if ln.startswith("#"):
                    continue
                c = _b_csv_split(ln)
                if dedupe and c[0] in seen:
                    continue
                seen.add(c[0])
                if c[5] == "취소" or int(c[4].rstrip("%")) < min_pct:
                    continue
                typ, ref = cinfo[_norm(c[2])]
                base = _parse_amt(c[3]) - (ref if refund else 0)
                per[_norm(c[1])] = per.get(_norm(c[1]), 0) + _floor10(base * rate[typ] // 100)
            total, capped, bydept = 0, 0, {}
            for nm in sorted(per):
                dept, rank = einfo[nm]
                v = per[nm]
                if cap and v > limit[rank]:
                    v = limit[rank]
                    capped += 1
                total += v
                bydept[dept] = bydept.get(dept, 0) + v
            return {"total_support": total, "capped_people": capped, "top_dept": _argmax(bydept)[0]}

        truth = solve()
        _b_need(truth["capped_people"] >= 2)
        wrong = _b_wrongs(truth, [solve(dedupe=False), solve(revised=False), solve(refund=False), solve(cap=False),
                                  solve(min_pct=0)])
        prompt = ("올해 사내 교육비 지원액을 확정하려고 합니다. 수강 신청 내역(CSV), 과정 목록(마크다운 표), 직원 명부(탭 구분)를 붙입니다.\n\n"
                  "[수강 신청 내역]\n" + "\n".join(lines) + "\n\n[과정 목록]\n" + ctab + "\n\n[직원 명부]\n" + etab + "\n\n"
                  "규칙:\n"
                  "1. '#' 줄은 메모입니다. 같은 신청번호가 여러 번 나오면 한 번만 셉니다. 과정코드는 대소문자·앞뒤 공백을 무시하고, 성명의 공백 차이도 무시합니다.\n"
                  "2. 상태가 '취소'인 신청은 제외합니다. 이수율이 80% 미만이면 상태와 상관없이 지원하지 않습니다.\n"
                  "3. 지원 대상 금액 = 수강료 − 환급액(과정 목록에서 고용보험 환급 과정만 환급액이 있음).\n"
                  "4. 신청 1건 지원액 = 지원 대상 금액 × 유형별 지원율(직무 100%, 어학 50%, 자기계발 30%), 10원 미만 버림.\n"
                  "5. 직원별 연간 지원 한도(지원액 합계 기준): 사원 100만원, 대리 120만원, 과장 150만원, 차장·부장 200만원. 넘으면 한도까지만 지급.\n"
                  "6. 과정 목록에 같은 과정코드가 두 번 있으면 비고에 '(개정)'이 붙은 행을 적용합니다.\n\n"
                  "지원 총액(원), 한도에 걸린 직원 수, 지원 총액이 가장 큰 부서를 알려주세요. "
                  + JSON_RULE + '{"total_support": 정수, "capped_people": 정수, "top_dept": "부서명"}')
        _add(18, "hr_training", prompt, {"total_support": "int", "capped_people": "int", "top_dept": "str"}, truth, wrong,
             {"rows": len(lines) - 1 + len(crows) + len(names), "tables": 3, "steps": 6,
              "mess": ["dup_rows", "contradiction_revised_row", "memo", "unit_mixed", "korean_amount", "code_case_space",
                       "name_space", "status_filter"]})
    _b_build(18, build)


# ---------------------------------------------------------------- hk_19 임금 소급분


def _hk19():
    def build(rng):
        names = _b_names(rng, 120)
        depts = ["영업부", "생산부", "관리부", "연구소"]
        ranks = ["사원", "대리", "과장", "차장", "부장"]
        basepay = {"사원": (250, 320), "대리": (310, 380), "과장": (370, 460), "차장": (440, 540), "부장": (520, 650)}
        raise_pct = {"사원": 45, "대리": 40, "과장": 35, "차장": 30, "부장": 25}   # 0.1% units
        allow = {"사원": 0, "대리": 100000, "과장": 200000, "차장": 300000, "부장": 400000}
        emps = []
        for i, nm in enumerate(names):
            r = rng.choices(ranks, [5, 4, 3, 2, 1])[0]
            lo, hi = basepay[r]
            emps.append([f"{24000 + i * 3}", nm, rng.choice(depts), r, rng.randrange(lo * 10, hi * 10) * 1000])
        quit_ = sorted(rng.sample(range(120), 4))
        nxt = {"사원": "대리", "대리": "과장", "과장": "차장", "차장": "부장"}
        cand = [i for i in range(120) if emps[i][3] != "부장" and i not in quit_]
        promo_idx = rng.sample(cand, 16)
        promos = []
        for i in promo_idx:
            d = date(2026, rng.choice([3, 4, 5, 6]), rng.choice([1, 1, rng.randrange(2, 29)]))
            promos.append([emps[i][0], d, nxt[emps[i][3]], ""])
        # contradiction: one promotion recorded twice; the '정정' row applies
        cp = rng.choice(promos)
        d2 = date(2026, cp[1].month, 1) if cp[1].day != 1 else date(2026, cp[1].month, 16)
        promos.insert(rng.randrange(len(promos) + 1), [cp[0], d2, cp[2], "정정"])
        leave_idx = rng.sample([i for i in range(120) if i not in quit_], 8)
        leaves = {}
        for i in leave_idx:
            m0 = rng.choice([3, 4, 5])
            leaves[emps[i][0]] = (m0, min(6, m0 + rng.randrange(0, 2)))
        # base table with dept subtotal rows, duplicates, mixed units
        rows = []
        for dpt in depts:
            sub = 0
            for i, e in enumerate(emps):
                if e[2] != dpt:
                    continue
                note = "6/30 퇴사" if i in quit_ else ""
                rows.append([e[0], _person_var(e[1], rng), e[2], e[3],
                             _amt(e[4], rng.choice(["won", "plain", "chun", "man"]), rng), note])
                sub += e[4]
            rows.append(["", f"{dpt} 소계", "", "", _amt(sub, "won"), ""])
        for _ in range(4):
            i = rng.randrange(len(rows))
            if rows[i][0]:
                rows.insert(rng.randrange(i + 1, len(rows) + 1), list(rows[i]))
        btab = _tsv(["사번", "성명", "부서", "직급(3/1 기준)", "월 기본급", "비고"], rows)
        ptab = _md(["사번", "승진일", "새 직급", "비고"], [[p[0], _dt(p[1], rng.choice(["iso", "dot", "kor"])), p[2], p[3]]
                                                    for p in promos])
        mtxt = "\n".join(f"- 사번 {s}: 2026년 {a}월" + (f"~{b}월" if b != a else "") + " 휴직(무급)"
                         for s, (a, b) in sorted(leaves.items()))
        mdays = {3: 31, 4: 30, 5: 31, 6: 30}

        def solve(dedupe=True, fix_row=True, leave=True, prorate=True, exclude_quit=True):
            base, seen = {}, set()
            for ln in btab.split("\n")[1:]:
                c = ln.split("\t")
                if not c[0]:
                    continue
                if c[0] in seen and dedupe:
                    continue
                seen.add(c[0])
                base.setdefault(c[0], [])
                base[c[0]].append((c[2], c[3], _parse_amt(c[4]), c[5]))
            pro = {}
            for p in _b_md_rows(ptab):
                if p[0] in pro and (p[3] != "정정") == fix_row:
                    continue
                pro[p[0]] = (_parse_dt(p[1]), p[2])
            lv = {}
            for ln in mtxt.split("\n"):
                m = re.match(r"- 사번 (\d+): 2026년 (\d+)월(?:~(\d+)월)?", ln)
                lv[m.group(1)] = (int(m.group(2)), int(m.group(3) or m.group(2)))
            total, paid, bydept = 0, 0, {}
            for sb in sorted(base):
                amt = 0
                for dept, rank, pay, note in base[sb]:
                    if exclude_quit and "퇴사" in note:
                        continue
                    inc = _floor10(pay * raise_pct[rank] // 1000)
                    for m in (3, 4, 5, 6):
                        if leave and sb in lv and lv[sb][0] <= m <= lv[sb][1]:
                            continue
                        amt += inc
                        if sb in pro:
                            pd, nr = pro[sb]
                            diff = allow[nr] - allow[rank]
                            if pd.month < m or (pd.month == m and pd.day == 1):
                                amt += diff
                            elif pd.month == m:
                                amt += _floor10(diff * (mdays[m] - pd.day + 1) // mdays[m]) if prorate else diff
                if amt:
                    paid += 1
                    total += amt
                    bydept[base[sb][0][0]] = bydept.get(base[sb][0][0], 0) + amt
            return {"retro_total": total, "paid_count": paid, "top_dept": _argmax(bydept)[0]}

        truth = solve()
        wrong = _b_wrongs(truth, [solve(dedupe=False), solve(fix_row=False), solve(leave=False), solve(prorate=False),
                                  solve(exclude_quit=False)])
        prompt = ("올해 임금 인상이 7월에 확정되어 3~6월분 소급분을 계산해야 합니다. 3~6월 급여는 인상 전 기준으로 이미 지급됐습니다.\n\n"
                  "[직원 기본급(탭 구분, 3/1 기준)]\n" + btab + "\n\n[승진 발령]\n" + ptab + "\n\n[휴직자]\n" + mtxt + "\n\n"
                  "규칙:\n"
                  "1. 기본급 인상은 2026-03-01부터 적용합니다. 월 인상분 = 월 기본급 × 직급(3/1 기준)별 인상률, 10원 미만 버림. "
                  "인상률: 사원 4.5%, 대리 4.0%, 과장 3.5%, 차장 3.0%, 부장 2.5%. 승진해도 인상률은 3/1 기준 직급으로 봅니다.\n"
                  "2. 직책수당(월): 사원 0원, 대리 100,000원, 과장 200,000원, 차장 300,000원, 부장 400,000원. 승진자는 승진일부터 "
                  "(새 직급 수당 − 3/1 기준 직급 수당)을 소급합니다. 승진일이 1일이면 그 달 전액, 1일이 아니면 그 달은 "
                  "(차액 × (그 달 말일 − 승진일 + 1) ÷ 그 달 일수)를 10원 미만 버림해 일할 지급합니다(3월 31일, 4월 30일, 5월 31일, 6월 30일). "
                  "승진 다음 달부터는 전액입니다.\n"
                  "3. 휴직 기간인 달은 그 달 소급분(인상분·수당 차액)이 전혀 없습니다.\n"
                  "4. 비고에 '퇴사'가 있는 직원은 지급일 현재 재직자가 아니므로 소급 대상에서 제외합니다.\n"
                  "5. 기본급 표의 '소계' 행은 집계 행입니다. 같은 사번 행이 반복되면 한 번만 봅니다. 금액 표기(원, 천원, 만원)는 원으로 환산합니다.\n"
                  "6. 승진 발령에 같은 사번이 두 번 있으면 비고가 '정정'인 행만 적용합니다.\n\n"
                  "소급분 총액(원), 소급분이 0보다 큰 직원 수, 소급분 합계가 가장 큰 부서를 알려주세요. "
                  + JSON_RULE + '{"retro_total": 정수, "paid_count": 정수, "top_dept": "부서명"}')
        _add(19, "hr_retro_pay", prompt, {"retro_total": "int", "paid_count": "int", "top_dept": "str"}, truth, wrong,
             {"rows": len(rows) + len(promos) + len(leaves), "tables": 3, "steps": 6,
              "mess": ["dup_rows", "subtotal", "contradiction_fix_row", "unit_mixed", "date_mixed", "name_space",
                       "prose_list", "exclusion_note"]})
    _b_build(19, build)


# ---------------------------------------------------------------- hk_20 경조금


def _hk20():
    def build(rng):
        names = _b_names(rng, 50)
        emps = []
        for i, nm in enumerate(names):
            hire = date(2015, 1, 1) + timedelta(days=rng.randrange(0, 4200))
            emps.append([f"S{310 + i * 11}", nm, hire])
        types = ["본인 결혼", "자녀 결혼", "형제자매 결혼", "부모 사망", "배우자 부모 사망", "조부모 사망", "자녀 출생"]
        amt_tab = {"본인 결혼": 500000, "자녀 결혼": 300000, "형제자매 결혼": 100000, "부모 사망": 500000,
                   "배우자 부모 사망": 300000, "조부모 사망": 100000, "자녀 출생": 200000}
        notice_gp = 150000
        apps = []
        for k in range(150):
            e = rng.choice(emps)
            ev = date(2026, 1, 1) + timedelta(days=rng.randrange(0, 270))
            gap = rng.randrange(0, 60) if rng.random() < 0.85 else rng.randrange(80, 140)
            ap = ev + timedelta(days=gap)
            apps.append([f"C-{700 + k}", e[0], e[1], rng.choices(types, [2, 2, 3, 2, 2, 3, 3])[0], ev, ap])
        # make sure some recent hires apply
        for k in range(6):
            e = rng.choice(emps)
            e[2] = date(2025, rng.randrange(6, 13), rng.randrange(1, 28))
        rows = []
        for a in apps:
            rows.append([a[0], a[1], _person_var(a[2], rng), a[3], _dt(a[4], rng.choice(["iso", "dot", "dots", "kor"])),
                         _dt(a[5], rng.choice(["iso", "dot", "dots", "kor"]))])
        rows = _b_dup(rng, rows, 6)
        lines = _csv(["신청번호", "사번", "성명", "경조 유형", "발생일", "신청일"], rows).split("\n")
        lines = _b_insert(rng, lines, ["# 3분기 마감 기준", "# 화환은 별도 예산"])
        etab = _md(["사번", "성명", "입사일"], [[e[0], e[1], _dt(e[2], rng.choice(["iso", "dot"]))] for e in emps])
        ttab = _md(["경조 유형", "지급액"], [[t, _amt(amt_tab[t], rng.choice(["won", "man"]))] for t in types])

        def solve(dedupe=True, notice=True, birth_change=True, deadline=True, tenure=True):
            hire = {r[0]: _parse_dt(r[2]) for r in _b_md_rows(etab)}
            tab = {r[0]: _parse_amt(r[1]) for r in _b_md_rows(ttab)}
            seen = set()
            total, rej, bytype = 0, 0, {}
            for ln in lines[1:]:
                if ln.startswith("#"):
                    continue
                c = _b_csv_split(ln)
                if dedupe and c[0] in seen:
                    continue
                seen.add(c[0])
                ev, ap = _parse_dt(c[4]), _parse_dt(c[5])
                if deadline and (ap - ev).days > 90:
                    rej += 1
                    continue
                a = tab[c[3]]
                if notice and c[3] == "조부모 사망":
                    a = notice_gp
                if birth_change and c[3] == "자녀 출생" and ev >= date(2026, 7, 1):
                    a = 300000
                h = hire[c[1]]
                one = date(h.year + 1, h.month, h.day) if not (h.month == 2 and h.day == 29) else date(h.year + 1, 3, 1)
                if tenure and ev < one:
                    a //= 2
                total += a
                bytype[c[3]] = bytype.get(c[3], 0) + a
            return {"total_paid": total, "rejected_count": rej, "top_type": _argmax(bytype)[0]}

        truth = solve()
        wrong = _b_wrongs(truth, [solve(dedupe=False), solve(notice=False), solve(birth_change=False),
                                  solve(deadline=False), solve(tenure=False)])
        prompt = ("올해 1~9월 경조금 신청을 정산합니다. 신청 내역(CSV), 직원 입사일(표), 경조금 지급 기준표를 붙입니다.\n\n"
                  "[신청 내역]\n" + "\n".join(lines) + "\n\n[직원 입사일]\n" + etab + "\n\n[경조금 지급 기준표]\n" + ttab + "\n\n"
                  "[개정 공지] 조부모 사망 조위금은 150,000원으로 인상되었고 기준표는 아직 고치지 못했습니다. 공지와 기준표가 다르면 공지를 따릅니다. "
                  "또한 발생일이 2026-07-01 이후인 '자녀 출생'은 300,000원을 지급합니다.\n\n"
                  "규칙:\n"
                  "1. '#' 줄은 메모입니다. 같은 신청번호가 반복되면 한 번만 봅니다. 직원은 사번으로 찾습니다.\n"
                  "2. 신청일이 발생일로부터 90일을 넘으면(신청일 − 발생일 > 90일) 지급하지 않고 반려 건으로 셉니다.\n"
                  "3. 지급액은 기준표(공지 반영) 금액입니다. 예외: 발생일 현재 입사 1년 미만(발생일이 입사일의 1년 뒤 같은 날짜보다 이전)이면 50%만 지급합니다.\n\n"
                  "지급 총액(원), 반려 건수, 지급 합계가 가장 큰 경조 유형을 알려주세요. "
                  + JSON_RULE + '{"total_paid": 정수, "rejected_count": 정수, "top_type": "유형명(표에 적힌 그대로)"}')
        _add(20, "hr_welfare", prompt, {"total_paid": "int", "rejected_count": "int", "top_type": "str"}, truth, wrong,
             {"rows": len(lines) - 1 + len(emps) + len(types), "tables": 3, "steps": 5,
              "mess": ["dup_rows", "contradiction_notice_vs_table", "memo", "date_mixed", "name_space", "unit_mixed",
                       "effective_date"]})
    _b_build(20, build)


# ---------------------------------------------------------------- hk_21 선입선출 매출원가


def _hk21():
    def build(rng):
        items = [("PK-101", "포장박스 대", 12), ("PK-102", "포장박스 소", 24), ("TP-201", "OPP 테이프", 50),
                 ("LB-301", "물류 라벨", 0), ("CN-401", "완충재 롤", 0), ("ST-501", "스트레치 필름", 6)]
        box = {c: b for c, _, b in items}
        stock = {}
        open_rows = []
        for c, nm, b in items:
            stock[c] = []
            for _ in range(rng.randrange(1, 3)):
                q = rng.randrange(20, 80) * (b or 10)
                u = rng.randrange(30, 400) * 10
                stock[c].append([q, u])
                open_rows.append([c, nm, f"{q:,}", _amt(u, "won")])
        price = {c: stock[c][-1][1] for c in stock}
        tx = []
        d = date(2026, 7, 1)
        for k in range(210):
            d = d + timedelta(days=rng.choice([0, 0, 1, 1, 2]))
            if d > date(2026, 9, 30):
                d = date(2026, 9, 30)
            c = rng.choice(list(box))
            have = sum(q for q, _ in stock[c])
            kind = rng.choices(["입고", "출고", "견본"], [3, 6, 1])[0]
            if kind == "입고" or have < 40:
                b = box[c]
                nb = rng.randrange(5, 40)
                q = nb * b if b else nb * 10
                price[c] = max(100, price[c] + rng.randrange(-30, 40) * 10)
                stock[c].append([q, price[c]])
                tx.append([d, c, "입고", nb if b else q, "박스" if b else "개", price[c]])
            else:
                lim = have if kind == "출고" else min(have, 30)
                b = box[c]
                if b and rng.random() < 0.5 and lim >= b:
                    nb = rng.randrange(1, max(2, lim // b // 2))
                    q, shown, un = nb * b, nb, "박스"
                else:
                    q = rng.randrange(1, max(2, lim // 2))
                    shown, un = q, "개"
                left = q
                while left:
                    take = min(left, stock[c][0][0])
                    stock[c][0][0] -= take
                    left -= take
                    if not stock[c][0][0]:
                        stock[c].pop(0)
                tx.append([d, c, kind, shown, un, None])
        rows = []
        bad_i = rng.choice([i for i, t in enumerate(tx) if t[2] == "입고" and i < 150])
        for i, t in enumerate(tx):
            q_ea = t[3] * box[t[1]] if t[4] == "박스" else t[3]
            if t[5] is None:
                up, am = "", ""
            else:
                amount = q_ea * t[5] + (t[3] * 1000 if i == bad_i else 0)
                up = _amt(t[5], rng.choice(["won", "plain", "krw"]))
                am = _amt(amount, rng.choice(["won", "plain", "krw"]))
            code = rng.choice([t[1], t[1].lower(), t[1] + " "])
            rows.append([f"J{26070 + i * 3:06d}", _dt(t[0], rng.choice(["iso", "dot", "dots", "md"])), code, t[2],
                         f"{t[3]:,}", t[4], up, am])
        rows = _b_dup(rng, rows, 6)
        lines = ["\t".join(r) for r in rows]
        # month subtotal rows after the last row of each month and memo lines
        out, last_m = [], 7
        for ln in lines:
            m = _parse_dt(ln.split("\t")[1], 2026).month
            if m != last_m:
                out.append(f"\t{last_m}월 소계\t\t\t\t\t\t")
                last_m = m
            out.append(ln)
        out.append("\t9월 소계\t\t\t\t\t\t")
        out = _b_insert(rng, out, ["※ 8/15 연휴 전 출고 몰림", "※ 단가는 개당 단가(부가세 별도)"])
        table = "전표번호\t일자\t품목코드\t구분\t수량\t단위\t단가\t금액\n" + "\n".join(out)
        otab = _md(["품목코드", "품명", "기초수량(개)", "개당 단가"], open_rows)
        btxt = "; ".join(f"{c} 1박스 = {b}개" for c, _, b in items if b) + ". 나머지 품목은 낱개(개)로만 거래합니다."

        def solve(dedupe=True, boxes=True, use_unit=True, fifo=True):
            layers = {}
            for r in _b_md_rows(otab):
                layers.setdefault(r[0], []).append([int(r[2].replace(",", "")), _parse_amt(r[3])])
            bx = {m.group(1): int(m.group(2)) for m in re.finditer(r"(\S+) 1박스 = (\d+)개", btxt)}
            seen = set()
            cogs = samp = 0
            for ln in table.split("\n")[1:]:
                c = ln.split("\t")
                if len(c) != 8 or not c[0]:
                    continue
                if dedupe and c[0] in seen:
                    continue
                seen.add(c[0])
                code = c[2].strip().upper()
                q = int(c[4].replace(",", ""))
                if c[5] == "박스" and boxes:
                    q *= bx[code]
                if c[3] == "입고":
                    u = _parse_amt(c[6]) if use_unit else _parse_amt(c[7]) / q
                    layers[code].append([q, u])
                    continue
                cost = 0
                while q and layers[code]:
                    lay = layers[code][0] if fifo else layers[code][-1]
                    take = min(q, lay[0])
                    cost += take * lay[1]
                    lay[0] -= take
                    q -= take
                    if not lay[0]:
                        layers[code].remove(lay)
                if c[3] == "출고":
                    cogs += cost
                else:
                    samp += cost
            end = sum(q * u for v in layers.values() for q, u in v)
            return {"cogs": _rhalf(cogs), "sample_cost": _rhalf(samp), "ending_value": _rhalf(end)}

        truth = solve()
        clean_end = sum(q * u for v in stock.values() for q, u in v)
        assert truth["ending_value"] == clean_end
        wrong = _b_wrongs(truth, [solve(dedupe=False), solve(boxes=False), solve(use_unit=False), solve(fifo=False)])
        prompt = ("3분기(7~9월) 포장자재 수불부를 엑셀에서 복사했습니다(탭 구분, 연도는 2026년). 선입선출법으로 원가를 계산해 주세요.\n\n"
                  "[기초재고(7/1)]\n" + otab + "\n\n[수불부]\n" + table + "\n\n[포장 단위] " + btxt + "\n\n"
                  "규칙:\n"
                  "1. '※' 줄과 '소계' 줄은 거래가 아닙니다. 같은 전표번호가 두 번 이상 나오면 처음 한 번만 반영합니다. 품목코드는 대소문자·공백을 무시합니다.\n"
                  "2. 단위가 '박스'인 수량은 포장 단위로 개수로 바꿉니다. 단가는 항상 개당 단가입니다.\n"
                  "3. 거래는 표의 순서대로 반영하고, 출고·견본은 가장 먼저 들어온 재고(기초재고 포함, 위 행부터)부터 소진합니다(선입선출).\n"
                  "4. 구분 '출고'의 원가 합계가 매출원가입니다. 예외: 구분 '견본'도 같은 방식으로 재고를 소진하지만 그 원가는 매출원가가 아니라 견본비로 따로 모읍니다.\n"
                  "5. 입고 행의 금액이 수량(개) × 단가와 다르면 단가를 기준으로 합니다.\n\n"
                  "매출원가(원), 견본비(원), 9월 말 기말재고 금액(원)을 알려주세요. "
                  + JSON_RULE + '{"cogs": 정수, "sample_cost": 정수, "ending_value": 정수}')
        _add(21, "inv_fifo", prompt, {"cogs": "int", "sample_cost": "int", "ending_value": "int"}, truth, wrong,
             {"rows": len(out) + len(open_rows), "tables": 3, "steps": 5,
              "mess": ["dup_rows", "subtotal", "memo", "contradiction_amount_vs_unit", "uom_box", "date_mixed",
                       "code_case_space", "unit_mixed"]})
    _b_build(21, build)


# ---------------------------------------------------------------- hk_22 이동평균법


def _hk22():
    def build(rng):
        items = [("MA-1", "SUS 볼트 M8"), ("MA-2", "평와셔 M8"), ("MA-3", "육각너트 M8")]
        op = {c: (rng.randrange(200, 900), rng.randrange(80, 300)) for c, _ in items}
        tx = []
        qty = {c: op[c][0] for c in op}
        d = date(2026, 4, 1)
        for k in range(150):
            d = min(date(2026, 6, 30), d + timedelta(days=rng.choice([0, 1, 1, 2])))
            c = rng.choice([c for c, _ in items])
            kind = rng.choices(["입고", "출고", "매입반품"], [4, 7, 1])[0]
            if kind == "입고" or qty[c] < 60:
                q = rng.randrange(100, 900)
                gross = q * rng.randrange(80, 320) // 100 * 100
                disc = rng.choice([0, 0, 2, 3, 5])
                fr = rng.choice([0, rng.randrange(5, 60) * 1000])
                tx.append([d, c, "입고", q, gross, disc, fr])
                qty[c] += q
            else:
                q = rng.randrange(10, max(11, qty[c] * 2 // 3)) if kind == "출고" else rng.randrange(5, 40)
                q = min(q, qty[c])
                tx.append([d, c, kind, q, None, None, None])
                qty[c] -= q
        rows, frt = [], []
        ins = [i for i, t in enumerate(tx) if t[2] == "입고" and t[6]]
        bad = rng.choice(ins)
        for i, t in enumerate(tx):
            no = f"{'R' if t[2] == '입고' else 'I'}-{4000 + i}"
            note = ""
            if t[2] == "입고":
                g = _amt(t[4], rng.choice(["won", "plain", "man", "krw"]) if t[4] % 1000 == 0 else rng.choice(["won", "plain"]))
                dsc = f"{t[5]}%" if t[5] else ""
                if t[6]:
                    frt.append([no, _amt(t[6], rng.choice(["won", "plain", "man"]))])
                if i == bad:
                    note = f"운임 {t[6] + 20000:,}원 별도"
            else:
                g, dsc = "", ""
            rows.append([no, _dt(t[0], rng.choice(["iso", "dot", "slash"])), t[1], t[2], f"{t[3]:,}", g, dsc, note])
        rows = _b_dup(rng, rows, 5)
        lines = _csv(["전표번호", "일자", "품목", "구분", "수량(개)", "매입금액(할인 전)", "할인율", "비고"], rows).split("\n")
        lines = _b_insert(rng, lines, ["# 4월분 마감 완료", "# 5/1 근로자의 날 입출고 없음"])
        ftab = _md(["입고 전표번호", "운임"], frt)
        otxt = "; ".join(f"{c}({nm}) {op[c][0]:,}개, 개당 {op[c][1]:,}원" for c, nm in items)

        def solve(dedupe=True, disc=True, freight=True, ret_issue=False, rnd=True):
            fr = {r[0]: _parse_amt(r[1]) for r in _b_md_rows(ftab)}
            st = {}
            for m in re.finditer(r"(MA-\d)\([^)]*\) ([\d,]+)개, 개당 ([\d,]+)원", otxt):
                st[m.group(1)] = [int(m.group(2).replace(",", "")), int(m.group(3).replace(",", ""))]
            seen = set()
            issue = 0
            for ln in lines[1:]:
                if ln.startswith("#"):
                    continue
                c = _b_csv_split(ln)
                if dedupe and c[0] in seen:
                    continue
                seen.add(c[0])
                s = st[c[2]]
                q = int(c[4].replace(",", ""))
                if c[3] == "입고":
                    cost = _parse_amt(c[5])
                    if disc and c[6]:
                        cost = cost * (100 - int(c[6].rstrip("%"))) // 100
                    if freight:
                        cost += fr.get(c[0], 0)
                    num, den = s[0] * s[1] + cost, s[0] + q
                    s[1] = (2 * num + den) // (2 * den) if rnd else num // den
                    s[0] = den
                else:
                    if c[3] == "출고" or ret_issue:
                        issue += q * s[1]
                    s[0] -= q
            return {"final_unit_ma1": st["MA-1"][1], "issue_cost_total": issue,
                    "ending_value_total": sum(a * b for a, b in st.values())}

        truth = solve()
        wrong = _b_wrongs(truth, [solve(dedupe=False), solve(disc=False), solve(freight=False), solve(ret_issue=True),
                                  solve(rnd=False)])
        prompt = ("2분기 체결부품 입출고 내역(CSV)입니다. 총평균이 아니라 이동평균법으로 단가를 관리합니다.\n\n"
                  "[기초재고(4/1)] " + otxt + "\n\n[입출고 내역]\n" + "\n".join(lines) + "\n\n[입고 운임표]\n" + ftab + "\n\n"
                  "규칙:\n"
                  "1. '#' 줄은 메모입니다. 같은 전표번호는 한 번만 반영합니다. 거래는 표의 순서대로 처리합니다.\n"
                  "2. 입고 원가 = 매입금액 × (1 − 할인율) (원 미만 버림) + 운임. 운임은 입고 운임표에 있는 금액이고, 운임표에 없는 입고는 운임 0원입니다. "
                  "비고에 적힌 운임이 운임표와 다르면 운임표를 따릅니다.\n"
                  "3. 입고할 때마다 새 단가 = (기존 수량 × 기존 단가 + 입고 원가) ÷ (기존 수량 + 입고 수량)을 원 단위로 반올림(0.5는 올림)합니다.\n"
                  "4. 출고 원가 = 출고 수량 × 그 시점 단가. 예외: 구분 '매입반품'은 그 시점 단가로 재고 수량만 줄이고 출고 원가에는 넣지 않습니다.\n"
                  "5. 기말재고 금액 = 품목별 (기말 수량 × 기말 단가)의 합.\n\n"
                  "MA-1의 6월 말 단가(원), 출고 원가 합계(원, 세 품목), 기말재고 금액 합계(원)를 알려주세요. "
                  + JSON_RULE + '{"final_unit_ma1": 정수, "issue_cost_total": 정수, "ending_value_total": 정수}')
        _add(22, "inv_movavg", prompt, {"final_unit_ma1": "int", "issue_cost_total": "int", "ending_value_total": "int"},
             truth, wrong, {"rows": len(lines) - 1 + len(frt), "tables": 2, "steps": 5,
                            "mess": ["dup_rows", "memo", "contradiction_note_vs_table", "unit_mixed", "csv_quoted",
                                     "date_mixed"]})
    _b_build(22, build)


# ---------------------------------------------------------------- hk_23 단가 이력(적용일) + 수량할인 + 긴급 할증


def _hk23():
    def build(rng):
        vendors = rng.sample(COMPANIES, 5)
        codes = [f"MT-{i:02d}" for i in range(1, 16)]
        vend = {c: vendors[i % 5] for i, c in enumerate(codes)}
        hist = []
        for c in codes:
            p = rng.randrange(20, 400) * 100
            dates = sorted(rng.sample(range(0, 240), rng.randrange(2, 5)))
            dates[0] = 0
            for dd in dates:
                hist.append([c, date(2026, 1, 1) + timedelta(days=dd), p, ""])
                p = max(1000, p + rng.randrange(-20, 40) * 100)
        cc = rng.choice([h for h in hist if h[1] > date(2026, 2, 1)])
        hist.append([cc[0], cc[1], cc[2] + rng.randrange(3, 15) * 100, "정정"])
        rng.shuffle(hist)
        orders = []
        for k in range(250):
            d = date(2026, 1, 2) + timedelta(days=rng.randrange(0, 270))
            c = rng.choice(codes)
            q = rng.choices([rng.randrange(5, 100), rng.randrange(100, 300), rng.randrange(300, 800)], [6, 3, 1])[0]
            orders.append([f"O-{1000 + k}", d, c, q, "Y" if rng.random() < 0.1 else ""])
        orders.sort(key=lambda o: o[1])
        canc = rng.sample([o[0] for o in orders], 3)
        rows = [[o[0], _dt(o[1], rng.choice(["iso", "dot", "dots", "compact"])), rng.choice([o[2], o[2].lower(), o[2] + " "]),
                 f"{o[3]:,}", o[4]] for o in orders]
        rows = _b_dup(rng, rows, 6)
        lines = ["\t".join(r) for r in rows]
        lines = _b_insert(rng, lines, [f"※ 주문번호 {x} 취소(공급사 품절)" for x in canc] + ["※ 9월분 납품 확인 중"])
        table = "주문번호\t주문일\t품목코드\t수량\t긴급\n" + "\n".join(lines)
        htab = _md(["품목코드", "적용시작일", "단가", "비고"],
                   [[h[0], _dt(h[1], rng.choice(["iso", "dot"])), _amt(h[2], rng.choice(["won", "plain", "krw"])), h[3]]
                    for h in hist])
        vtxt = "\n".join(f"- {v}: " + ", ".join(c for c in codes if vend[c] == v) for v in vendors)

        def solve(dedupe=True, cancel=True, fix=True, latest_le=True, urgent_disc=False):
            hp = {}
            for r in _b_md_rows(htab):
                k = (r[0], _parse_dt(r[1]))
                if k in hp and fix and r[3] != "정정":
                    continue
                if k in hp and not fix and r[3] == "정정":
                    continue
                hp[k] = _parse_amt(r[2])
            vmap = {}
            for ln in vtxt.split("\n"):
                v, cs = ln[2:].split(": ")
                for c in cs.split(", "):
                    vmap[c] = v
            cn = set(re.findall(r"※ 주문번호 (O-\d+) 취소", table)) if cancel else set()
            seen = set()
            tot, urg, byv = 0, 0, {}
            for ln in table.split("\n")[1:]:
                if ln.startswith("※"):
                    continue
                c = ln.split("\t")
                if (dedupe and c[0] in seen) or c[0] in cn:
                    continue
                seen.add(c[0])
                d = _parse_dt(c[1])
                code = c[2].strip().upper()
                q = int(c[3].replace(",", ""))
                cand = [(dd, p) for (cd, dd), p in hp.items() if cd == code and (dd <= d if latest_le else True)]
                p = max(cand)[1] if latest_le else min(cand)[1]
                if c[4] == "Y" and not urgent_disc:
                    amt = p * q * 110 // 100
                else:
                    rate = 95 if q >= 300 else (97 if q >= 100 else 100)
                    amt = p * q * rate // 100
                    if c[4] == "Y":
                        amt = amt * 110 // 100
                amt = _floor10(amt)
                tot += amt
                if c[4] == "Y":
                    urg += amt
                byv[vmap[code]] = byv.get(vmap[code], 0) + amt
            return {"grand_total": tot, "top_vendor": _argmax(byv)[0], "urgent_total": urg}

        truth = solve()
        wrong = _b_wrongs(truth, [solve(dedupe=False), solve(cancel=False), solve(fix=False), solve(latest_le=False),
                                  solve(urgent_disc=True)])
        prompt = ("올해 1~9월 원자재 주문 금액을 다시 계산해야 합니다. 주문 목록(탭 구분), 단가 이력(마크다운), 공급사별 품목을 붙입니다.\n\n"
                  "[주문 목록]\n" + table + "\n\n[단가 이력]\n" + htab + "\n\n[공급사별 품목]\n" + vtxt + "\n\n"
                  "규칙:\n"
                  "1. 주문 단가는 그 품목의 단가 이력 중 적용시작일이 주문일과 같거나 그 이전인 것 가운데 가장 늦은 날짜의 단가입니다.\n"
                  "2. 단가 이력에 같은 품목·같은 적용시작일이 두 번 있으면 비고가 '정정'인 행을 씁니다.\n"
                  "3. 수량 할인(주문 한 줄 기준): 100개 이상 3%, 300개 이상 5% 할인. 예외: 긴급 'Y' 주문은 할인 없이 10% 할증합니다.\n"
                  "4. 줄 금액 = 단가 × 수량 × (할인 또는 할증 반영), 10원 미만 버림.\n"
                  "5. '※' 줄은 메모지만, '주문번호 … 취소'라고 적힌 주문은 금액에서 뺍니다. 같은 주문번호가 반복되면 한 번만 셉니다. 품목코드는 대소문자·공백을 무시합니다.\n\n"
                  "주문 금액 총액(원), 금액 합계가 가장 큰 공급사, 긴급 주문 금액 합계(원)를 알려주세요. "
                  + JSON_RULE + '{"grand_total": 정수, "top_vendor": "공급사명", "urgent_total": 정수}')
        _add(23, "inv_price_hist", prompt, {"grand_total": "int", "top_vendor": "str", "urgent_total": "int"}, truth, wrong,
             {"rows": len(lines) + len(hist) + 5, "tables": 3, "steps": 5,
              "mess": ["dup_rows", "memo_with_instruction", "contradiction_fix_row", "effective_date", "date_mixed",
                       "code_case_space", "unit_mixed"]})
    _b_build(23, build)


# ---------------------------------------------------------------- hk_24 3-way match


def _hk24():
    def build(rng):
        vendors = rng.sample(COMPANIES, 8)
        tol_v = sorted(rng.sample(vendors, 2))
        pos = []
        for k in range(105):
            pos.append([f"PO-2026-{100 + k * 2:04d}", rng.choice(vendors), rng.randrange(10, 500), rng.randrange(50, 3000) * 10, 0])
        cp = rng.choice(pos)
        po_rows = [[p[0], p[1], f"{p[2]:,}", _amt(p[3], rng.choice(["won", "plain"])), str(p[4])] for p in pos]
        new_u = cp[3] + rng.randrange(5, 30) * 10
        po_rows.insert(rng.randrange(len(po_rows) + 1), [cp[0], cp[1], f"{cp[2]:,}", _amt(new_u, "won"), "1"])
        unit = {p[0]: p[3] for p in pos}
        unit[cp[0]] = new_u
        recv = []
        got = {}
        for p in pos:
            r = rng.random()
            if r < 0.08:
                continue
            parts = rng.choice([1, 1, 2, 3])
            left = p[2] if rng.random() < 0.92 else p[2] - rng.randrange(1, max(2, p[2] // 5))
            for j in range(parts):
                q = left if j == parts - 1 else rng.randrange(1, max(2, left))
                left -= q
                if q > 0:
                    recv.append([p[0], q])
                    got[p[0]] = got.get(p[0], 0) + q
        rng.shuffle(recv)

        def pofmt(no):
            dig = no.replace("PO-", "").replace("-", "")
            return rng.choice([no, no.lower(), "PO" + dig, f"PO {dig[:4]} {dig[4:]}"])
        rrows = [[f"GR-{9000 + i}", pofmt(r[0]), _dt(date(2026, 8, 1) + timedelta(days=rng.randrange(0, 50)),
                                                     rng.choice(["iso", "dot", "md"])), f"{r[1]:,}"] for i, r in enumerate(recv)]
        rrows = _b_dup(rng, rrows, 5)
        inv = []
        for p in pos:
            if rng.random() < 0.08:
                continue
            g = got.get(p[0], 0)
            q = p[2] if rng.random() < 0.8 else g
            if rng.random() < 0.06:
                q = g + rng.randrange(1, 6)
            u = unit[p[0]]
            x = rng.random()
            if x < 0.06:
                u = u + max(10, u * rng.randrange(2, 6) // 100 // 10 * 10)
            elif x < 0.14:
                u = u + (u // 100 // 10 * 10)
            elif x < 0.22:
                u = u - rng.randrange(1, 10) * 10
            amt = q * u
            if rng.random() < 0.03:
                amt += rng.randrange(1, 9) * 1000
            inv.append([p[0], p[1], q, u, amt])
        tl = [i for i in inv if i[1] in tol_v and got.get(i[0], 0) >= 40 and i[0] != cp[0]]
        for i in rng.sample(tl, min(3, len(tl))):
            g = got[i[0]]
            i[2], i[3] = g + max(1, g * 4 // 100), unit[i[0]]
            i[4] = i[2] * i[3]
        if cp[0] in got and all(i[0] != cp[0] for i in inv):
            inv.append([cp[0], cp[1], got[cp[0]], new_u, got[cp[0]] * new_u])
        irows = [[f"INV-{i + 1:03d}", pofmt(v[0]), _co_var(v[1], rng), f"{v[2]:,}", _amt(v[3], "plain"),
                  _amt(v[4], rng.choice(["won", "plain"]))] for i, v in enumerate(inv)]
        ptab = _csv(["PO번호", "공급사", "발주수량", "단가", "변경차수"], po_rows)
        rtab = _tsv(["입고번호", "PO번호", "입고일", "입고수량"], rrows)
        itab = _md(["송장번호", "PO번호", "공급사", "청구수량", "청구단가", "청구금액"], irows)

        def key(s):
            return re.sub(r"\D", "", s)

        def solve(dedupe=True, rev=True, tol=True, cheaper_ok=True, check_amt=True):
            pu, pv, prev = {}, {}, {}
            for ln in ptab.split("\n")[1:]:
                c = _b_csv_split(ln)
                k = key(c[0])
                r = int(c[4])
                if k in pu and ((r <= prev[k]) if rev else (r >= prev[k])):
                    continue
                pu[k], pv[k], prev[k] = _parse_amt(c[3]), c[1], r
            rq, seen = {}, set()
            for ln in rtab.split("\n")[1:]:
                c = ln.split("\t")
                if dedupe and c[0] in seen:
                    continue
                seen.add(c[0])
                rq[key(c[1])] = rq.get(key(c[1]), 0) + int(c[3].replace(",", ""))
            hold, hamt, byv = 0, 0, {}
            for r in _b_md_rows(itab):
                k = key(r[1])
                q, u, a = int(r[3].replace(",", "")), _parse_amt(r[4]), _parse_amt(r[5])
                g = rq.get(k, 0)
                allow = g * 105 // 100 if (tol and pv[k] in tol_v) else g
                bad = q > allow
                if cheaper_ok:
                    bad = bad or u * 100 > pu[k] * 101
                else:
                    bad = bad or abs(u - pu[k]) * 100 > pu[k] * 1
                if check_amt:
                    bad = bad or abs(a - q * u) > 10
                if bad:
                    hold += 1
                    hamt += a
                    byv[pv[k]] = byv.get(pv[k], 0) + 1
            return {"hold_count": hold, "hold_amount": hamt, "hold_vendors": sorted(v for v, n in byv.items() if n >= 3)}

        truth = solve()
        _b_need(2 <= len(truth["hold_vendors"]) <= 4)
        wrong = _b_wrongs(truth, [solve(dedupe=False), solve(rev=False), solve(tol=False), solve(cheaper_ok=False),
                                  solve(check_amt=False)])
        prompt = ("8월 매입 송장을 발주서·입고 기록과 대조(3-way match)해서 지급 보류 건을 골라야 합니다.\n\n"
                  "[발주서(CSV)]\n" + ptab + "\n\n[입고 기록(탭 구분, 연도 2026)]\n" + rtab + "\n\n[매입 송장]\n" + itab + "\n\n"
                  "규칙:\n"
                  "1. PO번호는 표기 방식(대소문자, 하이픈, 공백)이 달라도 숫자 부분이 같으면 같은 PO입니다. 공급사는 그 PO의 발주서 공급사로 봅니다.\n"
                  "2. 발주서에 같은 PO번호가 두 번 있으면 변경차수가 큰 행의 단가가 유효합니다.\n"
                  "3. 입고 기록에서 같은 입고번호는 한 번만 셉니다. PO별 입고수량은 그 PO의 입고수량 합계입니다.\n"
                  "4. 송장은 다음 중 하나라도 해당하면 지급 보류입니다: (가) 청구수량 > PO별 입고수량 합계, (나) 청구단가가 PO 단가보다 1%를 넘게 높음"
                  "(PO 단가보다 낮거나 1% 이내로 높은 것은 통과), (다) 청구금액과 청구수량 × 청구단가의 차이가 10원을 넘음.\n"
                  f"5. 예외: 공급사 {tol_v[0]}, {tol_v[1]}는 수량 허용 계약이라 (가)의 기준을 입고수량 합계 × 1.05(소수점 버림)로 봅니다.\n\n"
                  "지급 보류 송장 건수, 보류 송장의 청구금액 합계(원), 보류 송장이 3건 이상인 공급사 목록(가나다순)을 알려주세요. "
                  + JSON_RULE + '{"hold_count": 정수, "hold_amount": 정수, "hold_vendors": ["공급사명", ...]}')
        _add(24, "inv_3way", prompt, {"hold_count": "int", "hold_amount": "int", "hold_vendors": "list"}, truth, wrong,
             {"rows": len(po_rows) + len(rrows) + len(irows), "tables": 3, "steps": 5,
              "mess": ["dup_rows", "id_format_variants", "contradiction_revision", "company_name_variants", "date_mixed",
                       "unit_mixed"]})
    _b_build(24, build)


# ---------------------------------------------------------------- hk_25 재주문점


def _hk25():
    def build(rng):
        items = []
        for i in range(1, 9):
            items.append([f"SP-{i:02d}", rng.choice([10, 12, 20, 24, 50]), rng.randrange(3, 12), rng.randrange(2, 6),
                          rng.randrange(1, 4)])
        disc = rng.choice(items)[0]
        lt_change = rng.choice([it for it in items if it[0] != disc])
        new_lt = lt_change[2] + rng.randrange(3, 7)
        use = []
        for d in _days(date(2026, 9, 1), date(2026, 9, 30)):
            for it in items:
                if d.weekday() >= 5 or d in HOLIDAYS_2026:
                    use.append([d, it[0], None, ""])
                    continue
                q = rng.randrange(0, 60)
                if it[1] >= 20 and rng.random() < 0.3:
                    nb = rng.randrange(1, 4)
                    use.append([d, it[0], nb, "박스"])
                else:
                    use.append([d, it[0], q, "개"])
        rows = [[_dt(u[0], rng.choice(["iso", "dot", "md"])), rng.choice([u[1], u[1].lower()]),
                 "-" if u[2] is None else str(u[2]), u[3]] for u in use]
        rows = _b_dup(rng, rows, 6)
        lines = ["\t".join(r) for r in rows]
        lines = _b_insert(rng, lines, ["※ 9/14 재고 실사로 출고 중지 없음", "※ 사용량은 생산 투입 기준"])
        table = "일자\t품목\t사용량\t단위\n" + "\n".join(lines)
        avg = {}
        for it in items:
            tot = sum((u[2] * it[1] if u[3] == "박스" else u[2]) for u in use if u[1] == it[0] and u[2] is not None)
            n = sum(1 for u in use if u[1] == it[0] and u[2] is not None)
            avg[it[0]] = (tot, n)
        mrows = []
        for it in items:
            tot, n = avg[it[0]]
            lt = new_lt if it[0] == lt_change[0] else it[2]
            rop = _b_ceil(tot * (lt + it[3]), n)
            cur = max(0, rop + rng.randrange(-rop // 2, rop // 2 + 1))
            pend = rng.choice([0, 0, rng.randrange(1, 5) * it[1]])
            mrows.append([it[0], str(it[1]), str(it[2]), str(it[3]), f"{cur:,}", f"{pend:,}", str(it[4]),
                          "단종예정" if it[0] == disc else ""])
        mtab = _md(["품목", "박스당 개수", "리드타임(일)", "안전재고(일)", "현재고(개)", "발주잔량(개)", "최소발주(박스)", "비고"], mrows)
        memo = f"[구매팀 메모] {lt_change[0]}은 공급사 사정으로 10월부터 리드타임이 {new_lt}일입니다(품목표 미반영). 메모와 품목표가 다르면 메모를 따릅니다."

        def solve(dedupe=True, memo_ok=True, skip_disc=True, boxes=True, excl_off=True):
            m = {r[0]: r for r in _b_md_rows(mtab)}
            lt_over = {}
            if memo_ok:
                mm = re.search(r"(SP-\d+)은 .*리드타임이 (\d+)일", memo)
                lt_over[mm.group(1)] = int(mm.group(2))
            seen, s, n = set(), {}, {}
            for ln in table.split("\n")[1:]:
                if ln.startswith("※"):
                    continue
                c = ln.split("\t")
                k = (_parse_dt(c[0], 2026), c[1].upper())
                if dedupe and k in seen:
                    continue
                seen.add(k)
                code = c[1].upper()
                if c[2] == "-":
                    if not excl_off:
                        n[code] = n.get(code, 0) + 1
                    continue
                q = int(c[2]) * (int(m[code][1]) if (c[3] == "박스" and boxes) else 1)
                s[code] = s.get(code, 0) + q
                n[code] = n.get(code, 0) + 1
            need, boxes_total = [], 0
            for code in sorted(m):
                r = m[code]
                if skip_disc and r[7] == "단종예정":
                    continue
                lt = lt_over.get(code, int(r[2]))
                rop = _b_ceil(s[code] * (lt + int(r[3])), n[code])
                avail = int(r[4].replace(",", "")) + int(r[5].replace(",", ""))
                if avail <= rop:
                    tgt = _b_ceil(s[code] * (lt + int(r[3]) + 14), n[code])
                    bx = max(int(r[6]), _b_ceil(tgt - avail, int(r[1])))
                    need.append(code)
                    boxes_total += bx
            return {"reorder_items": need, "total_order_boxes": boxes_total}

        truth = solve()
        _b_need(2 <= len(truth["reorder_items"]) <= 6)
        wrong = _b_wrongs(truth, [solve(dedupe=False), solve(memo_ok=False), solve(skip_disc=False), solve(boxes=False),
                                  solve(excl_off=False)])
        prompt = ("9월 부품 사용량으로 재주문점을 다시 잡고 이번 주 발주 대상을 정하려 합니다(연도 2026).\n\n"
                  "[9월 일별 사용량(탭 구분)]\n" + table + "\n\n[품목표]\n" + mtab + "\n\n" + memo + "\n\n"
                  "규칙:\n"
                  "1. '※' 줄은 메모입니다. 같은 일자·같은 품목 행이 반복되면 한 번만 셉니다. 품목코드는 대소문자를 무시합니다.\n"
                  "2. 단위가 '박스'면 박스당 개수를 곱해 개로 바꿉니다. 사용량 '-'는 휴무일이라 평균을 낼 때 그 날을 일수에서 뺍니다(사용량 0인 날은 일수에 넣습니다).\n"
                  "3. 일평균 사용량 = 사용량 합계 ÷ 일수. 재주문점 = 일평균 × (리드타임 + 안전재고 일수), 소수점 올림(개).\n"
                  "4. 가용재고 = 현재고 + 발주잔량. 가용재고가 재주문점 이하이면 발주합니다. 예외: 비고가 '단종예정'인 품목은 발주하지 않습니다.\n"
                  "5. 발주 수량: 목표재고 = 일평균 × (리드타임 + 안전재고 일수 + 14), 소수점 올림(개). (목표재고 − 가용재고)를 박스 단위로 올림하고, "
                  "최소발주 박스 수보다 적으면 최소발주 박스 수로 합니다.\n\n"
                  "발주할 품목 목록(품목코드 오름차순)과 발주 박스 수 합계를 알려주세요. "
                  + JSON_RULE + '{"reorder_items": ["SP-..", ...], "total_order_boxes": 정수}')
        _add(25, "inv_reorder", prompt, {"reorder_items": "list", "total_order_boxes": "int"}, truth, wrong,
             {"rows": len(lines) + len(mrows), "tables": 2, "steps": 5,
              "mess": ["dup_rows", "memo", "contradiction_memo_vs_table", "uom_box", "missing_marker", "date_mixed",
                       "code_case"]})
    _b_build(25, build)


# ---------------------------------------------------------------- hk_26 재고 실사(팔레트/박스/낱개 환산)


def _b_qty_str(q, bp, eb, rng):
    """EA count -> '1PLT 3BOX 5EA' / '35BOX 2EA' / '437EA' (lower case sometimes)."""
    st = rng.randrange(3)
    if st == 0:
        p, r = divmod(q, bp * eb)
        b, e = divmod(r, eb)
        parts = [f"{p}PLT" if p else "", f"{b}BOX" if b else "", f"{e}EA" if e else ""]
        s = " ".join(x for x in parts if x) or "0EA"
    elif st == 1:
        b, e = divmod(q, eb)
        s = " ".join(x for x in [f"{b}BOX" if b else "", f"{e}EA" if e else ""] if x) or "0EA"
    else:
        s = f"{q}EA"
    return s.lower() if rng.random() < 0.15 else s


def _b_parse_qty(s, bp, eb):
    tot = 0
    for n, u in re.findall(r"(\d+)\s*(PLT|BOX|EA)", s.upper()):
        tot += int(n) * {"PLT": bp * eb, "BOX": eb, "EA": 1}[u]
    return tot


def _hk26():
    def build(rng):
        names = ["코팅장갑", "방진마스크", "안전화", "보안경", "귀마개", "작업복 상의", "작업복 하의", "안전모", "절연장갑", "방수앞치마",
                 "핫팩", "쿨토시", "토시", "방한장갑", "안전조끼", "니트릴장갑", "면장갑", "보호크림", "무릎보호대", "손목보호대"]
        items = []
        for i, nm in enumerate(names):
            eb = rng.choice([6, 10, 12, 20, 24, 48])
            items.append([f"WH-{i + 1:03d}", nm, rng.randrange(8, 40), eb, rng.randrange(30, 2000) * 10])
        chg = rng.choice([it for it in items if it[3] == 24] or items[:1])
        old_eb = chg[3]
        new_eb = 20 if old_eb != 20 else 16
        chg[3] = new_eb
        book, actual = {}, {}
        for it in items:
            b = rng.randrange(400, 9000)
            book[it[0]] = b
            r = rng.random()
            if r < 0.35:
                d = 0
            elif r < 0.65:
                d = rng.randrange(-(b // 100), b // 100 + 1)
            else:
                d = rng.choice([-1, 1]) * rng.randrange(b // 100 + 2, b // 12)
            actual[it[0]] = b + d
        rows = []
        for it in items:
            k = rng.randrange(3, 8)
            cuts = sorted(rng.sample(range(1, actual[it[0]]), k - 1))
            parts = [b - a for a, b in zip([0] + cuts, cuts + [actual[it[0]]])]
            for j, q in enumerate(parts):
                loc = f"{rng.choice('ABCD')}-{rng.randrange(1, 20):02d}-{j + 1:02d}"
                rows.append([loc, rng.choice([it[0], it[0].lower()]), _b_qty_str(q, it[2], it[3], rng), rng.choice(PEOPLE[:8]), q, it])
            if rng.random() < 0.4:
                rows.append([f"Q-{rng.randrange(1, 9):02d}", it[0], _b_qty_str(rng.randrange(5, 300), it[2], it[3], rng),
                             "품질팀", 0, it])
        rng.shuffle(rows)
        # recounts: first count wrong, later '재실사' row correct
        rec = rng.sample([i for i, r in enumerate(rows) if not r[0].startswith("Q")], 6)
        for i in sorted(rec, reverse=True):
            r = rows[i]
            wrongq = max(1, r[4] + rng.choice([-1, 1]) * rng.randrange(5, 60))
            first = [r[0], r[1], _b_qty_str(wrongq, r[5][2], r[5][3], rng), r[3], wrongq, r[5]]
            rows[i] = [r[0], r[1], r[2], "재실사", r[4], r[5]]
            rows.insert(rng.randrange(0, i + 1), first)
        lines = ["\t".join(r[:4]) for r in rows]
        lines = _b_insert(rng, lines, ["※ C동 2층 조명 고장으로 오후 재실사", "※ Q- 로케이션은 불량품 격리 구역"])
        table = "로케이션\t품목\t실사수량\t담당\n" + "\n".join(lines)
        mrows = [[it[0], it[1], str(it[2]), str(old_eb if it is chg else it[3]), _amt(it[4], rng.choice(["won", "plain", "krw"]))]
                 for it in items]
        mtab = _md(["품목", "품명", "PLT당 BOX", "BOX당 EA", "EA 단가"], mrows)
        btab = _csv(["품목", "품명", "장부수량(EA)"], [[it[0], it[1], f"{book[it[0]]:,}"] for it in items])
        note = (f"[물류팀 공지] {chg[0]}({chg[1]})은 9월 입고분부터 BOX당 {new_eb}EA 포장으로 바뀌었고 현재 창고 재고는 모두 새 포장입니다. "
                f"품목 마스터의 BOX당 EA({old_eb})는 이전 기준이니 공지를 따릅니다.")

        def solve(skip_q=True, replace=True, use_note=True, tolerance=True):
            m = {r[0]: [int(r[2]), int(r[3]), _parse_amt(r[4])] for r in _b_md_rows(mtab)}
            if use_note:
                mm = re.search(r"(WH-\d+)\(.*BOX당 (\d+)EA 포장", note)
                m[mm.group(1)][1] = int(mm.group(2))
            bk = {}
            for ln in btab.split("\n")[1:]:
                c = _b_csv_split(ln)
                bk[c[0]] = int(c[2].replace(",", ""))
            cnt = {}
            for ln in table.split("\n")[1:]:
                if ln.startswith("※"):
                    continue
                c = ln.split("\t")
                if skip_q and c[0].startswith("Q-"):
                    continue
                code = c[1].upper()
                q = _b_parse_qty(c[2], m[code][0], m[code][1])
                k = (c[0], code)
                if replace:
                    cnt[k] = q
                else:
                    cnt[k] = cnt.get(k, 0) + q
            act = {}
            for (loc, code), q in sorted(cnt.items()):
                act[code] = act.get(code, 0) + q
            sh = su = adj = 0
            for code in sorted(bk):
                d = act.get(code, 0) - bk[code]
                if tolerance and abs(d) * 100 <= bk[code]:
                    continue
                if d == 0:
                    continue
                adj += 1
                if d < 0:
                    sh += -d * m[code][2]
                else:
                    su += d * m[code][2]
            return {"shortage_value": sh, "surplus_value": su, "adjusted_items": adj}

        truth = solve()
        exp_adj = sum(1 for c in book if abs(actual[c] - book[c]) * 100 > book[c])
        assert truth["adjusted_items"] == exp_adj
        wrong = _b_wrongs(truth, [solve(skip_q=False), solve(replace=False), solve(use_note=False), solve(tolerance=False)])
        prompt = ("분기말 안전용품 창고 실사 결과입니다. 장부와 비교해 재고 조정 금액을 정해 주세요.\n\n"
                  "[실사 기록(탭 구분)]\n" + table + "\n\n[품목 마스터]\n" + mtab + "\n\n[장부 재고(CSV)]\n" + btab + "\n\n" + note + "\n\n"
                  "규칙:\n"
                  "1. 실사수량은 PLT(팔레트)·BOX(박스)·EA(낱개)를 섞어 적었습니다. 품목 마스터의 환산(PLT당 BOX, BOX당 EA)으로 EA로 바꿉니다. 단위·품목코드의 대소문자는 무시합니다.\n"
                  "2. 같은 로케이션·같은 품목이 두 번 나오면 담당이 '재실사'인 행이 최종 수량이고 앞의 행은 버립니다.\n"
                  "3. 예외: 로케이션이 'Q-'로 시작하면 불량 격리 구역이라 실사 수량에 넣지 않습니다. '※' 줄은 메모입니다.\n"
                  "4. 품목별 실사 수량(로케이션 합계) − 장부수량 = 차이. 차이의 절댓값이 장부수량의 1% 이하이면 허용 오차로 보고 조정하지 않습니다.\n"
                  "5. 조정 대상 품목의 차이 × EA 단가로 금액을 구합니다. 부족(음수)은 부족 금액, 초과(양수)는 초과 금액으로 따로 합칩니다.\n\n"
                  "부족 금액 합계(원, 양수로), 초과 금액 합계(원), 조정 대상 품목 수를 알려주세요. "
                  + JSON_RULE + '{"shortage_value": 정수, "surplus_value": 정수, "adjusted_items": 정수}')
        _add(26, "inv_uom", prompt, {"shortage_value": "int", "surplus_value": "int", "adjusted_items": "int"}, truth, wrong,
             {"rows": len(lines) + 2 * len(items), "tables": 3, "steps": 5,
              "mess": ["recount_rows", "mixed_uom", "contradiction_notice_vs_master", "excluded_zone", "memo",
                       "code_case", "unit_mixed"]})
    _b_build(26, build)


# ---------------------------------------------------------------- hk_27 지체상금


def _hk27():
    def build(rng):
        vendors = rng.sample(COMPANIES, 12)
        rate = {"물품": 10, "용역": 15, "공사": 5}   # 1/10000 per day
        cons = []
        for k in range(40):
            cons.append([f"K-26-{k + 1:03d}", rng.choice(vendors), rng.choice(["물품", "물품", "용역", "공사"]),
                         rng.randrange(5, 300) * 1000000 + rng.choice([0, 500000]), date(2026, 3, 2) + timedelta(days=rng.randrange(0, 150))])
        hol = set(HOLIDAYS_2026)
        dels = []
        very = rng.sample(range(40), 3)
        for i, c in enumerate(cons):
            n = rng.randrange(1, 6)
            amts = []
            left = c[3]
            for j in range(n):
                a = left if j == n - 1 else (left * rng.randrange(15, 50) // 100) // 100000 * 100000
                amts.append(a)
                left -= a
            for a in amts:
                if a <= 0:
                    continue
                r = rng.random()
                if i in very:
                    dd = _add_biz(c[4], rng.randrange(75, 120), hol)
                elif r < 0.55:
                    dd = c[4] - timedelta(days=rng.randrange(0, 20))
                else:
                    dd = _add_biz(c[4], rng.randrange(1, 35), hol)
                dels.append([c[0], dd, a])
        rng.shuffle(dels)
        late_cons = sorted({d[0] for d in dels if d[1] > [c for c in cons if c[0] == d[0]][0][4]})
        fm = rng.sample([x for x in late_cons if int(x[-3:]) - 1 not in very], 3)
        fm_days = {x: rng.randrange(2, 8) for x in fm}
        chg_c = rng.choice([x for x in late_cons if x not in fm and int(x[-3:]) - 1 not in very])
        cobj = [c for c in cons if c[0] == chg_c][0]
        new_due = _add_biz(cobj[4], rng.randrange(5, 15), hol)
        crow = [[c[0], _co_var(c[1], rng), c[2], _amt(c[3], rng.choice(["ko", "hangul", "won", "man"]), rng),
                 _dt(c[4], rng.choice(["iso", "dot", "kor"]))] for c in cons]
        ctab = _md(["계약번호", "업체", "구분", "계약금액", "납기"], crow)
        drows = [[f"D{6100 + i}", d[0], _dt(d[1], rng.choice(["iso", "dot", "dots", "compact"])),
                  _amt(d[2], rng.choice(["won", "plain", "man", "ko"]), rng)] for i, d in enumerate(dels)]
        drows = _b_dup(rng, drows, 5)
        dl = _csv(["납품번호", "계약번호", "납품일", "납품금액"], drows).split("\n")
        dl = _b_insert(rng, dl, ["# 검수 완료분만 기재", "# 8월 납품분 일부는 검수 대기"])
        holtxt = ", ".join(f"{h.month}/{h.day}" for h in HOLIDAYS_2026)
        fmtxt = "\n".join(f"- {x}: {fm_days[x]}일 (천재지변 승인)" for x in fm)
        chgtxt = f"- {chg_c}: 변경계약으로 납기를 {_dt(new_due, 'kor')}로 연장"

        def solve(dedupe=True, biz=True, cap=True, force=True, change=True):
            ci = {}
            for r in _b_md_rows(ctab):
                ci[r[0]] = [_norm(r[1]), rate[r[2]], _parse_amt(r[3]), _parse_dt(r[4]), r[1]]
            if change:
                m = re.search(r"- (K-26-\d+): 변경계약으로 납기를 (.+)로 연장", chgtxt)
                ci[m.group(1)][3] = _parse_dt(m.group(2))
            fmd = {m.group(1): int(m.group(2)) for m in re.finditer(r"- (K-26-\d+): (\d+)일", fmtxt)} if force else {}
            hs = {date(2026, int(a), int(b)) for a, b in (x.split("/") for x in holtxt.split(", "))}
            seen, pen = set(), {}
            for ln in dl[1:]:
                if ln.startswith("#"):
                    continue
                c = _b_csv_split(ln)
                if dedupe and c[0] in seen:
                    continue
                seen.add(c[0])
                k = c[1]
                due = ci[k][3]
                dd = _parse_dt(c[2])
                if dd <= due:
                    continue
                days = sum(1 for x in _days(due + timedelta(days=1), dd) if (not biz) or _is_biz(x, hs))
                days = max(0, days - fmd.get(k, 0))
                pen[k] = pen.get(k, 0) + _floor10(_parse_amt(c[3]) * ci[k][1] * days // 10000)
            tot, capped, byv, disp = 0, 0, {}, {}
            for k in sorted(pen):
                v = pen[k]
                if cap and v > ci[k][2] // 10:
                    v = ci[k][2] // 10
                    capped += 1
                tot += v
                byv[ci[k][0]] = byv.get(ci[k][0], 0) + v
            top = _argmax(byv)[0]
            name = next(v for v in vendors if _norm(v) == top)
            return {"penalty_total": tot, "capped_contracts": capped, "top_vendor": name}

        truth = solve()
        _b_need(truth["capped_contracts"] >= 2)
        wrong = _b_wrongs(truth, [solve(dedupe=False), solve(biz=False), solve(cap=False), solve(force=False),
                                  solve(change=False)])
        prompt = ("상반기 납품 지연에 대한 지체상금을 계산해 주세요. 계약 목록(마크다운), 납품 기록(CSV), 공휴일·승인 사항을 붙입니다.\n\n"
                  "[계약 목록]\n" + ctab + "\n\n[납품 기록]\n" + "\n".join(dl) + "\n\n"
                  "[2026년 공휴일] " + holtxt + "\n\n[불가항력 승인(지연일수에서 뺄 일수)]\n" + fmtxt + "\n\n[변경계약]\n" + chgtxt + "\n\n"
                  "규칙:\n"
                  "1. '#' 줄은 메모입니다. 같은 납품번호는 한 번만 셉니다. 업체명 표기 차이((주), 주식회사, 공백)는 같은 업체입니다.\n"
                  "2. 납품일이 납기 이후인 납품 건만 지연입니다. 지연일수 = 납기 다음날부터 납품일까지의 날 중 토·일요일과 위 공휴일을 뺀 날 수.\n"
                  "3. 계약 목록의 납기와 변경계약이 다르면 변경계약의 납기를 씁니다.\n"
                  "4. 불가항력 승인 계약은 그 계약의 각 지연 납품 건 지연일수에서 승인 일수를 뺍니다(0 미만이면 0).\n"
                  "5. 납품 건별 지체상금 = 납품금액 × 일 지체상금률 × 지연일수, 10원 미만 버림. 일 지체상금률: 물품 0.1%, 용역 0.15%, 공사 0.05%.\n"
                  "6. 계약별 지체상금 합계는 계약금액의 10%를 넘을 수 없습니다(넘으면 10%로).\n\n"
                  "지체상금 총액(원), 10% 상한에 걸린 계약 수, 지체상금 합계가 가장 큰 업체를 알려주세요. "
                  + JSON_RULE + '{"penalty_total": 정수, "capped_contracts": 정수, "top_vendor": "업체명"}')
        _add(27, "inv_late_penalty", prompt, {"penalty_total": "int", "capped_contracts": "int", "top_vendor": "str"},
             truth, wrong, {"rows": len(dl) - 1 + len(cons), "tables": 4, "steps": 6,
                            "mess": ["dup_rows", "memo", "contradiction_amendment", "korean_amount", "hangul_amount",
                                     "date_mixed", "company_name_variants", "business_days"]})
    _b_build(27, build)


# ---------------------------------------------------------------- hk_28 택배 운임(부피중량·권역·할증)


def _hk28():
    def build(rng):
        zones = {"수도권": ["서울", "경기", "인천"], "중부": ["대전", "세종", "충북", "충남", "강원"],
                 "남부": ["부산", "대구", "울산", "경북", "경남", "광주", "전북", "전남"], "제주": ["제주"]}
        rates = {"수도권": [4000, 5000, 6500, 8000, 10000, 300], "중부": [4500, 5500, 7000, 9000, 11500, 400],
                 "남부": [5000, 6000, 7500, 9500, 12000, 450], "제주": [7000, 8500, 10500, 13000, 16000, 600]}
        towns = {"서울": ["강남구", "마포구", "노원구"], "경기": ["수원시", "파주시", "용인시"], "인천": ["연수구", "옹진군"],
                 "대전": ["유성구"], "세종": ["조치원읍"], "충북": ["청주시", "단양군"], "충남": ["천안시", "태안군"],
                 "강원": ["춘천시", "홍천군"], "부산": ["해운대구"], "대구": ["수성구"], "울산": ["남구"], "경북": ["포항시", "울릉군"],
                 "경남": ["창원시", "통영시"], "광주": ["북구"], "전북": ["전주시"], "전남": ["여수시", "신안군"], "제주": ["제주시", "서귀포시"]}
        sidos = [s for z in zones.values() for s in z]
        ships = []
        for k in range(230):
            s = rng.choices(sidos, [8 if x in ("서울", "경기") else 2 for x in sidos])[0]
            L, W, H = rng.randrange(10, 80), rng.randrange(10, 60), rng.randrange(5, 50)
            g = rng.choice([rng.randrange(2, 20) * 100, rng.randrange(10, 400) * 100])
            note = rng.choices(["", "도서산간", "반품"], [18, 2, 1])[0]
            if s == "제주" and rng.random() < 0.4:
                note = "도서산간"
            ships.append([f"S{70000 + k * 13}", date(2026, 9, 1) + timedelta(days=rng.randrange(0, 30)), s, L, W, H, g, note])
        fix_i = rng.randrange(len(ships))
        fix_g = rng.randrange(20, 300) * 100
        rows = []
        for i, sh in enumerate(ships):
            g = sh[6]
            wt = f"{g}g" if (g < 2000 and rng.random() < 0.7) else f"{g / 1000:.1f}kg"
            sep = rng.choice(["x", "*", "×"])
            size = f"{sh[3]}{sep}{sh[4]}{sep}{sh[5]}" + rng.choice(["", "cm"])
            note = sh[7]
            if i == fix_i:
                note = (note + " " if note else "") + f"실중량 정정 {fix_g / 1000:.1f}kg"
            rows.append([sh[0], _dt(sh[1], rng.choice(["iso", "dot", "md"])), f"{sh[2]} {rng.choice(towns[sh[2]])}", wt, size, note])
        rows = _b_dup(rng, rows, 6)
        lines = ["\t".join(r) for r in rows]
        lines = _b_insert(rng, lines, ["※ 9/24~9/26 연휴 기간 집하 없음", "※ 크기는 가로×세로×높이(cm)"])
        table = "송장번호\t출고일\t받는 곳\t실중량\t크기\t비고\n" + "\n".join(lines)
        rtab = _md(["권역", "2kg 이하", "5kg 이하", "10kg 이하", "20kg 이하", "30kg 이하", "30kg 초과 1kg당 추가"],
                   [[z] + [f"{x:,}" for x in rates[z]] for z in zones])
        ztxt = "\n".join(f"- {z}: {', '.join(v)}" for z, v in zones.items())

        def solve(dedupe=True, vol=True, jeju_ex=True, ret=True, fix=True):
            rt = {r[0]: [int(x.replace(",", "")) for x in r[1:]] for r in _b_md_rows(rtab)}
            zm = {}
            for ln in ztxt.split("\n"):
                z, ss = ln[2:].split(": ")
                for s in ss.split(", "):
                    zm[s] = z
            seen = set()
            tot, vc, byz = 0, 0, {}
            for ln in table.split("\n")[1:]:
                if ln.startswith("※"):
                    continue
                c = ln.split("\t")
                if dedupe and c[0] in seen:
                    continue
                seen.add(c[0])
                z = zm[c[2].split()[0]]
                wt = c[3]
                m = re.search(r"실중량 정정 ([\d.]+)kg", c[5])
                if m and fix:
                    wt = m.group(1) + "kg"
                g = int(wt[:-1]) if wt.endswith("g") and not wt.endswith("kg") else int(round(float(wt[:-2]) * 1000))
                L, W, H = (int(x) for x in re.findall(r"\d+", c[4]))
                hr = _b_ceil(g, 500)
                hv = _b_ceil(L * W * H, 3000)
                if hv > hr:
                    vc += 1
                h = max(hr, hv) if vol else hr
                r = rt[z]
                if h <= 4:
                    base = r[0]
                elif h <= 10:
                    base = r[1]
                elif h <= 20:
                    base = r[2]
                elif h <= 40:
                    base = r[3]
                elif h <= 60:
                    base = r[4]
                else:
                    base = r[4] + _b_ceil(h - 60, 2) * r[5]
                if "도서산간" in c[5] and (z != "제주" or not jeju_ex):
                    base += 3000
                if "반품" in c[5] and ret:
                    base = _floor10(base * 50 // 100)
                tot += base
                byz[z] = byz.get(z, 0) + base
            return {"freight_total": tot, "volumetric_count": vc, "top_region": _argmax(byz)[0]}

        truth = solve()
        wrong = _b_wrongs(truth, [solve(dedupe=False), solve(vol=False), solve(jeju_ex=False), solve(ret=False),
                                  solve(fix=False)])
        prompt = ("9월 택배 출고분 운임을 요율표대로 다시 계산해서 택배사 청구서와 맞춰 보려 합니다(연도 2026).\n\n"
                  "[출고 목록(탭 구분)]\n" + table + "\n\n[요율표(원)]\n" + rtab + "\n\n[권역]\n" + ztxt + "\n\n"
                  "규칙:\n"
                  "1. '※' 줄은 메모입니다. 같은 송장번호가 반복되면 한 번만 셉니다. 권역은 받는 곳의 첫 단어(시·도)로 정합니다.\n"
                  "2. 실중량은 g 또는 kg으로 적혀 있습니다. 비고에 '실중량 정정 N kg'이 있으면 실중량 칸 대신 정정 값을 씁니다.\n"
                  "3. 부피중량(kg) = 가로 × 세로 × 높이(cm) ÷ 6000. 실중량과 부피중량을 각각 0.5kg 단위로 올림한 뒤 큰 쪽이 청구중량입니다.\n"
                  "4. 기본 운임은 청구중량이 속하는 구간의 요금입니다. 30kg 초과는 30kg 이하 요금 + 30kg을 넘는 무게를 1kg 단위로 올림한 kg 수 × 1kg당 추가 요금.\n"
                  "5. 비고 '도서산간'은 3,000원 할증. 예외: 제주 권역은 요율에 이미 포함되어 있어 할증하지 않습니다.\n"
                  "6. 비고 '반품'은 (기본 운임 + 할증)의 50%, 10원 미만 버림.\n\n"
                  "운임 총액(원), 부피중량(0.5kg 올림 후)이 실중량(0.5kg 올림 후)보다 큰 송장 수, 운임 합계가 가장 큰 권역을 알려주세요. "
                  + JSON_RULE + '{"freight_total": 정수, "volumetric_count": 정수, "top_region": "권역명"}')
        _add(28, "inv_freight", prompt, {"freight_total": "int", "volumetric_count": "int", "top_region": "str"}, truth, wrong,
             {"rows": len(lines) + 4, "tables": 3, "steps": 6,
              "mess": ["dup_rows", "memo", "contradiction_note_correction", "unit_g_kg", "size_format_mixed",
                       "date_mixed"]})
    _b_build(28, build)


# ---------------------------------------------------------------- hk_29 공급사 평가 점수·등급


def _hk29():
    from fractions import Fraction as F

    def build(rng):
        vendors = rng.sample(COMPANIES, 10)
        small = vendors[-1]
        qual = {v: rng.choice([0.002, 0.01, 0.02, 0.035, 0.06]) for v in vendors}
        ontime = {v: rng.choice([0.98, 0.9, 0.8, 0.65]) for v in vendors}
        idx = {v: rng.randrange(920, 1150) for v in vendors}
        idx[small] = 900
        dels = []
        for v in vendors:
            n = 7 if v == small else rng.randrange(18, 34)
            for _ in range(n):
                due = date(2026, 1, 5) + timedelta(days=rng.randrange(0, 170))
                late = rng.random() > ontime[v]
                arr = due + timedelta(days=rng.randrange(1, 8)) if late else due - timedelta(days=rng.randrange(0, 4))
                q = rng.randrange(50, 2000)
                bad = int(q * qual[v] * rng.uniform(0, 2))
                note = "납기 변경 합의" if (late and rng.random() < 0.15) else ""
                dels.append([v, due, arr, q, bad, note])
        rng.shuffle(dels)
        ci = rng.choice([i for i, d in enumerate(dels) if d[0] != small])
        dels[ci][4] = dels[ci][3] + rng.randrange(5, 50)
        rows = [[f"GR{3300 + i}", _co_var(d[0], rng), _dt(d[1], rng.choice(["iso", "dot", "md"])),
                 _dt(d[2], rng.choice(["iso", "dot", "md"])), f"{d[3]:,}", str(d[4]), d[5]] for i, d in enumerate(dels)]
        rows = _b_dup(rng, rows, 6)
        lines = ["\t".join(r) for r in rows]
        lines = _b_insert(rng, lines, ["※ 3월 입고분 검사 지연", "※ 불량수량은 수입검사 기준"])
        table = "입고번호\t공급사\t납기\t입고일\t입고수량\t불량수량\t비고\n" + "\n".join(lines)
        ptab = _md(["공급사", "단가지수"], [[v, f"{idx[v] / 10:.1f}"] for v in sorted(vendors)])

        def solve(dedupe=True, min_n=True, clamp=True, agreed=True, min_among_eval=True):
            pi = {_norm(r[0]): (F(r[1]), r[0]) for r in _b_md_rows(ptab)}
            seen, st = set(), {}
            for ln in table.split("\n")[1:]:
                if ln.startswith("※"):
                    continue
                c = ln.split("\t")
                if dedupe and c[0] in seen:
                    continue
                seen.add(c[0])
                v = _norm(c[1])
                s = st.setdefault(v, [0, 0, 0, 0])
                q, b = int(c[4].replace(",", "")), int(c[5])
                if clamp:
                    b = min(b, q)
                ok = _parse_dt(c[3], 2026) <= _parse_dt(c[2], 2026) or (agreed and c[6] == "납기 변경 합의")
                s[0] += 1
                s[1] += ok
                s[2] += q
                s[3] += b
            ev = [v for v in sorted(st) if st[v][0] >= 10 or not min_n]
            lo = min(pi[v][0] for v in (ev if min_among_eval else st))
            score = {}
            for v in ev:
                n, ok, q, b = st[v]
                sc = 40 * F(ok, n) + 40 * max(F(0), 1 - F(b, q) / F(5, 100)) + 20 * lo / pi[v][0]
                x = sc * 10
                _b_need(abs((x - int(x)) - F(1, 2)) > F(1, 100))
                score[v] = _rhalf(float(sc), 1)
            top = _argmax(score)[0]
            cs = sorted(pi[v][1] for v in ev if score[v] < 70)
            names = sorted(ev, key=lambda v: pi[v][1])
            return {"c_grade": cs, "top_vendor": pi[top][1], "top_score": score[top],
                    "scores": [score[v] for v in names]}

        truth = solve()
        _b_need(1 <= len(truth["c_grade"]) <= 4)
        wrong = _b_wrongs(truth, [solve(dedupe=False), solve(min_n=False), solve(clamp=False), solve(agreed=False),
                                  solve(min_among_eval=False)])
        prompt = ("상반기 공급사 평가를 해야 합니다. 입고 실적(탭 구분, 연도 2026)과 단가지수 표를 붙입니다.\n\n"
                  "[입고 실적]\n" + table + "\n\n[단가지수(낮을수록 저렴)]\n" + ptab + "\n\n"
                  "평가 방법:\n"
                  "1. '※' 줄은 메모입니다. 같은 입고번호는 한 번만 셉니다. 공급사명 표기 차이((주), ㈜, 주식회사, 공백)는 같은 회사입니다.\n"
                  "2. 예외: 입고 건수가 10건 미만인 공급사는 평가 대상에서 빼고 등급을 매기지 않습니다(가격 점수의 최저 지수 계산에서도 뺍니다).\n"
                  "3. 납기 점수 = 40 × (납기 준수 건수 ÷ 입고 건수). 입고일이 납기와 같거나 빠르면 준수입니다. 비고가 '납기 변경 합의'인 건은 늦었어도 준수로 봅니다.\n"
                  "4. 품질 점수 = 40 × (1 − 불량률 ÷ 5%), 0점 미만이면 0점. 불량률 = 불량수량 합계 ÷ 입고수량 합계. 불량수량이 입고수량보다 크게 적힌 행은 입고수량 전부가 불량인 것으로 봅니다.\n"
                  "5. 가격 점수 = 20 × (평가 대상 중 최저 단가지수 ÷ 해당 공급사 단가지수).\n"
                  "6. 총점 = 세 점수의 합을 소수 첫째 자리로 반올림. 등급: 85점 이상 A, 70점 이상 B, 70점 미만 C.\n\n"
                  "C등급 공급사 목록(가나다순), 총점이 가장 높은 공급사와 그 총점, 평가 대상 공급사 전체의 총점 목록(공급사명 가나다순)을 알려주세요. "
                  + JSON_RULE + '{"c_grade": ["공급사명", ...], "top_vendor": "공급사명", "top_score": 소수 첫째 자리 숫자, "scores": [총점, ...]}')
        _add(29, "inv_vendor_score", prompt, {"c_grade": "list", "top_vendor": "str", "top_score": "float", "scores": "list"},
             truth, wrong,
             {"rows": len(lines) + len(vendors), "tables": 2, "steps": 6,
              "mess": ["dup_rows", "memo", "contradiction_defect_gt_qty", "company_name_variants", "date_mixed",
                       "exclusion_threshold"]}, tol={"top_score": 0.05, "scores": 0.05})
    _b_build(29, build)


# ---------------------------------------------------------------- hk_30 유통기한 재고 평가


def _hk30():
    def build(rng):
        names = ["우유 1L", "요거트", "두부", "계란 30구", "햄 슬라이스", "치즈", "생크림", "어묵", "냉장 만두", "샐러드 키트",
                 "라면", "통조림 참치", "식용유", "밀가루", "설탕", "커피믹스", "과자 세트", "즉석밥", "생수 2L", "간장"]
        items = []
        for i, nm in enumerate(names):
            cold = i < 10
            items.append([f"FD-{i + 1:02d}", nm, "냉장" if cold else "상온", rng.randrange(10, 60) if cold else rng.randrange(120, 720),
                          rng.choice([6, 10, 12, 20, 24, 30]), rng.randrange(25, 1500) * 20])
        base = date(2026, 10, 31)
        lots = []
        for k in range(200):
            it = rng.choice(items)
            rem = rng.choice([rng.randrange(-40, 0), rng.randrange(0, 8), rng.randrange(8, 31), rng.randrange(31, 200)])
            exp = base + timedelta(days=rem)
            mfg = exp - timedelta(days=it[3])
            q = rng.randrange(1, 40)
            lots.append([f"L{26000 + k * 7}", it, mfg, exp, q, rng.random() < 0.5])
        ci = rng.choice([i for i, l in enumerate(lots) if l[1][2] == "상온" and 40 < (l[3] - base).days])
        rows = []
        for i, l in enumerate(lots):
            it = l[1]
            write = rng.random() < 0.3 or i == ci
            exp_s = ""
            if write:
                ex = l[3] if i != ci else base + timedelta(days=rng.randrange(5, 25))
                exp_s = _dt(ex, rng.choice(["iso", "dot"]))
                l.append(ex)
            else:
                l.append(l[3])
            qs = f"{l[4]}박스" if l[5] else f"{l[4] * it[4] + rng.randrange(0, it[4])}개"
            l.append(qs)
            rows.append([l[0], rng.choice([it[0], it[0].lower()]), _dt(l[2], rng.choice(["iso", "dot", "dots", "compact", "kor"])),
                         exp_s, qs, rng.choice(["1창고", "2창고", "냉장1"])])
        rows = _b_dup(rng, rows, 5)
        lines = _csv(["로트번호", "품목", "제조일", "유통기한(표기)", "수량", "창고"], rows).split("\n")
        lines = _b_insert(rng, lines, ["# 10/31 마감 재고", "# 반품 대기 로트 없음"])
        mtab = _md(["품목", "품명", "보관", "유통기한(제조일로부터 일수)", "박스당 개수", "개당 단가"],
                   [[it[0], it[1], it[2], str(it[3]), str(it[4]), _amt(it[5], rng.choice(["won", "plain", "krw"]))] for it in items])

        def solve(dedupe=True, cold_ex=True, boxes=True, written=True, mdown=True):
            m = {r[0]: (r[2], int(r[3]), int(r[4]), _parse_amt(r[5])) for r in _b_md_rows(mtab)}
            seen = set()
            disp = mk = nl = 0
            for ln in lines[1:]:
                if ln.startswith("#"):
                    continue
                c = _b_csv_split(ln)
                if dedupe and c[0] in seen:
                    continue
                seen.add(c[0])
                st, days, eb, up = m[c[1].upper()]
                exp = _parse_dt(c[3]) if (c[3] and written) else _parse_dt(c[2]) + timedelta(days=days)
                mm = re.fullmatch(r"(\d+)(박스|개)", c[4])
                q = int(mm.group(1)) * (eb if (mm.group(2) == "박스" and boxes) else 1)
                rem = (exp - base).days
                val = q * up
                if rem < 0 or (cold_ex and st == "냉장" and rem <= 3):
                    disp += val
                    nl += 1
                elif rem <= 30 and mdown:
                    mk += val // 2
            return {"disposal_value": disp, "markdown_loss": mk, "disposal_lots": nl}

        truth = solve()
        wrong = _b_wrongs(truth, [solve(dedupe=False), solve(cold_ex=False), solve(boxes=False), solve(written=False)])
        prompt = ("10월 말 식자재 재고의 유통기한 평가를 부탁드립니다. 기준일은 2026-10-31입니다. 로트별 재고(CSV)와 품목 마스터를 붙입니다.\n\n"
                  "[로트별 재고]\n" + "\n".join(lines) + "\n\n[품목 마스터]\n" + mtab + "\n\n"
                  "규칙:\n"
                  "1. '#' 줄은 메모입니다. 같은 로트번호는 한 번만 셉니다. 품목코드는 대소문자를 무시합니다.\n"
                  "2. 유통기한 = 제조일 + 품목 마스터의 일수(예: 10/1 제조, 30일이면 10/31). 단, '유통기한(표기)' 칸에 날짜가 적혀 있으면 계산값과 달라도 적힌 날짜(재포장 후 표기)를 씁니다.\n"
                  "3. 수량이 '박스'면 박스당 개수를 곱합니다. 로트 금액 = 개수 × 개당 단가.\n"
                  "4. 잔여일수 = 유통기한 − 기준일. 잔여일수가 0보다 작으면(이미 지남) 폐기입니다. 예외: 보관이 '냉장'인 품목은 잔여일수가 3일 이하이면 폐기입니다.\n"
                  "5. 폐기가 아닌 로트 중 잔여일수가 30일 이하(0 포함)면 50% 할인 판매하므로 평가손실 = 로트 금액의 50%입니다.\n\n"
                  "폐기 금액 합계(원), 할인 평가손실 합계(원), 폐기 로트 수를 알려주세요. "
                  + JSON_RULE + '{"disposal_value": 정수, "markdown_loss": 정수, "disposal_lots": 정수}')
        _add(30, "inv_expiry", prompt, {"disposal_value": "int", "markdown_loss": "int", "disposal_lots": "int"}, truth, wrong,
             {"rows": len(lines) - 1 + len(items), "tables": 2, "steps": 5,
              "mess": ["dup_rows", "memo", "contradiction_written_vs_computed", "uom_box", "date_mixed", "code_case",
                       "unit_mixed"]})
    _b_build(30, build)


# ================================================================= 영업 (hk_31 - hk_40)


def _hk31():
    """영업 인센티브: 전표 중복·정정, 계열사 제외, 반품 차감, 누진 구간 수수료, 팀 집계."""
    n = 31
    rng = random.Random(1000 + n)
    reps = rng.sample(PEOPLE, 12)
    teams = ["영업1팀", "영업2팀", "영업3팀"]
    master = [(f"S{101 + i}", nm, teams[i % 3]) for i, nm in enumerate(reps)]
    affiliates = ["한결건설", "하나포장"]
    recs = []
    for i in range(185):
        d = date(2026, 7, 1) + timedelta(days=rng.randrange(92))
        kind = "반품" if rng.random() < 0.12 else "매출"
        amt = rng.randrange(20, 700) * 10000 if kind == "매출" else rng.randrange(5, 80) * 10000
        w = rng.random()
        rep = reps[min(11, int(w * w * 12))] if rng.random() < 0.5 else rng.choice(reps)
        recs.append([d, rep, rng.choice(COMPANIES), kind, amt])
    recs.sort(key=lambda r: r[0])
    for i, r in enumerate(recs):
        r.insert(0, f"SL-{i + 1:04d}")
    ds = ("iso", "dot", "dots", "compact", "kor")
    ams = ("won", "plain", "man", "chun", "ko")

    def cells(r):
        return [r[0], _dt(r[1], rng.choice(ds)), _person_var(r[2], rng), _co_var(r[3], rng), r[4],
                _amt(r[5], rng.choice(ams), rng)]

    lines = []
    dup_idx = set(rng.sample(range(len(recs)), 12))
    contra = next(i for i in rng.sample(range(len(recs)), 40)
                  if recs[i][4] == "매출" and recs[i][3] not in affiliates and i not in dup_idx)
    contra_amt = recs[contra][5] + rng.randrange(30, 200) * 10000
    month_sum = {}
    later = []
    for i, r in enumerate(recs):
        lines.append(cells(r))
        month_sum[r[1].month] = month_sum.get(r[1].month, 0) + (r[5] if r[4] == "매출" else -r[5])
        if i in dup_idx:
            later.append((i + rng.randrange(1, 15), cells(r)))
        if i == contra:
            later.append((i + 25, [r[0], _dt(r[1], "iso"), _person_var(r[2], rng), _co_var(r[3], rng), r[4],
                                    _amt(contra_amt, "won", rng)]))
        nxt = recs[i + 1][1].month if i + 1 < len(recs) else None
        if nxt != r[1].month:
            lines.append(["", "", "", "", f"{r[1].month}월 소계", _amt(month_sum[r[1].month], "won", rng)])
    # insert later rows (dups / correction) at positions counted on data lines
    for pos, c in sorted(later, key=lambda x: x[0], reverse=True):
        idx = min(len(lines), pos + pos // 60 + 1)
        lines.insert(idx, c)
    for k, memo in enumerate(["※ 8월 마감 후 추가 입력분 포함", "※ 담당자 확인 필요 건은 비고 없음", "※ 9월 말일자 전표 일부 지연 입력"]):
        lines.insert(40 + k * 60, [memo, "", "", "", "", ""])
    header = ["전표번호", "일자", "담당자", "거래처", "구분", "금액"]
    text = _tsv(header, lines)

    def solve(first_wins=False, keep_dups=False, include_aff=False, flat=False, ignore_ret=False):
        by = {}
        order = []
        for c in lines:
            if c[0].startswith("※") or not c[0]:
                continue
            doc, rep, cust, kind, amt = c[0], _norm(c[2]), _norm(c[3]), c[4], _parse_amt(c[5])
            if keep_dups:
                order.append((rep, cust, kind, amt))
                continue
            if doc in by and first_wins:
                continue
            by[doc] = (rep, cust, kind, amt)
        rows = order if keep_dups else list(by.values())
        net = {}
        for rep, cust, kind, amt in rows:
            if not include_aff and cust in {_norm(a) for a in affiliates}:
                continue
            if kind == "반품" and ignore_ret:
                continue
            net[rep] = net.get(rep, 0) + (amt if kind == "매출" else -amt)
        comm = {}
        for rep, v in net.items():
            v = max(v, 0)
            if flat:
                rate = 2 if v <= 50_000_000 else (3 if v <= 100_000_000 else 4)
                c = v * rate // 100
            else:
                c = min(v, 50_000_000) * 2 // 100 + max(0, min(v, 100_000_000) - 50_000_000) * 3 // 100 \
                    + max(0, v - 100_000_000) * 4 // 100
            comm[rep] = _floor10(c)
        name_of = {_norm(nm): nm for _, nm, _ in master}
        team_of = {_norm(nm): t for _, nm, t in master}
        top, _ = _argmax(comm)
        tnet = {}
        for rep, v in net.items():
            tnet[team_of[rep]] = tnet.get(team_of[rep], 0) + v
        tt, _ = _argmax(tnet)
        return {"total_commission": sum(comm.values()), "top_person": name_of[top], "top_team": tt}

    truth = solve()
    wrong = [solve(keep_dups=True), solve(include_aff=True), solve(flat=True), solve(first_wins=True)]
    mtext = _md(["사번", "성명", "소속팀"], master)
    prompt = (
        "3분기(7~9월) 영업 실적 전표를 엑셀에서 그대로 복사했고(탭 구분), 아래에 담당자 마스터를 붙였습니다. "
        "분기 인센티브를 계산해 주세요.\n\n[전표]\n" + text + "\n\n[담당자 마스터]\n" + mtext + "\n\n"
        "규칙:\n"
        "1. '※'로 시작하는 줄은 메모, 'N월 소계' 줄은 집계 행이므로 데이터가 아닙니다.\n"
        "2. 전표번호가 같은 줄이 여러 번 나오면 하나의 전표입니다. 내용이 같으면 한 번만 세고, 금액이 서로 다르면 "
        "표에서 가장 아래(나중)에 있는 줄이 정정본이니 그 줄만 씁니다.\n"
        "3. 금액은 원, 천원, 만원, 한글 섞어 쓰기(예: 3백20만원) 등으로 섞여 있습니다. 모두 원으로 환산하세요. "
        "담당자·거래처 이름의 띄어쓰기와 (주)·㈜·주식회사 표기는 무시합니다.\n"
        f"4. 거래처가 계열사({', '.join(affiliates)})인 전표는 매출·반품 모두 실적에서 제외합니다.\n"
        "5. 담당자별 순매출 = 매출 합계 − 반품 합계. 순매출이 0 이하이면 인센티브는 0원.\n"
        "6. 인센티브는 순매출에 누진 구간 요율을 적용합니다: 5천만원 이하 부분 2%, 5천만원 초과~1억원 이하 부분 3%, "
        "1억원 초과 부분 4%. 각 구간 금액은 원 미만 버림, 담당자별 인센티브 합은 10원 미만 버림.\n"
        "7. 팀 순매출 = 소속 담당자 순매출(규칙 5의 값, 음수도 그대로)의 합.\n\n"
        "전체 인센티브 합계, 인센티브가 가장 많은 담당자 성명, 팀 순매출이 가장 큰 팀을 알려주세요. "
        + JSON_RULE + '{"total_commission": 원(정수), "top_person": 성명, "top_team": 팀명}')
    _add(n, "sales_commission", prompt, {"total_commission": "int", "top_person": "str", "top_team": "str"},
         truth, wrong,
         {"rows": len(lines) + len(master), "tables": 2, "steps": 6,
          "mess": ["dup_rows", "correction_contradiction", "subtotal_rows", "memo_lines", "mixed_units",
                   "korean_amounts", "mixed_dates", "name_variants"]})


def _hk32():
    """RFM 고객 등급: 주문 CSV + 고객 마스터(ID 통합) + 취소 처리 내역, 기준일 이후 주문 제외."""
    n = 32
    rng = random.Random(1000 + n)
    ids = [f"C{i:03d}" for i in range(1, 61)]
    names = {}
    pool = COMPANIES + [c + "상회" for c in COMPANIES] + [c + "몰" for c in COMPANIES]
    for i, c in enumerate(ids):
        names[c] = pool[i]
    merges = {}
    olds = rng.sample(ids[:30], 5)
    news = rng.sample(ids[30:], 5)
    for o, nw in zip(olds, news):
        merges[o] = nw
    weight = {c: rng.choice([1, 1, 1, 2, 3, 5]) for c in ids}
    base = date(2026, 9, 30)
    orders = []
    wl = [c for c in ids for _ in range(weight[c])]
    for i in range(285):
        c = rng.choice(wl)
        d = date(2026, 1, 2) + timedelta(days=rng.randrange(272))
        amt = rng.randrange(5, 160) * 10000 + rng.choice([0, 5000])
        st = "취소" if rng.random() < 0.08 else "완료"
        orders.append([f"OD{26000 + i * 3 + rng.randrange(3)}", c, d, amt, st])
    orders.sort(key=lambda r: r[2])
    # one order after base date (오기입)
    late = [f"OD{29990}", rng.choice(news), date(2026, 10, 3), 2_400_000, "완료"]
    orders.insert(len(orders) - 3, late)
    cancel_list = rng.sample([o for o in orders if o[4] == "완료" and o[2] <= base], 9)
    cancel_ids = [o[0] for o in cancel_list]
    ds = ("iso", "dot", "dots", "slash", "compact")
    ams = ("won", "plain", "man", "krw")
    lines = []
    dup = set(rng.sample(range(len(orders)), 11))
    for i, o in enumerate(orders):
        row = [o[0], o[1] if rng.random() < 0.8 else o[1].lower(), _dt(o[2], rng.choice(ds)),
               _amt(o[3], rng.choice(ams), rng), o[4]]
        lines.append(row)
        if i in dup:
            lines.append(list(row))
        if i in (70, 150, 230):
            lines.append(["# 엑셀 내보내기 중 끊김, 이하 이어서", "", "", "", ""])
    master_rows = []
    for c in ids:
        note = f"{merges[c]}로 통합(동일 법인)" if c in merges else ""
        master_rows.append([c, names[c], note])

    def solve(no_merge=False, no_cancel=False, keep_dup=False, keep_late=False):
        seen, rows = set(), []
        canc = set(cancel_ids)
        for r in lines:
            if r[0].startswith("#"):
                continue
            if r[0] in seen and not keep_dup:
                continue
            seen.add(r[0])
            cid = r[1].upper()
            d = _parse_dt(r[2])
            if d > base and not keep_late:
                continue
            if r[4] != "완료" or (r[0] in canc and not no_cancel):
                continue
            if not no_merge:
                cid = merges.get(cid, cid)
            rows.append((cid, d, _parse_amt(r[3])))
        agg = {}
        for cid, d, a in rows:
            g = agg.setdefault(cid, [date(2000, 1, 1), 0, 0])
            g[0] = max(g[0], d)
            g[1] += 1
            g[2] += a
        vip = []
        for cid, (last, f, m) in sorted(agg.items()):
            days = (base - last).days
            r = 3 if days <= 30 else (2 if days <= 90 else 1)
            fs = 3 if f >= 8 else (2 if f >= 4 else 1)
            ms = 3 if m >= 5_000_000 else (2 if m >= 2_000_000 else 1)
            if r + fs + ms >= 8:
                vip.append((cid, m))
        return {"vip_count": len(vip), "vip_ids": [c for c, _ in vip], "vip_m_total": sum(m for _, m in vip)}

    truth = solve()
    assert 4 <= truth["vip_count"] <= 20, truth
    wrong = [solve(no_merge=True), solve(no_cancel=True), solve(keep_dup=True), solve(keep_late=True)]
    prompt = (
        "CRM에서 1~9월 주문 내역을 CSV로 내려받았습니다. 고객 마스터와 '취소 처리 내역'도 함께 드립니다. "
        "기준일 2026-09-30으로 RFM 등급을 매겨 VIP 고객을 뽑아 주세요.\n\n[주문 CSV]\n"
        + _csv(["주문번호", "고객ID", "주문일", "결제금액", "상태"], lines)
        + "\n\n[고객 마스터]\n" + _tsv(["고객ID", "고객명", "비고"], master_rows)
        + "\n\n[취소 처리 내역] 아래 주문은 주문 CSV의 상태와 관계없이 취소된 주문입니다(취소 처리 내역이 우선): "
        + ", ".join(cancel_ids) + "\n\n"
        "규칙:\n"
        "1. '#'로 시작하는 줄은 데이터가 아닙니다. 주문번호가 같은 줄이 반복되면 한 건만 셉니다.\n"
        "2. 상태가 '완료'이고 취소 처리 내역에 없는 주문만 씁니다. 주문일이 기준일보다 뒤인 주문은 오기입으로 보고 제외합니다.\n"
        "3. 고객ID 대소문자는 무시합니다. 고객 마스터 비고에 'Cxxx로 통합'이 있으면 그 고객의 주문은 통합된 고객ID의 주문으로 합칩니다.\n"
        "4. 고객별로 R(마지막 주문일부터 기준일까지 일수: 30일 이하 3점, 31~90일 2점, 그 외 1점), "
        "F(주문 건수: 8건 이상 3점, 4~7건 2점, 그 외 1점), M(결제금액 합계: 500만원 이상 3점, 200만원 이상 2점, 그 외 1점)을 매깁니다.\n"
        "5. R+F+M이 8점 이상이면 VIP입니다. 유효 주문이 없는 고객은 대상이 아닙니다.\n\n"
        "VIP 고객 수, VIP 고객ID 목록(통합 후 ID, 오름차순, 대문자), VIP 고객 결제금액 합계를 알려주세요. "
        + JSON_RULE + '{"vip_count": 정수, "vip_ids": ["C001", ...], "vip_m_total": 원(정수)}')
    _add(n, "sales_rfm", prompt, {"vip_count": "int", "vip_ids": "list", "vip_m_total": "int"}, truth, wrong,
         {"rows": len(lines) + len(master_rows) + len(cancel_ids), "tables": 3, "steps": 5,
          "mess": ["dup_rows", "memo_lines", "mixed_units", "mixed_dates", "id_case", "id_merge",
                   "status_vs_cancel_list_contradiction", "out_of_range_date"]})


def _hk33():
    """판매 단가 정책: 가격표(개정 중복) + 거래처 등급 + 프로모션 기간 + 최저 마진, 특판 예외."""
    n = 33
    rng = random.Random(1000 + n)
    prods = []
    for i in range(30):
        price = rng.randrange(20, 400) * 1000
        thin = rng.random() < 0.3
        cost = (price * rng.randrange(78, 84) // 100) // 100 * 100 if thin else (price * rng.randrange(45, 70) // 100) // 100 * 100
        prods.append([f"P{i + 1:02d}", f"품목{i + 1:02d}", price, cost, rng.random() < 0.15])
    pl = []
    for p in prods:
        pl.append([p[0], p[1] + ("*" if p[4] else ""), f"{p[2]:,}", f"{p[3]:,}", _dt(date(2026, 1, 2), "iso")])
    rev = rng.choice([p for p in prods if not p[4]])
    old_price = rev[2] - rng.randrange(2, 9) * 1000
    pl.insert(rng.randrange(5, 25), [rev[0], rev[1], f"{old_price:,}", f"{rev[3]:,}", _dt(date(2025, 7, 1), "iso")])
    grades = {"일반": 0, "실버": 5, "골드": 10, "플래티넘": 15}
    custs = [(c, rng.choice(list(grades))) for c in COMPANIES]
    promo = {}
    for p in rng.sample(prods, 6):
        s = date(2026, 8, 1) + timedelta(days=rng.randrange(40))
        promo[p[0]] = (s, s + timedelta(days=rng.randrange(7, 20)), rng.choice([5, 8, 10, 12]))
    orders = []
    for i in range(210):
        d = date(2026, 8, 1) + timedelta(days=rng.randrange(61))
        orders.append([f"SO-{i + 1:04d}", d, rng.choice(custs)[0], rng.choice(prods)[0], rng.randrange(1, 60)])
    ds = ("iso", "dot", "dots", "md", "mdk")
    lines = []
    dup = set(rng.sample(range(len(orders)), 10))
    for i, o in enumerate(orders):
        row = [o[0], _dt(o[1], rng.choice(ds)), _co_var(o[2], rng), o[3], f"{o[4]}개" if rng.random() < 0.3 else str(o[4])]
        lines.append(row)
        if i in dup:
            lines.append(list(row))
        if i % 70 == 69:
            lines.append(["(메모) 이 아래는 2차 입력분", "", "", "", ""])
    pmap = {p[0]: p for p in prods}

    def solve(old=False, no_floor=False, special_disc=False, keep_dup=False):
        latest = {}
        for r in pl:
            d = _parse_dt(r[4])
            if r[0] not in latest or (d > latest[r[0]][0]) != old:
                latest[r[0]] = (d, _parse_amt(r[2]), _parse_amt(r[3]), r[1].endswith("*"))
        gmap = {_norm(c): grades[g] for c, g in custs}
        seen, tot, floors = set(), 0, 0
        for r in lines:
            if r[0].startswith("(메모)"):
                continue
            if r[0] in seen and not keep_dup:
                continue
            seen.add(r[0])
            d = _parse_dt(r[1], 2026)
            _, price, cost, sp = latest[r[3]]
            g = gmap[_norm(r[2])]
            unit = price if (sp and not special_disc) else _floor10(price * (100 - g) // 100)
            if r[3] in promo and promo[r[3]][0] <= d <= promo[r[3]][1]:
                unit = _floor10(unit * (100 - promo[r[3]][2]) // 100)
            fl = cost * 11 // 10
            if unit < fl and not no_floor:
                unit = fl
                floors += 1
            tot += unit * int(r[4].rstrip("개"))
        return {"total_sales": tot, "floor_lines": floors}

    truth = solve()
    assert truth["floor_lines"] >= 3
    wrong = [solve(old=True), solve(no_floor=True), solve(special_disc=True), solve(keep_dup=True)]
    ptext = "\n".join(f"- {k}: {_dt(v[0], 'dots')} ~ {_dt(v[1], 'dots')} 기간 주문에 추가 {v[2]}% 할인" for k, v in sorted(promo.items()))
    prompt = (
        "8~9월 수주 내역의 판매 단가를 정책대로 다시 계산하려고 합니다. 가격표(마크다운), 거래처 등급표(탭), "
        "프로모션 공지, 수주 내역(마크다운)을 드립니다. 수주 내역의 날짜는 모두 2026년입니다.\n\n[가격표] (원, 부가세 별도)\n"
        + _md(["품목코드", "품명", "정가", "원가", "개정일"], pl)
        + "\n\n[거래처 등급] 등급 할인율: 일반 0%, 실버 5%, 골드 10%, 플래티넘 15%\n" + _tsv(["거래처", "등급"], custs)
        + "\n\n[프로모션 공지]\n" + ptext + "\n\n[수주 내역]\n" + _md(["수주번호", "수주일", "거래처", "품목코드", "수량"], lines)
        + "\n\n규칙:\n"
        "1. '(메모)' 줄은 데이터가 아니고, 수주번호가 같은 줄은 한 건만 셉니다. 거래처명의 (주)·㈜·주식회사·띄어쓰기는 무시합니다.\n"
        "2. 가격표에 같은 품목코드가 두 번 있으면 개정일이 늦은 줄의 정가·원가를 씁니다.\n"
        "3. 단가 = 정가 × (1 − 등급 할인율), 10원 미만 버림. 단, 품명 끝에 '*'가 붙은 특판 품목은 등급 할인을 하지 않습니다(정가 그대로).\n"
        "4. 수주일이 그 품목의 프로모션 기간(시작일·종료일 포함) 안이면 3번 단가에 추가 할인율을 곱하고 10원 미만 버림. 특판 품목도 프로모션은 적용합니다.\n"
        "5. 최저 단가는 원가 × 1.1입니다. 4번까지의 단가가 이보다 낮으면 단가를 원가 × 1.1로 올립니다.\n"
        "6. 판매액 = 단가 × 수량.\n\n"
        "판매액 합계와, 5번 최저 단가가 적용된 수주 건수를 알려주세요. "
        + JSON_RULE + '{"total_sales": 원(정수), "floor_lines": 건수(정수)}')
    _add(n, "sales_pricing", prompt, {"total_sales": "int", "floor_lines": "int"}, truth, wrong,
         {"rows": len(lines) + len(pl) + len(custs) + len(promo), "tables": 4, "steps": 6,
          "mess": ["dup_rows", "memo_lines", "revised_price_contradiction", "mixed_dates", "year_omitted",
                   "name_variants", "qty_suffix"]})


def _hk34():
    """지역 목표 달성률: 담당자 발령(정정 포함)으로 지역 귀속, 본사직판 제외, 목표는 만원 단위."""
    n = 34
    rng = random.Random(1000 + n)
    regions = ["서울", "경기", "충청", "영남", "호남"]
    reps = rng.sample(PEOPLE, 15)
    home = {r: regions[i % 5] for i, r in enumerate(reps)}
    movers = rng.sample(reps, 4)
    transfers = []
    for m in movers:
        to = rng.choice([g for g in regions if g != home[m]])
        transfers.append([m, home[m], to, date(2026, 7, 15) + timedelta(days=rng.randrange(50)), ""])
    corr = transfers[0]
    wrong_date = corr[3] - timedelta(days=rng.randrange(15, 30))
    trows = [[t[0], t[1], t[2], t[3], ""] for t in transfers]
    trows.insert(0, [corr[0], corr[1], corr[2], wrong_date, ""])
    trows[1][4] = "정정(발령일 수정)"
    sales = []
    for i in range(225):
        d = date(2026, 7, 1) + timedelta(days=rng.randrange(92))
        cust = "본사직판" if rng.random() < 0.07 else rng.choice(COMPANIES)
        sales.append([f"M{i + 1:04d}", d, rng.choice(reps), cust, rng.randrange(30, 900) * 10000])
    sales.sort(key=lambda s: s[1])
    for i, s in enumerate(sales):
        s[0] = f"M{i + 1:04d}"
    ds = ("iso", "dot", "dots", "kor", "compact")
    ams = ("won", "man", "chun", "ko", "plain")
    lines = []
    dup = set(rng.sample(range(len(sales)), 10))
    msum = 0
    for i, s in enumerate(sales):
        row = [s[0], _dt(s[1], rng.choice(ds)), _person_var(s[2], rng), _co_var(s[3], rng) if s[3] != "본사직판" else "본사직판",
               _amt(s[4], rng.choice(ams), rng)]
        lines.append(row)
        msum += s[4]
        if i in dup:
            lines.append(list(row))
        if i + 1 == len(sales) or sales[i + 1][1].month != s[1].month:
            lines.append(["", "", "", f"{s[1].month}월 월계", _amt(msum, "won", rng)])
            msum = 0

    def region_at(rep, d, use_wrong=False, ignore=False):
        reg = home[rep]
        if ignore:
            return reg
        rows = [trows[0]] if use_wrong else trows[1:]
        rows = rows + [t for t in trows[2:]] if use_wrong else rows
        for t in rows:
            if _norm(t[0]) == _norm(rep) and d >= t[3]:
                reg = t[2]
        return reg

    def actual(use_wrong=False, ignore=False, keep_dup=False, hq=False):
        seen, act = set(), {g: 0 for g in regions}
        rmap = {_norm(r): r for r in reps}
        for r in lines:
            if not r[0]:
                continue
            if r[0] in seen and not keep_dup:
                continue
            seen.add(r[0])
            if r[3] == "본사직판" and not hq:
                continue
            rep = rmap[_norm(r[2])]
            act[region_at(rep, _parse_dt(r[1]), use_wrong, ignore)] += _parse_amt(r[4])
        return act

    a0 = actual()
    targets = {}
    for g in regions:
        while True:
            t = a0[g] * rng.randrange(82, 120) // 100 // 10000
            rate = a0[g] * 100 / (t * 10000)
            if abs(rate - 100) > 0.3 and abs(rate * 10 - int(rate * 10) - 0.5) > 0.01:
                break
        targets[g] = t

    def solve(**kw):
        act = actual(**kw)
        rates = {g: _rhalf(act[g] * 100 / (targets[g] * 10000), 1) for g in regions}
        top, _ = _argmax(rates)
        return {"achieved": sorted(g for g in regions if act[g] >= targets[g] * 10000), "top_region": top,
                "top_rate": rates[top]}

    truth = solve()
    wrong = [solve(use_wrong=True), solve(ignore=True), solve(keep_dup=True), solve(hq=True)]
    tlines = "\n".join(f"- {t[0]}: {t[1]} → {t[2]}, 발령일 {_dt(t[3], rng.choice(('dots', 'kor', 'iso')))}"
                       + (f" [{t[4]}]" if t[4] else "") for t in trows)
    prompt = (
        "3분기 지역별 매출 목표 달성률을 내야 합니다. 매출 원장(탭 구분), 담당자 기본 소속, 인사 발령 목록, 지역 목표를 드립니다.\n\n"
        "[매출 원장]\n" + _tsv(["매출번호", "일자", "담당자", "거래처", "금액"], lines)
        + "\n\n[담당자 기본 소속(7월 1일 기준)]\n" + _csv(["담당자", "지역"], [[r, home[r]] for r in reps])
        + "\n\n[인사 발령]\n" + tlines
        + "\n\n[3분기 지역 목표] (단위: 만원)\n" + _md(["지역", "목표"], [[g, f"{targets[g]:,}"] for g in regions])
        + "\n\n규칙:\n"
        "1. 'N월 월계' 줄은 집계 행입니다. 매출번호가 같은 줄은 한 건만 셉니다.\n"
        "2. 금액은 원·천원·만원·한글 혼용 표기를 모두 원으로 환산합니다. 담당자 이름의 띄어쓰기는 무시합니다.\n"
        "3. 매출은 매출일 당시 담당자 소속 지역에 귀속합니다. 발령일 당일 매출부터 새 지역 실적입니다.\n"
        "4. 같은 사람의 발령이 두 줄 있으면 '정정' 표시가 있는 줄만 유효하고 다른 줄은 무시합니다.\n"
        "5. 거래처가 '본사직판'인 매출은 어느 지역 실적도 아닙니다.\n"
        "6. 달성률(%) = 지역 실적 ÷ 목표(원 환산) × 100, 소수 첫째 자리에서 반올림(둘째 자리에서 반올림해 첫째 자리까지).\n\n"
        "목표를 달성한(실적 ≥ 목표) 지역 목록(가나다순), 달성률이 가장 높은 지역과 그 달성률을 알려주세요. "
        + JSON_RULE + '{"achieved": ["지역", ...], "top_region": 지역, "top_rate": 숫자(소수 첫째 자리)}')
    _add(n, "sales_target", prompt, {"achieved": "list", "top_region": "str", "top_rate": "float"}, truth, wrong,
         {"rows": len(lines) + len(reps) + len(trows) + len(regions), "tables": 4, "steps": 6,
          "mess": ["dup_rows", "subtotal_rows", "mixed_units", "korean_amounts", "mixed_dates", "name_variants",
                   "transfer_correction_contradiction", "prose_list"]},
         tol={"top_rate": 0.05})


def _hk35():
    """견적 버전: 수주 건만, 확정버전(없는 버전이면 최신), 삭제 줄 제외, 버전 할인, 천원 미만 절사."""
    n = 35
    rng = random.Random(1000 + n)
    items = ["서버랙", "UPS", "스위치", "방화벽", "NAS", "모니터", "노트북", "도킹스테이션", "프린터", "라이선스", "설치비", "유지보수"]
    quotes = []
    for q in range(1, 39):
        qid = f"Q-26{q:03d}"
        nv = rng.choice([1, 2, 2, 3, 3])
        base = rng.sample(items, rng.randrange(2, 5))
        vers = []
        for v in range(1, nv + 1):
            lines = []
            for it in base:
                lines.append([it, rng.randrange(1, 20), rng.randrange(5, 300) * 10000 + rng.choice([0, 5000]),
                              "삭제" if (v > 1 and rng.random() < 0.15) else ""])
            if rng.random() < 0.3:
                lines.append([rng.choice([x for x in items if x not in base]), rng.randrange(1, 5),
                              rng.randrange(5, 100) * 10000, ""])
            vers.append((v, rng.choice([0, 0, 3, 5, 7, 10]), date(2026, 6, 1) + timedelta(days=q * 2 + v * 3), lines))
        quotes.append((qid, rng.choice(COMPANIES), vers))
    status = []
    for qid, cust, vers in quotes:
        res = rng.choice(["수주", "수주", "실주", "진행"])
        cv = ""
        if res == "수주" and rng.random() < 0.5:
            cv = f"v{rng.randrange(1, len(vers) + 1)}"
        status.append([qid, cust, res, cv])
    bad = next(s for s, q in zip(status, quotes) if s[2] == "수주" and s[3] == "" and len(q[2]) == 2)
    bad[3] = "v3"
    ams = ("plain", "won", "man", "krw")
    lrows, hrows = [], []
    for qid, cust, vers in quotes:
        for v, disc, d, lines in vers:
            hrows.append([qid, f"v{v}", f"{disc}%", _dt(d, rng.choice(("iso", "dot", "dots")))])
            for it, qty, up, note in lines:
                lrows.append([qid, f"v{v}" if rng.random() < 0.7 else f"V{v}", it, qty, _amt(up, rng.choice(ams), rng), note])
    for k in rng.sample(range(len(lrows)), 9):
        lrows.insert(k + 1, list(lrows[k]))
    for k in (60, 140, 220):
        lrows.insert(k, ["// 영업지원팀 재작성분", "", "", "", "", ""])

    def solve(use_given=False, keep_del=False, keep_dup=False, no_disc=False):
        lines = {}
        seen = set()
        for r in lrows:
            if r[0].startswith("//"):
                continue
            key = (r[0], r[1].lower(), r[2], r[3], r[4], r[5])
            if key in seen and not keep_dup:
                continue
            seen.add(key)
            if r[5] == "삭제" and not keep_del:
                continue
            k = (r[0], int(r[1][1:]))
            lines[k] = lines.get(k, 0) + int(r[3]) * _parse_amt(r[4])
        disc = {(h[0], int(h[1][1:])): int(h[2].rstrip("%")) for h in hrows}
        won = {}
        for qid, cust, res, cv in status:
            if res != "수주":
                continue
            vs = [v for (q, v) in disc if q == qid]
            v = int(cv[1:]) if cv and (int(cv[1:]) in vs or use_given) else max(vs)
            amt = lines.get((qid, v), 0) * (100 - (0 if no_disc else disc.get((qid, v), 0))) // 100
            won[qid] = amt // 1000 * 1000
        top, _ = _argmax(won)
        return {"won_total": sum(won.values()), "won_count": len(won), "max_quote": top}

    truth = solve()
    wrong = [solve(use_given=True), solve(keep_del=True), solve(keep_dup=True), solve(no_disc=True)]
    prompt = (
        "올해 상반기 견적들 가운데 수주한 건의 최종 금액을 정리해 주세요. 견적 품목(CSV), 버전별 할인(마크다운), 영업 결과(탭)를 드립니다.\n\n"
        "[견적 품목 CSV]\n" + _csv(["견적번호", "버전", "품목", "수량", "단가", "비고"], lrows)
        + "\n\n[버전별 할인]\n" + _md(["견적번호", "버전", "할인율", "작성일"], hrows)
        + "\n\n[영업 결과]\n" + _tsv(["견적번호", "거래처", "결과", "확정버전"], status)
        + "\n\n규칙:\n"
        "1. '//'로 시작하는 줄은 메모입니다. 버전 표기의 대소문자(v2, V2)는 같은 버전입니다. 견적번호·버전·품목·수량·단가·비고가 모두 같은 줄은 중복이니 한 번만 셉니다.\n"
        "2. 결과가 '수주'인 견적만 대상입니다.\n"
        "3. 확정버전이 적혀 있으면 그 버전을 씁니다. 확정버전이 비어 있거나, 적힌 버전이 견적 품목에 존재하지 않으면 그 견적의 가장 높은 버전(최신)을 씁니다.\n"
        "4. 선택한 버전에서 비고가 '삭제'인 줄은 뺍니다. 버전 금액 = Σ(수량 × 단가). 단가는 원·만원 등 섞인 표기를 원으로 환산합니다.\n"
        "5. 최종 금액 = 버전 금액 × (1 − 그 버전의 할인율), 원 미만 버림 후 천원 미만 버림.\n\n"
        "수주 최종 금액 합계, 수주 견적 수, 최종 금액이 가장 큰 견적번호를 알려주세요. "
        + JSON_RULE + '{"won_total": 원(정수), "won_count": 정수, "max_quote": "Q-26xxx"}')
    _add(n, "sales_quote_ver", prompt, {"won_total": "int", "won_count": "int", "max_quote": "str"}, truth, wrong,
         {"rows": len(lrows) + len(hrows) + len(status), "tables": 3, "steps": 5,
          "mess": ["dup_rows", "memo_lines", "case_variants", "mixed_units", "missing_version_contradiction",
                   "deleted_lines"]})


def _hk36():
    """구독 MRR: 고객별로 흩어진 이벤트를 날짜순 재구성, 무효 이벤트 무시, 연간 요금 월할, 가격 공지 우선."""
    n = 36
    rng = random.Random(1000 + n)
    plans = ["Basic", "Pro", "Biz", "Pro연간", "Biz연간", "Trial"]
    custs = [f"K{i:03d}" for i in range(1, 81)]
    events = []
    end = date(2026, 9, 30)
    for c in custs:
        if rng.random() < 0.06:
            continue
        d = date(2026, 1, 2) + timedelta(days=rng.randrange(230))
        active = False
        while d <= end and len(events) < 260:
            if not active:
                events.append([d, c, "신규", rng.choice(plans)])
                active = True
            else:
                r = rng.random()
                if r < 0.55:
                    events.append([d, c, "변경", rng.choice(plans)])
                else:
                    events.append([d, c, "해지", ""])
                    active = False
            d += timedelta(days=rng.randrange(12, 80))
    ghosts = [c for c in custs if c not in {e[1] for e in events}]
    assert len(ghosts) >= 3
    for c in ghosts[:3]:
        events.append([date(2026, 6, 1) + timedelta(days=rng.randrange(90)), c, "변경", rng.choice(["Pro", "Biz"])])
    events.sort(key=lambda e: (e[0], e[1]))
    for i, e in enumerate(events):
        e.insert(0, f"E{i + 1:04d}")
    pv = {"Basic": ["Basic", "basic", "BASIC"], "Pro": ["Pro", "pro", "PRO"], "Biz": ["Biz", "biz", "BIZ"],
          "Pro연간": ["Pro연간", "Pro 연간", "pro(연간)"], "Biz연간": ["Biz연간", "BIZ 연간", "biz(연간)"],
          "Trial": ["Trial", "trial", "무료체험(Trial)"]}
    ds = ("iso", "dot", "dots", "kor", "compact")
    lines = []
    for c in sorted({e[2] for e in events}):
        ce = [e for e in events if e[2] == c]
        rng.shuffle(ce)
        for e in ce:
            pl = (" " + rng.choice(pv[e[4]])) if e[4] else ""
            lines.append(f"- [{e[0]}] {_dt(e[1], rng.choice(ds))} {c} {e[3]}{pl}")
    for k in rng.sample(range(len(lines)), 10):
        lines.insert(k + 1, lines[k])
    for k in (50, 120, 190):
        lines.insert(k, "(참고) 이 사이에 3월 누락분이 섞여 있음")
    price = {"Basic": 29000, "Pro": 89000, "Biz": 199000, "Pro연간": 790000 // 12, "Biz연간": 1990000 // 12, "Trial": 0}

    def canon(p):
        p = p.replace(" ", "").replace("(", "").replace(")", "").lower().replace("무료체험", "")
        return {"basic": "Basic", "pro": "Pro", "biz": "Biz", "pro연간": "Pro연간", "biz연간": "Biz연간", "trial": "Trial"}[p]

    def solve(old_pro=False, annual_full=False, apply_invalid=False):
        evs = {}
        for ln in lines:
            m = re.match(r"- \[(E\d+)\] (.+?) (K\d{3}) (신규|변경|해지)(?: (.+))?$", ln)
            if not m:
                continue
            evs[m.group(1)] = (_parse_dt(m.group(2)), m.group(1), m.group(3), m.group(4), canon(m.group(5)) if m.group(5) else "")
        state, churn = {}, set()
        for d, eid, c, typ, p in sorted(evs.values()):
            cur = state.get(c)
            if typ == "신규" and cur is None:
                state[c] = p
            elif typ == "변경" and (cur is not None or apply_invalid):
                state[c] = p
            elif typ == "해지" and cur is not None:
                state[c] = None
                if d.month == 9:
                    churn.add(c)
        pr = dict(price)
        if old_pro:
            pr["Pro"] = 79000
        if annual_full:
            pr["Pro연간"], pr["Biz연간"] = 790000, 1990000
        act = [p for p in state.values() if p]
        return {"mrr_end": sum(pr[p] for p in act), "active_paid": sum(1 for p in act if p != "Trial"),
                "churned_sep": len(churn)}

    truth = solve()
    wrong = [solve(old_pro=True), solve(annual_full=True), solve(apply_invalid=True)]
    prompt = (
        "구독 서비스 이벤트 로그를 고객별로 정렬된 상태로 받았습니다(고객 안에서는 순서가 뒤섞여 있음). "
        "2026-09-30 영업 종료 시점의 MRR(월 반복 매출)을 계산해 주세요.\n\n[요금표]\n"
        + _md(["플랜", "요금"], [["Basic", "월 29,000원"], ["Pro", "월 79,000원"], ["Biz", "월 199,000원"],
                                 ["Pro연간", "연 790,000원"], ["Biz연간", "연 1,990,000원"], ["Trial", "무료"]])
        + "\n\n[가격 변경 공지] 2026-07-01부터 Pro 요금은 월 89,000원입니다. 기존 구독자에게도 같은 날부터 적용됩니다. "
        "요금표와 공지가 다르면 공지가 우선입니다.\n\n[이벤트 로그] 형식: - [이벤트ID] 날짜 고객 유형 플랜\n" + "\n".join(lines)
        + "\n\n규칙:\n"
        "1. '(참고)' 줄은 데이터가 아닙니다. 이벤트ID가 같은 줄은 한 번만 셉니다.\n"
        "2. 고객마다 이벤트를 날짜순(같은 날이면 이벤트ID 순)으로 처리합니다.\n"
        "3. '신규'는 구독이 없는 고객이 해당 플랜으로 구독을 시작하는 것, '변경'은 구독 중인 고객의 플랜을 바꾸는 것, "
        "'해지'는 그 날로 구독을 끝내는 것입니다. 구독 중이 아닌 고객의 '변경'·'해지', 구독 중인 고객의 '신규'는 잘못 들어온 이벤트이니 무시합니다.\n"
        "4. 플랜명의 대소문자·띄어쓰기·괄호는 무시합니다(예: pro(연간) = Pro연간, 무료체험(Trial) = Trial).\n"
        "5. MRR = 9/30 시점 구독 중인 고객의 월 요금 합. 연간 플랜의 월 요금 = 연 요금 ÷ 12, 원 미만 버림. Trial은 0원.\n\n"
        "9/30 MRR, 9/30 유료 구독 고객 수(Trial 제외), 9월에 해지한 고객 수를 알려주세요. "
        + JSON_RULE + '{"mrr_end": 원(정수), "active_paid": 정수, "churned_sep": 정수}')
    _add(n, "sales_mrr", prompt, {"mrr_end": "int", "active_paid": "int", "churned_sep": "int"}, truth, wrong,
         {"rows": len(lines) + 6, "tables": 3, "steps": 5,
          "mess": ["dup_rows", "memo_lines", "unsorted_events", "mixed_dates", "case_variants", "invalid_events",
                   "price_notice_contradiction", "prose_list"]})


def _hk37():
    """대리점 수수료: 등급 이력(늦은 변경일), 등급×품목군 요율, 월 실적 보너스, 반품·판촉물 예외."""
    n = 37
    rng = random.Random(1000 + n)
    ags = ["강남", "서초", "분당", "수원", "인천", "대전", "청주", "광주", "전주", "대구", "부산", "울산", "창원", "제주", "춘천"]
    ags = [a + "대리점" for a in ags]
    grade = {a: rng.choice("ABC") for a in ags}
    mrows = [[a, grade[a], _dt(date(2025, 1, 2) + timedelta(days=rng.randrange(300)), "iso")] for a in ags]
    chg = rng.choice([a for a in ags if grade[a] != "A"])
    newg = "A" if grade[chg] == "B" else "B"
    mrows.append([chg, newg, _dt(date(2026, 5, 1), "iso")])
    rng.shuffle(mrows)
    rates = {"A": {"가전": 8, "생활": 10, "소모품": 12, "판촉물": 0}, "B": {"가전": 6, "생활": 8, "소모품": 10, "판촉물": 0},
             "C": {"가전": 4, "생활": 6, "소모품": 8, "판촉물": 0}}
    cats = ["가전", "생활", "소모품", "판촉물"]
    sales = []
    big = rng.sample(ags, 6)
    for i in range(290):
        a = rng.choice(big) if rng.random() < 0.45 else rng.choice(ags)
        d = date(2026, 7, 1) + timedelta(days=rng.randrange(92))
        kind = "반품" if rng.random() < 0.1 else "판매"
        amt = rng.randrange(10, 600) * 10000 if kind == "판매" else rng.randrange(5, 60) * 10000
        sales.append([d, a, rng.choice(cats), kind, amt])
    sales.sort(key=lambda s: s[0])
    ams = ("won", "plain", "man", "chun", "ko", "hangul")
    lines = []
    tot = 0
    for i, s in enumerate(sales):
        av = rng.choice([s[1], s[1].replace("대리점", " 대리점"), s[1] + " ", s[1].replace("대리점", "")])
        row = [f"AG{i + 1:04d}", _dt(s[0], rng.choice(("iso", "dot", "dots", "compact"))), av, s[2], s[3],
               _amt(s[4], rng.choice(ams), rng)]
        lines.append(row)
        tot += s[4] if s[3] == "판매" else -s[4]
        if i % 47 == 13:
            lines.append(list(row))
        if i + 1 == len(sales) or sales[i + 1][0].month != s[0].month:
            lines.append(["", "", "", "", f"{s[0].month}월 합계", _amt(tot, "won", rng)])
            tot = 0
    for k in (30, 130, 230):
        lines.insert(k, ["※ 반품은 금액을 양수로 적고 구분에 '반품' 표기", "", "", "", "", ""])

    def akey(s):
        return _norm(s).replace("대리점", "")

    def solve(old_grade=False, keep_dup=False, gross_bonus=False, promo_in=False):
        g = {}
        for a, gr, d in sorted(mrows, key=lambda r: r[2], reverse=old_grade):
            g[akey(a)] = gr
        seen, net = set(), {}
        for r in lines:
            if not r[0] or r[0].startswith("※"):
                continue
            if r[0] in seen and not keep_dup:
                continue
            seen.add(r[0])
            m = _parse_dt(r[1]).month
            k = (akey(r[2]), m)
            v = _parse_amt(r[5])
            sign = 1 if r[4] == "판매" else -1
            net.setdefault(k, {c: [0, 0] for c in cats})[r[3]][0] += sign * v
            net[k][r[3]][1] += v if sign > 0 else 0
        fees, bonus = {}, set()
        for (a, m), cd in sorted(net.items()):
            base = sum((cd[c][1] if gross_bonus else cd[c][0]) for c in cats if c != "판촉물" or promo_in)
            b = 1 if base >= 30_000_000 else 0
            if b:
                bonus.add(a)
            f = 0
            for c in cats:
                r = rates[g[a]][c] + (b if c != "판촉물" else 0)
                f += max(cd[c][0], 0) * r // 100
            fees[a] = fees.get(a, 0) + _floor10(f)
        full = {akey(a): a for a in ags}
        top, _ = _argmax(fees)
        return {"total_fee": sum(fees.values()), "top_agency": full[top], "bonus_agencies": sorted(full[a] for a in bonus)}

    truth = solve()
    assert truth["bonus_agencies"]
    wrong = [solve(old_grade=True), solve(keep_dup=True), solve(gross_bonus=True), solve(promo_in=True)]
    wrong = [w for w in wrong if w != truth]
    prompt = (
        "3분기 대리점 판매 수수료 정산입니다. 판매 내역(CSV), 대리점 등급표(탭), 수수료율표(마크다운)를 드립니다.\n\n[판매 내역]\n"
        + _csv(["판매번호", "일자", "대리점", "품목군", "구분", "금액"], lines)
        + "\n\n[대리점 등급표]\n" + _tsv(["대리점", "등급", "변경일"], mrows)
        + "\n\n[수수료율표] (%)\n" + _md(["등급"] + cats, [[k] + [rates[k][c] for c in cats] for k in "ABC"])
        + "\n\n규칙:\n"
        "1. '※' 줄과 'N월 합계' 줄은 데이터가 아닙니다. 판매번호가 같은 줄은 한 번만 셉니다.\n"
        "2. 대리점명은 '대리점' 글자 유무와 띄어쓰기를 무시합니다(예: '강남', '강남 대리점' = 강남대리점).\n"
        "3. 등급표에 같은 대리점이 두 줄이면 변경일이 늦은 줄의 등급을 3분기 내내 적용합니다.\n"
        "4. 금액은 원·천원·만원·한글 표기를 원으로 환산합니다. 반품은 같은 대리점·같은 달·같은 품목군 판매에서 뺍니다(순매출). "
        "품목군 순매출이 음수면 0으로 봅니다.\n"
        "5. 월 보너스: 대리점의 그 달 순매출(판촉물 제외, 반품 차감 후)이 3,000만원 이상이면 그 달 가전·생활·소모품 요율에 1%p를 더합니다. 판촉물은 항상 0%입니다.\n"
        "6. 대리점·월별 수수료 = Σ(품목군 순매출 × 요율), 품목군별 원 미만 버림, 대리점·월 합계는 10원 미만 버림. 분기 수수료는 3개월 합입니다.\n\n"
        "전체 수수료 합계, 분기 수수료가 가장 큰 대리점, 보너스를 한 달이라도 받은 대리점 목록(가나다순, '○○대리점' 형태)을 알려주세요. "
        + JSON_RULE + '{"total_fee": 원(정수), "top_agency": "○○대리점", "bonus_agencies": ["○○대리점", ...]}')
    _add(n, "sales_agency", prompt, {"total_fee": "int", "top_agency": "str", "bonus_agencies": "list"}, truth, wrong,
         {"rows": len(lines) + len(mrows) + 3, "tables": 3, "steps": 6,
          "mess": ["dup_rows", "memo_lines", "subtotal_rows", "mixed_units", "korean_amounts", "hangul_amounts",
                   "name_variants", "grade_history_contradiction"]})


def _hk38():
    """포인트: 등급별 적립(승급일), 상품권 결제 적립 제외, 선입선출 사용, 2025년 적립분 6/30 소멸, 잔액 초과 사용."""
    n = 38
    rng = random.Random(1000 + n)
    mem = rng.sample(PEOPLE, 28)
    gold = set(rng.sample(mem, 7))
    promoted = rng.choice([m for m in mem if m not in gold])
    promo_day = date(2026, 4, 1)
    start, end = date(2025, 7, 1), date(2026, 9, 30)
    evs = []
    for i in range(300):
        d = start + timedelta(days=rng.randrange((end - start).days + 1))
        m = rng.choice(mem)
        evs.append([d, m])
    evs.sort(key=lambda e: e[0])
    rows = []
    lots = {m: [] for m in mem}
    over_done = False
    expired_gen = False
    for d, m in evs:
        if d > date(2026, 6, 30) and not expired_gen:
            expired_gen = True
            for L in lots.values():
                for lot in L:
                    if lot[0].year == 2025:
                        lot[1] = 0
        bal = sum(x[1] for x in lots[m])
        if bal > 3000 and rng.random() < 0.35:
            use = rng.randrange(1000, bal // 100 * 100 + 1, 100)
            if not over_done and d > date(2026, 7, 15):
                use = bal + rng.randrange(5, 40) * 100
                over_done = True
            rows.append([d, m, "사용", use, ""])
            left = use
            for lot in lots[m]:
                t = min(lot[1], left)
                lot[1] -= t
                left -= t
        else:
            amt = rng.randrange(10, 500) * 1000 + rng.choice([0, 0, 300, 700])
            pay = rng.choice(["카드", "카드", "카드", "현금", "상품권"])
            rows.append([d, m, "구매", amt, pay])
            if pay != "상품권":
                g = m in gold or (m == promoted and d >= promo_day)
                lots[m].append([d, amt * (2 if g else 1) // 100])
    assert over_done
    ds = ("iso", "dot", "dots", "slash", "kor")
    lines = []
    for r in rows:
        amt = (f"{r[3]:,}P" if r[2] == "사용" else _amt(r[3], rng.choice(("won", "plain", "krw")), rng))
        lines.append([_dt(r[0], rng.choice(ds)), _person_var(r[1], rng), r[2], amt, r[4]])
    for k in (60, 160, 260):
        lines.insert(k, ["-- 시스템 이관 구간 --", "", "", "", ""])
    gtable = [[m, "골드" if m in gold else "일반"] for m in mem]

    def solve(no_expire=False, lifo=False, no_gold=False, gift_earn=False, no_cap=False):
        lots = {}
        expired = 0
        done_exp = False
        for r in lines:
            if r[0].startswith("--"):
                continue
            d = _parse_dt(r[0])
            if d > date(2026, 6, 30) and not done_exp:
                done_exp = True
                if not no_expire:
                    for m in lots:
                        for lot in lots[m]:
                            if lot[0].year == 2025:
                                expired += lot[1]
                                lot[1] = 0
            m = _norm(r[1])
            L = lots.setdefault(m, [])
            if r[2] == "구매":
                if r[4] == "상품권" and not gift_earn:
                    continue
                g = (_norm(m) in {_norm(x) for x in gold} or (m == _norm(promoted) and d >= promo_day)) and not no_gold
                L.append([d, _parse_amt(r[3]) * (2 if g else 1) // 100])
            else:
                left = int(r[3].rstrip("P").replace(",", ""))
                bal = sum(x[1] for x in L)
                if left > bal and not no_cap:
                    left = bal
                for lot in (reversed(L) if lifo else L):
                    t = min(lot[1], left)
                    lot[1] -= t
                    left -= t
                if left:
                    L.append([d, -left])
        balm = {m: sum(x[1] for x in L) for m, L in lots.items()}
        top, _ = _argmax(balm)
        name = {_norm(x): x for x in mem}
        return {"expired_total": expired, "balance_total": sum(balm.values()), "top_member": name[top]}

    truth = solve()
    assert truth["expired_total"] > 0
    wrong = [solve(no_expire=True), solve(lifo=True), solve(no_gold=True), solve(gift_earn=True), solve(no_cap=True)]
    wrong = [w for w in wrong if w != truth]
    prompt = (
        "멤버십 포인트 원장(2025-07-01 ~ 2026-09-30)을 마크다운 표로 붙여요. 포인트를 처음부터 다시 계산해 2026-09-30 잔액을 확인하려고 합니다.\n\n"
        "[회원 등급]\n" + _tsv(["회원", "등급"], gtable)
        + f"\n\n[등급 변경 공지] {promoted} 회원은 {_dt(promo_day, 'kor')}부터 골드입니다(그 전 구매는 일반 등급으로 적립). "
        "등급표와 공지가 다르면 공지가 우선입니다.\n\n[원장]\n"
        + _md(["일자", "회원", "구분", "금액", "결제수단"], lines)
        + "\n\n규칙:\n"
        "1. '--'로 시작하는 줄은 데이터가 아닙니다. 회원 이름의 띄어쓰기는 무시합니다. 같은 날짜의 줄은 표 순서대로 처리합니다.\n"
        "2. '구매' 줄: 결제금액의 1%(골드는 2%)를 적립, 포인트 미만 버림. 결제수단이 '상품권'인 구매는 적립하지 않습니다.\n"
        "3. '사용' 줄: 금액(P)만큼 포인트를 씁니다. 적립일이 오래된 포인트부터 차감합니다(선입선출). "
        "사용 포인트가 그 시점 잔액보다 크면 잔액만큼만 사용된 것으로 봅니다.\n"
        "4. 2025년에 적립된 포인트 중 2026-06-30 하루가 끝날 때까지 쓰이지 않은 포인트는 그 시점에 소멸합니다(6/30 사용분까지 반영한 뒤 소멸).\n\n"
        "소멸 포인트 합계, 2026-09-30 기준 전체 회원 잔액 합계, 잔액이 가장 많은 회원을 알려주세요. "
        + JSON_RULE + '{"expired_total": 포인트(정수), "balance_total": 포인트(정수), "top_member": 이름}')
    _add(n, "sales_points", prompt, {"expired_total": "int", "balance_total": "int", "top_member": "str"}, truth, wrong,
         {"rows": len(lines) + len(gtable), "tables": 2, "steps": 5,
          "mess": ["memo_lines", "mixed_dates", "mixed_units", "name_variants", "grade_notice_contradiction",
                   "overdraw_row"]})


def _hk39():
    """채널 정산: 주문번호 접두어로 채널 확정(채널 칸과 모순), 채널×카테고리 수수료, S마켓 가전 상한, 부분환불·취소."""
    n = 39
    rng = random.Random(1000 + n)
    ch = {"S": "S마켓", "N": "N스토어", "J": "자사몰", "T": "T몰"}
    rate = {"S": {"의류": 12, "식품": 9, "가전": 7}, "N": {"의류": 6, "식품": 5, "가전": 4},
            "T": {"의류": 10, "식품": 8, "가전": 6}, "J": {"의류": 0, "식품": 0, "가전": 0}}
    orders = []
    for i in range(290):
        p = rng.choice("SSNNJT")
        cat = rng.choice(["의류", "식품", "가전"])
        amt = (rng.randrange(80, 2500) if cat == "가전" else rng.randrange(8, 300)) * 1000 + rng.choice([0, 500])
        r = rng.random()
        st, rf = ("취소", 0) if r < 0.07 else (("부분환불", rng.randrange(1, max(2, amt // 4000)) * 1000) if r < 0.17 else ("정상", 0))
        orders.append([f"{p}-{260900 + i}", ch[p], cat, amt, st, rf])
    wrongch = rng.sample([o for o in orders if o[4] == "정상"], 3)
    for o in wrongch:
        o[1] = rng.choice([v for k, v in ch.items() if v != o[1]])
    ams = ("won", "plain", "krw", "ko")
    lines = []
    for i, o in enumerate(orders):
        row = [o[0], o[1], o[2], _amt(o[3], rng.choice(ams), rng), o[4], _amt(o[5], "won", rng) if o[5] else ""]
        lines.append(row)
        if i % 41 == 7:
            lines.append(list(row))
        if i % 100 == 50:
            lines.append(["메모: 정산 담당 교체", "", "", "", "", ""])
    lines.append(["합계", "", "", _amt(sum(o[3] for o in orders), "won", rng), "", ""])

    def solve(use_col=False, no_cap=False, gross=False, keep_cancel=False, keep_dup=False):
        inv = {v: k for k, v in ch.items()}
        seen, sett, fee_t, caps = set(), 0, 0, 0
        for r in lines:
            if not re.match(r"[SNJT]-\d+", r[0]):
                continue
            if r[0] in seen and not keep_dup:
                continue
            seen.add(r[0])
            if r[4] == "취소" and not keep_cancel:
                continue
            p = inv[r[1]] if use_col else r[0][0]
            base = _parse_amt(r[3]) - (_parse_amt(r[5]) if (r[5] and not gross) else 0)
            if p == "J":
                f = _floor10(base * 33 // 1000)
            else:
                f = _floor10(base * rate[p][r[2]] // 100)
                if p == "S" and r[2] == "가전" and f > 50000 and not no_cap:
                    f = 50000
                    caps += 1
            sett += base - f
            fee_t += f
        return {"settlement_total": sett, "fee_total": fee_t, "cap_count": caps}

    truth = solve()
    assert truth["cap_count"] >= 3
    wrong = [solve(use_col=True), solve(no_cap=True), solve(gross=True), solve(keep_cancel=True), solve(keep_dup=True)]
    wrong = [w for w in wrong if w != truth]
    prompt = (
        "9월 판매 채널별 정산 자료를 엑셀에서 복사했습니다(탭 구분). 채널 수수료를 빼고 받을 정산액을 계산해 주세요.\n\n[주문]\n"
        + _tsv(["주문번호", "채널", "카테고리", "판매금액", "상태", "환불액"], lines)
        + "\n\n[채널 수수료율] (%)\n"
        + _md(["채널", "의류", "식품", "가전"], [[ch[k]] + [rate[k][c] for c in ("의류", "식품", "가전")] for k in "SNT"])
        + "\n\n규칙:\n"
        "1. '메모:' 줄과 맨 아래 '합계' 줄은 데이터가 아닙니다. 주문번호가 같은 줄은 한 건만 셉니다.\n"
        "2. 주문번호 앞 글자가 채널입니다: S-=S마켓, N-=N스토어, J-=자사몰, T-=T몰. 채널 칸과 주문번호 앞 글자가 다르면 주문번호 쪽을 믿습니다.\n"
        "3. 상태 '취소' 주문은 정산에서 뺍니다. '부분환불'은 판매금액 − 환불액을 기준금액으로 합니다. 그 외는 판매금액이 기준금액입니다.\n"
        "4. 수수료 = 기준금액 × 채널·카테고리 요율, 10원 미만 버림. 자사몰은 채널 수수료가 없고 대신 결제대행 수수료 3.3%(10원 미만 버림)를 뗍니다.\n"
        "5. 예외: S마켓 가전은 주문 1건당 수수료가 50,000원을 넘지 않습니다(넘으면 50,000원).\n"
        "6. 정산액 = 기준금액 − 수수료(결제대행 수수료 포함).\n\n"
        "정산액 합계, 수수료(결제대행 포함) 합계, 5번 상한이 적용된 주문 수를 알려주세요. "
        + JSON_RULE + '{"settlement_total": 원(정수), "fee_total": 원(정수), "cap_count": 정수}')
    _add(n, "sales_channel_fee", prompt, {"settlement_total": "int", "fee_total": "int", "cap_count": "int"}, truth, wrong,
         {"rows": len(lines) + 3, "tables": 2, "steps": 6,
          "mess": ["dup_rows", "memo_lines", "total_row", "mixed_units", "channel_prefix_contradiction"]})


def _hk40():
    """환불 심사: 요청(탭) + 주문(CSV) 조인, 경과일·사유·상품상태 규칙, 중복 요청, 요청금액≠주문금액."""
    n = 40
    rng = random.Random(1000 + n)
    orders = {}
    for i in range(200):
        od = date(2026, 6, 1) + timedelta(days=rng.randrange(100))
        orders[f"O{70000 + i * 7}"] = (od, od + timedelta(days=rng.randrange(1, 5)), rng.randrange(15, 400) * 1000 + rng.choice([0, 500]))
    oids = sorted(orders)
    reqs = []
    for i, oid in enumerate(rng.sample(oids, 125)):
        _, dl, amt = orders[oid]
        rd = dl + timedelta(days=rng.choice([rng.randrange(0, 8), rng.randrange(0, 8), rng.randrange(8, 31), rng.randrange(31, 45)]))
        reason = rng.choice(["단순변심", "단순변심", "불량", "오배송"])
        cond = rng.choice(["미개봉", "개봉", "사용흔적"])
        reqs.append([rd, oid, reason, cond, amt])
    for oid in rng.sample([r[1] for r in reqs], 6):
        _, dl, amt = orders[oid]
        reqs.append([dl + timedelta(days=rng.randrange(1, 20)), oid, rng.choice(["불량", "단순변심"]), "개봉", amt])
    reqs.sort(key=lambda r: r[0])
    rows = []
    for i, r in enumerate(reqs):
        rows.append([f"R{i + 1:04d}"] + r)
    contra = [r for r in rows if r[3] in ("불량", "오배송")][2]
    contra[5] = contra[5] + 20000
    ds = ("iso", "dot", "dots", "md", "mdk")
    lines = []
    for r in rows:
        row = [r[0], _dt(r[1], rng.choice(ds)), r[2], r[3], r[4], _amt(r[5], rng.choice(("won", "plain", "ko")), rng)]
        lines.append(row)
        if rng.random() < 0.06:
            lines.append(list(row))
    for k in (40, 100):
        lines.insert(k, ["(상담 메모) 고객 재문의 건 포함", "", "", "", "", ""])
    olines = [[o, _dt(orders[o][0], rng.choice(("iso", "dot", "compact"))), _dt(orders[o][1], rng.choice(("iso", "dot", "compact"))),
               _amt(orders[o][2], rng.choice(("won", "plain")), rng)] for o in oids]

    def solve(use_req_amt=False, keep_dup_req=False, no_open_fee=False, count_dup_rej=False, from_order=False):
        omap = {o[0]: (_parse_dt(o[1]), _parse_dt(o[2]), _parse_amt(o[3])) for o in olines}
        seen, reqs = set(), []
        for r in lines:
            if r[0].startswith("("):
                continue
            if r[0] in seen:
                continue
            seen.add(r[0])
            reqs.append((_parse_dt(r[1], 2026), r[0], r[2], r[3], r[4], _parse_amt(r[5])))
        reqs.sort()
        done, ok, tot, rej = set(), 0, 0, 0
        for rd, rid, oid, reason, cond, ramt in reqs:
            if oid in done and not keep_dup_req:
                if count_dup_rej:
                    rej += 1
                continue
            done.add(oid)
            od, dl, amt = omap[oid]
            if use_req_amt:
                amt = ramt
            days = (rd - (od if from_order else dl)).days
            refund = None
            if reason == "단순변심":
                if days <= 7 and cond != "사용흔적":
                    refund = amt - 6000 - (0 if (cond == "미개봉" or no_open_fee) else _floor10(amt // 10))
            elif days <= 30:
                refund = amt
            if refund is None:
                rej += 1
            else:
                ok += 1
                tot += refund
        return {"approved_count": ok, "refund_total": tot, "rejected_count": rej}

    truth = solve()
    wrong = [solve(use_req_amt=True), solve(keep_dup_req=True), solve(no_open_fee=True), solve(count_dup_rej=True),
             solve(from_order=True)]
    wrong = [w for w in wrong if w != truth]
    prompt = (
        "6~9월 환불 요청을 정책대로 심사해 주세요. 요청 목록(탭, 요청일은 모두 2026년)과 주문 목록(CSV)을 드립니다.\n\n[환불 요청]\n"
        + _tsv(["요청번호", "요청일", "주문번호", "사유", "상품상태", "요청금액"], lines)
        + "\n\n[주문 목록]\n" + _csv(["주문번호", "주문일", "배송완료일", "결제금액"], olines)
        + "\n\n규칙:\n"
        "1. '(상담 메모)' 줄은 데이터가 아닙니다. 요청번호가 같은 줄은 한 건입니다.\n"
        "2. 경과일 = 요청일 − 배송완료일(일수). 주문일이 아니라 배송완료일 기준입니다.\n"
        "3. 환불 기준 금액은 주문 목록의 결제금액입니다. 요청금액이 결제금액과 달라도 결제금액을 씁니다.\n"
        "4. 사유 '단순변심': 경과일 7일 이하이고 상품상태가 '사용흔적'이 아니면 승인. 환불액 = 결제금액 − 왕복배송비 6,000원, "
        "상품상태가 '개봉'이면 결제금액의 10%(10원 미만 버림)를 추가로 뺍니다. 그 밖의 단순변심은 거절.\n"
        "5. 사유 '불량'·'오배송': 경과일 30일 이하이면 상품상태와 관계없이 결제금액 전액 환불, 30일 초과는 거절.\n"
        "6. 같은 주문번호에 요청이 여러 번이면 요청일이 가장 이른 요청(같은 날이면 요청번호가 작은 것)만 심사하고, "
        "나머지는 심사 대상이 아닙니다(승인·거절 어느 쪽에도 세지 않음).\n\n"
        "승인 건수, 환불액 합계, 거절 건수를 알려주세요. "
        + JSON_RULE + '{"approved_count": 정수, "refund_total": 원(정수), "rejected_count": 정수}')
    _add(n, "sales_refund", prompt, {"approved_count": "int", "refund_total": "int", "rejected_count": "int"}, truth, wrong,
         {"rows": len(lines) + len(olines), "tables": 2, "steps": 6,
          "mess": ["dup_rows", "memo_lines", "mixed_dates", "year_omitted", "mixed_units",
                   "request_amount_contradiction", "duplicate_requests"]})


# ================================================================= 총무 (hk_41 - hk_45)


def _c_hm(s):
    """'14:00' / '1400' -> minutes."""
    s = s.strip().replace(":", "")
    return int(s[:-2]) * 60 + int(s[-2:])


def _c_stamp(s):
    """'2026.9.1 10:23' (any _dt date style + hh:mm) -> (date, minutes)."""
    d, t = s.rsplit(" ", 1)
    return (_parse_dt(d), _c_hm(t))


def _hk41():
    """회의실 예약: 취소·정원 초과(증설 공지 우선)·공사 기간 제외 후 신청 시각 순 선착 배정."""
    n = 41
    rng = random.Random(1000 + n)
    rooms = {"대회의실": 20, "중회의실A": 10, "중회의실B": 10, "소회의실1": 6, "소회의실2": 6, "화상회의실": 8}
    real = dict(rooms, 중회의실A=14)
    closed = ("소회의실2", date(2026, 9, 14), date(2026, 9, 18))
    days = [d for d in _days(date(2026, 9, 1), date(2026, 9, 30)) if _is_biz(d, HOLIDAYS_2026)]
    bk = []
    used_stamp = set()
    for i in range(205):
        room = rng.choice(list(rooms))
        d = rng.choice(days[:10]) if rng.random() < 0.5 else rng.choice(days)
        st = rng.randrange(18, 34) * 30
        dur = rng.choice([30, 60, 60, 90, 120, 180])
        en = min(st + dur, 18 * 60)
        ppl = rng.randrange(2, real[room] + 4)
        while True:
            sd = d - timedelta(days=rng.randrange(1, 15))
            sm = rng.randrange(8 * 60, 19 * 60)
            if (sd, sm) not in used_stamp:
                used_stamp.add((sd, sm))
                break
        stt = "취소" if rng.random() < 0.08 else "확정"
        bk.append([room, d, st, en, ppl, sd, sm, stt])
    bk.sort(key=lambda b: (b[1], b[2], b[0]))
    rv = {"중회의실A": ["중회의실A", "중회의실 A", "중회의실a"], "중회의실B": ["중회의실B", "중회의실 B", "중회의실b"],
          "소회의실1": ["소회의실1", "소회의실 1"], "소회의실2": ["소회의실2", "소회의실 2"], "대회의실": ["대회의실"],
          "화상회의실": ["화상회의실", "화상 회의실"]}
    lines = []
    for i, b in enumerate(bk):
        tf = rng.choice(["{a:02d}:{b:02d}~{c:02d}:{d:02d}", "{a:02d}{b:02d}-{c:02d}{d:02d}", "{a:02d}:{b:02d}-{c:02d}:{d:02d}"])
        tt = tf.format(a=b[2] // 60, b=b[2] % 60, c=b[3] // 60, d=b[3] % 60)
        row = [f"B{i + 1:04d}", rng.choice(rv[b[0]]), _dt(b[1], rng.choice(("iso", "dots", "mdk", "md"))), tt, f"{b[4]}명",
               f"{_dt(b[5], rng.choice(('iso', 'dot', 'dots')))} {b[6] // 60:02d}:{b[6] % 60:02d}", b[7]]
        lines.append(row)
        if rng.random() < 0.05:
            lines.append(list(row))
    for k in (50, 120):
        lines.insert(k, ["(총무팀 메모) 이 아래는 그룹웨어 2차 추출분", "", "", "", "", "", ""])
    rkey = {_norm(r): r for r in rooms}

    def solve(cap=None, row_order=False, ignore_closed=False, no_cap_check=False, keep_cancel=False):
        cap = cap or real
        seen, cand = set(), []
        for i, r in enumerate(lines):
            if not r[0].startswith("B"):
                continue
            if r[0] in seen:
                continue
            seen.add(r[0])
            if r[6] == "취소" and not keep_cancel:
                continue
            room = rkey[_norm(r[1])]
            d = _parse_dt(r[2], 2026)
            a, b = re.split(r"[~-]", r[3])
            st, en = _c_hm(a), _c_hm(b)
            ppl = int(r[4].rstrip("명"))
            if ppl > cap[room] and not no_cap_check:
                continue
            if room == closed[0] and closed[1] <= d <= closed[2] and not ignore_closed:
                continue
            cand.append(((i,) if row_order else _c_stamp(r[5]), room, d, st, en))
        cand.sort()
        acc = []
        for _, room, d, st, en in cand:
            if all(not (x[0] == room and x[1] == d and st < x[3] and x[2] < en) for x in acc):
                acc.append((room, d, st, en))
        mins = {}
        for room, d, st, en in acc:
            mins[room] = mins.get(room, 0) + en - st
        top, _ = _argmax(mins)
        return {"approved_count": len(acc), "approved_minutes": sum(mins.values()), "top_room": top}

    truth = solve()
    wrong = [solve(cap=rooms), solve(row_order=True), solve(ignore_closed=True), solve(no_cap_check=True), solve(keep_cancel=True)]
    wrong = [w for w in wrong if w != truth]
    prompt = (
        "9월 회의실 예약을 그룹웨어에서 뽑았는데 겹치는 예약이 많습니다. 규칙대로 확정 예약을 다시 배정해 주세요. 사용일은 모두 2026년입니다.\n\n"
        "[회의실 정원]\n" + _tsv(["회의실", "정원"], [[r, f"{c}명"] for r, c in rooms.items()])
        + "\n\n[총무팀 공지] 중회의실A는 9월 1일 증설 공사를 마쳐 정원이 14명입니다(정원표보다 공지가 우선). "
        f"소회의실2는 {_dt(closed[1], 'kor')}부터 {_dt(closed[2], 'kor')}까지 누수 공사로 사용할 수 없습니다.\n\n[예약 목록]\n"
        + _md(["예약ID", "회의실", "사용일", "시간", "인원", "신청일시", "상태"], lines)
        + "\n\n규칙:\n"
        "1. '(총무팀 메모)' 줄은 데이터가 아닙니다. 예약ID가 같은 줄은 한 건입니다. 회의실명의 띄어쓰기·대소문자는 무시합니다.\n"
        "2. 상태 '취소'는 뺍니다. 인원이 회의실 정원보다 많으면 뺍니다. 공사 기간(시작·종료일 포함)의 소회의실2 예약은 뺍니다.\n"
        "3. 남은 예약을 신청일시가 이른 순서로 하나씩 확정합니다. 같은 회의실·같은 날에 이미 확정된 예약과 시간이 겹치면 확정하지 않습니다. "
        "끝나는 시각과 시작 시각이 같은 것은 겹침이 아닙니다(예: 10:00~11:00과 11:00~12:00).\n"
        "4. 시간은 '14:00~15:30', '1400-1530', '14:00-15:30'처럼 섞여 있습니다.\n\n"
        "확정 예약 건수, 확정 예약 사용 시간 합계(분), 확정 사용 시간이 가장 긴 회의실을 알려주세요. "
        + JSON_RULE + '{"approved_count": 정수, "approved_minutes": 분(정수), "top_room": 회의실명}')
    _add(n, "ga_room", prompt, {"approved_count": "int", "approved_minutes": "int", "top_room": "str"}, truth, wrong,
         {"rows": len(lines) + len(rooms), "tables": 2, "steps": 5,
          "mess": ["dup_rows", "memo_lines", "mixed_dates", "year_omitted", "time_format_mix", "name_variants",
                   "capacity_notice_contradiction"]})


def _hk42():
    """차량 유류비: 운행일지(누적km) + 차량 연비 + 월별 유가, 주말 업무는 승인분만, 역전 주행거리 1건."""
    n = 42
    rng = random.Random(1000 + n)
    cars = [("12가3456", 115, "휘발유"), ("34나5678", 98, "경유"), ("56다7890", 132, "휘발유"), ("78라1234", 84, "경유"),
            ("90마5678", 150, "휘발유")]
    price = {(m, f): p for m in (7, 8, 9) for f, p in (("휘발유", rng.randrange(1620, 1760)), ("경유", rng.randrange(1480, 1620)))}
    drivers = rng.sample(PEOPLE, 9)
    odo = {c[0]: rng.randrange(20000, 90000) for c in cars}
    logs = []
    for i in range(215):
        d = date(2026, 7, 1) + timedelta(days=rng.randrange(92))
        logs.append([d, rng.choice(cars)[0]])
    logs.sort()
    rows = []
    for d, c in logs:
        km = rng.randrange(8, 260)
        wk = d.weekday() >= 5
        use = "개인" if rng.random() < 0.12 else "업무"
        rows.append([d, c, rng.choice(drivers), odo[c], odo[c] + km, use])
        odo[c] += km
    wkend = [r for r in rows if r[0].weekday() >= 5 and r[5] == "업무"]
    assert len(wkend) >= 8
    approved = rng.sample(wkend, len(wkend) // 2)
    swap = rng.choice([r for r in rows if r[0].weekday() < 5 and r[5] == "업무"])
    cv = {c[0]: [c[0], c[0][:3] + " " + c[0][3:], c[0][:2] + " " + c[0][2:]] for c in cars}
    lines = []
    for r in rows:
        s, e = (r[4], r[3]) if r is swap else (r[3], r[4])
        row = [_dt(r[0], rng.choice(("iso", "dot", "dots", "compact"))), rng.choice(cv[r[1]]), _person_var(r[2], rng),
               f"{s:,}", f"{e:,}", r[5]]
        lines.append(row)
        if rng.random() < 0.05:
            lines.append(list(row))
    for k in (45, 150):
        lines.insert(k, ["※ 7월분 수기 일지 입력", "", "", "", "", ""])
    ap_text = "\n".join(f"- {_dt(r[0], 'kor')} {r[1]} ({r[2]}) 주말 업무 운행 승인" for r in sorted(approved, key=lambda r: (r[0], r[1])))

    def solve(signed=False, all_weekend=False, keep_dup=False, flat_price=False):
        eff = {c[0]: (c[1], c[2]) for c in cars}
        appr = {(r[0], r[1]) for r in approved}
        seen, km_t, cost_t, by = set(), 0, 0, {}
        for r in lines:
            if r[0].startswith("※"):
                continue
            key = tuple(r)
            if key in seen and not keep_dup:
                continue
            seen.add(key)
            d = _parse_dt(r[0])
            car = r[1].replace(" ", "")
            if r[5] != "업무":
                continue
            if d.weekday() >= 5 and (d, car) not in appr and not all_weekend:
                continue
            km = _parse_amt(r[4]) - _parse_amt(r[3])
            if not signed:
                km = abs(km)
            e10, fuel = eff[car]
            p = price[(7 if flat_price else d.month, fuel)]
            cost = _floor10(km * p * 10 // e10) if km >= 0 else -_floor10(-km * p * 10 // e10)
            km_t += km
            cost_t += cost
            nm = _norm(r[2])
            by[nm] = by.get(nm, 0) + cost
        top, _ = _argmax(by)
        name = {_norm(x): x for x in drivers}
        return {"business_km": km_t, "fuel_total": cost_t, "top_driver": name[top]}

    truth = solve()
    wrong = [solve(signed=True), solve(all_weekend=True), solve(keep_dup=True), solve(flat_price=True)]
    wrong = [w for w in wrong if w != truth]
    prompt = (
        "3분기 법인차량 운행일지(탭 구분)로 업무용 유류비를 정산해 주세요. 차량 연비표, 월별 유가, 주말 운행 승인 목록도 붙입니다.\n\n[운행일지]\n"
        + _tsv(["일자", "차량번호", "운전자", "출발 누적km", "도착 누적km", "용도"], lines)
        + "\n\n[차량 연비]\n" + _md(["차량번호", "연비(km/L)", "유종"], [[c[0], f"{c[1] / 10:.1f}", c[2]] for c in cars])
        + "\n\n[월별 유가] (원/L)\n" + _csv(["월", "휘발유", "경유"], [[f"{m}월", f"{price[(m, '휘발유')]:,}", f"{price[(m, '경유')]:,}"] for m in (7, 8, 9)])
        + "\n\n[주말 업무 운행 승인 목록]\n" + ap_text
        + "\n\n규칙:\n"
        "1. '※' 줄은 메모입니다. 모든 칸이 똑같은 줄이 반복되면 한 번만 셉니다. 차량번호·운전자 이름의 띄어쓰기는 무시합니다.\n"
        "2. 주행거리 = 도착 누적km − 출발 누적km. 출발이 도착보다 큰 줄은 두 칸을 바꿔 적은 것이니 차이의 절댓값을 씁니다.\n"
        "3. 용도 '업무'만 정산합니다. 토·일요일 업무 운행은 승인 목록에 같은 날짜·같은 차량이 있을 때만 업무로 인정하고, 없으면 정산하지 않습니다.\n"
        "4. 1회 유류비 = 주행거리 ÷ 연비 × 운행한 달의 유종별 유가, 10원 미만 버림(운행 1회마다).\n\n"
        "정산 대상 주행거리 합계(km), 유류비 합계, 유류비 합계가 가장 큰 운전자를 알려주세요. "
        + JSON_RULE + '{"business_km": 정수, "fuel_total": 원(정수), "top_driver": 이름}')
    _add(n, "ga_vehicle", prompt, {"business_km": "int", "fuel_total": "int", "top_driver": "str"}, truth, wrong,
         {"rows": len(lines) + len(cars) + 3 + len(approved), "tables": 4, "steps": 5,
          "mess": ["dup_rows", "memo_lines", "mixed_dates", "name_variants", "swapped_odometer_contradiction", "prose_list"]})


def _hk43():
    """자산 실사: 대장(CSV) vs 실사(탭), 자산번호 표기 정규화, 수리중 예외, 늦은 실사일 우선, 5년 경과 불용 폐기."""
    n = 43
    rng = random.Random(1000 + n)
    depts = ["경영지원팀", "인사팀", "재무팀", "영업1팀", "영업2팀", "개발팀", "디자인팀", "물류팀"]
    kinds = ["노트북", "데스크톱", "모니터", "복합기", "프로젝터", "태블릿", "서버", "의자", "책상", "냉장고"]
    assets = []
    seq = {}
    for i in range(160):
        acq = date(2018, 1, 1) + timedelta(days=rng.randrange(3100))
        seq[acq.year] = seq.get(acq.year, 0) + 1
        aid = f"A-{acq.year}-{seq[acq.year] * 3 + rng.randrange(3):04d}"
        cost = rng.randrange(15, 400) * 10000 + rng.choice([0, 5000])
        assets.append([aid, rng.choice(kinds), rng.choice(depts), acq, cost, "수리중(외부)" if rng.random() < 0.05 else ""])
    assert len({a[0] for a in assets}) == 160
    audit = []
    for a in assets:
        r = rng.random()
        if a[5] and r < 0.8:
            continue
        if r < 0.1:
            continue
        dept = a[2] if rng.random() < 0.88 else rng.choice([d for d in depts if d != a[2]])
        st = rng.choice(["정상"] * 7 + ["불용", "불용", "파손"])
        audit.append([a[0], dept, st, date(2026, 9, 21) + timedelta(days=rng.randrange(5))])
    for k in range(5):
        audit.append([f"A-2026-{9001 + k * 4}", rng.choice(depts), "정상", date(2026, 9, 22)])
    rng.shuffle(audit)
    rdept = {a[0]: a[2] for a in assets}
    cx = next(x for x in audit if x[0] in rdept and x[1] == rdept[x[0]] and x[3] < date(2026, 9, 25))
    moved_to = rng.choice([d for d in depts if d != cx[1]])
    audit.append([cx[0], moved_to, cx[2], cx[3] + timedelta(days=1)])
    cx_first = audit.index(cx)
    audit[cx_first], audit[-1] = audit[-1], audit[cx_first]

    def idv(a):
        return rng.choice([a, a.lower(), a.replace("-", ""), a.replace("-", " ")])

    def dv(d):
        return rng.choice([d, d, d.replace("팀", " 팀"), " " + d])

    alines = [[a[0], a[1], dv(a[2]), _dt(a[3], rng.choice(("iso", "dot", "compact"))),
               _amt(a[4], rng.choice(("won", "plain", "man", "chun")) if a[4] % 1000 == 0 else "won", rng), a[5]] for a in assets]
    ulines = []
    for x in audit:
        row = [idv(x[0]), dv(x[1]), x[2], _dt(x[3], rng.choice(("md", "mdk", "dots")))]
        ulines.append(row)
        if rng.random() < 0.05:
            ulines.append(list(row))
    for k in (40, 110):
        ulines.insert(k, ["// 3층 실사 종료, 4층 시작", "", "", ""])

    def canon(s):
        t = re.sub(r"[\s-]", "", s).upper()
        return f"{t[:1]}-{t[1:5]}-{t[5:]}"

    def solve(repair_lost=False, first_wins=False, no_age=False, raw_id=False):
        reg = {}
        for r in alines:
            reg[r[0]] = (_norm(r[2]), _parse_dt(r[3]), _parse_amt(r[4]), r[5])
        aud = {}
        for r in ulines:
            if r[0].startswith("//"):
                continue
            k = r[0] if raw_id else canon(r[0])
            d = _parse_dt(r[3], 2026)
            if k in aud and not first_wins and d <= aud[k][2]:
                continue
            aud[k] = (_norm(r[1]), r[2], d)
        lost = sorted(k for k, v in reg.items() if k not in aud and (repair_lost or not v[3].startswith("수리중")))
        moved = sum(1 for k, v in aud.items() if k in reg and v[0] != reg[k][0])
        disp = sum(1 for k, v in aud.items() if k in reg and v[1] == "불용" and (no_age or reg[k][1] <= date(2021, 10, 1)))
        return {"lost_ids": lost, "lost_amount": sum(reg[k][2] for k in lost), "moved_count": moved, "disposal_count": disp}

    truth = solve()
    wrong = [solve(repair_lost=True), solve(first_wins=True), solve(no_age=True), solve(raw_id=True)]
    wrong = [w for w in wrong if w != truth]
    prompt = (
        "연말 자산 실사 결과를 대장과 맞춰 보려고 합니다. 자산대장(CSV)과 실사 기록(탭, 실사일은 2026년)을 드립니다. 기준일은 2026-10-01입니다.\n\n"
        "[자산대장]\n" + _csv(["자산번호", "품명", "관리부서", "취득일", "취득가", "비고"], alines)
        + "\n\n[실사 기록]\n" + _tsv(["자산번호", "확인부서", "상태", "실사일"], ulines)
        + "\n\n규칙:\n"
        "1. '//' 줄은 메모입니다. 자산번호는 하이픈·띄어쓰기·대소문자를 무시하고 비교합니다(a20190012 = A-2019-0012). "
        "부서명의 띄어쓰기도 무시합니다.\n"
        "2. 같은 자산이 실사 기록에 여러 번 있으면 실사일이 가장 늦은 기록만 씁니다.\n"
        "3. 분실: 대장에 있는데 실사 기록에 없는 자산. 단, 대장 비고가 '수리중'으로 시작하는 자산은 외부에 있으므로 분실이 아닙니다.\n"
        "4. 이동: 대장과 실사 모두에 있고 확인부서가 관리부서와 다른 자산.\n"
        "5. 폐기 대상: 실사 상태가 '불용'이고 취득일이 2021-10-01 이전(당일 포함)인 자산. 그보다 나중에 취득한 불용 자산은 폐기 대상이 아닙니다.\n"
        "6. 취득가는 원·만원·천원 표기를 원으로 환산합니다.\n\n"
        "분실 자산번호 목록(A-YYYY-NNNN 형식, 오름차순), 분실 자산 취득가 합계, 이동 자산 수, 폐기 대상 수를 알려주세요. "
        + JSON_RULE + '{"lost_ids": ["A-2019-0012", ...], "lost_amount": 원(정수), "moved_count": 정수, "disposal_count": 정수}')
    _add(n, "ga_asset_audit", prompt, {"lost_ids": "list", "lost_amount": "int", "moved_count": "int", "disposal_count": "int"},
         truth, wrong,
         {"rows": len(alines) + len(ulines), "tables": 2, "steps": 6,
          "mess": ["dup_rows", "memo_lines", "id_format_variants", "name_variants", "mixed_dates", "year_omitted",
                   "mixed_units", "repeat_audit_contradiction"]})


def _hk44():
    """관리비 배부: 전표(CSV) × 배부기준(면적/인원/직접/본사부담), 버림 후 끝수는 기준이 가장 큰 부서, 인원 정정."""
    n = 44
    rng = random.Random(1000 + n)
    depts = ["경영지원팀", "영업팀", "개발팀", "마케팅팀", "생산관리팀", "품질팀"]
    area = dict(zip(depts, [180, 240, 410, 150, 320, 205]))
    head = dict(zip(depts, [14, 31, 38, 12, 22, 17]))
    head_new = dict(head, 영업팀=41)
    items = [("임차료", "면적"), ("청소용역비", "면적"), ("경비용역비", "면적"), ("공용전기료", "면적"), ("복리후생-간식", "인원"),
             ("통근버스", "인원"), ("사내식당 위탁", "인원"), ("복합기 임차", "인원"), ("소모품", "직접"), ("광고물 제작", "직접"),
             ("시험장비 수리", "직접"), ("대표이사 차량", "본사부담"), ("이사회 운영", "본사부담")]
    rows = []
    for i in range(135):
        it, basis = rng.choice(items)
        amt = rng.randrange(3, 900) * 1000 + rng.choice([0, 0, 370, 840])
        b = f"직접:{rng.choice(depts)}" if basis == "직접" else basis
        rows.append([f"G{i + 1:04d}", date(2026, 9, 1) + timedelta(days=rng.randrange(30)), it, amt, b])
    rows.sort(key=lambda r: (r[1], r[0]))
    lines = []
    sub = 0
    for i, r in enumerate(rows):
        st = rng.choice(("won", "plain", "chun", "man", "ko")) if r[3] % 1000 == 0 else rng.choice(("won", "plain", "ko"))
        bt = r[4] if not r[4].startswith("직접") else "직접:" + rng.choice([r[4][3:], r[4][3:].replace("팀", " 팀")])
        row = [r[0], _dt(r[1], rng.choice(("iso", "dot", "dots", "kor"))), r[2], _amt(r[3], st, rng), bt]
        lines.append(row)
        sub += r[3]
        if rng.random() < 0.05:
            lines.append(list(row))
        if i % 45 == 44:
            lines.append(["", "", "소계", _amt(sub, "won", rng), ""])
            sub = 0
    lines.insert(70, ["※ 전기료 검침분은 다음 달 반영", "", "", "", ""])

    def solve(old_head=False, keep_dup=False, no_rem=False, hq_alloc=False):
        hc = head if old_head else head_new
        seen, tot = set(), {d: 0 for d in depts}
        dmap = {_norm(d): d for d in depts}
        for r in lines:
            if not r[0].startswith("G"):
                continue
            if r[0] in seen and not keep_dup:
                continue
            seen.add(r[0])
            amt = _parse_amt(r[3])
            basis = r[4]
            if basis == "본사부담":
                if not hq_alloc:
                    continue
                basis = "면적"
            if basis.startswith("직접:"):
                tot[dmap[_norm(basis[3:])]] += amt
                continue
            base = area if basis == "면적" else hc
            s = sum(base.values())
            shares = {d: amt * base[d] // s for d in depts}
            if not no_rem:
                big, _ = _argmax(base)
                shares[big] += amt - sum(shares.values())
            for d in depts:
                tot[d] += shares[d]
        top, tv = _argmax(tot)
        return {"sales_total": tot["영업팀"], "top_dept": top, "top_total": tv}

    truth = solve()
    wrong = [solve(old_head=True), solve(keep_dup=True), solve(no_rem=True), solve(hq_alloc=True)]
    wrong = [w for w in wrong if w != truth]
    prompt = (
        "9월 공통 관리비를 부서별로 배부해 주세요. 관리비 전표(CSV), 부서별 전용면적, 부서별 인원표를 드립니다.\n\n[관리비 전표]\n"
        + _csv(["전표번호", "일자", "항목", "금액", "배부기준"], lines)
        + "\n\n[부서별 전용면적] (㎡)\n" + _md(["부서", "면적"], [[d, area[d]] for d in depts])
        + "\n\n[부서별 인원] (9월 1일 기준)\n" + _tsv(["부서", "인원"], [[d, f"{head[d]}명"] for d in depts])
        + "\n인사팀 회신: 9월 15일 조직 개편으로 영업팀 인원은 9월 말 41명입니다. 배부는 9월 말 인원 기준이므로 인원표와 회신이 다르면 회신이 우선합니다.\n\n"
        "규칙:\n"
        "1. '※' 줄과 '소계' 줄은 데이터가 아닙니다. 전표번호가 같은 줄은 한 건만 셉니다.\n"
        "2. 금액은 원·천원·만원·한글 혼용 표기를 원으로 환산합니다.\n"
        "3. 배부기준 '본사부담'은 부서에 배부하지 않습니다. '직접:부서명'은 그 부서에 전액 부담합니다(부서명 띄어쓰기 무시).\n"
        "4. '면적'은 전용면적 비율, '인원'은 인원 비율로 전표마다 나눕니다. 부서별 몫 = 금액 × 부서 기준값 ÷ 기준값 합계, 원 미만 버림. "
        "버림으로 남은 끝수는 그 기준값이 가장 큰 부서에 더합니다.\n\n"
        "영업팀 배부액 합계, 배부액 합계가 가장 큰 부서와 그 금액을 알려주세요. "
        + JSON_RULE + '{"sales_total": 원(정수), "top_dept": 부서명, "top_total": 원(정수)}')
    _add(n, "ga_cost_alloc", prompt, {"sales_total": "int", "top_dept": "str", "top_total": "int"}, truth, wrong,
         {"rows": len(lines) + 12, "tables": 3, "steps": 5,
          "mess": ["dup_rows", "memo_lines", "subtotal_rows", "mixed_units", "korean_amounts", "mixed_dates",
                   "name_variants", "headcount_reply_contradiction"]})


def _hk45():
    """행사 참석: 신청서 두 개(CSV) + 취소 목록(문장) + 직원 마스터, 사번 기준 최신 제출 우선, 근무지별 교통비."""
    n = 45
    rng = random.Random(1000 + n)
    sur = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오"]
    giv = ["민준", "서윤", "도윤", "하은", "지호", "수아", "예준", "지유", "시우", "채원", "주원", "다인"]
    names = [s + g for s in sur for g in giv]
    rng.shuffle(names)
    sites = ["본사"] * 7 + ["판교", "대전", "부산", "제주"]
    emp = [(f"E{1001 + i}", names[i], rng.choice(["경영지원", "영업", "개발", "생산", "품질"]), rng.choice(sites)) for i in range(120)]
    eids = [e[0] for e in emp]
    subs = []
    t0 = date(2026, 10, 1)
    used = set()

    def stamp():
        while True:
            s = (t0 + timedelta(days=rng.randrange(10)), rng.randrange(8 * 60, 20 * 60))
            if s not in used:
                used.add(s)
                return s
    for e in rng.sample(eids, 100):
        for _ in range(rng.choice([1, 1, 1, 2, 2, 3])):
            subs.append([stamp(), e, rng.choice(["참석", "참석", "참석", "불참"]), rng.choice(["일반", "일반", "채식", "없음"])])
    for k in range(3):
        subs.append([stamp(), f"E{9001 + k}", "참석", "일반"])
    subs.sort()
    cancels = []
    for e in rng.sample(sorted({s[1] for s in subs if s[1] in eids}), 8):
        last = max(s[0] for s in subs if s[1] == e)
        before = rng.random() < 0.3
        cancels.append((stamp() if not before else (last[0], max(last[1] - 30, 0)), e))
        if before:
            used.add(cancels[-1][0])
    name_of = {e[0]: e[1] for e in emp}
    lastsub = {}
    for s_ in subs:
        lastsub[s_[1]] = s_
    for c in cancels:
        assert c[0] not in [s_[0] for s_ in subs if s_[1] == c[1]]
    site0 = {e[0]: e[3] for e in emp}
    mism = next(lastsub[e] for e in sorted(lastsub) if e in site0 and lastsub[e][2] == "참석" and site0[e] != "본사"
                and e not in {c[1] for c in cancels})
    lines = []
    for s in subs:
        if s[1] in eids:
            nm = name_of[s[1]] if s is not mism else rng.choice([x for x in names[120:]])
        else:
            nm = "외부강사" + s[1][-1]
        eid = s[1] if rng.random() < 0.8 else s[1].lower()
        st = f"{_dt(s[0][0], rng.choice(('iso', 'dot', 'dots')))} {s[0][1] // 60:02d}:{s[0][1] % 60:02d}"
        lines.append([st, eid, _person_var(nm, rng), s[2], s[3]])
        if rng.random() < 0.04:
            lines.append(list(lines[-1]))
    lines.insert(90, ["# 2차 신청서 응답", "", "", "", ""])
    ctext = "\n".join(f"- {_dt(c[0][0], 'kor')} {c[0][1] // 60:02d}:{c[0][1] % 60:02d}, 사번 {c[1]} 참석 취소 요청"
                      for c in sorted(cancels))
    site_of = {e[0]: e[3] for e in emp}

    def solve(first=False, no_cancel=False, by_name=False, jeju_flat=False, keep_ext=False):
        ev = []
        nm2id = {_norm(e[1]): e[0] for e in emp}
        for r in lines:
            if r[0].startswith("#"):
                continue
            eid = r[1].upper()
            if by_name:
                eid = nm2id.get(_norm(r[2]), None if eid in site_of else eid)
                if eid is None:
                    continue
            ev.append((_c_stamp(r[0]), eid, r[3], r[4]))
        if not no_cancel:
            for c in cancels:
                ev.append(((c[0][0], c[0][1]), c[1], "불참", "없음"))
        ev.sort(reverse=first)
        fin = {}
        for t, eid, a, m in ev:
            fin[eid] = (a, m)
        att = [e for e, (a, m) in sorted(fin.items()) if a == "참석" and (e in site_of or keep_ext)]
        veg = sum(1 for e in att if fin[e][1] == "채식")
        tr = sum(0 if site_of.get(e, "본사") == "본사" else (50000 if site_of[e] == "제주" and not jeju_flat else 20000) for e in att)
        return {"attendees": len(att), "veg_count": veg, "transport_total": tr}

    truth = solve()
    wrong = [solve(first=True), solve(no_cancel=True), solve(by_name=True), solve(jeju_flat=True), solve(keep_ext=True)]
    wrong = [w for w in wrong if w != truth]
    prompt = (
        "창립기념 행사 참석 신청을 집계해 주세요. 신청서 응답(CSV, 1차·2차 신청서를 이어 붙임), 별도로 받은 취소 요청, 직원 마스터를 드립니다.\n\n"
        "[신청서 응답]\n" + _csv(["제출시각", "사번", "이름", "참석여부", "식사"], lines)
        + "\n\n[취소 요청]\n" + ctext
        + "\n\n[직원 마스터]\n" + _tsv(["사번", "이름", "부서", "근무지"], emp)
        + "\n\n규칙:\n"
        "1. '#' 줄은 데이터가 아닙니다. 사번 대소문자는 무시합니다.\n"
        "2. 사람은 사번으로 구분합니다. 신청서의 이름이 직원 마스터와 달라도 사번을 믿습니다. 직원 마스터에 없는 사번은 집계에서 뺍니다.\n"
        "3. 한 사람의 응답이 여러 개면 제출시각이 가장 늦은 응답이 최종입니다. 취소 요청도 그 시각에 '불참'으로 낸 응답으로 봅니다"
        "(취소 요청보다 늦게 낸 신청서 응답이 있으면 그 응답이 최종).\n"
        "4. 최종 응답이 '참석'인 사람이 참석자입니다. 식사는 최종 응답의 식사 선택을 따릅니다.\n"
        "5. 교통비: 근무지가 본사가 아닌 참석자 1인당 20,000원, 단 근무지가 제주인 참석자는 50,000원.\n\n"
        "참석자 수, 채식 식사 인원(참석자 중), 교통비 합계를 알려주세요. "
        + JSON_RULE + '{"attendees": 정수, "veg_count": 정수, "transport_total": 원(정수)}')
    _add(n, "ga_event", prompt, {"attendees": "int", "veg_count": "int", "transport_total": "int"}, truth, wrong,
         {"rows": len(lines) + len(cancels) + len(emp), "tables": 3, "steps": 5,
          "mess": ["dup_rows", "memo_lines", "id_case", "name_variants", "mixed_dates", "name_vs_id_contradiction",
                   "unknown_ids", "prose_list"]})


# ================================================================= 총무 (hk_46-hk_50), 법무 (hk_51-hk_60)



def _d_top(d, strict):
    """Key with the largest value; strict asserts there is no tie (used for the truth, not wrong variants)."""
    if strict:
        return _argmax(d)[0]
    return max(sorted(d), key=lambda k: d[k])


def _d_area(s):
    """'152㎡' / '152.5㎡' / '46평' -> Fraction m² (1평 = 3.3㎡ as the prompt states)."""
    s = s.strip()
    if s.endswith("평"):
        return _F(s[:-1]) * _F(33, 10)
    return _F(s.rstrip("㎡m²").strip())


def _d_alloc(amount, weights):
    """floor(amount * w / W) per key; returns (shares, remainder)."""
    tot = sum(weights.values())
    sh = {k: int(_F(amount) * w / tot) for k, w in weights.items()}
    return sh, amount - sum(sh.values())


def _hk46():
    rng = random.Random(1046)
    depts = ["경영지원팀", "총무팀", "인사팀", "재무팀", "기획팀", "법무팀", "영업1팀", "영업2팀", "영업3팀", "마케팅팀",
             "고객지원팀", "개발1팀", "개발2팀", "개발3팀", "QA팀", "디자인팀", "데이터팀", "보안팀", "구매팀", "물류팀",
             "품질팀", "교육팀", "홍보팀", "전략팀"]
    # --- area table (markdown), two vacant zones, 마케팅팀 listed twice (정정 row wins)
    area_rows, zone = [], 0
    occupants = depts[:12] + ["공실"] + depts[12:20] + ["공실"] + depts[20:]
    for i, d in enumerate(occupants):
        fl = 3 + i * 4 // len(occupants)
        zone += 1
        if rng.random() < 0.3:
            a = f"{rng.randrange(12, 70)}평"
        elif rng.random() < 0.3:
            a = f"{rng.randrange(40, 230)}.5㎡"
        else:
            a = f"{rng.randrange(40, 230)}㎡"
        area_rows.append([f"{fl}층", f"{fl}{zone:02d}", d, a, ""])
    mk = next(r for r in area_rows if r[2] == "마케팅팀")
    mk_old = list(mk)
    mk[3], mk[4] = f"{rng.randrange(40, 230)}㎡", "정정(9월 실측)"
    assert _d_area(mk[3]) != _d_area(mk_old[3])
    mk_old[4] = "계약서 기준"
    area_rows.insert(area_rows.index(mk) + 1, mk_old)
    # --- meter readings (TSV), cumulative kWh at month ends 6/30..9/30
    ends = [date(2026, 6, 30), date(2026, 7, 31), date(2026, 8, 31), date(2026, 9, 30)]
    swap_old_final = None
    readings = []
    for d in depts:
        v = rng.randrange(5000, 90000)
        vals = [v]
        for _ in range(3):
            v += rng.randrange(800, 6000)
            vals.append(v)
        if d == "기획팀":
            jul = vals[1]
            swap_old_final = jul + rng.randrange(300, 1500)
            aug_new = rng.randrange(400, 2500)
            vals = [vals[0], jul, aug_new, aug_new + rng.randrange(800, 6000)]
        for e, val in zip(ends, vals):
            readings.append([d, e, val])
    lines, memo_at = [], None
    for d, e, val in readings:
        if d == "기획팀" and e == ends[2]:
            memo_at = len(lines)
        nm = d if rng.random() < 0.8 else rng.choice([d[:2] + " " + d[2:], " " + d])
        line = f"{nm}\t{_dt(e, rng.choice(DATE_STYLES))}\t{val:,}"
        lines.append(line)
        if rng.random() < 0.06:
            lines.append(line)
    lines.insert(memo_at, f"※ 8/14 기획팀 계량기 교체: 구 계량기 최종 지침 {swap_old_final:,}kWh, 신 계량기는 0부터 시작")
    lines.insert(rng.randrange(10, 40), "※ 9월 검침은 9/30 18시 기준(메모)")
    meter_text = "부서\t검침일\t누적지침(kWh)\n" + "\n".join(lines)
    # --- bills (prose, mixed units)
    items = ["전용 전기료", "공용 전기료", "청소용역비", "경비용역비", "승강기 유지비"]
    bills = {}
    btxt = []
    for m in (7, 8, 9):
        amts = [rng.randrange(3000, 9000) * 1000, rng.randrange(800, 2000) * 1000, rng.randrange(4000, 7000) * 1000,
                rng.randrange(5000, 8000) * 1000, rng.randrange(600, 1500) * 1000]
        bills[m] = amts
        parts = [f"{it} {_amt(a, rng.choice(['won', 'chun', 'man', 'ko']), rng)}" for it, a in zip(items, amts)]
        btxt.append(f"- {m}월 고지서: " + ", ".join(parts))
    # ---------------- solver over rendered rows
    area = {}
    for fl, zn, d, a, note in area_rows:
        key = zn if d == "공실" else _norm(d)
        if key in area and "정정" not in note:
            continue
        area[key] = _d_area(a)
    seen, rd = set(), {}
    for l in lines:
        if l.startswith("※"):
            continue
        d, e, v = l.split("\t")
        k = (_norm(d), _parse_dt(e))
        if k in seen:
            continue
        seen.add(k)
        rd[k] = int(v.replace(",", ""))

    def usage(dn, m, swap=True):
        a, b = ends[m - 7], ends[m - 6]
        if swap and dn == _norm("기획팀") and m == 8:
            return swap_old_final - rd[(dn, a)] + rd[(dn, b)]
        return rd[(dn, b)] - rd[(dn, a)]

    def solve(swap=True, fix=True, vacant_in=True):
        ar = dict(area)
        if not fix:
            ar[_norm("마케팅팀")] = _d_area(mk_old[3])
        if not vacant_in:
            ar = {k: v for k, v in ar.items() if not re.fullmatch(r"\d+", k)}
        tot = {}
        for m in (7, 8, 9):
            amts = bills[m]
            w = {_norm(d): usage(_norm(d), m, swap) for d in depts}
            sh, rem = _d_alloc(amts[0], w)
            for k, v in sh.items():
                tot[k] = tot.get(k, 0) + v
            tot["총무팀"] = tot.get("총무팀", 0) + rem
            for a in amts[1:]:
                sh, rem = _d_alloc(a, ar)
                for k, v in sh.items():
                    k2 = "총무팀" if re.fullmatch(r"\d+", k) else k
                    tot[k2] = tot.get(k2, 0) + v
                tot["총무팀"] += rem
        assert sum(tot.values()) == sum(sum(v) for v in bills.values())
        top, _ = _argmax({k: v for k, v in tot.items() if k != "총무팀"})
        return {"planning_total": tot["기획팀"], "ga_total": tot["총무팀"],
                "top_dept": next(d for d in depts if _norm(d) == top)}

    truth = solve()
    prompt = (
        "사옥 3분기(7~9월) 관리비를 부서별로 나누려고 합니다. 자료 세 가지를 붙여 넣을게요.\n\n"
        "[자료 1] 층별 전용면적표(마크다운). 면적은 ㎡ 또는 평으로 적혀 있고 1평 = 3.3㎡로 환산합니다. "
        "'공실'은 비어 있는 구역입니다.\n\n" + _md(["층", "구역", "사용 부서", "전용면적", "비고"], area_rows) + "\n\n"
        "[자료 2] 부서별 전기 계량기 월말 누적 지침(탭 구분, 엑셀 복사). 날짜 표기가 섞여 있고 부서명 띄어쓰기가 다른 줄은 "
        "같은 부서입니다. 같은 부서·같은 검침일 줄이 두 번 나오면 한 번만 봅니다. ※로 시작하는 줄은 메모입니다.\n\n"
        + meter_text + "\n\n[자료 3] 월별 관리비 고지서(금액 단위가 섞여 있음)\n" + "\n".join(btxt) + "\n\n"
        "배분 규칙\n"
        "1. 월 전기 사용량 = 그 달 말일 지침 − 전월 말일 지침. 계량기를 교체한 달은 (구 계량기 최종 지침 − 전월 말일 지침) + "
        "(신 계량기의 그 달 말일 지침)입니다.\n"
        "2. '전용 전기료'는 그 달 부서별 전기 사용량 비율로 나눕니다(공실은 사용량이 없음).\n"
        "3. 나머지 네 항목(공용 전기료, 청소용역비, 경비용역비, 승강기 유지비)은 전용면적 비율로 나눕니다. 이때 공실 구역 면적도 "
        "분모에 넣고, 공실 몫은 총무팀이 부담합니다.\n"
        "4. 면적표에 같은 부서가 두 줄 있으면 비고에 '정정'이 적힌 줄의 면적만 쓰고 다른 줄은 무시합니다(그 줄이 공실이 되지 않습니다).\n"
        "5. 월별·항목별로 각 부서 몫은 원 미만을 버리고, 버려서 남는 금액(고지 금액 − 부서 몫 합계)은 총무팀이 부담합니다.\n\n"
        "기획팀의 3분기 부담 합계, 총무팀의 3분기 부담 합계(공실 몫과 끝전 포함), 총무팀을 뺀 부서 중 3분기 부담 합계가 가장 큰 부서를 알려주세요. "
        + JSON_RULE + '{"planning_total": 원(정수), "ga_total": 원(정수), "top_dept": 부서명}')
    wrong = [solve(swap=False), solve(fix=False), solve(vacant_in=False)]
    _add(46, "ga_mgmt_fee", prompt, {"planning_total": "int", "ga_total": "int", "top_dept": "str"}, truth, wrong,
         {"rows": len(area_rows) + len(lines) + 3, "tables": 3, "steps": 5,
          "mess": ["mixed_units", "pyeong_sqm", "dup_rows", "memo_lines", "date_formats", "name_spacing",
                   "meter_swap", "contradiction_area"]})


def _hk47():
    rng = random.Random(1047)
    depts = [("개발팀", 62), ("영업팀", 47), ("마케팅팀", 41), ("고객지원팀", 38), ("구매팀", 30), ("총무팀", 22),
             ("인사팀", 12), ("품질팀", 18)]
    bands = [(2, 3500), (5, 4200), (10, 5800), (20, 7900), (30, 10500)]
    sur = {"일반": 0, "제주": 3000, "도서산간": 5000}
    ships = []
    no = 6021340000
    for d, k in depts:
        for _ in range(k):
            no += rng.randrange(1, 40)
            day = date(2026, 9, rng.randrange(1, 31))
            w10 = rng.choice([rng.randrange(3, 50), rng.randrange(20, 200), rng.randrange(100, 290)])
            if rng.random() < 0.02:
                w10 = rng.randrange(300, 360)
            dims = [rng.randrange(10, 47) for _ in range(3)]
            if rng.random() < 0.03:
                dims = [rng.randrange(50, 75) for _ in range(3)]
            reg = rng.choices(["일반", "제주", "도서산간"], [85, 9, 6])[0]
            kind = "반품" if rng.random() < 0.12 else "일반"
            ships.append([str(no), day, d, w10, dims, reg, kind])
    rng.shuffle(ships)
    ships.sort(key=lambda s: s[1])
    # rendered lines: duplicates, corrections (contradiction), cancellations, memo lines
    rows = []
    for s in ships:
        rows.append(list(s))
        r = rng.random()
        if r < 0.04:
            rows.append(list(s))                                  # exact duplicate
        elif r < 0.07:
            c = list(s)
            c[6] = "취소"
            rows.append(c)                                        # cancelled later
    corr = next(s for s in ships if s[3] < 100 and max(s[4]) < 50 and s[5] == "일반")
    fixed = list(corr)
    fixed[3] = corr[3] + 150
    rows.insert(rows.index(corr) + rng.randrange(5, 25), fixed)  # same 송장 with different weight, later line
    lines = ["송장번호,접수일,부서,실중량(kg),크기(cm),도착지,구분"]
    for i, (sn, day, d, w10, dims, reg, kind) in enumerate(rows):
        dn = d if rng.random() < 0.8 else rng.choice([d[:2] + " " + d[2:], d + " ", " " + d])
        lines.append(",".join([sn, _dt(day, rng.choice(["iso", "dot", "dots", "compact"])), dn, f"{w10 / 10:.1f}",
                               "x".join(map(str, dims)), reg, kind]))
        if i in (40, 151):
            lines.append("# 이 아래는 전산 장애로 수기 입력한 분(형식 동일)" if i == 40 else "# 소계 행 아님, 메모")
    rate_tsv = "청구중량(kg)\t기본요금(원)\n" + "\n".join(
        f"{lo + 1 if lo else 0}~{hi}\t{fee:,}" for (hi, fee), lo in zip(bands, [0] + [b[0] for b in bands[:-1]]))

    def solve(vol=True, last=True, disc=True):
        recs = {}
        for l in lines[1:]:
            if l.startswith("#"):
                continue
            sn, _, dn, w, dims, reg, kind = l.split(",")
            if not last and sn in recs:
                continue
            recs[sn] = (_norm(dn), float(w), [int(x) for x in dims.split("x")], reg, kind)
        base, extra, cnt, freight = {}, {}, {}, []
        for sn in sorted(recs):
            dn, w, (a, b, c), reg, kind = recs[sn]
            if kind == "취소":
                continue
            bw = -(-int(round(w * 10)) // 10)
            if vol:
                bw = max(bw, -(-(a * b * c) // 6000))
            if bw > 30:
                freight.append(sn)
                continue
            fee = next(f for hi, f in bands if bw <= hi)
            if kind == "반품":
                fee = fee * 8 // 10
            base[dn] = base.get(dn, 0) + fee
            extra[dn] = extra.get(dn, 0) + sur[reg]
            cnt[dn] = cnt.get(dn, 0) + 1
        tot = {}
        for dn in base:
            dis = base[dn] // 10 if (disc and cnt[dn] >= 40) else 0
            tot[dn] = base[dn] - dis + extra[dn]
        assert any(c >= 40 for c in cnt.values()) and any(c < 40 for c in cnt.values())
        return {"total": sum(tot.values()), "dev_total": tot[_norm("개발팀")], "freight_ids": freight}

    truth = solve()
    prompt = (
        "9월 택배 발송 내역(쉼표 CSV, 전산 내려받기)으로 부서별 택배비를 정산하려고 합니다. #으로 시작하는 줄은 메모입니다. "
        "부서명은 띄어쓰기가 달라도 같은 부서입니다.\n\n" + "\n".join(lines) + "\n\n"
        "[요금표] 청구중량별 기본요금(탭 구분)\n" + rate_tsv + "\n\n"
        "정산 규칙\n"
        "1. 같은 송장번호가 여러 줄 있으면 표에서 맨 아래(나중) 줄만 유효합니다. 정정 입력이나 취소가 나중 줄로 들어옵니다. "
        "유효한 줄의 구분이 '취소'인 송장은 비용이 없습니다.\n"
        "2. 부피중량(kg) = 가로×세로×높이(cm) ÷ 6000. 청구중량은 실중량과 부피중량 중 큰 값을 kg 단위로 올림한 정수입니다.\n"
        "3. 청구중량이 30kg을 넘는 송장은 택배가 아니라 화물로 별도 정산하므로 이 정산에서 빼고 목록으로만 알려 주세요.\n"
        "4. 구분이 '반품'이면 기본요금의 80%만 냅니다.\n"
        "5. 도착지 할증: 제주 +3,000원, 도서산간 +5,000원 (반품에도 붙음, 할인 대상 아님).\n"
        "6. 부서별로 9월 정산 대상 송장(화물·취소 제외)이 40건 이상이면 그 부서 기본요금 합계(반품 조정 후)의 10%를 깎아 줍니다"
        "(원 미만 버림). 할증은 깎지 않습니다.\n\n"
        "전체 부서 정산 합계, 개발팀 정산액, 화물로 뺀 송장번호 목록(오름차순, 문자열)을 알려주세요. "
        + JSON_RULE + '{"total": 원(정수), "dev_total": 원(정수), "freight_ids": ["송장번호", ...]}')
    wrong = [solve(vol=False), solve(last=False), solve(disc=False)]
    _add(47, "ga_parcel", prompt, {"total": "int", "dev_total": "int", "freight_ids": "list"}, truth, wrong,
         {"rows": len(lines) - 1 + len(bands), "tables": 2, "steps": 6,
          "mess": ["dup_rows", "later_row_wins", "cancel_rows", "memo_lines", "date_formats", "name_spacing",
                   "contradiction_weight"]})


def _d_time(h, m, style):
    if style == 0:
        return f"{h:02d}:{m:02d}"
    if style == 1:
        return f"{h:02d}:{m:02d}:00"
    return f"{'오전' if h < 12 else '오후'} {h if h <= 12 else h - 12}:{m:02d}"


def _d_ptime(s):
    s = s.strip()
    mm = re.fullmatch(r"(오전|오후)\s*(\d{1,2}):(\d{2})", s)
    if mm:
        h = int(mm.group(2))
        h = h + 12 if mm.group(1) == "오후" and h != 12 else h
        return h * 60 + int(mm.group(3))
    mm = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", s)
    return int(mm.group(1)) * 60 + int(mm.group(2))


def _hk48():
    rng = random.Random(1048)
    hol = {date(2026, 9, 24), date(2026, 9, 25)}
    emps = [(f"E21{i:02d}", nm) for i, nm in zip(range(1, 10), rng.sample(PEOPLE, 9))]
    logs, manual, trips = [], [], []
    err_day = None
    for eid, nm in emps:
        for d in _days(date(2026, 9, 1), date(2026, 9, 30)):
            biz = _is_biz(d, hol)
            if not biz:
                if rng.random() < 0.06:
                    i = rng.randrange(9 * 60, 11 * 60)
                    logs += [(d, i, eid, "IN"), (d, i + rng.randrange(120, 400), eid, "OUT")]
                continue
            r = rng.random()
            if r < 0.05:
                trips.append((nm, d))
                continue
            if r < 0.09:
                continue
            i = rng.randrange(8 * 60, 10 * 60)
            o = i + (rng.randrange(150, 230) if rng.random() < 0.08 else rng.randrange(420, 700))
            ev = [(d, i, eid, "IN")]
            if rng.random() < 0.3:
                lo = i + rng.randrange(150, 200)
                ev += [(d, lo, eid, "OUT"), (d, lo + rng.randrange(30, 70), eid, "IN")]
            if rng.random() < 0.06:
                if rng.random() < 0.6:
                    manual.append((nm, d, o))
            else:
                ev.append((d, o, eid, "OUT"))
            if err_day is None and eid == emps[3][0] and d.day > 10 and len(ev) == 2:
                ev = [ev[0], (d, i - 100, eid, "OUT")]
                manual.append((nm, d, o))
                err_day = (eid, d)
            logs += ev
    logs.sort(key=lambda e: (e[0], e[1], e[2]))
    gates = ["정문", "정문", "B1 주차장", "후문"]
    lines = []
    for d, t, eid, io in logs:
        lines.append(f"{_dt(d, 'iso')} {_d_time(t // 60, t % 60, rng.choice([0, 0, 1, 2]))} {eid} {io} {rng.choice(gates)}")
    lines.insert(len(lines) // 2, "---- 9/15 게이트 서버 재시작(기록 누락 없음) ----")
    man_lines = [f"- {_person_var(nm, rng)} / {_dt(d, 'md')} / 퇴근 {_d_time(o // 60, o % 60, 2)}" for nm, d, o in manual]
    trip_lines = [f"- {_dt(d, 'mdk')} {_person_var(nm, rng)}" for nm, d in trips]
    roster = _tsv(["사번", "이름"], emps)

    def solve(manual_on=True, ignore_err=True, cap=True, trip_on=True):
        name2id = {_norm(nm): eid for eid, nm in emps}
        ev = {}
        for l in lines:
            if l.startswith("----"):
                continue
            mm = re.fullmatch(r"(\S+) (.+?) (E\d+) (IN|OUT) .+", l)
            d, t, eid, io = _parse_dt(mm.group(1)), _d_ptime(mm.group(2)), mm.group(3), mm.group(4)
            ev.setdefault((eid, d), []).append((t, io))
        man = {}
        for l in man_lines:
            nm, d, o = [x.strip() for x in l[2:].split(" / ")]
            man[(name2id[_norm(nm)], _parse_dt(d, 2026))] = _d_ptime(o.replace("퇴근", ""))
        tripd = set()
        for l in trip_lines:
            mm = re.fullmatch(r"- (\d+월 \d+일) (.+)", l)
            tripd.add((name2id[_norm(mm.group(2))], _parse_dt(mm.group(1), 2026)))
        meal, attend, short = 0, 0, 0
        for eid, _ in emps:
            days = 0
            for d in _days(date(2026, 9, 1), date(2026, 9, 30)):
                if not _is_biz(d, hol):
                    continue
                if (eid, d) in tripd:
                    attend += trip_on
                    continue
                e = ev.get((eid, d))
                if not e:
                    continue
                first_in = min(t for t, io in e if io == "IN")
                outs = [t for t, io in e if io == "OUT" and (t > first_in or not ignore_err)]
                last = max(outs) if outs else (man.get((eid, d)) if manual_on else None)
                if last is not None and last - first_in >= 240:
                    days += 1
                else:
                    short += 1
            attend += days
            meal += 9000 * (min(days, 16) if cap else days)
        return {"meal_total": meal, "attend_days": attend, "uncounted_days": short}

    truth = solve()
    prompt = (
        "9월 식대 지원금을 출입 게이트 기록으로 정산합니다. 2026년 9월 공휴일은 9/24(목), 9/25(금)이고 토·일은 휴일입니다.\n\n"
        "[사원 명부]\n" + roster + "\n\n[게이트 기록] 한 줄 = 날짜 시각 사번 IN/OUT 게이트. 시각 표기가 섞여 있습니다"
        "(18:30, 18:30:00, 오후 6:30). ----로 시작하는 줄은 시스템 메모입니다.\n" + "\n".join(lines) + "\n\n"
        "[퇴근 수기 기록] 카드를 안 찍고 퇴근해서 총무팀에 신고한 건\n" + "\n".join(man_lines) + "\n\n"
        "[출장자 명단] 하루 종일 외부 출장(게이트 기록 없음)\n" + "\n".join(trip_lines) + "\n\n"
        "규칙\n"
        "1. 평일(공휴일 아님) 하루를 사원별로 봅니다. 그날 첫 IN 시각부터 마지막 OUT 시각까지가 4시간(240분) 이상이면 출근일입니다. "
        "점심 외출(OUT 후 다시 IN)은 신경 쓰지 않고 첫 IN과 마지막 OUT만 봅니다.\n"
        "2. 그날 OUT 기록이 없으면 퇴근 수기 기록의 시각을 마지막 OUT으로 씁니다. 수기 기록도 없으면 출근일로 인정하지 않습니다.\n"
        "3. 게이트 시계 오류로 OUT 시각이 그날 첫 IN보다 이른 줄이 있으면 그 OUT 줄은 없는 것으로 봅니다(그러면 규칙 2 적용).\n"
        "4. 출장자 명단의 날은 출근일로 세지만 식대는 출장비에 포함되어 있어 식대 지원 일수에서는 뺍니다.\n"
        "5. 주말·공휴일 출입 기록은 휴일근무로 따로 처리하므로 이 정산(출근일, 식대, 미인정 일수)에서 모두 뺍니다.\n"
        "6. 식대 = 사원별 식대 지원 일수 × 9,000원, 단 사원별 월 16일분(144,000원)이 상한입니다.\n\n"
        "전 사원 식대 합계, 전 사원 출근일 합계(출장일 포함), 게이트 기록이 있는 평일 중 출근일로 인정되지 않은 날 수(사원·날짜 단위)를 "
        "알려주세요. " + JSON_RULE + '{"meal_total": 원(정수), "attend_days": 일(정수), "uncounted_days": 일(정수)}')
    wrong = [solve(manual_on=False), solve(ignore_err=False), solve(cap=False), solve(trip_on=False)]
    assert err_day is not None
    _add(48, "ga_access_meal", prompt, {"meal_total": "int", "attend_days": "int", "uncounted_days": "int"}, truth, wrong,
         {"rows": len(lines) + len(man_lines) + len(trip_lines) + len(emps), "tables": 4, "steps": 6,
          "mess": ["time_formats", "memo_lines", "manual_records", "name_spacing", "clock_error_contradiction",
                   "holiday_rows", "cap"]})


def _d_mdays(y, m):
    return (date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)).day


def _hk49():
    rng = random.Random(1049)
    grades = ["사원", "대리", "과장", "차장", "부장"]
    cap = {"사원": 50000, "대리": 70000, "과장": 70000, "차장": 100000, "부장": 100000}
    emps = []
    for i, nm in enumerate(rng.sample(PEOPLE, 40) + ["김민준", "이도윤", "박서준", "최하은", "정시우"]):
        g = rng.choices(grades, [30, 25, 20, 15, 10])[0]
        job = "영업" if rng.random() < 0.35 else "일반"
        hire = date(2026, rng.choice([7, 8, 9]), rng.randrange(2, 28)) if rng.random() < 0.12 else \
            date(rng.randrange(2015, 2026), rng.randrange(1, 13), rng.randrange(1, 29))
        emps.append([f"T{3001 + i}", nm, g, job, hire])
    promo = next(e for e in emps if e[2] == "과장" and e[4].year < 2026)
    promo[3] = "일반"
    promo_day = date(2026, 8, 16)
    leaves = []
    for e in rng.sample([e for e in emps if e[4].year < 2026 and e is not promo], 5):
        s = date(2026, rng.choice([7, 8, 9]), rng.randrange(1, 25))
        leaves.append((e[0], s, s + timedelta(days=rng.choice([rng.randrange(5, 20), rng.randrange(40, 70)]))))
    roster_rows = [[e[0], e[1], e[2], e[3], _dt(e[4], rng.choice(["iso", "dot", "kor"])), "입사"] for e in emps]
    roster_rows.insert(emps.index(promo) + 1, [promo[0], promo[1], "차장", promo[3], _dt(promo_day, "dot"), "승진 발령"])
    bills = []
    for m in (7, 8, 9):
        for e in emps:
            if e[4] > date(2026, m, _d_mdays(2026, m)):
                continue
            base = rng.randrange(25, 90) * 1000 - rng.choice([0, 0, 100, 500])
            data = rng.choice([0, 0, rng.randrange(3, 30) * 1100])
            micro = rng.choice([0, 0, 0, rng.randrange(1, 80) * 990])
            addon = rng.choice([0, 0, 3300, 5500, 9900])
            if e is promo and m >= 8:
                base, data = 88000, 11000
            bills.append([f"2026-{m:02d}", e[0], e[1], base, data, micro, addon])
    lines = []
    for b in bills:
        cells = [b[0], b[1], _person_var(b[2], rng)] + [
            _amt(x, rng.choice(["plain", "won", "plain", "ko"] if x % 1000 else ["plain", "won", "chun", "man", "ko"]), rng)
            if x else "0" for x in b[3:]]
        lines.append("\t".join(cells))
        if rng.random() < 0.04:
            lines.append("\t".join(cells))
    lines.insert(60, "※ 8월분부터 통신사 청구서 양식 변경(열 순서 동일)")
    leave_txt = "\n".join(f"- {eid}: {_dt(s, 'dots')} ~ {_dt(t, 'dots')}" for eid, s, t in leaves)

    def solve(items_all=False, mult=True, prorate=True, promo_on=True):
        info, hist = {}, {}
        for eid, nm, g, job, d, note in roster_rows:
            dd = _parse_dt(d)
            if note == "입사":
                info[eid] = (job, dd)
            hist.setdefault(eid, []).append((dd, g))
        lv = {}
        for l in leave_txt.splitlines():
            mm = re.fullmatch(r"- (T\d+): (\S+) ~ (\S+)", l)
            lv.setdefault(mm.group(1), []).append((_parse_dt(mm.group(2)), _parse_dt(mm.group(3))))
        seen, tot, sales, capped = set(), 0, 0, 0
        for l in lines:
            if l.startswith("※"):
                continue
            c = l.split("\t")
            if (c[0], c[1]) in seen:
                continue
            seen.add((c[0], c[1]))
            m = int(c[0][5:])
            eid = c[1]
            a = [_parse_amt(x) for x in c[3:]]
            target = sum(a) if items_all else a[0] + a[1]
            job, hire = info[eid]
            first, last = date(2026, m, 1), date(2026, m, _d_mdays(2026, m))
            hs = sorted(hist[eid])
            g = [gg for dd, gg in hs if dd <= last][-1] if promo_on else hs[0][1]
            lim = cap[g] * (3 if (mult and job == "영업") else 2)  # x2 then /2 keeps 1.5배 exact
            work = _d_mdays(2026, m)
            if prorate and hire > first:
                work = (last - hire).days + 1
            off = 0
            for s, t in lv.get(eid, []):
                off += sum(1 for d in _days(max(s, first), min(t, last)))
            if prorate:
                work -= off
            limit = lim * work // (2 * _d_mdays(2026, m))
            pay = min(target, limit)
            capped += target > limit
            tot += pay
            sales += pay if job == "영업" else 0
        return {"support_total": tot, "sales_total": sales, "capped_months": capped}

    truth = solve()
    prompt = (
        "7~9월 개인 휴대폰 요금 지원금을 정산합니다.\n\n[직원 명부](탭 구분) 같은 사번이 두 줄이면 아래 줄은 승진 발령입니다.\n"
        + _tsv(["사번", "이름", "직급", "직군", "일자", "구분"], roster_rows) + "\n\n"
        "[휴직 기간](시작일·종료일 모두 휴직)\n" + leave_txt + "\n\n"
        "[통신사 청구 내역](탭 구분, 열: 청구월 사번 이름 기본료 데이터추가 소액결제 부가서비스). 금액 표기가 섞여 있고 "
        "같은 청구월·사번 줄이 두 번 나오면 한 번만 봅니다. ※ 줄은 메모입니다.\n" + "\n".join(lines) + "\n\n"
        "규칙\n"
        "1. 지원 대상 금액 = 기본료 + 데이터추가. 소액결제와 부가서비스는 지원하지 않습니다.\n"
        "2. 월 한도: 사원 50,000원 / 대리·과장 70,000원 / 차장·부장 100,000원. 직군이 '영업'이면 한도의 1.5배입니다.\n"
        "3. 승진 발령이 있으면 발령일이 속한 달부터 새 직급 한도를 씁니다(그 달 전체에 새 한도).\n"
        "4. 입사일이 그 달 1일보다 늦으면 한도 × (입사일~말일 일수) ÷ (그 달 일수). 휴직일이 있는 달은 한도 × (그 달 일수 − 그 달 "
        "휴직일수 − 입사 전 일수) ÷ (그 달 일수). 일할한 한도는 원 미만 버림.\n"
        "5. 지원액 = min(지원 대상 금액, 한도).\n\n"
        "3개월 지원액 합계, 그중 영업 직군 지원액 합계, 지원 대상 금액이 한도를 넘어서 한도만큼만 지급된 건수(사번·월 단위)를 "
        "알려주세요. " + JSON_RULE + '{"support_total": 원(정수), "sales_total": 원(정수), "capped_months": 건(정수)}')
    wrong = [solve(items_all=True), solve(mult=False), solve(prorate=False), solve(promo_on=False)]
    _add(49, "ga_telecom", prompt, {"support_total": "int", "sales_total": "int", "capped_months": "int"}, truth, wrong,
         {"rows": len(roster_rows) + len(leaves) + len(lines), "tables": 3, "steps": 5,
          "mess": ["mixed_units", "korean_amounts", "dup_rows", "memo_lines", "date_formats", "name_spacing",
                   "promotion_two_rows", "prorate"]})


def _hk50():
    rng = random.Random(1050)
    depts = ["경영지원", "영업", "개발", "생산1", "생산2", "품질", "물류", "연구소"]
    hol = {date(2026, 9, 24), date(2026, 9, 25)}
    days = [d for d in _days(date(2026, 9, 1), date(2026, 9, 30)) if d.weekday() < 5]
    counts = {}
    lines = ["일자,부서,식수,비고"]
    for d in days:
        sub = 0
        for dp in depts:
            n = rng.randrange(8, 70) if d not in hol else rng.randrange(0, 4)
            counts[(d, dp)] = n
            sub += n
            dn = dp if rng.random() < 0.85 else rng.choice([dp + "팀", " " + dp])
            row = f"{_dt(d, rng.choice(['iso', 'dot', 'dots', 'md']))},{dn},{n},"
            lines.append(row)
            if rng.random() < 0.03:
                lines.append(row)
        lines.append(f"{_dt(d, 'iso')},소계,{sub},")
    lines.append(f"합계,,{sum(counts.values())},")
    # contradiction: one 소계 that does not match its detail rows
    bad = next(i for i, l in enumerate(lines) if ",소계," in l and "2026-09-10" in l)
    p = lines[bad].split(",")
    lines[bad] = ",".join([p[0], p[1], str(int(p[2]) + 37), "수기 수정"])
    guests = []
    for _ in range(32):
        d = rng.choice(days)
        guests.append((d, rng.choice(depts), rng.randrange(1, 9), rng.random() < 0.15))
    g_lines = [f"- {_dt(d, 'mdk')} {dp}팀 손님 {n}명" + (" (임원 동반 회의, 회사 전액 부담)" if ex else "")
               for d, dp, n, ex in guests]
    exec_meals = {d: rng.randrange(3, 9) for d in days if d not in hol}
    e_lines = [f"{_dt(d, 'md')}\t{n}" for d, n in sorted(exec_meals.items())]
    weeks = {}
    for d in days:
        wk = d - timedelta(days=d.weekday())
        weeks.setdefault(wk, []).append(d)
    # vendor invoice: per week, meals billed (vendor counts holidays and double-counts one week's 소계)
    inv = []
    for wk, ds in sorted(weeks.items()):
        meals = sum(counts[(d, dp)] for d in ds for dp in depts) + sum(n for d, _, n, _ in guests if d in ds) \
            + sum(exec_meals.get(d, 0) for d in ds)
        if wk == sorted(weeks)[2]:
            meals += 37
        inv.append((wk, ds[-1], meals))

    def price(d):
        return 6500 if d < date(2026, 9, 16) else 7000

    vendor_total = 0
    inv_lines = []
    for wk, end, meals in inv:
        amt = meals * 7000 * 11 // 10 if wk >= date(2026, 9, 14) else meals * 6500 * 11 // 10
        vendor_total += amt
        inv_lines.append(f"| {_dt(wk, 'md')}~{_dt(end, 'md')} | {meals:,} | {_amt(amt, rng.choice(['won', 'plain', 'ko']), rng)} |")

    def solve(skip_sub=True, skip_hol=True, guests_on=True, price_cut=True):
        cnt, dept = {}, {}
        for l in lines[1:]:
            d, dn, n, _ = l.split(",")
            if d == "합계" or (skip_sub and dn == "소계"):
                continue
            dd = _parse_dt(d, 2026)
            if skip_hol and dd in hol:
                continue
            k = (dd, _norm(dn).replace("팀", ""))
            cnt[k] = int(n)
            if not skip_sub and dn == "소계":
                cnt[(dd, "소계")] = int(n)
        for k, n in cnt.items():
            dept[k[1]] = dept.get(k[1], 0) + n
        sup = sum(n * (price(k[0]) if price_cut else 6500) for k, n in cnt.items())
        for l in g_lines:
            mm = re.fullmatch(r"- (\d+월 \d+일) (\S+)팀 손님 (\d+)명( .*)?", l)
            dd, dp, n = _parse_dt(mm.group(1), 2026), mm.group(2), int(mm.group(3))
            if skip_hol and dd in hol:
                continue
            sup += n * (price(dd) if price_cut else 6500)
            if guests_on and not mm.group(4):
                dept[dp] = dept.get(dp, 0) + n
        for l in e_lines:
            d, n = l.split("\t")
            dd = _parse_dt(d, 2026)
            sup += int(n) * (price(dd) if price_cut else 6500)
        settle = sup * 11 // 10
        top, _ = _argmax({k: v for k, v in dept.items() if k != "소계"})
        return {"settle_total": settle, "diff": vendor_total - settle, "top_dept": top}

    truth = solve()
    prompt = (
        "구내식당 9월 식대를 업체와 정산합니다. 2026년 9월 공휴일은 9/24(목)·9/25(금)이고 이날은 식당을 운영하지 않았습니다.\n\n"
        "[자료 1] 부서별 일일 식수 집계(쉼표 CSV, 날짜 표기 섞임, 부서명 뒤 '팀'이나 앞 공백이 붙은 줄도 같은 부서). "
        "같은 날짜·부서 줄이 두 번 나오면 한 번만 셉니다.\n" + "\n".join(lines) + "\n\n"
        "[자료 2] 손님 식수(초청 부서 기준)\n" + "\n".join(g_lines) + "\n\n"
        "[자료 3] 임원 식수(날짜\\t인원, 회사 전액 부담, 부서 식수 아님)\n" + "\n".join(e_lines) + "\n\n"
        "[자료 4] 업체 주간 청구서(마크다운, 청구액은 부가세 포함)\n| 기간 | 청구 식수 | 청구액 |\n|---|---|---|\n"
        + "\n".join(inv_lines) + "\n\n"
        "규칙\n"
        "1. 식수는 자료 1의 부서별 행, 자료 2의 손님, 자료 3의 임원을 모두 더합니다. 자료 1의 '소계'·'합계' 행은 집계 행이라 "
        "세지 않습니다. 소계가 상세 행 합과 다른 날이 있는데, 상세 행이 맞습니다.\n"
        "2. 공휴일(9/24, 9/25) 행은 식당 미운영이므로 모두 뺍니다.\n"
        "3. 1식 공급가는 9/15까지 6,500원, 9/16부터 7,000원입니다(부가세 별도).\n"
        "4. 정산액(부가세 포함) = 9월 전체 공급가 합계 × 1.1, 원 미만 버림.\n"
        "5. 부서별 식수에는 자료 1의 그 부서 식수와 그 부서가 초청한 손님 식수를 더합니다. 단 '회사 전액 부담'이라고 적힌 손님은 "
        "부서 식수에 넣지 않습니다(정산액에는 포함). 임원 식수는 어느 부서에도 넣지 않습니다.\n\n"
        "정산액, 업체 청구액 합계에서 정산액을 뺀 차액, 9월 부서별 식수(손님 포함)가 가장 많은 부서를 알려주세요. 부서명은 자료 1의 "
        "표기('팀' 없이)로 써 주세요. " + JSON_RULE + '{"settle_total": 원(정수), "diff": 원(정수), "top_dept": 부서명}')
    wrong = [solve(skip_sub=False), solve(skip_hol=False), solve(price_cut=False)]
    if solve(guests_on=False)["top_dept"] != truth["top_dept"]:
        wrong.append(solve(guests_on=False))
    _add(50, "ga_cafeteria", prompt, {"settle_total": "int", "diff": "int", "top_dept": "str"}, truth, wrong,
         {"rows": len(lines) - 1 + len(g_lines) + len(e_lines) + len(inv_lines), "tables": 4, "steps": 5,
          "mess": ["subtotal_rows", "total_row", "dup_rows", "date_formats", "name_suffix", "holiday_rows",
                   "subtotal_contradiction", "korean_amounts", "price_change_date"]})


_D_ARTS = [
    ("목적", ["이 계약은 갑이 을에게 위탁하는 물류 운영 업무의 수행 조건을 정함을 목적으로 한다."]),
    ("정의", ["이 계약에서 '물품'이란 갑이 을에게 보관 또는 운송을 맡기는 모든 재화를 말한다.",
              "'영업일'이란 토요일, 일요일 및 공휴일을 제외한 날을 말한다."]),
    ("계약기간", ["계약기간은 계약 체결일부터 {m}개월로 한다.", "기간 만료 {d}일 전까지 서면 통지가 없으면 같은 조건으로 1년 연장된다."]),
    ("업무 범위", ["을은 입고, 보관, 출고, 배송 업무를 수행한다.", "갑은 업무 범위 변경을 {d}일 전에 {how}으로 요청한다."]),
    ("계약금액", ["월 기본 위탁료는 금 {a}으로 한다.", "물동량이 기준치를 {p}% 넘으면 초과분에 대해 별도 정산한다."]),
    ("대금 지급", ["갑은 을의 세금계산서를 받은 날부터 {d}일 이내에 대금을 지급한다.", "지급일이 휴일이면 다음 영업일에 지급한다."]),
    ("지연 이자", ["갑이 대금 지급을 지연하면 지연 일수에 대해 연 {p}%의 이자를 더하여 지급한다."]),
    ("계약보증금", ["을은 계약 체결 시 금 {a}을 계약보증금으로 납부한다.", "보증금은 계약 종료 후 {d}일 이내에 반환한다."]),
    ("보관 책임", ["을은 선량한 관리자의 주의로 물품을 보관한다.", "보관 중 멸실된 물품은 입고 단가의 {p}%로 배상한다."]),
    ("재고 실사", ["양 당사자는 {m}개월마다 재고 실사를 한다.", "실사 차이가 {p}%를 넘으면 을이 원인을 {d}일 이내에 보고한다."]),
    ("운송 기준", ["을은 출고 지시를 받은 날부터 {d}영업일 이내에 배송을 마친다."]),
    ("파손 처리", ["배송 중 파손이 생기면 을은 사진과 함께 {d}일 이내에 {how}으로 통지한다.",
                  "파손 물품 1건당 배상 한도는 금 {a}으로 한다."]),
    ("보험", ["을은 물품 가액 전부에 대하여 적재물 배상책임보험에 가입한다.", "보험 증권 사본은 매년 {m}월 말까지 갑에게 제출한다."]),
    ("인력 운영", ["을은 현장 책임자 1명 이상을 상주시킨다.", "책임자를 바꿀 때는 {d}일 전에 갑에게 알린다."]),
    ("안전 관리", ["을은 산업안전 관련 법령을 지키고 월 1회 이상 안전 점검을 한다."]),
    ("재위탁", ["을은 갑의 사전 서면 동의 없이 업무의 전부 또는 일부를 제3자에게 다시 맡기지 못한다."]),
    ("비밀유지", ["양 당사자는 계약 중 알게 된 상대방의 영업 비밀을 공개하지 않는다.", "이 의무는 계약 종료 후 {m}개월 동안 유지된다."]),
    ("개인정보", ["을은 배송을 위해 받은 개인정보를 업무 목적 외로 쓰지 않는다.", "업무가 끝나면 {d}일 이내에 개인정보를 파기한다."]),
    ("지식재산", ["업무 수행 중 만든 양식과 자료의 권리는 갑에게 속한다."]),
    ("성과 평가", ["갑은 분기마다 정시 배송률을 평가한다.", "정시 배송률이 {p}% 미만이면 다음 달 위탁료의 3%를 감액한다."]),
    ("위약금", ["을이 정당한 사유 없이 업무를 중단하면 1일당 금 {a}의 위약금을 낸다.", "위약금 총액은 월 기본 위탁료의 {p}%를 넘지 않는다."]),
    ("손해배상", ["당사자 일방이 계약을 위반하여 상대방에게 손해를 입힌 경우 그 손해를 배상한다."]),
    ("불가항력", ["천재지변 등 불가항력으로 이행이 늦어지면 책임을 지지 않는다.", "불가항력 사유는 발생 후 {d}일 이내에 {how}으로 알린다."]),
    ("계약 변경", ["이 계약의 변경은 양 당사자의 {how} 합의로만 한다."]),
    ("양도 금지", ["어느 당사자도 상대방 동의 없이 계약상 지위를 양도하지 못한다."]),
    ("해지", ["당사자 일방이 중대한 위반을 하고 {d}일 이내에 고치지 않으면 상대방은 계약을 해지할 수 있다.",
             "해지 통지는 {how}으로 한다."]),
    ("중도 해지", ["갑은 {m}개월 전에 통지하여 계약을 중도 해지할 수 있다.", "이 경우 갑은 을에게 금 {a}의 정산금을 지급한다."]),
    ("계약 종료 후 조치", ["계약이 끝나면 을은 {d}일 이내에 보관 물품을 갑이 지정한 장소로 옮긴다."]),
    ("자료 보관", ["을은 입출고 기록을 {m}개월 이상 보관한다."]),
    ("감사", ["갑은 {d}일 전에 통지하고 을의 업무 현장과 장부를 감사할 수 있다."]),
    ("하도급 대금", ["을이 하도급을 준 경우 하도급 대금은 을이 직접 지급한다."]),
    ("세금", ["이 계약에 따른 부가가치세는 별도로 한다."]),
    ("통지", ["이 계약에 따른 통지는 계약서에 적힌 주소로 {how}으로 한다."]),
    ("분쟁 해결", ["분쟁이 생기면 먼저 협의하고, 협의가 {d}일 안에 안 되면 소송으로 해결한다."]),
    ("관할 법원", ["소송의 관할 법원은 갑의 본점 소재지 법원으로 한다."]),
    ("반부패", ["양 당사자는 계약과 관련하여 금품이나 향응을 주고받지 않는다.", "위반 시 상대방은 즉시 계약을 해지할 수 있다."]),
    ("환경", ["을은 포장재 재활용률을 {p}% 이상으로 유지한다."]),
    ("품질 기준", ["오출고율은 월 {p}% 이하로 유지한다.", "기준을 넘긴 달에는 을이 개선 계획을 {d}일 이내에 낸다."]),
    ("가격 조정", ["위탁료는 {m}개월마다 물가 변동을 반영하여 협의로 조정할 수 있다."]),
    ("기타", ["이 계약에 없는 사항은 관련 법령과 상관례에 따른다."]),
]
_D_NEW = [("탄소 배출 보고", ["을은 분기마다 배송 차량의 탄소 배출량을 갑에게 보고한다."]),
          ("전자 문서", ["이 계약에 따른 문서는 전자 문서로 주고받을 수 있다.", "전자 문서는 수신 확인 후 {d}일 안에 보관 시스템에 등록한다."])]


def _d_fill(tpl, v, rng, amt_style):
    s = tpl
    for k in ("m", "d", "p"):
        s = s.replace("{" + k + "}", str(v[k]))
    s = s.replace("{how}", v["how"])
    if "{a}" in s:
        s = s.replace("{a}", _ko(v["a"], rng, "원").replace(" ", "") if amt_style == "ko" else f"{v['a']:,}원")
    return s


def _d_canon(text):
    """Material content of an article: amounts to numbers, spaces and punctuation dropped."""
    t = re.sub(r"금\s*(\S+?원)", lambda mm: "금" + str(_parse_amt(mm.group(1))) + "원", text)
    return re.sub(r"[\s.,·]", "", t)


def _d_parse_contract(text):
    arts, cur = {}, None
    for l in text.splitlines():
        mm = re.fullmatch(r"제(\d+)조\((.+)\)", l.strip())
        if mm:
            cur = mm.group(2)
            arts[cur] = [int(mm.group(1)), []]
        elif cur and l.strip():
            arts[cur][1].append(l.strip())
    return arts


def _hk51():
    rng = random.Random(1051)
    circ = "①②③④"
    vals = []
    for _ in _D_ARTS:
        vals.append({"m": rng.choice([3, 6, 12, 24]), "d": rng.choice([7, 10, 14, 15, 30, 60]),
                     "p": rng.choice([1, 2, 3, 5, 10, 20]), "how": rng.choice(["서면", "전자우편"]),
                     "a": rng.randrange(5, 900) * 100000})
    idx = list(range(len(_D_ARTS)))
    pool = [i for i in idx if i > 1]
    rng.shuffle(pool)
    deleted = sorted(pool[:2])
    by_rider = pool[2]
    numeric = [i for i in pool[3:] if re.search(r"\{[mdp]\}|\{how\}", "".join(_D_ARTS[i][1]))]
    changed = sorted(numeric[:6])
    rest = [i for i in pool[3:] if i not in changed]
    amt_arts = [i for i in rest if "{a}" in "".join(_D_ARTS[i][1])]
    cosmetic = sorted(set(amt_arts[:2] + [i for i in rest if i not in amt_arts][:3]))
    v2vals = [dict(v) for v in vals]
    for i in changed:
        tpls = "".join(_D_ARTS[i][1])
        opts = [k for k in ("m", "d", "p", "how") if "{" + k + "}" in tpls]
        k = rng.choice(opts)
        if k == "how":
            v2vals[i]["how"] = "구두" if vals[i]["how"] == "서면" else "서면"
        else:
            choices = {"m": [3, 6, 12, 24, 36], "d": [5, 7, 10, 14, 15, 20, 30, 60, 90], "p": [1, 2, 3, 5, 10, 15, 20]}[k]
            v2vals[i][k] = rng.choice([c for c in choices if c != vals[i][k]])

    def render(order, vv, cos):
        out = []
        for no, i in enumerate(order, 1):
            title, tpls = _D_ARTS[i] if isinstance(i, int) else i
            out.append(f"제{no}조({title})")
            for j, tp in enumerate(tpls):
                style = "ko" if (cos and i in cosmetic and i in amt_arts) else "won"
                s = _d_fill(tp, vv[i] if isinstance(i, int) else vals[0], rng, style)
                if cos and i in cosmetic and i not in amt_arts:
                    s = s.replace(" ", "  ", 1) if j == 0 else s.rstrip(".")
                out.append(f"  {circ[j]} {s}" if len(tpls) > 1 else f"  {s}")
        return "\n".join(out)

    v1 = render(idx, vals, False)
    order2 = [i for i in idx if i not in deleted]
    ins = sorted(rng.sample(range(5, len(order2) - 3), 2))
    order2.insert(ins[1], _D_NEW[1])
    order2.insert(ins[0], _D_NEW[0])
    v2 = render(order2, v2vals, True)
    rider = (f"부칙\n  제1조(시행일) 이 개정 계약은 2026년 11월 1일부터 시행한다.\n"
             f"  제2조(경과조치) 본문의 「{_D_ARTS[by_rider][0]}」 조항은 이번 개정으로 삭제한다. 본문 정리가 늦어져 개정안 본문에 "
             f"남아 있더라도 삭제된 것으로 본다.")

    def solve(by_title=True, cosmetic_counts=False, rider_on=True):
        a, b = _d_parse_contract(v1), _d_parse_contract(v2)
        if not by_title:
            a = {str(n): [n, ls] for n, ls in a.values()}
            b = {str(n): [n, ls] for n, ls in b.values()}
        canon = (lambda ls: "".join(ls)) if cosmetic_counts else (lambda ls: _d_canon("".join(ls)))
        dele = [a[t][0] for t in a if t not in b]
        add = [b[t][0] for t in b if t not in a]
        chg = [a[t][0] for t in a if t in b and canon(a[t][1]) != canon(b[t][1])]
        if rider_on and by_title:
            t = _D_ARTS[by_rider][0]
            dele.append(a[t][0])
            add = [x for x in add if x != b[t][0]]
            chg = [x for x in chg if x != a[t][0]]
        return {"changed": sorted(chg), "deleted": sorted(dele), "added": sorted(add)}

    truth = solve()
    assert truth["changed"] == [i + 1 for i in changed]
    assert truth["deleted"] == sorted(i + 1 for i in deleted + [by_rider])
    prompt = (
        "물류 위탁계약서 현행본과 개정안을 비교해 주세요. 개정안은 조항이 빠지고 새로 들어가면서 조 번호가 바뀌었습니다.\n\n"
        "[현행 계약서]\n" + v1 + "\n\n[개정안]\n" + v2 + "\n\n" + rider + "\n\n"
        "비교 규칙\n"
        "1. 조 번호가 아니라 조 제목(괄호 안)으로 같은 조를 찾습니다. 제목이 같으면 번호가 달라도 같은 조입니다.\n"
        "2. 띄어쓰기, 마침표·쉼표 유무, 금액 표기 방식(예: '금 1억2,000만원'과 '금 120,000,000원')만 다른 것은 변경이 아닙니다. "
        "숫자·기간·비율·통지 방법 같은 단어가 달라지면 변경입니다.\n"
        "3. 부칙에서 삭제한다고 한 조항은 개정안 본문에 남아 있어도 삭제로 봅니다(변경·신설로 세지 않음).\n\n"
        "내용이 바뀐 조의 현행 조 번호 목록, 삭제된 조의 현행 조 번호 목록, 새로 생긴 조의 개정안 조 번호 목록을 각각 오름차순 "
        "정수 목록으로 알려주세요. " + JSON_RULE + '{"changed": [정수, ...], "deleted": [정수, ...], "added": [정수, ...]}')
    wrong = [solve(by_title=False), solve(cosmetic_counts=True), solve(rider_on=False)]
    nl = len(v1.splitlines()) + len(v2.splitlines())
    _add(51, "legal_clause_diff", prompt, {"changed": "list", "deleted": "list", "added": "list"}, truth, wrong,
         {"rows": nl, "tables": 2, "steps": 3,
          "mess": ["renumbering", "spacing_only_changes", "amount_format_changes", "punctuation_changes",
                   "rider_contradiction"]})


def _d_addm(d, n):
    """d plus n months; a missing day becomes that month's last day."""
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, _d_mdays(y, m)))


def _hk52():
    rng = random.Random(1052)
    base = date(2026, 10, 22)
    hol = set(HOLIDAYS_2026) | {date(2027, 1, 1)}
    names = ["사무실 임대차", "복합기 임대", "정수기 렌탈", "보안 용역", "청소 용역", "SW 유지보수", "클라우드 구독", "차량 리스",
             "택배 위탁", "급식 위탁", "법률 자문", "세무 자문", "광고 대행", "콜센터 위탁", "전산 장비 임차", "통신 회선"]
    cons = []
    for i in range(150):
        start = date(rng.randrange(2022, 2027), rng.randrange(1, 13), rng.choice([1, 1, 15, rng.randrange(1, 32)]))
        start = date(start.year, start.month, min(start.day, _d_mdays(start.year, start.month)))
        if start > base:
            start = date(2026, rng.randrange(1, 10), rng.randrange(1, 29))
        months = rng.choice([6, 12, 12, 24, 36])
        auto = rng.random() < 0.7
        unit = rng.choice(["1년", "원 기간과 같음"]) if auto else ""
        nt = rng.choice([("일", 30), ("일", 60), ("일", 90), ("개월", 1), ("개월", 2), ("개월", 3)])
        memo = "해지 합의 완료" if rng.random() < 0.06 else ""
        cons.append([f"C-{2101 + i}", f"{rng.choice(names)} {rng.randrange(1, 9)}차", rng.choice(COMPANIES), start, months,
                     auto, unit, nt, memo])
    for c in cons[:6]:   # month-end starts, so clamping matters
        c[3] = date(2026, rng.choice([1, 3, 5, 8]), 31)
        c[4], c[5], c[6] = rng.choice([1, 13, 25]), True, "원 기간과 같음"
    cons[6][3:9] = [date(2026, 8, 31), 1, True, "원 기간과 같음", ("일", 7), ""]
    cons[40][3:9] = [date(2025, 7, 10), 12, True, "원 기간과 같음", ("일", 30), ""]
    rows = []
    for c in cons:
        no, nm, co, start, months, auto, unit, (nu, nv), memo = c
        per = f"{months}개월" if months % 12 or rng.random() < 0.5 else f"{months // 12}년"
        cells = [no, nm, _co_var(co, rng), _dt(start, rng.choice(["iso", "dot", "kor", "compact"])), per,
                 rng.choice(["Y", "예"]) if auto else rng.choice(["N", "아니오"]), unit, f"만료 {nv}{nu} 전", memo]
        rows.append(cells)
        if rng.random() < 0.04:
            rows.append(list(cells))
    tgt = 40
    alt = list(rows[[r[0] for r in rows].index(cons[tgt][0])])
    alt[4], alt[8] = "18개월", "변경계약 반영(기간 연장)"
    rows.insert([r[0] for r in rows].index(cons[tgt][0]) + 1, alt)

    def solve(clamp=True, roll=True, biz=True, drop_done=True, change=True):
        recs = {}
        for r in rows:
            if r[0] in recs and ("변경계약" not in r[8] or not change):
                continue
            recs[r[0]] = r
        out = []
        for no, r in recs.items():
            _, _, _, s, per, auto, unit, nt, memo = r
            if drop_done and "해지" in memo:
                continue
            if auto not in ("Y", "예"):
                continue
            months = int(per[:-2]) if per.endswith("개월") else int(per[:-1]) * 12
            st = _parse_dt(s)

            def end_of(st, n):
                if clamp:
                    return _d_addm(st, n) - timedelta(days=1)
                y, m = divmod(st.month - 1 + n, 12)
                try:
                    return date(st.year + y, m + 1, st.day) - timedelta(days=1)
                except ValueError:
                    return date(st.year + y, m + 2, 1) - timedelta(days=1)
            end = end_of(st, months)
            step = 12 if unit == "1년" else months
            while end < base and roll:
                st = end + timedelta(days=1)
                end = end_of(st, step)
            if end < base:
                continue
            mm = re.fullmatch(r"만료 (\d+)(일|개월) 전", nt)
            n = int(mm.group(1))
            dl = end - timedelta(days=n) if mm.group(2) == "일" else _d_addm(end, -n)
            while biz and not _is_biz(dl, hol):
                dl -= timedelta(days=1)
            if base <= dl <= base + timedelta(days=89):
                out.append((dl, no))
        out.sort()
        return {"due": [no for _, no in out], "count": len(out), "earliest_deadline": f"{out[0][0]:%Y-%m-%d}"}

    truth = solve()
    prompt = (
        "계약 관리 대장(쉼표 CSV)에서 해지 통지 마감이 다가오는 자동연장 계약을 골라 주세요. 기준일은 2026-10-22(목)입니다.\n\n"
        + _csv(["계약번호", "계약명", "상대방", "시작일", "기간", "자동연장", "갱신 단위", "해지 통지", "비고"], rows) + "\n\n"
        "규칙\n"
        "1. 같은 계약번호가 여러 줄이면 비고에 '변경계약'이 적힌 줄을 쓰고, 그런 줄이 없으면 내용이 같은 중복이니 한 줄만 봅니다.\n"
        "2. 만료일 = 시작일에 기간(개월)을 더한 날의 전날. 더한 달에 그 날짜가 없으면 그 달 말일에 더한 것으로 봅니다"
        "(예: 1월 31일 + 1개월 = 2월 28일, 만료일은 2월 27일).\n"
        "3. 자동연장(Y 또는 예) 계약만 봅니다. 만료일이 기준일보다 앞이면 만료일 다음 날부터 갱신 단위만큼 자동 연장된 것으로 보고, "
        "기준일 이후 첫 만료일이 나올 때까지 반복합니다. 갱신 단위가 '원 기간과 같음'이면 원래 기간만큼 연장합니다. 연장 기간의 만료일도 "
        "규칙 2로 계산합니다.\n"
        "4. 해지 통지 마감일 = 만료일에서 N일 전(일 단위) 또는 만료일에서 N개월 전 같은 날(개월 단위, 그 날짜가 없으면 그 달 말일).\n"
        "5. 마감일이 토·일요일이나 공휴일이면 그 전 영업일로 당깁니다. 공휴일: 2026-12-25, 2027-01-01 (기준일 이후 90일 안의 공휴일은 이 둘뿐).\n"
        "6. 비고에 '해지 합의 완료'가 있는 계약은 뺍니다.\n"
        "7. 마감일이 기준일부터 90일 안(2026-10-22 ~ 2027-01-19, 양끝 포함)인 계약이 대상입니다.\n\n"
        "대상 계약번호 목록(마감일이 빠른 순, 같으면 계약번호 순), 대상 건수, 가장 이른 마감일을 알려주세요. "
        + JSON_RULE + '{"due": ["C-....", ...], "count": 정수, "earliest_deadline": "YYYY-MM-DD"}')
    wv = {"clamp": solve(clamp=False), "roll": solve(roll=False), "biz": solve(biz=False), "done": solve(drop_done=False),
          "change": solve(change=False)}
    assert all(v != truth for v in wv.values()), {k: v != truth for k, v in wv.items()}
    wrong = [w for w in wv.values() if w != truth]
    _add(52, "legal_renewal", prompt, {"due": "list", "count": "int", "earliest_deadline": "str"}, truth, wrong,
         {"rows": len(rows), "tables": 1, "steps": 7,
          "mess": ["dup_rows", "date_formats", "period_units", "yes_no_variants", "company_variants", "month_end_clamp",
                   "contradiction_change_contract"]})


def _hk53():
    rng = random.Random(1053)
    base = date(2026, 9, 30)
    debtors = rng.sample(PEOPLE, 24)
    loans = []
    for i, nm in enumerate(debtors):
        lend = date(2025, rng.randrange(1, 13), rng.randrange(1, 29))
        due = _d_addm(lend, rng.choice([6, 12, 18]))
        rate = rng.choice([5, 7.5, 9, 12, 15, 18, 20, 24, 30])
        loans.append([f"L{501 + i}", nm, rng.randrange(10, 300) * 1000000, lend, due, rate])
    contra = next(l for l in loans if l[5] < 15)
    real_rate = contra[5] + 6
    pays = []
    for l in loans:
        k = rng.randrange(3, 9)
        for d in sorted(rng.sample(range((base - l[3]).days), k)):
            pays.append([l[3] + timedelta(days=d + 1), l[1], rng.randrange(1, max(2, l[2] // 6000000)) * 500000])
    pays.sort(key=lambda p: p[0])
    lines = []
    for i, (d, nm, a) in enumerate(pays):
        cells = [f"P{7001 + i}", _dt(d, rng.choice(["iso", "dots", "kor"])), _person_var(nm, rng),
                 _amt(a, rng.choice(["won", "man", "ko", "plain"]), rng), ""]
        lines.append("\t".join(cells))
        if rng.random() < 0.04:
            lines.append("\t".join(cells))
        if rng.random() < 0.03:
            lines.append("\t".join([f"P{7001 + i}R", cells[1], cells[2], cells[3], "오입금 반환(변제 아님)"]))

    def solve(cap=True, contra_on=True, order_int=True, late=True):
        terms = {}
        for no, nm, p, lend, due, rate in loans:
            r = real_rate if (contra_on and no == contra[0]) else rate
            terms[_norm(nm)] = [p, lend, due, min(r, 20) if cap else r]
        st = {k: {"p": v[0], "acc": 0, "last": v[1], "paid_int": 0} for k, v in terms.items()}

        def accrue(k, upto):
            s, (p0, lend, due, r) = st[k], terms[k]
            a, b = s["last"], upto
            pieces = []
            if a < due < b:
                pieces = [(a, due, r), (due, b, min(r + 3, 20) if (cap and late) else (r + 3 if late else r))]
            elif a >= due:
                pieces = [(a, b, min(r + 3, 20) if (cap and late) else (r + 3 if late else r))]
            else:
                pieces = [(a, b, r)]
            for x, y, rr in pieces:
                s["acc"] += int(_F(s["p"]) * _F(str(rr)) / 100 * (y - x).days / 365)
            s["last"] = upto

        seen = set()
        for l in lines:
            no, d, nm, a, memo = l.split("\t")
            if no in seen or memo:
                continue
            seen.add(no)
            k, d, a = _norm(nm), _parse_dt(d), _parse_amt(a)
            accrue(k, d)
            s = st[k]
            if order_int:
                pi = min(a, s["acc"])
            else:
                pi = max(0, a - s["p"])
            s["acc"] -= pi
            s["paid_int"] += pi
            s["p"] -= a - pi
            assert s["p"] >= 0
        for k in st:
            accrue(k, base)
        return {"principal_left": sum(s["p"] for s in st.values()), "interest_received": sum(s["paid_int"] for s in st.values()),
                "unpaid_interest": sum(s["acc"] for s in st.values())}

    truth = solve()
    loan_tbl = _md(["채권번호", "채무자", "원금", "대여일", "변제기", "약정이율(연)"],
                   [[no, nm, _amt(p, rng.choice(["won", "man", "ko"]), rng), _dt(ld, "iso"), _dt(du, "iso"), f"{r}%"]
                    for no, nm, p, ld, du, r in loans])
    prompt = (
        "개인 대여금 채권의 9월 말 잔액을 정리하려고 합니다.\n\n[채권 목록]\n" + loan_tbl + "\n\n"
        f"계약서 원본 확인 메모: {contra[0]}({contra[1]}) 건의 약정이율은 목록의 {contra[5]}%가 아니라 연 {real_rate}%입니다. "
        "목록과 계약서가 다르면 계약서가 맞습니다.\n\n"
        "[입금 내역](탭 구분: 입금번호 입금일 입금자 금액 비고) 이름 띄어쓰기가 다른 줄도 같은 사람입니다. 같은 입금번호가 두 번 나오면 "
        "한 번만 봅니다. 비고가 있는 줄은 변제가 아니니 뺍니다.\n" + "\n".join(lines) + "\n\n"
        "계산 규칙\n"
        "1. 약정이율이 연 20%를 넘으면 연 20%로 봅니다.\n"
        "2. 이자는 (남은 원금) × (연이율) × (일수) ÷ 365. 일수는 직전 계산일(처음에는 대여일)부터 이번 입금일까지 날짜 차이"
        "(입금일 − 직전 계산일)입니다. 한 구간의 이자는 원 미만을 버립니다. 이자에는 이자를 붙이지 않습니다.\n"
        "3. 변제기 다음 날부터는 지연이율 = 약정이율(규칙 1 적용 후) + 3%p, 단 연 20%를 넘지 않습니다. 구간이 변제기를 걸치면 "
        "변제기를 경계로 두 구간으로 나눠 각각 계산하고 각각 원 미만을 버립니다.\n"
        "4. 입금액은 그때까지 쌓인 미지급 이자에 먼저 충당하고 남는 금액으로 원금을 갚습니다.\n"
        "5. 9월 30일을 마지막 계산일로 보고 그날까지 이자를 계산합니다(입금은 없음).\n\n"
        "9/30 기준 남은 원금 합계, 지금까지 받은 이자 합계, 9/30 기준 미지급 이자 합계(전 채권)를 알려주세요. "
        + JSON_RULE + '{"principal_left": 원(정수), "interest_received": 원(정수), "unpaid_interest": 원(정수)}')
    wrong = [solve(cap=False), solve(contra_on=False), solve(order_int=False), solve(late=False)]
    _add(53, "legal_loan_interest", prompt, {"principal_left": "int", "interest_received": "int", "unpaid_interest": "int"},
         truth, wrong,
         {"rows": len(loans) + len(lines), "tables": 2, "steps": 5,
          "mess": ["mixed_units", "korean_amounts", "dup_rows", "reversal_rows", "date_formats", "name_spacing",
                   "contradiction_rate"]})


def _hk54():
    rng = random.Random(1054)
    partners = [("한빛상사", "hanbit.co.kr"), ("대성산업", "daesung-ind.com"), ("미래테크", "miraetech.io"),
                ("세진전자", "sejin.co.kr"), ("청솔유통", "chungsol.kr"), ("누리소프트", "nurisoft.com"),
                ("Acme Supply", "acme-supply.com"), ("Nordic Parts", "nordicparts.eu"), ("Orion Labs", "orionlabs.ai"),
                ("태영정밀", "taeyoung-p.co.kr"), ("가람물류", "garam-logis.com"), ("백두철강", "baekdu-steel.com"),
                ("Pacific Freight", "pacfreight.com"), ("보람기계", "boram-mc.co.kr")]
    nda = []
    for co, dom in partners[:11]:
        s = date(rng.randrange(2024, 2026), rng.randrange(1, 13), rng.randrange(1, 29))
        nda.append([co, dom, s, _d_addm(s, rng.choice([18, 24, 36])) - timedelta(days=1), rng.choice("AAAB")])
    renew_i = 2
    nda[renew_i][2:4] = [date(2024, 3, 1), date(2026, 2, 28)]
    old = nda[renew_i]
    gap_start = old[3] + timedelta(days=rng.randrange(20, 40))
    nda.insert(renew_i + 1, [old[0], old[1], gap_start, _d_addm(gap_start, 24) - timedelta(days=1), "A"])
    subs = ["ourco-cloud.com", "ourco-lab.co.kr"]
    grades = ["공개", "사내한정", "대외비", "극비"]
    docs = [(f"DOC-{i:04d}", rng.choices(grades, [60, 17, 16, 7])[0]) for i in range(1, 71)]
    senders = rng.sample(PEOPLE, 12)
    log = []
    for i in range(240):
        d = date(2026, rng.randrange(1, 10), rng.randrange(1, 29))
        r = rng.random()
        if r < 0.08:
            dom = rng.choice(subs)
        elif r < 0.95:
            dom = rng.choice(partners[:11] * 4 + partners[11:])[1]
        else:
            dom = rng.choice(["gmail.com", "naver.com", "consult-kim.com"])
        if rng.random() < 0.25:
            dom = rng.choice(["mail.", "biz.", "kr."]) + dom
        user = rng.choice(["kim", "lee", "sales", "pm", "jh.park", "contact"])
        att = rng.sample(docs, rng.choice([1, 1, 1, 1, 2]))
        log.append([f"M{90001 + i}", d, rng.choices(senders, range(12, 0, -1))[0], f"{user}@{dom}", [a[0] for a in att]])

    def code_var(c):
        return rng.choice([c, c.lower(), c.replace("-", ""), c.replace("-", "_")])

    lines = []
    for mid, d, s, to, att in log:
        to2 = to if rng.random() < 0.8 else to.upper() if rng.random() < 0.5 else to.capitalize()
        row = f"{mid} | {_dt(d, rng.choice(['iso', 'dot', 'compact']))} | {_person_var(s, rng).strip()} | {to2} | " \
              f"{'; '.join(code_var(a) for a in att)}"
        lines.append(row)
        if rng.random() < 0.04:
            lines.append(row)
    doc_lines = [f"{c}\t{g}" for c, g in docs]
    nda_tbl = _md(["회사", "도메인", "체결일", "만료일", "등급"],
                  [[co, dom, _dt(s, "iso"), _dt(e, "iso"), g] for co, dom, s, e, g in nda])

    def solve(sub_on=True, subdomain=True, union=True, grade_a=True):
        strict = sub_on and subdomain and union and grade_a
        grade_of = {c: g for c, g in (l.split("\t") for l in doc_lines)}
        nd = {}
        for r in nda:
            nd.setdefault(r[1], []).append((r[2], r[3], r[4]))
        if not union:
            nd = {k: v[-1:] for k, v in nd.items()}
        seen, viol, by = set(), [], {}
        for l in lines:
            mid, d, s, to, att = [x.strip() for x in l.split("|")]
            if mid in seen:
                continue
            seen.add(mid)
            d = _parse_dt(d)
            dom = to.split("@")[1].lower()
            if sub_on and any(dom == x or dom.endswith("." + x) for x in subs):
                continue
            codes = ["DOC-" + re.sub(r"\D", "", a) for a in att.split(";")]
            top = max(grades.index(grade_of[c]) for c in codes)
            if top == 0:
                continue
            reg = next((k for k in nd if dom == k or (subdomain and dom.endswith("." + k))), None)
            ok = reg is not None and any(a <= d <= b and (top < 3 or g == "A" or not grade_a) for a, b, g in nd[reg])
            if not ok:
                viol.append(mid)
                by[_norm(s)] = by.get(_norm(s), 0) + 1
        top_s = _d_top(by, strict)
        return {"violation_count": len(viol), "violation_ids": sorted(viol),
                "top_sender": next(p for p in senders if _norm(p) == top_s)}

    truth = solve()
    prompt = (
        "1~9월 외부 메일 첨부 발송 기록을 NDA 체결 현황과 대조해서 보안 위반 건을 찾아 주세요.\n\n"
        "[NDA 체결 현황](마크다운)\n" + nda_tbl + "\n\n"
        "[자회사 도메인] " + ", ".join(subs) + " — 자회사는 내부로 보고 검사하지 않습니다(하위 도메인 포함).\n\n"
        "[문서 등급 대장](탭 구분)\n문서코드\t등급\n" + "\n".join(doc_lines) + "\n\n"
        "[외부 발송 기록](| 구분: 메일ID | 발송일 | 발신자 | 수신 주소 | 첨부 문서코드, 여러 개는 ;로 구분) 같은 메일ID가 두 번 나오면 "
        "한 번만 봅니다. 문서코드는 대소문자, 하이픈(-) 유무, 밑줄(_)이 달라도 숫자가 같으면 같은 문서입니다(예: doc0012 = DOC-0012).\n"
        + "\n".join(lines) + "\n\n"
        "판정 규칙\n"
        "1. 수신 도메인은 주소의 @ 뒤 부분이며 대소문자를 가리지 않습니다. 수신 도메인이 NDA 도메인과 같거나 '.NDA도메인'으로 끝나면"
        "(예: mail.hanbit.co.kr) 그 회사입니다.\n"
        "2. 메일의 첨부 중 가장 높은 등급으로 판정합니다(공개 < 사내한정 < 대외비 < 극비). 공개뿐이면 위반이 아닙니다.\n"
        "3. 사내한정·대외비는 발송일에 유효한 NDA(체결일~만료일, 양끝 포함)가 있어야 합니다. 극비는 유효한 NDA의 등급이 A여야 합니다.\n"
        "4. 같은 회사가 NDA 현황에 두 줄 있으면 재체결이므로 두 기간 모두 유효 기간으로 인정합니다(두 기간 사이 공백은 무효).\n"
        "5. NDA 현황에 없는 도메인(개인 메일 포함)으로 사내한정 이상 문서를 보내면 위반입니다.\n\n"
        "위반 건수, 위반 메일ID 목록(오름차순), 위반이 가장 많은 발신자 이름을 알려주세요. "
        + JSON_RULE + '{"violation_count": 정수, "violation_ids": ["M.....", ...], "top_sender": 이름}')
    wrong = [solve(sub_on=False), solve(subdomain=False), solve(union=False), solve(grade_a=False)]
    _add(54, "legal_nda_mail", prompt, {"violation_count": "int", "violation_ids": "list", "top_sender": "str"}, truth, wrong,
         {"rows": len(lines) + len(doc_lines) + len(nda), "tables": 4, "steps": 5,
          "mess": ["dup_rows", "case_variants", "code_variants", "subdomains", "date_formats", "name_spacing",
                   "renewal_two_rows"]})


def _hk55():
    rng = random.Random(1055)
    taxable = ["공사도급계약서", "용역도급계약서", "부동산매매계약서", "금전소비대차계약서"]
    exempt = ["물품공급계약서", "비밀유지계약서", "업무협약서(MOU)", "위임장"]
    bands = [(10**7, 0), (3 * 10**7, 20000), (5 * 10**7, 40000), (10**8, 70000), (10**9, 150000), (None, 350000)]

    def tax_of(a):
        if a <= 0:
            return 0
        return next(t for hi, t in bands if hi is None or a <= hi)

    docs = []
    for i in range(170):
        kind = rng.choice(taxable * 3 + exempt)
        amt = rng.choice([rng.randrange(5, 100) * 10**6, rng.randrange(10, 200) * 10**7, rng.randrange(1, 40) * 10**5 * 10])
        docs.append({"no": f"K26-{301 + i}", "kind": kind, "amt": amt, "joint": rng.random() < 0.2,
                     "vat": rng.random() < 0.15, "orig": None, "memo": ""})
    for d in rng.sample(docs[60:], 18):            # change contracts reference an earlier same-kind contract
        o = rng.choice([x for x in docs[:60] if x["kind"] == d["kind"] and not x["vat"]] or docs[:1])
        d["orig"], d["vat"] = o["no"], False
        d["amt"] = o["amt"] + rng.choice([-1, 1, 1, 1]) * rng.randrange(1, 60) * 10**6
        d["amt"] = max(d["amt"], 10**6)
    for d in rng.sample(docs, 6):
        d["memo"] = "인지세 상대방 부담 특약"
    fix = rng.choice([d for d in docs if not d["orig"] and not d["vat"] and d["kind"] in taxable and d["amt"] > 2 * 10**8])
    rows = []
    for d in docs:
        shown = d["amt"] * 11 // 10 if d["vat"] else d["amt"]
        a = _amt(shown, rng.choice(["won", "chun", "man", "ko", "hangul", "plain"]) if shown % 1000 == 0 else "won", rng)
        rows.append([d["no"], d["kind"], a + (" (VAT 포함)" if d["vat"] else ""), "공동" if d["joint"] else "단독",
                     d["orig"] or "", d["memo"]])
        if rng.random() < 0.03:
            rows.append(list(rows[-1]))
        if d is fix:
            rows.append([d["no"], d["kind"], _amt(rng.randrange(31, 49) * 10**6, "ko", rng), rows[-1][3], "",
                         "금액 정정(계약서 원본 대조)"])

    def solve(vat=True, delta=True, joint=True, fix_on=True):
        recs = {}
        for r in rows:
            if r[0] in recs and not ("정정" in r[5] and fix_on):
                continue
            recs[r[0]] = r
        amt = {}
        for no, kind, a, j, orig, memo in recs.values():
            v = _parse_amt(a.replace("(VAT 포함)", "").strip())
            if vat and "VAT 포함" in a:
                v = v * 10 // 11
            amt[no] = v
        tot, cnt, chg = 0, 0, 0
        for no, kind, a, j, orig, memo in recs.values():
            if kind not in taxable:
                continue
            base = amt[no] - amt[orig] if (orig and delta) else amt[no]
            t = tax_of(base)
            if t:
                cnt += 1
            share = 0 if "상대방 부담" in memo else (t // 2 if (j == "공동" and joint) else t)
            tot += share
            if orig:
                chg += share
        return {"company_tax": tot, "taxable_count": cnt, "change_tax": chg}

    truth = solve()
    prompt = (
        "2026년 상반기 체결 계약서의 인지세를 정리합니다(쉼표 CSV). 금액 표기가 섞여 있습니다.\n\n"
        + _csv(["문서번호", "문서종류", "기재금액", "작성", "원계약번호", "비고"], rows) + "\n\n"
        "규칙\n"
        "1. 과세 문서: " + ", ".join(taxable) + ". 그 밖의 문서(" + ", ".join(exempt) + ")는 인지세가 없습니다.\n"
        "2. 세액표(기재금액 기준): 1천만원 이하 0원 / 1천만원 초과 3천만원 이하 2만원 / 3천만원 초과 5천만원 이하 4만원 / "
        "5천만원 초과 1억원 이하 7만원 / 1억원 초과 10억원 이하 15만원 / 10억원 초과 35만원.\n"
        "3. 기재금액은 부가세 제외 금액입니다. '(VAT 포함)'이 붙은 금액은 × 10 ÷ 11 하고 원 미만을 버린 금액을 씁니다.\n"
        "4. 원계약번호가 있는 줄은 변경계약입니다. 변경계약의 기재금액은 (변경계약 금액 − 원계약 금액)이고, 0 이하이면 세액이 없습니다.\n"
        "5. 작성이 '공동'이면 회사 부담은 세액의 절반, '단독'이면 전액입니다. 비고에 '상대방 부담 특약'이 있으면 회사 부담은 0원입니다"
        "(세액이 있으면 과세 문서 수에는 셉니다).\n"
        "6. 같은 문서번호가 여러 줄이면 비고에 '정정'이 적힌 줄의 금액을 쓰고, 그런 줄이 없으면 중복이니 한 줄만 봅니다.\n\n"
        "회사 부담 인지세 합계, 세액이 0원이 아닌 과세 문서 수, 그중 변경계약의 회사 부담 합계를 알려주세요. "
        + JSON_RULE + '{"company_tax": 원(정수), "taxable_count": 정수, "change_tax": 원(정수)}')
    wrong = [solve(vat=False), solve(delta=False), solve(joint=False), solve(fix_on=False)]
    _add(55, "legal_stamp_tax", prompt, {"company_tax": "int", "taxable_count": "int", "change_tax": "int"}, truth, wrong,
         {"rows": len(rows), "tables": 1, "steps": 6,
          "mess": ["mixed_units", "korean_amounts", "hangul_amounts", "vat_included", "dup_rows", "self_join",
                   "contradiction_amount_fix"]})


def _d_addy(d, n):
    """d plus n years; Feb 29 becomes Feb 28."""
    return date(d.year + n, d.month, 28 if (d.month == 2 and d.day == 29) else d.day)


def _hk56():
    rng = random.Random(1056)
    base = date(2026, 10, 22)
    purposes = {"마케팅": ["마케팅", "마케팅 수신", "광고성 정보 수신"], "거래": ["거래", "거래기록", "주문·결제"],
                "불만처리": ["불만처리", "고객 불만", "민원"], "이벤트": ["이벤트", "경품 이벤트"]}
    recs = []
    for i in range(270):
        p = rng.choices(list(purposes), [35, 35, 15, 15])[0]
        col = date(rng.randrange(2019, 2026), rng.randrange(1, 13), rng.randrange(1, 29))
        if rng.random() < 0.03:
            col = date(rng.choice([2020, 2024]), 2, 29)
        last = col + timedelta(days=rng.randrange(0, 1500)) if p == "거래" else None
        if last and last > base:
            last = base - timedelta(days=rng.randrange(1, 300))
        renew = col + timedelta(days=rng.randrange(300, 700)) if p == "마케팅" and rng.random() < 0.25 else None
        if renew and renew > base:
            renew = None
        wd = col + timedelta(days=rng.randrange(10, 900)) if rng.random() < 0.15 else None
        if wd and wd > base:
            wd = None
        recs.append([f"U{100230 + i * 7}", p, col, last, renew, wd])
    err = next(r for r in recs if r[1] == "마케팅" and r[5] is None and r[4] is None and _d_addy(r[2], 2) >= base)
    err[5] = err[2] - timedelta(days=40)
    rows = []
    for uid, p, col, last, renew, wd in recs:
        f = lambda d: _dt(d, rng.choice(["iso", "dot", "dots", "compact", "kor"])) if d else ""
        rows.append([uid if rng.random() < 0.9 else uid.lower(), rng.choice(purposes[p]), f(col), f(last), f(renew), f(wd)])
    for r in rng.sample(rows, 10):   # older duplicate collection rows for the same member and purpose
        d = _parse_dt(r[2]) - timedelta(days=rng.randrange(200, 900))
        rows.insert(rows.index(r), [r[0], r[1], _dt(d, "iso"), "", "", ""])
    canon = {v: k for k, vs in purposes.items() for v in vs}

    def solve(dedupe_latest=True, withdraw=True, legal_keep=True, err_rule=True, renew_on=True):
        best = {}
        for uid, pv, c, l, rn, w in rows:
            k = (uid.upper(), canon[pv])
            c = _parse_dt(c)
            if k in best and dedupe_latest and best[k][0] >= c:
                continue
            if k in best and not dedupe_latest:
                continue
            best[k] = (c, _parse_dt(l) if l else None, _parse_dt(rn) if rn else None, _parse_dt(w) if w else None)
        cnt = {p: 0 for p in purposes}
        for (uid, p), (c, l, rn, w) in sorted(best.items()):
            if w and err_rule and w < c:
                w = None
            if p == "마케팅":
                until = _d_addy(rn if (rn and renew_on) else c, 2)
            elif p == "거래":
                until = _d_addy(l or c, 5)
            elif p == "불만처리":
                until = _d_addy(c, 3)
            else:
                until = _d_addm(c + timedelta(days=30), 6)
            if w and withdraw and (p in ("마케팅", "이벤트") or not legal_keep):
                until = min(until, w - timedelta(days=1))
            cnt[p] += until < base
        return {"destroy_count": sum(cnt.values()), "marketing_destroy": cnt["마케팅"], "transaction_destroy": cnt["거래"]}

    truth = solve()
    prompt = (
        "개인정보 보유기간 점검입니다. 기준일 2026-10-22에 파기 대상인 건을 세어 주세요. 아래는 회원 개인정보 처리 대장(탭 구분)입니다. "
        "빈 칸은 해당 없음입니다.\n\n" + _tsv(["회원ID", "수집 목적", "수집(동의)일", "마지막 거래일", "재동의일", "동의 철회일"], rows)
        + "\n\n규칙\n"
        "1. 회원ID는 대소문자를 가리지 않습니다. 수집 목적은 다음처럼 묶습니다: 마케팅 = 마케팅·마케팅 수신·광고성 정보 수신 / "
        "거래 = 거래·거래기록·주문·결제 / 불만처리 = 불만처리·고객 불만·민원 / 이벤트 = 이벤트·경품 이벤트.\n"
        "2. 같은 회원·같은 목적(묶은 뒤 기준) 줄이 여러 개면 수집(동의)일이 가장 늦은 줄 하나만 봅니다.\n"
        "3. 보유 종료일: 마케팅 = 수집일(재동의일이 있으면 재동의일)부터 2년 되는 날 / 거래 = 마지막 거래일부터 5년 되는 날 / "
        "불만처리 = 수집일부터 3년 되는 날 / 이벤트 = 수집일 + 30일(이벤트 종료일)부터 6개월 되는 날(그 날짜가 없으면 그 달 말일). "
        "'N년 되는 날'은 같은 월·일이고, 2월 29일은 2월 28일로 봅니다.\n"
        "4. 동의 철회일이 있으면 마케팅·이벤트는 철회일 전날이 보유 종료일입니다(원래 종료일보다 늦어지지는 않음). 거래·불만처리는 "
        "법정 보존 대상이라 철회해도 규칙 3의 종료일까지 보유합니다.\n"
        "5. 동의 철회일이 수집(동의)일보다 이르면 입력 오류이므로 철회가 없는 것으로 봅니다.\n"
        "6. 보유 종료일이 기준일보다 앞이면(종료일 < 2026-10-22) 파기 대상입니다.\n\n"
        "파기 대상 전체 건수, 그중 마케팅 건수, 거래 건수를 알려주세요(건 = 회원·목적 한 묶음). "
        + JSON_RULE + '{"destroy_count": 정수, "marketing_destroy": 정수, "transaction_destroy": 정수}')
    wv = [solve(dedupe_latest=False), solve(withdraw=False), solve(legal_keep=False), solve(err_rule=False),
          solve(renew_on=False)]
    wrong = [w for w in wv if w != truth]
    assert len(wrong) == len(wv), [w == truth for w in wv]
    _add(56, "legal_privacy_retention", prompt,
         {"destroy_count": "int", "marketing_destroy": "int", "transaction_destroy": "int"}, truth, wrong,
         {"rows": len(rows), "tables": 1, "steps": 6,
          "mess": ["date_formats", "id_case", "purpose_synonyms", "dup_rows_keep_latest", "leap_day",
                   "contradiction_withdraw_before_collect"]})


def _hk57():
    rng = random.Random(1057)
    base = date(2026, 9, 30)
    vendors = rng.sample(COMPANIES, 9)
    dels = []
    for i in range(140):
        v = rng.choices(vendors, range(9, 0, -1))[0]
        rcv = date(2026, rng.randrange(1, 8), rng.randrange(1, 29))
        dels.append([f"D{6100 + i}", v, rcv, rng.randrange(20, 900) * 10000])
    redo = rng.sample(dels[:110], 8)
    redo_day = {d[0]: d[2] + timedelta(days=rng.randrange(5, 25)) for d in redo}
    pays = []
    for no, v, rcv, amt in dels:
        start = redo_day.get(no, rcv)
        left = amt
        k = rng.choice([1, 1, 1, 2, 2, 3])
        for j in range(k):
            if start + timedelta(days=40) > base:
                break
            part = left if j == k - 1 else rng.randrange(1, max(2, left // 10000)) * 10000
            part = min(part, left)
            d = start + timedelta(days=rng.choice([rng.randrange(20, 60), rng.randrange(55, 75), rng.randrange(60, 110)]))
            if d > base:
                break
            note = "어음" if rng.random() < 0.12 else ""
            mat = d + timedelta(days=rng.choice([30, 60, 90])) if note else None
            if mat and mat > base:
                note, mat = "", None
            pays.append([d, no, part, note, mat])
            left -= part
            if left == 0:
                break
    pays.sort(key=lambda p: (p[0], p[1]))
    d_rows = []
    for no, v, rcv, amt in dels:
        d_rows.append([no, _co_var(v, rng), _dt(rcv, rng.choice(["iso", "dot", "kor"])), _amt(amt, rng.choice(["won", "man", "ko", "chun"]), rng)])
        if rng.random() < 0.03:
            d_rows.append(list(d_rows[-1]))
    p_lines = []
    for i, (d, no, part, note, mat) in enumerate(pays):
        line = ",".join(_csv_cell(c) for c in [_dt(d, rng.choice(['iso', 'dots'])), no,
                                                _amt(part, rng.choice(['plain', 'won', 'man']), rng), note,
                                                _dt(mat, "iso") if mat else ""])
        p_lines.append(line)
        if rng.random() < 0.03:
            p_lines.append(line)
    insp = [f"- {no}: 1차 검수 불합격, 재납품 {_dt(redo_day[no], 'mdk')} 수령" for no in sorted(redo_day)]

    def solve(redo_on=True, bill_mat=True, open_on=True, dedupe=True):
        info, seen = {}, set()
        for no, v, r, a in d_rows:
            info[no] = [_norm(v), _parse_dt(r), _parse_amt(a)]
        for l in insp:
            mm = re.fullmatch(r"- (D\d+): .*재납품 (\d+월 \d+일) 수령", l)
            if redo_on:
                info[mm.group(1)][1] = _parse_dt(mm.group(2), 2026)
        paid = {no: 0 for no in info}
        inter, late, byv = 0, set(), {}
        for l in p_lines:
            if dedupe and l in seen:
                continue
            seen.add(l)
            d, no, a, note, mat = next(_d_csv.reader([l]))
            d, a = _parse_dt(d), _parse_amt(a)
            if note == "어음" and bill_mat:
                d = _parse_dt(mat)
            due = info[no][1] + timedelta(days=60)
            paid[no] += a
            if d > due:
                x = a * 155 * (d - due).days // (1000 * 365)
                inter += x
                late.add(no)
                byv[info[no][0]] = byv.get(info[no][0], 0) + x
        if open_on:
            for no, (v, r, a) in info.items():
                rest = a - paid[no]
                due = r + timedelta(days=60)
                if rest > 0 and base > due:
                    x = rest * 155 * (base - due).days // (1000 * 365)
                    inter += x
                    late.add(no)
                    byv[v] = byv.get(v, 0) + x
        strict = redo_on and bill_mat and open_on and dedupe
        top = _d_top(byv, strict)
        return {"total_interest": inter, "late_count": len(late), "top_vendor": next(c for c in vendors if _norm(c) == top)}

    truth = solve()
    prompt = (
        "하도급 대금 지급 지연이자를 계산해 주세요. 기준일은 2026-09-30입니다.\n\n[납품 대장](마크다운, 금액은 공급가액)\n"
        + _md(["납품번호", "수급사업자", "수령일", "금액"], d_rows) + "\n\n[검수 결과 메모]\n" + "\n".join(insp) + "\n\n"
        "[지급 내역](쉼표 CSV: 지급일,납품번호,금액,수단,어음만기일) 완전히 같은 줄은 중복 입력입니다.\n" + "\n".join(p_lines) + "\n\n"
        "규칙\n"
        "1. 지급 기한 = 수령일 + 60일(그날까지 지급하면 지연 아님). 검수 메모에 재납품이 있으면 납품 대장의 수령일 대신 재납품 수령일을 씁니다"
        "(두 자료가 다르면 검수 메모가 맞음).\n"
        "2. 나눠 지급한 경우 지급분마다 따로 봅니다. 지연일수 = 지급일 − 지급 기한(일).\n"
        "3. 수단이 '어음'이면 어음만기일을 지급일로 봅니다.\n"
        "4. 지연이자 = 지급분 금액 × 연 15.5% × 지연일수 ÷ 365, 지급분마다 원 미만 버림.\n"
        "5. 기준일까지 다 못 받은 금액(납품 금액 − 지급 합계)이 있고 기준일이 지급 기한을 넘었으면, 남은 금액을 기준일에 지급한 것으로 보고 "
        "규칙 4로 계산합니다(이것도 원 미만 버림).\n\n"
        "지연이자 합계, 지연이자가 1원 이상 생긴 납품번호 수, 지연이자 합계가 가장 큰 수급사업자를 알려주세요. "
        + JSON_RULE + '{"total_interest": 원(정수), "late_count": 정수, "top_vendor": 회사명}')
    wv = [solve(redo_on=False), solve(bill_mat=False), solve(open_on=False), solve(dedupe=False)]
    wrong = [w for w in wv if w != truth]
    assert len(wrong) == len(wv)
    _add(57, "legal_subcontract_interest", prompt, {"total_interest": "int", "late_count": "int", "top_vendor": "str"},
         truth, wrong,
         {"rows": len(d_rows) + len(p_lines) + len(insp), "tables": 3, "steps": 5,
          "mess": ["mixed_units", "korean_amounts", "company_variants", "dup_rows", "date_formats", "partial_payments",
                   "contradiction_receipt_date"]})


def _hk58():
    rng = random.Random(1058)
    ranks = ["팀장", "본부장", "부사장", "대표이사"]
    limits = {"구매": [(10**7, 0), (5 * 10**7, 1), (3 * 10**8, 2), (None, 3)],
              "계약": [(3 * 10**7, 1), (5 * 10**8, 2), (None, 3)],
              "지출": [(5 * 10**6, 0), (3 * 10**7, 1), (None, 2)]}

    def need(kind, a):
        return next(r for hi, r in limits[kind] if hi is None or a <= hi)

    items = ["사무용 PC", "모니터", "복합기 토너", "안전화", "작업복", "서버 랙", "네트워크 스위치", "소프트웨어 라이선스"]
    vendors = rng.sample(COMPANIES, 8)
    docs = []
    for i in range(230):
        kind = rng.choices(["구매", "계약", "지출"], [55, 20, 25])[0]
        d = date(2026, rng.randrange(7, 10), rng.randrange(1, 29))
        a = rng.choice([rng.randrange(5, 100) * 10**5, rng.randrange(1, 60) * 10**6, rng.randrange(5, 80) * 10**7])
        r = need(kind, a)
        approver = r if rng.random() < 0.93 else max(0, min(3, r + rng.choice([-1, -1, 1])))
        urgent = rng.random() < 0.08
        docs.append([f"A26-{4001 + i}", d, kind, rng.choice(vendors), rng.choice(items) if kind == "구매" else "", a,
                     approver, urgent])
    # split orders: same vendor + item within one week, each under 1천만 but together over
    for _ in range(5):
        v, it = rng.choice(vendors), rng.choice(items)
        d0 = date(2026, 8, rng.randrange(3, 20))
        d0 -= timedelta(days=d0.weekday())
        for k in range(rng.choice([2, 3])):
            docs.append([f"A26-{4001 + len(docs)}", d0 + timedelta(days=rng.randrange(0, 5)), "구매", v, it,
                         rng.randrange(40, 95) * 10**5, 0, False])
    docs.sort(key=lambda x: (x[1], x[0]))
    low = [d for d in docs if d[7] and need(d[2], d[5]) >= 1][:4]
    for d in low:
        d[6] = need(d[2], d[5]) - 1
    post = sorted(set([d[0] for d in low[:3]] + rng.sample([d[0] for d in docs if d[7]], sum(d[7] for d in docs) // 2)))
    rows = []
    for no, d, kind, v, it, a, ap, urg in docs:
        title = ranks[ap] + rng.choice(["", "", "", "(전결)"])
        rows.append([no, _dt(d, rng.choice(["iso", "dot", "dots"])), kind, _co_var(v, rng), it,
                     _amt(a, rng.choice(["won", "man", "ko", "chun", "plain"]), rng), title, "Y" if urg else ""])
        if rng.random() < 0.03:
            rows.append(list(rows[-1]))
    fx = next(r for r in rows if r[2] == "계약" and _parse_amt(r[5]) <= 3 * 10**7 and r[6].startswith("본부장") and not r[7])
    rows.insert(rows.index(fx) + 1, fx[:5] + [_amt(_parse_amt(fx[5]) + 4 * 10**7, "ko", rng), fx[6], fx[7]])
    rows[rows.index(fx) + 1].append("금액 정정")
    for r in rows:
        if len(r) == 8:
            r.append("")

    def solve(split=True, urgent_rule=True, fix_on=True, dedupe=True):
        recs, order = {}, []
        for r in rows:
            if r[0] in recs:
                if dedupe and not (fix_on and "정정" in r[8]):
                    continue
                if not dedupe and "정정" not in r[8]:
                    recs[r[0] + "#dup"] = r
                    order.append(r[0] + "#dup")
                    continue
                if not fix_on:
                    continue
            else:
                order.append(r[0])
            recs[r[0]] = r
        info = {}
        for k in order:
            no, d, kind, v, it, a, title, urg, memo = recs[k]
            info[k] = (no, _parse_dt(d), kind, _norm(v), it, _parse_amt(a), ranks.index(title.replace("(전결)", "")), urg == "Y")
        wk = {}
        for k, (no, d, kind, v, it, a, ap, urg) in info.items():
            if kind == "구매":
                g = (v, it, d - timedelta(days=d.weekday()))
                wk.setdefault(g, []).append(k)
        viol, amt = [], 0
        for k, (no, d, kind, v, it, a, ap, urg) in info.items():
            base_amt = a
            if split and kind == "구매":
                grp = wk[(v, it, d - timedelta(days=d.weekday()))]
                if len(grp) >= 2:
                    base_amt = sum(info[x][5] for x in grp)
            rq = need(kind, base_amt)
            ok = ap >= rq or (urgent_rule and urg and ap == rq - 1 and no in post)
            if not ok:
                viol.append(no)
                amt += a
        return {"violation_count": len(viol), "violation_ids": sorted(viol), "violation_amount": amt}

    truth = solve()
    prompt = (
        "7~9월 결재 문서가 위임전결 규정을 지켰는지 점검해 주세요.\n\n[결재 대장](쉼표 CSV, 금액 표기 섞임)\n"
        + _csv(["문서번호", "결재일", "유형", "거래처", "품목", "금액", "최종 결재자", "긴급", "비고"], rows) + "\n\n"
        "[긴급 건 사후 보고 완료 목록] " + ", ".join(post) + "\n\n"
        "위임전결 규정(금액은 그 금액 이하까지 해당 직위가 결재)\n"
        "- 구매: 1천만원 이하 팀장 / 5천만원 이하 본부장 / 3억원 이하 부사장 / 그 초과 대표이사\n"
        "- 계약: 3천만원 이하 본부장 / 5억원 이하 부사장 / 그 초과 대표이사 (팀장 전결 없음)\n"
        "- 지출: 5백만원 이하 팀장 / 3천만원 이하 본부장 / 그 초과 부사장\n"
        "직위 순서: 팀장 < 본부장 < 부사장 < 대표이사. 필요한 직위보다 높은 직위가 결재하면 문제없습니다. '(전결)' 표시는 무시합니다.\n\n"
        "점검 규칙\n"
        "1. 같은 문서번호가 여러 줄이면 비고에 '금액 정정'이 적힌 줄을 쓰고, 아니면 중복이니 한 줄만 봅니다.\n"
        "2. 분할 발주: 구매 유형에서 같은 거래처·같은 품목이 같은 주(월요일~일요일)에 2건 이상이면 그 주 합계 금액으로 필요 직위를 정하고, "
        "그 묶음의 모든 문서에 적용합니다. 거래처명은 (주)·㈜·주식회사·띄어쓰기 차이를 무시합니다.\n"
        "3. 긴급이 Y인 문서는 필요 직위보다 한 단계 낮은 직위의 결재도 인정하지만, 사후 보고 완료 목록에 있어야 합니다. 목록에 없으면 위반입니다.\n"
        "4. 그 밖에 최종 결재자가 필요 직위보다 낮으면 위반입니다.\n\n"
        "위반 문서 수, 위반 문서번호 목록(오름차순), 위반 문서 금액 합계(문서 자체 금액)를 알려주세요. "
        + JSON_RULE + '{"violation_count": 정수, "violation_ids": ["A26-....", ...], "violation_amount": 원(정수)}')
    wv = [solve(split=False), solve(urgent_rule=False), solve(fix_on=False), solve(dedupe=False)]
    wrong = [w for w in wv if w != truth]
    assert len(wrong) == len(wv), [w == truth for w in wv]
    _add(58, "legal_approval_rules", prompt, {"violation_count": "int", "violation_ids": "list", "violation_amount": "int"},
         truth, wrong,
         {"rows": len(rows) + len(post), "tables": 3, "steps": 4,
          "mess": ["mixed_units", "korean_amounts", "company_variants", "dup_rows", "date_formats", "split_orders",
                   "title_suffix", "contradiction_amount_fix"]})


def _hk59():
    rng = random.Random(1059)
    V = {"세진전자": dict(m=12, cm=12, ex={"사용자 과실", "소모품"}, per=3 * 10**6, cap=2 * 10**7),
         "미래테크": dict(m=24, cm=24, ex={"사용자 과실", "낙뢰·침수"}, per=None, cap=15 * 10**6),
         "태영정밀": dict(m=18, cm=18, ex={"사용자 과실"}, per=2 * 10**6, cap=None),
         "보람기계": dict(m=36, cm=6, ex={"사용자 과실"}, per=5 * 10**6, cap=3 * 10**7)}
    vn = list(V)
    goods = [("노트북", "본체"), ("모니터", "본체"), ("복합기", "본체"), ("프린터 드럼", "소모품"), ("UPS 배터리", "소모품"),
             ("서버", "본체"), ("필터 카트리지", "소모품"), ("CNC 스핀들", "본체"), ("공구 팁", "소모품")]
    assets = []
    for i in range(90):
        g, cls = rng.choice(goods)
        assets.append([f"AS-{7001 + i}", g, cls, rng.choice(vn),
                       date(rng.randrange(2023, 2026), rng.randrange(1, 13), rng.randrange(1, 32) if False else rng.randrange(1, 29))])
    for a in assets[:4]:
        a[4] = date(2025, rng.choice([1, 3, 8]), 31)
    causes = ["자연 고장", "자연 고장", "자연 고장", "사용자 과실", "낙뢰·침수", "소모품 마모"]
    claims = []
    for i in range(190):
        a = rng.choice(assets)
        d = date(2026, rng.randrange(1, 10), rng.randrange(1, 29))
        cause = rng.choice(causes)
        cost = rng.choice([rng.randrange(10, 200) * 10**4, rng.randrange(100, 700) * 10**4])
        claims.append([f"W{3100 + i}", d, a[0], a[3], cause, cost])
    wrongv = next(c for c in claims if c[4] == "자연 고장")
    wrongv[3] = next(v for v in vn if v != wrongv[3])
    claims.sort(key=lambda c: (c[1], c[0]))
    a_tbl = _tsv(["자산번호", "품목", "분류", "공급사", "검수일"],
                 [[a[0], a[1], a[2], a[3], _dt(a[4], rng.choice(["iso", "dot", "kor"]))] for a in assets])
    lines = []
    for no, d, aid, v, cause, cost in claims:
        cells = [no, _dt(d, rng.choice(["iso", "dots", "md"])), aid.lower() if rng.random() < 0.1 else aid, _co_var(v, rng),
                 cause, _amt(cost, rng.choice(["won", "man", "ko", "chun"]), rng)]
        lines.append(" / ".join(cells))
        if rng.random() < 0.04:
            lines.append(" / ".join(cells))
    clause = (
        "- 세진전자: 하자보수 기간은 검수일부터 12개월. 사용자 과실과 소모품(분류가 소모품인 자산 또는 원인이 '소모품 마모')은 보상하지 않는다. "
        "1건당 300만원, 2026년 신고분 합계 2,000만원까지 보상한다.\n"
        "- 미래테크: 하자보수 기간은 검수일부터 24개월. 사용자 과실과 낙뢰·침수는 보상하지 않는다. 1건당 한도는 없고 2026년 신고분 합계 "
        "1,500만원까지 보상한다.\n"
        "- 태영정밀: 하자보수 기간은 검수일부터 18개월. 사용자 과실만 보상하지 않는다(소모품도 보상). 1건당 200만원까지, 연간 한도는 없다.\n"
        "- 보람기계: 하자보수 기간은 검수일부터 36개월, 단 분류가 소모품인 자산은 6개월. 사용자 과실은 보상하지 않는다. 1건당 500만원, "
        "2026년 신고분 합계 3,000만원까지 보상한다.")

    def solve(ledger_vendor=True, consum=True, annual=True, dedupe=True, month_end=True):
        A = {}
        for l in a_tbl.splitlines()[1:]:
            aid, g, cls, v, d = l.split("\t")
            A[aid] = (cls, v, _parse_dt(d))
        seen, used, total, valid, hit = set(), {v: 0 for v in vn}, 0, 0, set()
        for l in lines:
            no, d, aid, v, cause, cost = l.split(" / ")
            if dedupe and no in seen:
                continue
            seen.add(no)
            cls, lv, acc = A[aid.upper()]
            vend = lv if ledger_vendor else next(x for x in vn if _norm(x) == _norm(v))
            t = V[vend]
            months = t["cm"] if (cls == "소모품" and consum) else t["m"]
            end = _d_addm(acc, months) if month_end else acc + timedelta(days=30 * months)
            d = _parse_dt(d, 2026)
            if d > end:
                continue
            ex = set(t["ex"])
            bad = cause in ex or ("소모품" in ex and (cls == "소모품" or cause == "소모품 마모"))
            if cause == "소모품 마모" and "소모품" not in ex:
                bad = False
            if bad:
                continue
            valid += 1
            pay = _parse_amt(cost)
            if t["per"]:
                pay = min(pay, t["per"])
            if t["cap"] and annual:
                room = t["cap"] - used[vend]
                if pay >= room:
                    hit.add(vend)
                pay = min(pay, room)
            used[vend] += pay
            total += pay
        return {"reimb_total": total, "valid_count": valid, "capped_vendors": sorted(hit)}

    truth = solve()
    assert truth["capped_vendors"]
    prompt = (
        "2026년 1~9월 장비 하자 신고 건 중 공급사가 보상해야 할 금액을 계산해 주세요.\n\n[공급사별 계약 조항 요약]\n" + clause + "\n\n"
        "[자산 대장](탭 구분)\n" + a_tbl + "\n\n"
        "[하자 신고](' / ' 구분: 신고번호 / 신고일(2026년) / 자산번호 / 공급사 / 원인 / 수리비) 같은 신고번호가 두 번 나오면 한 번만 봅니다. "
        "자산번호는 대소문자를 가리지 않습니다.\n" + "\n".join(lines) + "\n\n"
        "규칙\n"
        "1. 공급사는 자산 대장 기준입니다. 신고서의 공급사가 자산 대장과 다르면 자산 대장이 맞습니다.\n"
        "2. 하자보수 기간의 끝은 검수일에 N개월을 더한 같은 날짜(그 날짜가 없으면 그 달 말일)이며 그날 신고까지 대상입니다.\n"
        "3. 위 조항에서 보상하지 않는 원인이면 대상이 아닙니다. 원인 '소모품 마모'는 소모품 제외 조항이 있는 공급사에서만 제외됩니다.\n"
        "4. 보상액 = 수리비, 1건당 한도가 있으면 한도까지.\n"
        "5. 연간 한도는 신고일 순서(같은 날은 신고번호 순)로 채웁니다. 한도를 넘는 건은 남은 한도만큼만, 한도를 다 쓴 뒤의 건은 0원입니다. "
        "보상 대상 건수는 0원이 된 건도 셉니다.\n\n"
        "보상액 합계, 보상 대상 건수, 연간 한도를 다 쓴 공급사 목록(가나다순)을 알려주세요. "
        + JSON_RULE + '{"reimb_total": 원(정수), "valid_count": 정수, "capped_vendors": ["공급사", ...]}')
    wv = [solve(ledger_vendor=False), solve(consum=False), solve(annual=False), solve(dedupe=False), solve(month_end=False)]
    wrong = [w for w in wv if w != truth]
    assert len(wrong) >= 3, [w == truth for w in wv]
    _add(59, "legal_warranty_claims", prompt, {"reimb_total": "int", "valid_count": "int", "capped_vendors": "list"},
         truth, wrong,
         {"rows": len(assets) + len(lines) + 4, "tables": 3, "steps": 5,
          "mess": ["mixed_units", "korean_amounts", "company_variants", "dup_rows", "date_formats", "id_case",
                   "per_vendor_clauses", "contradiction_vendor"]})


def _hk60():
    rng = random.Random(1060)
    base = date(2026, 10, 1)
    stores = [f"S{11 + i:02d}" for i in range(36)]
    hist = []
    for s in stores:
        d = date(rng.randrange(2019, 2023), rng.randrange(1, 13), rng.randrange(1, 29))
        dep, rent = rng.randrange(2, 30) * 10**7, rng.randrange(80, 500) * 10**4
        hist.append([s, d, "최초계약", dep, rent, ""])
        while True:
            d = d + timedelta(days=rng.choice([300, 366, 380, 420, 500, 730]))
            if d > base:
                break
            kind = rng.choices(["증액청구", "갱신", "감액합의"], [50, 35, 15])[0]
            if kind == "감액합의":
                dep2, rent2 = dep, rent - rng.randrange(5, 40) * 10**4
            else:
                f = rng.choice([1.0, 1.02, 1.03, 1.05, 1.05, 1.08, 1.1])
                dep2, rent2 = int(dep * f) // 10**6 * 10**6, int(rent * f) // 10**4 * 10**4
            hist.append([s, d, kind, dep2, rent2, ""])
            dep, rent = dep2, rent2
    fixs = rng.choice(stores[5:])
    i0 = next(i for i, h in enumerate(hist) if h[0] == fixs)
    hist.insert(i0 + 1, [fixs, hist[i0][1], "최초계약", hist[i0][3] + 2 * 10**7, hist[i0][4] + 50 * 10**4, "계약서 원본 대조"])
    rows = []
    for s, d, kind, dep, rent, memo in hist:
        r = [s, _dt(d, rng.choice(["iso", "dot", "kor", "compact"])), kind,
             _amt(dep, rng.choice(["won", "man", "ko", "hangul"]), rng), _amt(rent, rng.choice(["won", "man", "plain", "ko"]), rng), memo]
        rows.append(r)
        if rng.random() < 0.04:
            rows.append(list(r))

    def solve(cap=True, year_rule=True, fix_on=True, dec_reset=False):
        recs, seen = {}, set()
        for r in rows:
            key = tuple(r)
            if key in seen:
                continue
            seen.add(key)
            s, d, kind, dep, rent, memo = r
            lst = recs.setdefault(s, [])
            if kind == "최초계약" and any(x[1] == "최초계약" for x in lst):
                if fix_on and "원본" in memo:
                    lst[:] = [x for x in lst if x[1] != "최초계약"]
                else:
                    continue
            lst.append((_parse_dt(d), kind, _parse_amt(dep), _parse_amt(rent)))
        total_rent, invalid, over = 0, 0, 0
        for s in sorted(recs):
            ev = sorted(recs[s], key=lambda x: (x[0], x[1] != "최초계약"))
            dep = rent = None
            anchor = None
            for d, kind, a, b in ev:
                if d > base:
                    continue
                if kind == "최초계약":
                    dep, rent, anchor = a, b, d
                    continue
                if kind == "감액합의":
                    dep, rent = min(dep, a), min(rent, b)
                    if dec_reset:
                        anchor = d
                    continue
                if a <= dep and b <= rent:
                    dep, rent = a, b
                    continue
                if year_rule and d < _d_addy(anchor, 1):
                    invalid += 1
                    continue
                na = min(a, dep * 105 // 100) if cap else a
                nb = min(b, rent * 105 // 100) if cap else b
                invalid += (na, nb) != (a, b)
                dep, rent = na, nb
                anchor = d
            total_rent += rent
            over += dep + rent * 100 > 5 * 10**8
        return {"total_rent": total_rent, "invalid_count": invalid, "over_5eok": over}

    truth = solve()
    prompt = (
        "매장 임대차 계약 이력(쉼표 CSV)을 보고 2026-10-01 기준 유효한 월세를 정리해 주세요. 금액 표기가 섞여 있습니다"
        "(만원, 억, 한글 금액 등).\n\n" + _csv(["점포", "변경일", "구분", "보증금", "월세", "비고"], rows) + "\n\n"
        "규칙\n"
        "1. 완전히 같은 줄은 한 번만 봅니다. 한 점포에 '최초계약'이 두 줄이면 비고에 '원본 대조'가 적힌 줄만 쓰고 다른 줄은 버립니다.\n"
        "2. 점포별로 변경일 순서대로 적용합니다. '감액합의'는 언제든 유효하며 적힌 금액으로 바꿉니다.\n"
        "3. '갱신'과 '증액청구'에서 보증금이나 월세가 직전 유효 금액보다 늘어나면 증액입니다. 증액은 직전 기산일부터 1년이 지나야"
        "(변경일이 기산일 + 1년 같은 날짜 이후) 할 수 있고, 그 전이면 그 줄 전체가 무효입니다(금액 그대로 유지). 기산일은 최초계약일 "
        "또는 마지막으로 유효하게 증액된 날이며, 감액합의는 기산일을 바꾸지 않습니다.\n"
        "4. 유효한 증액도 항목(보증금, 월세)마다 직전 유효 금액의 5%까지만 인정합니다: 인정 금액 = min(청구 금액, 직전 금액 × 1.05, "
        "원 미만 버림). 늘지 않은 항목은 적힌 금액을 그대로 씁니다.\n"
        "5. 금액이 하나도 늘지 않은 갱신은 그대로 적용하고 기산일을 바꾸지 않습니다.\n"
        "6. 환산보증금 = 보증금 + 월세 × 100.\n\n"
        "2026-10-01 기준 전 점포 월세 합계, 무효가 되었거나 5% 상한으로 깎인 증액 줄 수, 환산보증금이 5억원을 넘는 점포 수를 알려주세요. "
        + JSON_RULE + '{"total_rent": 원(정수), "invalid_count": 정수, "over_5eok": 정수}')
    wv = [solve(cap=False), solve(year_rule=False), solve(fix_on=False), solve(dec_reset=True)]
    wrong = [w for w in wv if w != truth]
    assert len(wrong) >= 3, [w == truth for w in wv]
    _add(60, "legal_lease_rent", prompt, {"total_rent": "int", "invalid_count": "int", "over_5eok": "int"}, truth, wrong,
         {"rows": len(rows), "tables": 1, "steps": 6,
          "mess": ["mixed_units", "korean_amounts", "hangul_amounts", "dup_rows", "date_formats", "anniversary_rule",
                   "contradiction_initial_contract"]})


# ================================================================= registration and self-check

for _n in range(1, 61):
    globals()[f"_hk{_n:02d}"]()

assert len(TASKS) == 60 and len({t["id"] for t in TASKS}) == 60


def _selftest():
    import json
    bad = 0
    print(f"{'id':6} {'domain':10} {'rows':>4} {'tab':>3} {'steps':>5} {'chars':>6} oracle wrong  mess")
    for t in TASKS:
        st, m = SELFTEST[t["id"]], META[t["id"]]
        ok = t["check"](json.dumps(st["oracle"], ensure_ascii=False), st["oracle"], None)
        wr = [t["check"](json.dumps(w, ensure_ascii=False), w, None) for w in st["wrong"]]
        good = ok and not any(wr)
        bad += not good
        print(f"{t['id']:6} {t['domain']:10} {m['rows']:>4} {m['tables']:>3} {m['steps']:>5} {m['chars']:>6} "
              f"{'pass' if ok else 'FAIL':6} {sum(not w for w in wr)}/{len(wr)}  {','.join(m['mess'])}"
              + ("" if good else "   <-- PROBLEM"))
    ls = sorted(m["chars"] for m in META.values())
    print(f"prompt chars: min {ls[0]}, median {ls[len(ls) // 2]}, max {ls[-1]}; problems: {bad}")
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if _selftest() else 0)
