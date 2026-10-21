"""Messy-paste fault-injection tasks: business data pasted into chat the way office workers paste it.

Eight fault types, three tasks each (domain = fault type): tsv_excel, units, korean_numbers,
merged_cells, dirty_rows, no_table_prose, multi_table, markdown_or_pipe. Every prompt carries
the data and states how to read the mess, so there is one defensible answer. Data comes from
random.Random(seed); ground truth is computed from the same underlying values the text is
rendered from. SELFTEST holds, per task, the oracle answer and "fell for the mess" answers.
Standard library only. No tools.
"""
import random
import re
from collections import defaultdict

import grade

JSON_RULE = "답은 다른 설명 없이 JSON 한 줄로만 주세요: "

TASKS = []
SELFTEST = {}

# ================================================================= helpers


def _norm(s):
    s = str(s if s is not None else "")
    for t in ("주식회사", "(주)", "㈜", "（주）"):
        s = s.replace(t, "")
    return re.sub(r"\s+", "", s).lower()


def _get(p, k):
    return p.get(k) if isinstance(p, dict) else None


def _eq_num(p, k, expected):
    v = grade.num(_get(p, k))
    return v is not None and v == expected


def _eq_name(p, k, expected):
    v = _get(p, k)
    return isinstance(v, str) and _norm(v) == _norm(expected)


def _eq_names(p, k, expected):
    v = _get(p, k)
    if not isinstance(v, list):
        return False
    return sorted(_norm(x) for x in v) == sorted(_norm(x) for x in expected)


def _json_check(fn):
    def check(answer, parsed, ws):
        if not isinstance(parsed, dict):
            return False
        try:
            return bool(fn(parsed))
        except Exception:
            return False
    return check


def _add(tid, domain, prompt, keys, fn, oracle, wrong):
    TASKS.append(dict(id=tid, split="messy", domain=domain, prompt=prompt, tools="none",
                      contract={"type": "json", "keys": keys}, check=_json_check(fn)))
    SELFTEST[tid] = {"oracle": oracle, "wrong": wrong}


def _argmax(d):
    items = sorted(d.items(), key=lambda x: -x[1])
    assert len(items) < 2 or items[0][1] != items[1][1], "tie"
    return items[0]


def _dec(x):
    return f"{x:.2f}".rstrip("0").rstrip(".")


def _unit(n, style):
    """Positive n (multiple of 10,000) in one of five pasted formats."""
    if style == 0:
        return f"{n:,}원"
    if style == 1:
        return f"{n // 10000:,}만원"
    if style == 2:
        return f"{_dec(n / 1e6)}백만"
    if style == 3:
        return f"₩{n:,}"
    return f"{n:,}"


def _misread(n, style):
    """What a naive reader gets: '120만원' -> 120, '1.2백만' -> 1.2."""
    if style == 1:
        return n // 10000
    if style == 2:
        return n / 1e6
    return n


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


def _ko(n, rng, won=None):
    """320000000 -> '3억 2천만원' / '3억2,000만' / ..., digits and Korean units mixed."""
    groups = ((n // 10**8, "억"), (n // 10**4 % 10**4, "만"), (n % 10**4, ""))
    parts = []
    for g, u in groups:
        if g:
            if u == "만" and g == 1 and n < 10**8 and rng.random() < 0.6:
                parts.append("만")
            else:
                parts.append(_k4(g, rng.random() < 0.5) + u)
    sep = rng.choice(["", " "])
    tail = rng.choice(["원", "원", ""]) if won is None else won
    return sep.join(parts) + tail


_HD = "영일이삼사오육칠팔구"


def _h4(x):
    s = ""
    for unit, val in (("천", 1000), ("백", 100), ("십", 10), ("", 1)):
        d = x // val % 10
        if d:
            s += ("" if d == 1 and unit else _HD[d]) + unit
    return s


def _hangul(n):
    """123000000 -> '일억이천삼백만'."""
    eok, man, rest = n // 10**8, n // 10**4 % 10**4, n % 10**4
    s = ""
    if eok:
        s += ("일" if eok == 1 else _h4(eok)) + "억"
    if man:
        s += ("일" if man == 1 else _h4(man)) + "만"
    if rest:
        s += _h4(rest)
    return s


def _eun(word):
    """Topic particle 은/는 for a Korean or alphanumeric item name."""
    w = re.sub(r"\([^)]*\)$", "", word.strip()) or word
    ch = w[-1]
    if "가" <= ch <= "힣":
        final = (ord(ch) - 0xAC00) % 28 != 0
    elif ch.isdigit():
        final = ch in "013678"
    else:
        final = ch.upper() in "LMNR"
    return word + ("은" if final else "는")


NAMES = ["김민수", "이서연", "박지훈", "최유진", "정다은", "강현우", "조수아", "윤도현", "장하린", "임재원",
         "한소희", "오세훈", "서지민", "신동욱", "권나래", "황보람", "안태준", "송예린", "류건우", "배수빈"]

# ================================================================= 1. tsv_excel


def _mx01():
    rng = random.Random(101)
    regions = [("수도권", ["강남", "종로", "분당", "일산", "인천"]), ("충청", ["대전", "청주", "천안"]),
               ("영남", ["부산", "대구", "울산", "창원"]), ("호남", ["광주", "전주", "목포"])]
    lines = ["\t\t1분기\t\t2분기\t", "지역\t지점\t매출\t비용\t매출\t비용"]
    rows, total = [], [0] * 4
    for reg, brs in regions:
        sub = [0] * 4
        for b in brs:
            s1, s2 = rng.randrange(800, 3000) * 1000, rng.randrange(800, 3000) * 1000
            v = [s1, s1 * rng.randrange(45, 95) // 100000 * 1000, s2, s2 * rng.randrange(45, 95) // 100000 * 1000]
            rows.append((b, v))
            lines.append("\t".join([reg, b] + [f"{x:,}" for x in v]))
            sub = [a + c for a, c in zip(sub, v)]
        lines.append("\t".join([reg, "소계"] + [f"{x:,}" for x in sub]))
        total = [a + c for a, c in zip(total, sub)]
    lines.append("\t".join(["합계", ""] + [f"{x:,}" for x in total]))
    q2 = sum(v[2] for _, v in rows)
    top, _ = _argmax({b: v[0] - v[1] + v[2] - v[3] for b, v in rows})
    top_q2, _ = _argmax({b: v[2] for b, v in rows})
    prompt = ("엑셀에서 지점별 실적표를 그대로 복사해 왔어요(탭으로 구분). 첫 두 줄이 머리글인데 위 줄은 분기, 아래 줄은 "
              "항목(매출/비용)입니다. 각 지역 끝의 '소계' 행과 맨 아래 '합계' 행은 데이터가 아니라 집계 행이니 중복으로 "
              "세지 마세요. 금액은 원 단위입니다.\n\n" + "\n".join(lines) + "\n\n"
              "2분기 매출의 전체 합계와, 상반기(1분기+2분기) 영업이익(매출-비용)이 가장 큰 지점 이름을 알려주세요. "
              + JSON_RULE + '{"q2_sales_total": 합계(원, 정수), "top_branch": 지점명}')
    _add("mx_01", "tsv_excel", prompt, {"q2_sales_total": "int", "top_branch": "str"},
         lambda p: _eq_num(p, "q2_sales_total", q2) and _eq_name(p, "top_branch", top),
         {"q2_sales_total": q2, "top_branch": top},
         [{"q2_sales_total": 2 * q2, "top_branch": top}, {"q2_sales_total": 3 * q2, "top_branch": top},
          {"q2_sales_total": q2, "top_branch": top_q2 if top_q2 != top else "소계"}])


def _mx02():
    rng = random.Random(102)
    groups = [("제조원가", ["원재료비", "부재료비", "직접노무비", "외주가공비", "전력비", "수선비", "소모품비", "감가상각비(제조)", "포장비"]),
              ("판관비", ["급여", "복리후생비", "여비교통비", "접대비", "통신비", "지급수수료", "광고선전비", "차량유지비", "도서인쇄비", "교육훈련비"])]
    lines = ["\t2026년 3분기\t\t\t", "계정과목\t7월\t8월\t9월\t분기계"]
    accts, grand = [], [0] * 3
    for g, names in groups:
        sub = [0] * 3
        for nm in names:
            v = [rng.randrange(50, 4000) * 10000 for _ in range(3)]
            accts.append((nm, v))
            lines.append("\t".join([nm] + [f"{x:,}" for x in v] + [f"{sum(v):,}"]))
            sub = [a + c for a, c in zip(sub, v)]
        lines.append("\t".join([f"{g} 계"] + [f"{x:,}" for x in sub] + [f"{sum(sub):,}"]))
        grand = [a + c for a, c in zip(grand, sub)]
    lines.append("\t".join(["총계"] + [f"{x:,}" for x in grand] + [f"{sum(grand):,}"]))
    aug = sum(v[1] for _, v in accts)
    up = sum(1 for _, v in accts if v[2] > v[0])
    up_with_sub = up + sum(1 for s in [grand] if s[2] > s[0])
    prompt = ("3분기 계정별 비용 집계표를 엑셀에서 복사했습니다(탭 구분, 맨 왼쪽 위 칸은 비어 있음). 첫 줄은 '2026년 3분기' "
              "제목이 7~9월 위에 걸쳐 있는 머리글이고 둘째 줄이 실제 열 이름입니다. '제조원가 계', '판관비 계', '총계' 행과 "
              "맨 오른쪽 '분기계' 열은 집계이므로 계정 데이터로 세지 않습니다. 단위는 원.\n\n" + "\n".join(lines) + "\n\n"
              "계정과목 기준으로 8월 비용 합계와, 9월 금액이 7월보다 큰(같으면 제외) 계정과목 수를 알려주세요. "
              + JSON_RULE + '{"aug_total": 원(정수), "up_count": 개수(정수)}')
    _add("mx_02", "tsv_excel", prompt, {"aug_total": "int", "up_count": "int"},
         lambda p: _eq_num(p, "aug_total", aug) and _eq_num(p, "up_count", up),
         {"aug_total": aug, "up_count": up},
         [{"aug_total": 2 * aug, "up_count": up}, {"aug_total": 3 * aug, "up_count": up},
          {"aug_total": aug, "up_count": up + 3 if up_with_sub == up else up_with_sub + 2}])


def _mx03():
    rng = random.Random(103)
    teams = {"개발팀": 6, "영업팀": 5, "생산팀": 6, "품질팀": 4}
    pool = iter(rng.sample(NAMES, 20) + [n + "B" for n in NAMES])
    lines = ["\t\t초과근무(시간)\t\t수당", "팀\t성명\t평일\t휴일\t(원)"]
    emps, grand = [], [0, 0, 0]
    for t, k in teams.items():
        sub = [0, 0, 0]
        for _ in range(k):
            nm = next(pool)
            wd, hd = rng.randrange(0, 30), rng.randrange(0, 16)
            pay = (wd * 15 + hd * 22) * 1000
            emps.append((t, nm, wd, hd, pay))
            lines.append(f"{t}\t{nm}\t{wd}\t{hd}\t{pay:,}")
            sub = [sub[0] + wd, sub[1] + hd, sub[2] + pay]
        lines.append(f"{t}\t소계\t{sub[0]}\t{sub[1]}\t{sub[2]:,}")
        grand = [a + c for a, c in zip(grand, sub)]
    lines.append(f"총계\t\t{grand[0]}\t{grand[1]}\t{grand[2]:,}")
    cnt = sum(1 for e in emps if e[3] >= 8)
    dev = sum(e[4] for e in emps if e[0] == "개발팀")
    prompt = ("9월 초과근무 현황 엑셀 시트를 붙여넣어요(탭 구분). 머리글이 두 줄입니다: 윗줄 '초과근무(시간)'은 평일·휴일 두 열에 "
              "걸쳐 있고, '수당' 아래 '(원)'은 단위 표시입니다. 팀마다 '소계' 행이 있고 맨 끝에 '총계' 행이 있는데, 둘 다 "
              "사람이 아니라 합계 행입니다.\n\n" + "\n".join(lines) + "\n\n"
              "휴일 초과근무가 8시간 이상인 직원 수(합계 행 제외)와, 개발팀 직원 수당의 합계를 알려주세요. "
              + JSON_RULE + '{"holiday8_count": 명(정수), "dev_pay_total": 원(정수)}')
    _add("mx_03", "tsv_excel", prompt, {"holiday8_count": "int", "dev_pay_total": "int"},
         lambda p: _eq_num(p, "holiday8_count", cnt) and _eq_num(p, "dev_pay_total", dev),
         {"holiday8_count": cnt, "dev_pay_total": dev},
         [{"holiday8_count": cnt + 5, "dev_pay_total": dev}, {"holiday8_count": cnt, "dev_pay_total": 2 * dev}])


# ================================================================= 2. units


def _mx04():
    rng = random.Random(104)
    depts = ["영업부", "총무부", "생산부", "연구소"]
    items = ["거래처 식대", "택시비", "사무용품", "출장 숙박", "교육비", "소모품", "주차비", "회의 다과", "택배비"]
    rows = []
    kinds = ["neg"] * 4 + ["zero"] * 3 + ["pos"] * 25
    rng.shuffle(kinds)
    lines = ["일자\t부서\t적요\t금액"]
    for i, kd in enumerate(kinds):
        d, it = rng.choice(depts), rng.choice(items)
        day = f"10/{i // 2 + 1:02d}"
        if kd == "pos":
            n, st = rng.randrange(3, 300) * 10000, rng.randrange(5)
            txt, mis = _unit(n, st), _misread(n, st)
        elif kd == "neg":
            m = rng.randrange(2, 60) * 10000
            n, txt, mis, it = -m, rng.choice([f"({m:,})", f"△{m:,}"]), m, it + " 환불"
        else:
            n, txt, mis = 0, "-", 0
        rows.append((d, n, mis))
        lines.append(f"{day}\t{d}\t{it}\t{txt}")
    sales = sum(n for d, n, _ in rows if d == "영업부")
    negs = sum(1 for _, n, _ in rows if n < 0)
    total = sum(n for _, n, _ in rows)
    wrong_pos = sum(abs(n) for _, n, _ in rows)
    wrong_mis = sum(m if n >= 0 else -m for _, n, m in rows)
    sales_pos = sum(abs(n) for d, n, _ in rows if d == "영업부")
    prompt = ("법인카드 사용 내역을 여기저기서 모아 붙였더니 금액 표기가 제각각이에요. 해석 규칙: '120만원'=1,200,000원, "
              "'1.2백만'=1,200,000원, '₩1,200,000'과 숫자만 있는 '1,200,000'도 원 단위, 괄호 '(300,000)'와 '△300,000'은 "
              "음수(환불, -300,000원), '-' 한 글자는 0원입니다.\n\n" + "\n".join(lines) + "\n\n"
              "영업부 금액의 순합계(환불 차감), 음수(환불) 행의 개수, 전체 순합계를 알려주세요. "
              + JSON_RULE + '{"sales_net": 원(정수), "refund_rows": 개수(정수), "total_net": 원(정수)}')
    _add("mx_04", "units", prompt, {"sales_net": "int", "refund_rows": "int", "total_net": "int"},
         lambda p: _eq_num(p, "sales_net", sales) and _eq_num(p, "refund_rows", negs) and _eq_num(p, "total_net", total),
         {"sales_net": sales, "refund_rows": negs, "total_net": total},
         [{"sales_net": sales_pos, "refund_rows": 0, "total_net": wrong_pos},
          {"sales_net": sales, "refund_rows": negs, "total_net": wrong_mis},
          {"sales_net": sales, "refund_rows": negs, "total_net": wrong_pos}])


def _mx05():
    rng = random.Random(105)
    goods = ["노트북", "모니터 27인치", "도킹스테이션", "레이저프린터", "무선키보드", "마우스", "웹캠", "헤드셋",
             "외장SSD 1TB", "NAS", "공유기", "UPS", "태블릿", "프로젝터", "스캐너", "화이트보드", "의자", "책상",
             "서랍장", "사물함", "정수기", "공기청정기", "문서세단기", "전화기"]
    lines = ["품목\t수량\t단가"]
    rows = []
    for g in goods:
        q = rng.randrange(1, 25)
        p = rng.randrange(8, 2500) * 1000
        if rng.random() < 0.3:
            txt, raw_k = rng.choice([f"{p:,}원", f"₩{p:,}"]), p * 1000
        else:
            txt, raw_k = f"{p // 1000:,}", p // 1000
        rows.append((g, q, p, raw_k))
        lines.append(f"{g}\t{q}\t{txt}")
    total = sum(q * p for _, q, p, _ in rows)
    big = sum(1 for _, _, p, _ in rows if p >= 1_000_000)
    wrong_all_k = sum(q * rk if rk != p // 1000 else q * p for _, q, p, rk in rows)  # '원' rows also x1000
    wrong_all_won = sum(q * (p // 1000 if rk == p // 1000 else p) for _, q, p, rk in rows)  # plain rows left as is
    prompt = ("비품 구매 요청 목록입니다. 원래 표는 '(단위: 천원)'인데 몇 줄은 다른 견적서에서 원 단위로 붙여넣었어요. "
              "규칙: 숫자만 있는 단가는 천원 단위(예: 1,250 = 1,250,000원), '원'이나 '₩'이 붙은 단가는 그대로 원 단위입니다.\n\n"
              "(단위: 천원)\n" + "\n".join(lines) + "\n\n"
              "수량×단가의 총 구매금액(원)과, 단가가 1,000,000원 이상인 품목 수를 알려주세요. "
              + JSON_RULE + '{"total_won": 원(정수), "items_over_1m": 개수(정수)}')
    _add("mx_05", "units", prompt, {"total_won": "int", "items_over_1m": "int"},
         lambda p: _eq_num(p, "total_won", total) and _eq_num(p, "items_over_1m", big),
         {"total_won": total, "items_over_1m": big},
         [{"total_won": wrong_all_k, "items_over_1m": big}, {"total_won": wrong_all_won, "items_over_1m": big},
          {"total_won": total // 1000, "items_over_1m": big}])


def _mx06():
    rng = random.Random(106)
    lines = ["프로젝트\t예산\t집행액"]
    rows = []
    for i in range(20):
        name = f"PJ-{i + 1:02d}"
        b = rng.randrange(50, 900) * 10000
        bs = rng.randrange(5)
        r = rng.random()
        if r < 0.15:
            a, at, am = 0, "-", 0
        elif r < 0.3:
            m = rng.randrange(1, 30) * 10000
            a, at, am = -m, f"({m:,})", m
        else:
            a = b * rng.randrange(50, 125) // 100 // 10000 * 10000
            ast = rng.randrange(5)
            at, am = _unit(a, ast), _misread(a, ast)
        rows.append((name, b, a, _misread(b, bs), am))
        lines.append(f"{name}\t{_unit(b, bs)}\t{at}")
    over = sorted(n for n, b, a, _, _ in rows if a > b)
    rem = sum(b - a for _, b, a, _, _ in rows)
    rem_pos = sum(b - abs(a) for _, b, a, _, _ in rows)
    over_mis = sorted(n for n, _, a, bm, am in rows if (am if a >= 0 else -am) > bm)
    assert over and over != over_mis
    prompt = ("과제별 예산·집행 현황인데 담당자마다 금액을 다르게 적어 보냈어요. 모두 원으로 바꿔서 봐 주세요: '350만원'=3,500,000원, "
              "'3.5백만'=3,500,000원, '₩3,500,000'·'3,500,000원'·'3,500,000'은 그대로 원, 집행액의 '-'는 0원(미집행), "
              "괄호 '(100,000)'은 환입이라 -100,000원입니다.\n\n" + "\n".join(lines) + "\n\n"
              "집행액이 예산을 초과한 프로젝트 목록과, 전체 잔액 합계(각 프로젝트 예산-집행액의 합)를 알려주세요. "
              + JSON_RULE + '{"overrun": ["PJ-00", ...], "remaining_total": 원(정수)}')
    _add("mx_06", "units", prompt, {"overrun": "list", "remaining_total": "int"},
         lambda p: _eq_names(p, "overrun", over) and _eq_num(p, "remaining_total", rem),
         {"overrun": over, "remaining_total": rem},
         [{"overrun": over, "remaining_total": rem_pos}, {"overrun": over_mis, "remaining_total": rem}])


# ================================================================= 3. korean_numbers


def _mx07():
    rng = random.Random(107)
    vendors = ["한빛시스템", "다온건설", "서진정밀", "온누리IT", "청솔인쇄", "가람물산", "미래엔지니어링", "새솔테크"]
    works = ["전산 유지보수", "사옥 리모델링", "설비 교체", "보안 컨설팅", "물류 위탁", "교육 용역", "홍보물 제작", "청소 용역",
             "ERP 고도화", "CCTV 증설"]
    lines = ["No\t계약명\t거래처\t계약금액"]
    rows = []
    for i in range(20):
        n = rng.randrange(8, 650) * 10**6
        v, w = rng.choice(vendors), rng.choice(works)
        r = rng.random()
        if r < 0.2:
            txt = f"{n:,}원"
        elif r < 0.3 and n % 10**7 == 0 and n >= 10**8:
            txt = f"{_dec(n / 10**8)}억"
        else:
            txt = _ko(n, rng)
        rows.append((v, n))
        lines.append(f"{i + 1}\t{w}\t{v}\t{txt}")
    total = sum(n for _, n in rows)
    over2 = sum(1 for _, n in rows if n >= 2 * 10**8)
    big_v = max(rows, key=lambda x: x[1])
    assert sorted(n for _, n in rows)[-1] != sorted(n for _, n in rows)[-2]
    prompt = ("올해 체결 계약 목록인데 금액을 사람마다 다르게 적었어요. 모두 원 단위 금액입니다. 예: '3억 2천만원'=320,000,000원, "
              "'1억2,500만'=125,000,000원, '8,500만원'=85,000,000원, '4.5억'=450,000,000원, '원'이 빠진 것도 원입니다.\n\n"
              + "\n".join(lines) + "\n\n"
              "계약금액 총합, 2억원 이상(2억 포함) 계약 건수, 금액이 가장 큰 계약의 거래처를 알려주세요. "
              + JSON_RULE + '{"total": 원(정수), "count_2eok_plus": 건수(정수), "largest_vendor": 거래처명}')
    _add("mx_07", "korean_numbers", prompt, {"total": "int", "count_2eok_plus": "int", "largest_vendor": "str"},
         lambda p: _eq_num(p, "total", total) and _eq_num(p, "count_2eok_plus", over2)
         and _eq_name(p, "largest_vendor", big_v[0]),
         {"total": total, "count_2eok_plus": over2, "largest_vendor": big_v[0]},
         [{"total": total // 10**4, "count_2eok_plus": over2, "largest_vendor": big_v[0]},
          {"total": total, "count_2eok_plus": over2 + 2, "largest_vendor": big_v[0]}])


def _mx08():
    rng = random.Random(108)
    people = ["김민수", "이서연", "박지훈", "최유진", "정다은"]
    what = ["커피", "점심", "택시", "문구", "복사", "주차", "간식", "퀵"]
    lines = []
    rows = []
    for i in range(30):
        who = rng.choice(people)
        n = rng.choice([rng.randrange(2, 20) * 500, rng.randrange(20, 300) * 500, rng.randrange(20, 40) * 500])
        r = rng.random()
        if r < 0.25:
            txt = f"{n:,}원"
        else:
            txt = _ko(n, rng)
        rows.append((who, n))
        lines.append(f"{who} {rng.choice(what)} {txt}")
    per = defaultdict(int)
    for w, n in rows:
        per[w] += n
    top, top_amt = _argmax(per)
    grand = sum(per.values())
    prompt = ("팀 단톡방에 각자 올린 소액 경비를 그대로 긁어왔어요. 한 줄에 '이름 내용 금액'입니다. 금액은 모두 원이고 "
              "'원'이 빠진 것도 원으로 봅니다. 예: '5천'=5,000원, '12만 3천원'=123,000원, '만2천원'=12,000원, "
              "'3천5백'=3,500원, '4만5백원'=40,500원.\n\n" + "\n".join(lines) + "\n\n"
              "가장 많이 쓴 사람과 그 사람의 합계, 그리고 전체 합계를 알려주세요. "
              + JSON_RULE + '{"top_person": 이름, "top_total": 원(정수), "grand_total": 원(정수)}')
    wrong_man = sum(n - 10000 if 10000 <= n < 20000 else n for _, n in rows)
    _add("mx_08", "korean_numbers", prompt, {"top_person": "str", "top_total": "int", "grand_total": "int"},
         lambda p: _eq_name(p, "top_person", top) and _eq_num(p, "top_total", top_amt) and _eq_num(p, "grand_total", grand),
         {"top_person": top, "top_total": top_amt, "grand_total": grand},
         [{"top_person": top, "top_total": top_amt, "grand_total": wrong_man},
          {"top_person": top, "top_total": top_amt // 1000, "grand_total": grand // 1000}])


def _mx09():
    rng = random.Random(109)
    lines = ["차수\t지급예정일\t금액\t상태"]
    rows = []
    for i in range(16):
        n = rng.randrange(30, 2500) * 10**5
        paid = i < 9 and rng.random() < 0.85
        txt = f"금 {_hangul(n)}원정" if rng.random() < 0.75 else f"{n:,}원"
        rows.append((n, paid))
        lines.append(f"{i + 1}차\t{2026 + i // 12}-{(i % 12) + 1:02d}-25\t{txt}\t{'지급완료' if paid else '미지급'}")
    unpaid = sum(n for n, p in rows if not p)
    paid = sum(n for n, p in rows if p)
    prompt = ("공사 기성금 지급 일정표예요. 계약서 양식 그대로 금액이 한글로 적힌 줄이 많아요. '금 일억이천삼백만원정'은 "
              "123,000,000원, '금 천오백오십만원정'은 15,500,000원, '금 이천삼백사십만원정'은 23,400,000원처럼 읽으면 됩니다.\n\n"
              + "\n".join(lines) + "\n\n"
              "아직 지급되지 않은(미지급) 금액의 합계와 지급완료 금액의 합계를 알려주세요. "
              + JSON_RULE + '{"unpaid_total": 원(정수), "paid_total": 원(정수)}')
    _add("mx_09", "korean_numbers", prompt, {"unpaid_total": "int", "paid_total": "int"},
         lambda p: _eq_num(p, "unpaid_total", unpaid) and _eq_num(p, "paid_total", paid),
         {"unpaid_total": unpaid, "paid_total": paid},
         [{"unpaid_total": paid, "paid_total": unpaid}, {"unpaid_total": unpaid + paid, "paid_total": paid},
          {"unpaid_total": unpaid // 10**4, "paid_total": paid // 10**4}])


# ================================================================= 4. merged_cells


def _mx10():
    rng = random.Random(110)
    depts = [("영업부", 6), ("생산부", 7), ("총무부", 3), ("연구소", 5), ("구매부", 4), ("품질부", 5)]
    items = ["교통비", "식대", "소모품", "도서", "교육비", "통신비", "회의비"]
    pool = iter(NAMES * 3)
    lines = ["부서\t성명\t항목\t금액"]
    rows = []
    for d, k in depts:
        for j in range(k):
            nm, it, n = next(pool), rng.choice(items), rng.randrange(10, 900) * 1000
            rows.append((d, n, j == 0))
            lines.append(f"{d if j == 0 else ''}\t{nm}\t{it}\t{n:,}")
    per = defaultdict(int)
    for d, n, _ in rows:
        per[d] += n
    top, amt = _argmax(per)
    prod_cnt = sum(1 for d, _, _ in rows if d == "생산부")
    unf = defaultdict(int)
    for d, n, first in rows:
        if first:
            unf[d] += n
    utop, uamt = max(unf.items(), key=lambda x: x[1])
    prompt = ("부서별 경비 청구 피벗을 복사했더니 부서 칸이 병합돼 있던 게 풀려서, 부서 이름이 각 부서 첫 줄에만 있고 그 아래는 "
              "비어 있어요. 빈 부서 칸은 바로 위와 같은 부서입니다. 금액은 원.\n\n" + "\n".join(lines) + "\n\n"
              "청구 합계가 가장 큰 부서와 그 합계, 그리고 생산부 청구 건수를 알려주세요. "
              + JSON_RULE + '{"top_dept": 부서명, "top_total": 원(정수), "production_count": 건수(정수)}')
    _add("mx_10", "merged_cells", prompt, {"top_dept": "str", "top_total": "int", "production_count": "int"},
         lambda p: _eq_name(p, "top_dept", top) and _eq_num(p, "top_total", amt) and _eq_num(p, "production_count", prod_cnt),
         {"top_dept": top, "top_total": amt, "production_count": prod_cnt},
         [{"top_dept": utop, "top_total": uamt, "production_count": 1},
          {"top_dept": top, "top_total": amt, "production_count": 1}])


def _mx11():
    rng = random.Random(111)
    tree = [("북부", ["의정부", "파주", "고양"]), ("남부", ["수원", "용인", "평택", "안성"]), ("동부", ["남양주", "구리"])]
    lines = ["권역\t지점\t월\t매출"]
    rows = []
    for reg, brs in tree:
        for bi, b in enumerate(brs):
            for mi, m in enumerate(["7월", "8월", "9월"]):
                n = rng.randrange(1500, 9000) * 10000
                rows.append((reg, b, m, n, bi == 0 and mi == 0, mi == 0))
                r_txt = reg if (bi == 0 and mi == 0) else ""
                b_txt = b if mi == 0 else ""
                lines.append(f"{r_txt}\t{b_txt}\t{m}\t{n:,}")
    south9 = sum(n for r, _, m, n, _, _ in rows if r == "남부" and m == "9월")
    per = defaultdict(int)
    for _, b, _, n, _, _ in rows:
        per[b] += n
    top, amt = _argmax(per)
    south9_unf = sum(n for r, _, m, n, rf, _ in rows if r == "남부" and m == "9월" and rf)
    unf = defaultdict(int)
    for _, b, _, n, _, bf in rows:
        if bf:
            unf[b] += n
    utop = max(unf.items(), key=lambda x: x[1])
    prompt = ("3분기 지점 매출 보고서를 붙여넣어요. 원래 권역과 지점 칸이 병합 셀이라, 복사하니 권역은 그 권역 첫 줄에만, 지점은 "
              "그 지점 첫 줄(7월)에만 이름이 있고 나머지는 빈 칸이에요. 빈 칸은 위 칸과 같은 값입니다. 매출은 원.\n\n"
              + "\n".join(lines) + "\n\n"
              "남부 권역의 9월 매출 합계와, 3개월 매출 합계가 가장 큰 지점 및 그 합계를 알려주세요. "
              + JSON_RULE + '{"south_sep_total": 원(정수), "top_branch": 지점명, "top_branch_total": 원(정수)}')
    _add("mx_11", "merged_cells", prompt, {"south_sep_total": "int", "top_branch": "str", "top_branch_total": "int"},
         lambda p: _eq_num(p, "south_sep_total", south9) and _eq_name(p, "top_branch", top)
         and _eq_num(p, "top_branch_total", amt),
         {"south_sep_total": south9, "top_branch": top, "top_branch_total": amt},
         [{"south_sep_total": south9_unf, "top_branch": top, "top_branch_total": amt},
          {"south_sep_total": south9, "top_branch": utop[0], "top_branch_total": utop[1]}])


def _mx12():
    rng = random.Random(112)
    cats = [("부품", ["베어링", "볼트 M8", "너트 M8", "기어", "샤프트", "스프링", "패킹"]),
            ("소재", ["강판", "알루미늄봉", "동파이프", "PVC관"]),
            ("완제품", ["펌프 A형", "펌프 B형", "밸브 50A", "밸브 80A", "모터 2HP"]),
            ("소모품", ["절삭유", "장갑", "연마석", "용접봉"])]
    lines = ["\t\t판매수량(개)\t", "분류\t제품\t3분기\t4분기"]
    rows = []
    for c, prods in cats:
        for j, pr in enumerate(prods):
            q3, q4 = rng.randrange(100, 3000), rng.randrange(100, 3000)
            rows.append((c, pr, q3, q4, j == 0))
            lines.append(f"{c if j == 0 else ''}\t{pr}\t{q3:,}\t{q4:,}")
    per = defaultdict(int)
    for c, _, _, q4, _ in rows:
        per[c] += q4
    top, amt = _argmax(per)
    down = sorted(pr for c, pr, q3, q4, _ in rows if c == "부품" and q4 < q3)
    unf = defaultdict(int)
    for c, _, _, q4, f in rows:
        if f:
            unf[c] += q4
    utop = max(unf.items(), key=lambda x: x[1])
    down_unf = [pr for c, pr, q3, q4, f in rows if c == "부품" and f and q4 < q3]
    assert utop[0] != top or down_unf != down
    prompt = ("분류별 판매 수량 피벗표를 복사했어요(탭 구분). 머리글이 두 줄이고, '분류'는 병합 셀이었어서 각 분류의 첫 제품 줄에만 "
              "적혀 있습니다. 분류 칸이 비어 있으면 위 줄과 같은 분류예요.\n\n" + "\n".join(lines) + "\n\n"
              "4분기 판매수량 합계가 가장 큰 분류와 그 수량, 그리고 '부품' 분류 중 4분기가 3분기보다 줄어든 제품 목록을 알려주세요. "
              + JSON_RULE + '{"top_category": 분류명, "top_q4_qty": 개수(정수), "parts_decreased": [제품명, ...]}')
    _add("mx_12", "merged_cells", prompt, {"top_category": "str", "top_q4_qty": "int", "parts_decreased": "list"},
         lambda p: _eq_name(p, "top_category", top) and _eq_num(p, "top_q4_qty", amt)
         and _eq_names(p, "parts_decreased", down),
         {"top_category": top, "top_q4_qty": amt, "parts_decreased": down},
         [{"top_category": utop[0], "top_q4_qty": utop[1], "parts_decreased": down_unf},
          {"top_category": top, "top_q4_qty": amt, "parts_decreased": down_unf}])


# ================================================================= 5. dirty_rows


def _mx13():
    rng = random.Random(113)
    variants = {"한빛": ["(주)한빛", "한빛", "㈜한빛 ", "주식회사 한빛", "한빛 "],
                "다온상사": ["다온상사", "(주)다온상사", "다온상사  "],
                "서진정밀": ["서진정밀", "㈜서진정밀", " 서진정밀"],
                "가람물산": ["가람물산", "가람물산(주)"],
                "새솔테크": ["새솔테크"]}
    recs = []
    for i in range(24):
        v = rng.choice(list(variants))
        recs.append((f"V26-{1001 + i}", v, rng.randrange(5, 500) * 10000))
    out = []
    for r in recs:
        out.append(r)
        if rng.random() < 0.2:
            out.append(r)
    dup_n = len(out) - len(recs)
    assert dup_n >= 3
    lines = ["전표번호\t거래처\t지급액"]
    shown = set()
    for k, (no, v, n) in enumerate(out):
        if k in (6, 17):
            lines.append("")
        if k == 10:
            lines.append("※ 아래부터 9월 후반분 (박과장 확인 중) — 메모 줄")
        if k == 20:
            lines.append("# 중복 있을 수 있음, 확인 바람")
        vt = rng.choice(variants[v])
        shown.add(vt.strip())
        lines.append(f"{no} \t{vt}\t{n:,}{rng.choice(['', ' ', '  '])}")
    hb = sum(n for _, v, n in recs if v == "한빛")
    hb_dup = sum(n for _, v, n in out if v == "한빛")
    nv = len({v for _, v, _ in recs})
    raw_v = len(shown)
    assert raw_v != nv
    cnt = len(recs)
    prompt = ("9월 거래처 지급 내역을 메신저로 받은 걸 붙여요. 정리가 안 돼 있어요. 규칙: 전표번호가 같은 줄은 같은 건이 중복으로 "
              "붙은 것이니 한 번만 셉니다. 회사 이름 앞이나 뒤에 붙은 '(주)', '㈜', '주식회사'와 앞뒤 공백은 무시하고 같은 회사로 봅니다"
              "(예: '(주)한빛', '한빛', '㈜한빛 '은 모두 한빛). '※'나 '#'로 시작하는 줄은 메모라 데이터가 아니고, 빈 줄도 무시하세요.\n\n"
              + "\n".join(lines) + "\n\n"
              "한빛에 지급한 총액, 실제 지급 건수(중복 제외), 서로 다른 거래처 수를 알려주세요. "
              + JSON_RULE + '{"hanbit_total": 원(정수), "payment_count": 건수(정수), "vendor_count": 개수(정수)}')
    _add("mx_13", "dirty_rows", prompt, {"hanbit_total": "int", "payment_count": "int", "vendor_count": "int"},
         lambda p: _eq_num(p, "hanbit_total", hb) and _eq_num(p, "payment_count", cnt) and _eq_num(p, "vendor_count", nv),
         {"hanbit_total": hb, "payment_count": cnt, "vendor_count": nv},
         [{"hanbit_total": hb_dup if hb_dup != hb else hb + 1, "payment_count": cnt + dup_n, "vendor_count": nv},
          {"hanbit_total": hb, "payment_count": cnt, "vendor_count": raw_v}])


def _mx14():
    rng = random.Random(214)
    courses = ["엑셀 실무", "보고서 작성", "정보보안 기초", "리더십"]
    people = [(f"2{rng.randrange(10000, 99999)}", nm) for nm in rng.sample(NAMES, 18)]
    signups = []
    for sid, nm in people:
        for c in rng.sample(courses, rng.choice([1, 1, 2, 2, 3])):
            signups.append((sid, nm, c))
    rng.shuffle(signups)
    out = []
    for s in signups:
        out.append(s)
        if rng.random() < 0.18:
            out.append(s)
    lines = ["사번,이름,신청과정"]
    for k, (sid, nm, c) in enumerate(out):
        if k in (5, 19, 30):
            lines.append("")
        if k == 12:
            lines.append("// 여기부터 2차 접수분")
        nm_t = rng.choice([nm, nm + " ", " " + nm, nm[0] + " " + nm[1:]])
        lines.append(f"{sid},{nm_t},{c}{rng.choice(['', ' '])}")
    per = defaultdict(set)
    for sid, _, c in signups:
        per[c].add(sid)
    top, amt = _argmax({c: len(s) for c, s in per.items()})
    uniq = len({sid for sid, _, _ in signups})
    rawc = defaultdict(int)
    for _, _, c in out:
        rawc[c] += 1
    assert rawc[top] != amt
    prompt = ("사내 교육 신청 명단을 설문 결과에서 그대로 복사했어요(쉼표 구분). 같은 사람이 같은 과정을 두 번 제출한 줄이 있는데 "
              "사번이 같으면 같은 사람이고, 같은 사람의 같은 과정 신청은 한 번만 셉니다. 이름에 공백이 들쭉날쭉한 건 무시하세요. "
              "'//'로 시작하는 줄은 메모, 빈 줄은 무시합니다.\n\n" + "\n".join(lines) + "\n\n"
              "신청 인원이 가장 많은 과정과 그 인원, 그리고 한 과정 이상 신청한 전체 인원(서로 다른 사번 수)을 알려주세요. "
              + JSON_RULE + '{"top_course": 과정명, "top_count": 명(정수), "unique_people": 명(정수)}')
    _add("mx_14", "dirty_rows", prompt, {"top_course": "str", "top_count": "int", "unique_people": "int"},
         lambda p: _eq_name(p, "top_course", top) and _eq_num(p, "top_count", amt) and _eq_num(p, "unique_people", uniq),
         {"top_course": top, "top_count": amt, "unique_people": uniq},
         [{"top_course": top, "top_count": rawc[top], "unique_people": uniq},
          {"top_course": top, "top_count": amt, "unique_people": len(signups)}])


def _mx15():
    rng = random.Random(115)
    items = {"A4용지": ["A4용지", "A4 용지", "a4용지", "A4 용지 ", "a4 용지"],
             "토너": ["토너", "토너 ", " 토너"],
             "볼펜": ["볼펜", "볼 펜"],
             "포스트잇": ["포스트잇", "포스트 잇", "포스트잇 "],
             "클리어파일": ["클리어파일", "클리어 파일"],
             "스테이플러심": ["스테이플러심", "스테이플러 심"]}
    recs = []
    for i in range(26):
        it = rng.choice(list(items))
        recs.append((f"IN-{501 + i}", it, rng.randrange(1, 60)))
    out = []
    for r in recs:
        out.append(r)
        if rng.random() < 0.2:
            out.append(r)
    lines = ["입고번호 | 품목 | 수량"]
    for k, (no, it, q) in enumerate(out):
        if k in (4, 15):
            lines.append("")
        if k == 9:
            lines.append("(메모) 2창고 재고실사 후 다시 맞춰볼 것")
        lines.append(f"{no} | {rng.choice(items[it])} | {q}{rng.choice(['', '개', ' 개'])}")
    a4 = sum(q for _, it, q in recs if it == "A4용지")
    a4_dup = sum(q for _, it, q in out if it == "A4용지")
    per = defaultdict(int)
    for _, it, q in recs:
        per[it] += q
    top, amt = _argmax(per)
    prompt = ("비품 입고 기록을 여러 사람이 이어 붙인 메모입니다. 규칙: 입고번호가 같은 줄은 같은 입고가 두 번 붙은 것이니 한 번만 "
              "셉니다. 품목명은 띄어쓰기·대소문자·앞뒤 공백을 무시하고 같은 품목으로 봅니다(예: 'A4 용지'와 'a4용지'는 같은 품목). "
              "'(메모)'로 시작하는 줄과 빈 줄은 데이터가 아닙니다. 수량 뒤 '개'는 단위일 뿐입니다.\n\n"
              + "\n".join(lines) + "\n\n"
              "A4용지 총 입고 수량, 서로 다른 품목 수, 총 입고 수량이 가장 많은 품목을 알려주세요. "
              + JSON_RULE + '{"a4_qty": 개수(정수), "item_kinds": 개수(정수), "top_item": 품목명}')
    _add("mx_15", "dirty_rows", prompt, {"a4_qty": "int", "item_kinds": "int", "top_item": "str"},
         lambda p: _eq_num(p, "a4_qty", a4) and _eq_num(p, "item_kinds", len(per)) and _eq_name(p, "top_item", top),
         {"a4_qty": a4, "item_kinds": len(per), "top_item": top},
         [{"a4_qty": a4_dup if a4_dup != a4 else a4 + 1, "item_kinds": len(per), "top_item": top},
          {"a4_qty": a4, "item_kinds": len(per) + 8, "top_item": top}])


# ================================================================= 6. no_table_prose


def _mx16():
    rng = random.Random(116)
    cats = ["식대", "교통비", "소모품비", "접대비"]
    tmpl = ["{p}님은 {c}로 {a}을 쓰셨습니다.", "{p} 쪽에서 {c} {a}이 나갔습니다.", "그리고 {c}는 {p}님이 {a} 결제했어요.",
            "{p}님 {c} 건이 {a}입니다.", "{c} 명목으로 {p}님이 {a}을 썼습니다."]
    sents, rows = [], []
    for i in range(16):
        p, c = rng.choice(NAMES[:8]), rng.choice(cats)
        n = rng.randrange(1, 60) * 5000
        a = rng.choice([f"{n:,}원", _ko(n, rng, won="원")])
        canceled = rng.random() < 0.2
        s = rng.choice(tmpl).format(p=p, c=c, a=a)
        if canceled:
            s += " 이 건은 나중에 결제 취소됐습니다."
        rows.append((c, n, canceled))
        sents.append(s)
        if i == 5:
            sents.append("참고로 이번 달 식대 한도는 1인당 30만원이고, 팀 전체 경비 예산은 300만원입니다.")
        if i == 11:
            sents.append("다음 달에는 접대비를 50만원 이내로 줄이자는 얘기가 나왔습니다.")
    meal = sum(n for c, n, x in rows if c == "식대" and not x)
    big = sum(1 for _, n, x in rows if n >= 100000 and not x)
    total = sum(n for _, n, x in rows if not x)
    meal_all = sum(n for c, n, x in rows if c == "식대")
    assert meal_all != meal
    prompt = ("어제 팀 회의록 중 경비 얘기한 부분이에요. 표는 없고 말로만 정리돼 있어요. 실제로 쓴 지출만 세고, '결제 취소됐다'는 건은 "
              "빼 주세요. 한도·예산·목표처럼 앞으로의 기준 금액은 지출이 아닙니다. 금액은 모두 원입니다.\n\n"
              + " ".join(sents) + "\n\n"
              "취소 건을 뺀 식대 합계, 10만원 이상(10만원 포함)인 지출 건수, 전체 지출 합계를 알려주세요. "
              + JSON_RULE + '{"meal_total": 원(정수), "over_100k_count": 건수(정수), "total": 원(정수)}')
    _add("mx_16", "no_table_prose", prompt, {"meal_total": "int", "over_100k_count": "int", "total": "int"},
         lambda p: _eq_num(p, "meal_total", meal) and _eq_num(p, "over_100k_count", big) and _eq_num(p, "total", total),
         {"meal_total": meal, "over_100k_count": big, "total": total},
         [{"meal_total": meal_all, "over_100k_count": big, "total": sum(n for _, n, _ in rows)},
          {"meal_total": meal, "over_100k_count": big, "total": total + 3_000_000 + 300_000 + 500_000}])


def _mx17():
    rng = random.Random(117)
    branches = ["부산지점", "대구지점", "광주지점", "대전지점", "인천지점", "울산지점"]
    sents, data, naive = [], {}, {}
    for b in branches:
        m = [rng.randrange(1500, 6000) * 10**5 for _ in range(3)]
        data[b] = m
        f = lambda n: rng.choice([f"{n // 10**4:,}만원", _ko(n, rng, won="원"), f"{n:,}원"])
        mode = rng.randrange(3)
        nv = list(m)
        if mode == 1:
            nv[1] = abs(m[1] - m[0])
        elif mode == 2:
            nv[2] = abs(m[2] - m[1])
        naive[b] = nv
        if mode == 0:
            sents.append(f"{b}은 7월 {f(m[0])}, 8월 {f(m[1])}, 9월 {f(m[2])}을 기록했습니다.")
        elif mode == 1:
            d = m[1] - m[0]
            word = "늘어난" if d > 0 else "줄어든"
            sents.append(f"{b}의 7월 매출은 {f(m[0])}이었고 8월은 그보다 {f(abs(d))} {word} 수준이었으며, 9월은 {f(m[2])}였습니다.")
        else:
            d = m[2] - m[1]
            word = "증가" if d > 0 else "감소"
            sents.append(f"{b}은 8월에 {f(m[1])}로 7월({f(m[0])})보다 나았다는 평가인데, 9월에는 8월 대비 {f(abs(d))} {word}했습니다."
                         if m[1] > m[0] else
                         f"{b}은 8월에 {f(m[1])}로 7월({f(m[0])})보다 부진했고, 9월에는 8월 대비 {f(abs(d))} {word}했습니다.")
        if b == "광주지점":
            sents.append("참고로 연간 목표는 지점당 20억원입니다.")
    per = {b: sum(m) for b, m in data.items()}
    top, amt = _argmax(per)
    aug = sum(m[1] for m in data.values())
    prompt = ("3분기 영업회의 발언을 받아 적은 메모입니다. 지점별 월 매출이 문장으로만 있어요. '그보다 X 늘어난/줄어든', "
              "'8월 대비 X 증가/감소' 같은 표현은 해당 월 매출을 그 차이로 계산하면 됩니다. 목표 금액은 실적이 아닙니다.\n\n"
              + "\n".join(sents) + "\n\n"
              "7~9월 매출 합계가 가장 큰 지점과 그 합계, 그리고 6개 지점의 8월 매출 합계를 알려주세요. "
              + JSON_RULE + '{"top_branch": 지점명, "top_total": 원(정수), "aug_total": 원(정수)}')
    n_top, n_amt = _argmax({b: sum(v) for b, v in naive.items()})
    n_aug = sum(v[1] for v in naive.values())
    assert (n_top, n_amt, n_aug) != (top, amt, aug) and n_aug != aug
    _add("mx_17", "no_table_prose", prompt, {"top_branch": "str", "top_total": "int", "aug_total": "int"},
         lambda p: _eq_name(p, "top_branch", top) and _eq_num(p, "top_total", amt) and _eq_num(p, "aug_total", aug),
         {"top_branch": top, "top_total": amt, "aug_total": aug},
         [{"top_branch": n_top, "top_total": n_amt, "aug_total": n_aug},
          {"top_branch": top, "top_total": amt, "aug_total": n_aug},
          {"top_branch": top, "top_total": amt // 10**4, "aug_total": aug // 10**4}])


def _mx18():
    rng = random.Random(218)
    items = ["볼트 M8", "너트 M8", "와셔 8mm", "베어링 6204", "오링 P20", "케이블타이", "절연테이프", "용접봉 3.2",
             "그라인더날", "장갑(코팅)", "방진마스크", "절삭유 4L"]
    sents, rows = [], []
    for it in items:
        cur, safe = rng.randrange(0, 3000), rng.randrange(200, 2500)
        r = rng.random()
        if r < 0.3:
            add = rng.randrange(1, 10) * 100
            sents.append(f"{_eun(it)} 오늘 아침 기준 {cur - add if cur >= add else cur:,}개였는데 오후에 {add:,}개가 추가 입고됐고, "
                         f"안전재고는 {safe:,}개로 잡혀 있습니다.")
            if cur < add:
                cur = cur + add
        elif r < 0.5:
            used = rng.randrange(1, 5) * 100
            cur0 = cur + used
            sents.append(f"{it} 재고는 {cur0:,}개였다가 오늘 라인에 {used:,}개가 불출됐어요. 안전재고 기준은 {safe:,}개.")
        else:
            sents.append(f"{_eun(it)} 현재 {cur:,}개 남아 있고 안전재고는 {safe:,}개입니다.")
        rows.append((it, cur, safe))
    below = sorted(it for it, c, s in rows if c < s)
    short = sum(s - c for _, c, s in rows if c < s)
    assert below
    prompt = ("자재 담당자가 메신저로 보낸 재고 현황입니다. 표가 없어서 문장에서 읽어야 해요. 입고는 더하고 불출은 빼서 지금 재고를 "
              "구하세요. 현재 재고가 안전재고보다 적으면(같으면 제외) 부족 품목이고, 부족 수량은 안전재고-현재고입니다.\n\n"
              + "\n".join(sents) + "\n\n"
              "부족 품목 목록과 부족 수량 합계를 알려주세요. "
              + JSON_RULE + '{"below_safety": [품목명, ...], "shortage_total": 개수(정수)}')
    # naive: take the first number in each sentence as current stock
    naive = []
    for (it, c, s), sent in zip(rows, sents):
        first = int(re.search(r"([\d,]+)개", sent)[1].replace(",", ""))
        naive.append((it, first, s))
    nb = sorted(it for it, c, s in naive if c < s)
    ns = sum(s - c for _, c, s in naive if c < s)
    assert (nb, ns) != (below, short)
    _add("mx_18", "no_table_prose", prompt, {"below_safety": "list", "shortage_total": "int"},
         lambda p: _eq_names(p, "below_safety", below) and _eq_num(p, "shortage_total", short),
         {"below_safety": below, "shortage_total": short},
         [{"below_safety": nb, "shortage_total": ns}, {"below_safety": below, "shortage_total": ns if ns != short else short + 1}])


# ================================================================= 7. multi_table


def _mx19():
    rng = random.Random(119)
    prices = {f"P-{10 + i}": (nm, rng.randrange(5, 200) * 100) for i, nm in
              enumerate(["A4용지(박스)", "토너", "볼펜(12입)", "파일철", "포스트잇", "USB 32GB", "마우스", "건전지(AA)"])}
    customers = ["가나상사", "다온유통", "라온마트", "바른오피스", "새길문구"]
    vip = ["가나상사", "라온마트"]
    orders = []
    for i in range(24):
        orders.append((f"O-{2001 + i}", rng.choice(customers), rng.choice(list(prices)), rng.choice([rng.randrange(5, 49), rng.randrange(50, 150)])))
    o_lines = ["[주문]", "주문번호\t고객\t품목코드\t수량"] + [f"{a}\t{b}\t{c}\t{d}" for a, b, c, d in orders]
    p_lines = ["[단가표]", "품목코드\t품명\t단가(원)"] + [f"{k}\t{nm}\t{p:,}" for k, (nm, p) in prices.items()]
    r_lines = ["[할인 규칙]", "1) 한 주문의 수량이 50개 이상이면 그 주문 10% 할인",
               f"2) VIP 고객({', '.join(vip)})은 모든 주문 5% 할인", "3) 두 할인이 겹치면 할인율을 더한다(15%)",
               "4) 주문별 금액 = 수량×단가×(1-할인율), 원 미만 버림"]

    def amt(o, use_q=True, use_v=True):
        _, c, k, q = o
        r = (10 if use_q and q >= 50 else 0) + (5 if use_v and c in vip else 0)
        return q * prices[k][1] * (100 - r) // 100
    tgt = "라온마트"
    t_c = sum(amt(o) for o in orders if o[1] == tgt)
    t_all = sum(amt(o) for o in orders)
    prompt = ("주문 목록, 단가표, 할인 규칙을 한꺼번에 붙여넣을게요. 주문의 품목코드로 단가표를 찾아 금액을 계산하고 할인 규칙을 "
              "적용해 주세요.\n\n" + "\n".join(o_lines) + "\n\n" + "\n".join(p_lines) + "\n\n" + "\n".join(r_lines) + "\n\n"
              f"{tgt}의 할인 후 주문금액 합계와, 전체 주문의 할인 후 금액 합계를 알려주세요. "
              + JSON_RULE + '{"customer_total": 원(정수), "grand_total": 원(정수)}')
    _add("mx_19", "multi_table", prompt, {"customer_total": "int", "grand_total": "int"},
         lambda p: _eq_num(p, "customer_total", t_c) and _eq_num(p, "grand_total", t_all),
         {"customer_total": t_c, "grand_total": t_all},
         [{"customer_total": sum(amt(o, False, False) for o in orders if o[1] == tgt),
           "grand_total": sum(amt(o, False, False) for o in orders)},
          {"customer_total": sum(amt(o, True, False) for o in orders if o[1] == tgt),
           "grand_total": sum(amt(o, True, False) for o in orders)}])


def _mx20():
    rng = random.Random(120)
    depts = {"D10": "경영지원팀", "D20": "영업1팀", "D30": "영업2팀", "D40": "생산기술팀", "D50": "연구개발팀"}
    emps = [(f"E{301 + i}", nm, rng.choice(list(depts))) for i, nm in enumerate(rng.sample(NAMES, 15))]
    claims = [(rng.choice(emps)[0], f"10/{rng.randrange(1, 31):02d}", rng.randrange(1, 80) * 5000) for _ in range(30)]
    e_lines = ["== 직원 ==", "사번 | 이름 | 부서코드"] + [f"{a} | {b} | {c}" for a, b, c in emps]
    d_lines = ["== 부서 ==", "부서코드 | 부서명"] + [f"{k} | {v}" for k, v in depts.items()]
    c_lines = ["== 경비 청구 ==", "사번 | 청구일 | 금액"] + [f"{a} | {b} | {c:,}" for a, b, c in claims]
    edept = {e: d for e, _, d in emps}
    per = defaultdict(int)
    for e, _, n in claims:
        per[depts[edept[e]]] += n
    top, amt = _argmax(per)
    cnt = sum(1 for e, _, _ in claims if depts[edept[e]] == "영업2팀")
    prompt = ("인사 명단, 부서 코드표, 10월 경비 청구 목록을 따로따로 뽑아서 붙였어요. 청구는 사번으로 직원을, 직원은 부서코드로 "
              "부서명을 찾아 연결하면 됩니다. 금액은 원.\n\n" + "\n".join(e_lines) + "\n\n" + "\n".join(d_lines) + "\n\n"
              + "\n".join(c_lines) + "\n\n"
              "청구 금액 합계가 가장 큰 부서명과 그 합계, 그리고 영업2팀의 청구 건수를 알려주세요. "
              + JSON_RULE + '{"top_dept": 부서명, "top_total": 원(정수), "sales2_count": 건수(정수)}')
    wrong_code = _argmax({k: sum(n for e, _, n in claims if edept[e] == k) for k in depts})
    _add("mx_20", "multi_table", prompt, {"top_dept": "str", "top_total": "int", "sales2_count": "int"},
         lambda p: _eq_name(p, "top_dept", top) and _eq_num(p, "top_total", amt) and _eq_num(p, "sales2_count", cnt),
         {"top_dept": top, "top_total": amt, "sales2_count": cnt},
         [{"top_dept": wrong_code[0], "top_total": amt, "sales2_count": cnt},
          {"top_dept": top, "top_total": amt, "sales2_count": cnt + 2}])


def _mx21():
    rng = random.Random(121)
    weights = {"냉장고": 70, "세탁기": 60, "전자레인지": 12, "청소기": 6, "공기청정기": 9, "TV 55인치": 20}
    rates = {"수도권": (8000, 300), "강원": (12000, 450), "영남": (11000, 400), "호남": (11000, 420), "제주": (25000, 900)}
    ships = [(f"S-{701 + i}", rng.choice(list(weights)), rng.randrange(1, 12), rng.choice(list(rates))) for i in range(22)]
    s_lines = ["<출고>", "출고번호\t품목\t수량\t지역"] + [f"{a}\t{b}\t{c}\t{d}" for a, b, c, d in ships]
    w_lines = ["<품목 중량>", "품목\t개당 중량(kg)"] + [f"{k}\t{v}" for k, v in weights.items()]
    r_lines = ["<운임표>", "지역\t건당 기본료(원)\tkg당 요금(원)"] + [f"{k}\t{a:,}\t{b:,}" for k, (a, b) in rates.items()]

    def cost(s, base=True):
        _, it, q, rg = s
        return (rates[rg][0] if base else 0) + rates[rg][1] * q * weights[it]
    total = sum(cost(s) for s in ships)
    per = defaultdict(int)
    for s in ships:
        per[s[3]] += cost(s)
    top, amt = _argmax(per)
    no_qty = sum(rates[s[3]][0] + rates[s[3]][1] * weights[s[1]] for s in ships)
    prompt = ("출고 목록, 품목별 중량표, 지역별 운임표 세 개를 붙입니다. 출고 한 건의 운임 = 그 지역 건당 기본료 + kg당 요금 × "
              "(수량 × 개당 중량)입니다. 기본료는 출고 건마다 한 번씩 붙습니다.\n\n" + "\n".join(s_lines) + "\n\n"
              + "\n".join(w_lines) + "\n\n" + "\n".join(r_lines) + "\n\n"
              "전체 운임 합계와, 운임 합계가 가장 큰 지역 및 그 금액을 알려주세요. "
              + JSON_RULE + '{"freight_total": 원(정수), "top_region": 지역명, "top_region_total": 원(정수)}')
    _add("mx_21", "multi_table", prompt, {"freight_total": "int", "top_region": "str", "top_region_total": "int"},
         lambda p: _eq_num(p, "freight_total", total) and _eq_name(p, "top_region", top) and _eq_num(p, "top_region_total", amt),
         {"freight_total": total, "top_region": top, "top_region_total": amt},
         [{"freight_total": sum(cost(s, False) for s in ships), "top_region": top, "top_region_total": amt},
          {"freight_total": no_qty, "top_region": top, "top_region_total": amt}])


# ================================================================= 8. markdown_or_pipe


def _mx22():
    rng = random.Random(122)
    rows = []
    for i in range(18):
        b = rng.randrange(500, 6000)
        act = None if rng.random() < 0.25 else b * rng.randrange(40, 115) // 100
        rows.append([f"P-{i + 1:02d}", rng.choice(["ERP", "그룹웨어", "보안", "MES", "BI", "CRM"]) + f" {rng.choice(['고도화', '구축', '유지보수', '전환'])}", b, act])
    # footnote target: an executed project whose revised budget flips the overrun status
    tgt = next(r for r in rows if r[3] is not None and r[3] < r[2] and r[3] > 600)
    new_b = (tgt[3] * 9 // 10) // 100 * 100
    lines = ["| 코드 | 과제명 | 예산(만원) | 실적(만원) | 비고 |", "|:---|:---|---:|---:|:--:|"]
    for code, nm, b, a in rows:
        mark = "*" if code == tgt[0] else ""
        lines.append(f"| {code}{mark} | {nm} | {b:,} | {'' if a is None else f'{a:,}'} | {rng.choice(['', '', '계속', '신규'])} |")
    note = f"\n\n\\* {tgt[0]} 예산은 10/5 이사회에서 {new_b:,}만원으로 감액 확정(표의 금액은 변경 전)."
    eff = {code: (new_b if code == tgt[0] else b) for code, _, b, _ in rows}
    budget = sum(eff.values()) * 10000
    empty = sum(1 for r in rows if r[3] is None)
    over = sum(1 for code, _, b, a in rows if a is not None and a > eff[code])
    over_old = sum(1 for code, _, b, a in rows if a is not None and a > b)
    assert over != over_old
    prompt = ("과제별 예산 현황 마크다운 표를 위키에서 복사했어요. 금액 단위는 만원입니다. 실적 칸이 비어 있으면 아직 실적이 없는 것(0)이고, "
              "비고 칸은 계산과 무관합니다. 표 아래 각주가 표의 값을 바꾸니 각주를 반영하세요.\n\n" + "\n".join(lines) + note + "\n\n"
              "각주 반영 후 예산 총액(원 단위로 환산), 실적이 비어 있는 과제 수, 실적이 예산을 초과한 과제 수를 알려주세요. "
              + JSON_RULE + '{"budget_total_won": 원(정수), "empty_count": 개수(정수), "overrun_count": 개수(정수)}')
    _add("mx_22", "markdown_or_pipe", prompt, {"budget_total_won": "int", "empty_count": "int", "overrun_count": "int"},
         lambda p: _eq_num(p, "budget_total_won", budget) and _eq_num(p, "empty_count", empty)
         and _eq_num(p, "overrun_count", over),
         {"budget_total_won": budget, "empty_count": empty, "overrun_count": over},
         [{"budget_total_won": sum(r[2] for r in rows) * 10000, "empty_count": empty, "overrun_count": over_old},
          {"budget_total_won": budget // 10000, "empty_count": empty, "overrun_count": over}])


def _mx23():
    rng = random.Random(123)
    people = rng.sample(NAMES, 20)
    rows = []
    for nm in people:
        sc = None if rng.random() < 0.2 else rng.randrange(45, 96)
        rows.append([nm, rng.choice(["영업", "생산", "연구", "관리"]), sc])
    takers = [r for r in rows if r[2] is not None]
    top0 = max(r[2] for r in takers)
    fix = next(r for r in takers if r[2] < top0 - 3)
    new = min(100, top0 + 3)
    lines = ["이름 | 부서 | 점수", ":--- | :---: | ---:"]
    for nm, d, sc in rows:
        lines.append(f"{nm}{'¹' if nm == fix[0] else ''} | {d} | {'' if sc is None else sc}")
    eff = {r[0]: (new if r[0] == fix[0] else r[2]) for r in takers}
    n_t = len(eff)
    tot = sum(eff.values())
    top, _ = _argmax(eff)
    old_top = _argmax({r[0]: r[2] for r in takers})[0]
    prompt = ("사내 자격시험 결과를 메일 본문에서 복사했어요(파이프 표, 양끝 파이프 없음). 점수 칸이 비어 있으면 미응시라 응시자에서 "
              "제외합니다. 이름 옆 ¹ 표시는 아래 각주가 적용된다는 뜻입니다.\n\n" + "\n".join(lines) + "\n\n"
              f"¹ {fix[0]} 점수는 재채점 결과 {new}점으로 정정됨.\n\n"
              "응시자 수, 응시자 점수 합계(정정 반영), 최고점자 이름을 알려주세요. "
              + JSON_RULE + '{"takers": 명(정수), "score_sum": 정수, "top_scorer": 이름}')
    _add("mx_23", "markdown_or_pipe", prompt, {"takers": "int", "score_sum": "int", "top_scorer": "str"},
         lambda p: _eq_num(p, "takers", n_t) and _eq_num(p, "score_sum", tot) and _eq_name(p, "top_scorer", top),
         {"takers": n_t, "score_sum": tot, "top_scorer": top},
         [{"takers": n_t, "score_sum": sum(r[2] for r in takers), "top_scorer": old_top},
          {"takers": len(rows), "score_sum": tot, "top_scorer": top}])


def _mx24():
    rng = random.Random(124)
    goods = ["B-01 복사용지", "B-02 토너(흑)", "B-03 토너(컬러)", "B-04 바인더", "B-05 라벨지", "B-06 보드마커", "B-07 수정테이프",
             "B-08 클립", "B-09 스테이플러", "B-10 가위", "B-11 커터칼", "B-12 문서세단기", "B-13 계산기", "B-14 명함케이스",
             "B-15 파일박스", "B-16 데스크매트"]
    rows = []
    for g in goods:
        code, nm = g.split(" ", 1)
        p = rng.randrange(10, 900) * 110
        q = None if rng.random() < 0.25 else rng.randrange(1, 40)
        rows.append([code, nm, p, q])
    tgt = next(r for r in rows if r[0] == "B-12")
    tgt[2] = rng.randrange(150, 400) * 1100
    if tgt[3] is None:
        tgt[3] = rng.randrange(2, 6)
    lines = ["| 코드 | 품명 | 단가(원) | 발주수량 |", "|---|:--:|--:|:--:|"]
    for code, nm, p, q in rows:
        lines.append(f"| {code}{'†' if code == 'B-12' else ''} | {nm} | {p:,} | {'' if q is None else q} |")
    net = {r[0]: (r[2] * 10 // 11 if r[0] == "B-12" else r[2]) for r in rows}
    total = sum(net[r[0]] * r[3] for r in rows if r[3])
    raw = sum(r[2] * r[3] for r in rows if r[3])
    ordered = sum(1 for r in rows if r[3])
    prompt = ("분기 소모품 발주서 초안이에요(마크다운 표). 단가는 부가세 별도 금액이고 발주수량이 빈 칸인 품목은 이번에 발주하지 않습니다. "
              "표 아래 각주를 꼭 반영해 주세요.\n\n" + "\n".join(lines) + "\n\n"
              "† B-12는 다른 업체 견적을 옮겨 적어서 표의 단가가 부가세(10%) 포함 금액임. 부가세 별도 단가 = 표의 단가 ÷ 1.1.\n\n"
              "부가세 별도 기준 발주 총액(수량×단가 합)과 발주하는 품목 수를 알려주세요. "
              + JSON_RULE + '{"order_total": 원(정수), "ordered_items": 개수(정수)}')
    _add("mx_24", "markdown_or_pipe", prompt, {"order_total": "int", "ordered_items": "int"},
         lambda p: _eq_num(p, "order_total", total) and _eq_num(p, "ordered_items", ordered),
         {"order_total": total, "ordered_items": ordered},
         [{"order_total": raw, "ordered_items": ordered}, {"order_total": total, "ordered_items": len(rows)},
          {"order_total": total * 11 // 10, "ordered_items": ordered}])


for _f in (_mx01, _mx02, _mx03, _mx04, _mx05, _mx06, _mx07, _mx08, _mx09, _mx10, _mx11, _mx12,
           _mx13, _mx14, _mx15, _mx16, _mx17, _mx18, _mx19, _mx20, _mx21, _mx22, _mx23, _mx24):
    _f()

assert len(TASKS) == 24 and len({t["id"] for t in TASKS}) == 24
