"""No-tool task set: everything the model needs is pasted into the prompt, one reply.

30 tasks (data 8, doc 6, calc 6, code 5, logic 5). Each task: id, split, domain, prompt
(Korean, states the answer format), tools="none", contract, check(answer, parsed, ws).
Data rows come from fixed-seed random.Random; ground truth is computed at import time from
the same Python values the prompts are rendered from. Logic puzzles are generated from a
hidden solution and pruned until brute force leaves exactly one solution.
Code answers run in a subprocess (python -I) in a fresh temp dir. Standard library only.
"""
import datetime as _dt
import itertools
import random
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

import grade

# ================================================================= helpers

JSON_RULE = "답은 다른 설명 없이 JSON 한 줄로만 주세요: "


def _norm(s):
    """Names: drop spaces, corporate markers, honorifics."""
    s = str(s if s is not None else "")
    for t in ("주식회사", "(주)", "㈜", "（주）"):
        s = s.replace(t, "")
    s = re.sub(r"\s+", "", s)
    return re.sub(r"(씨|님)$", "", s)


def _date(s):
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", str(s or ""))
    return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}" if m else None


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
    return isinstance(v, list) and grade.same_set([_norm(x) for x in v], [_norm(x) for x in expected])


def _eq_codes(p, k, expected):
    v = _get(p, k)
    if not isinstance(v, list):
        return False
    return sorted(re.sub(r"\s+", "", str(x)).upper() for x in v) == sorted(x.upper() for x in expected)


def _ym(s):
    m = re.search(r"(\d{4})\D+(\d{1,2})", str(s or ""))
    return f"{int(m[1]):04d}-{int(m[2]):02d}" if m else None


def _eq_date(p, k, expected):
    return _date(_get(p, k)) == expected


def _json(fn):
    def check(answer, parsed, ws):
        if not isinstance(parsed, dict):
            return False
        try:
            return bool(fn(parsed))
        except Exception:
            return False
    return check


def _csv(header, rows):
    return "\n".join([",".join(header)] + [",".join(str(x) for x in r) for r in rows])


def _task(id, domain, prompt, keys, fn):
    return {"id": id, "split": "notool", "domain": domain, "prompt": prompt, "tools": "none",
            "contract": {"type": "json", "keys": keys}, "check": _json(fn)}


def _unique_top(d):
    s = sorted(d.items(), key=lambda x: -x[1])
    assert len(s) < 2 or s[0][1] != s[1][1], "tie at the top"
    return s


tasks = []

# ================================================================= data

# ---- nt_01 vouchers: Sept 2026 pending, per dept max (2025 rows are distractors)
_r = random.Random(101)
_DEPTS = ["영업팀", "마케팅팀", "구매팀", "생산팀", "인사팀", "재무팀"]
_raw = []
for i in range(50):
    if i % 7 == 3:
        y, m = 2025, 9
    else:
        y, m = 2026, _r.choice([8, 9, 9, 9, 10])
    _raw.append((_dt.date(y, m, _r.randint(1, 30)), _r.choice(_DEPTS),
                 _r.randrange(30_000, 2_500_000, 10), _r.choice(["승인", "승인", "미결", "미결", "반려"])))
_raw.sort(key=lambda x: x[0])
D01_ROWS = [(f"EV-{1001 + i}", d.isoformat(), dp, a, st) for i, (d, dp, a, st) in enumerate(_raw)]
_agg = defaultdict(int)
_cnt = defaultdict(int)
for vid, d, dp, a, st in D01_ROWS:
    if d.startswith("2026-09") and st == "미결":
        _agg[dp] += a
        _cnt[dp] += 1
_top = _unique_top(_agg)[0]
T01 = {"dept": _top[0], "total": _top[1], "count": _cnt[_top[0]]}
tasks.append(_task("nt_01", "data", (
    "다음은 지출 전표 내역(CSV)입니다.\n\n" + _csv(["전표번호", "일자", "부서", "금액", "상태"], D01_ROWS) +
    "\n\n2026년 9월(2026-09-01 ~ 2026-09-30) 일자이면서 상태가 '미결'인 전표만 대상으로 부서별 금액 합계를 "
    "냈을 때, 합계가 가장 큰 부서와 그 합계, 그 부서의 해당 전표 건수를 알려주세요. 2025년 전표도 섞여 있으니 제외해야 합니다. "
    + JSON_RULE + '{"dept": 부서명, "total": 합계(원, 정수), "count": 건수(정수)}'),
    {"dept": "str", "total": "int", "count": "int"},
    lambda p: _eq_name(p, "dept", T01["dept"]) and _eq_num(p, "total", T01["total"]) and _eq_num(p, "count", T01["count"])))

# ---- nt_02 sales: Q3 2026, excluding cancelled, rep ranking
_r = random.Random(202)
_REPS = ["김도현", "이수빈", "박재원", "최지아", "정우진"]
_PROD = {"스마트센서 S1": 128_000, "게이트웨이 G2": 412_000, "모니터링 라이선스": 89_500, "설치 서비스": 55_000}
_raw = []
for i in range(52):
    if i % 9 == 4:
        d = _dt.date(2025, _r.choice([7, 8, 9]), _r.randint(1, 28))
    else:
        d = _dt.date(2026, _r.choice([6, 7, 8, 9, 9, 10]), _r.randint(1, 28))
    p = _r.choice(list(_PROD))
    _raw.append((d, _r.choice(_REPS), p, _r.randint(1, 14), _PROD[p],
                 "취소" if _r.random() < 0.15 else "정상"))
_raw.sort(key=lambda x: x[0])
D02_ROWS = [(f"SO-{26000 + i * 7}", d.isoformat(), rep, p, q, u, st) for i, (d, rep, p, q, u, st) in enumerate(_raw)]
_agg = defaultdict(int)
for _, d, rep, p, q, u, st in D02_ROWS:
    if "2026-07-01" <= d <= "2026-09-30" and st == "정상":
        _agg[rep] += q * u
_s = _unique_top(_agg)
assert _s[1][1] != _s[2][1]
T02 = {"top": _s[0][0], "amount": _s[0][1], "second": _s[1][0]}
tasks.append(_task("nt_02", "data", (
    "아래는 영업 주문 내역(CSV)입니다. 매출액은 수량×단가입니다.\n\n" +
    _csv(["주문번호", "주문일", "담당자", "제품", "수량", "단가", "상태"], D02_ROWS) +
    "\n\n2026년 3분기(2026-07-01 ~ 2026-09-30, 양 끝 포함) 주문 중 상태가 '취소'인 건은 빼고, 담당자별 매출액 합계를 "
    "구해 1위 담당자, 1위의 매출액, 2위 담당자를 알려주세요. 2025년 주문은 대상이 아닙니다. "
    + JSON_RULE + '{"top": 1위 이름, "amount": 1위 매출액(원, 정수), "second": 2위 이름}'),
    {"top": "str", "amount": "int", "second": "str"},
    lambda p: _eq_name(p, "top", T02["top"]) and _eq_num(p, "amount", T02["amount"]) and _eq_name(p, "second", T02["second"])))

# ---- nt_03 inventory: sum across warehouses vs safety stock
_r = random.Random(303)
_NAMES = ["볼트 M8", "너트 M8", "와셔 8mm", "베어링 6204", "오링 20mm", "케이블타이 200", "퓨즈 5A", "릴레이 12V",
          "단자대 10P", "커넥터 4핀", "필터 카트리지", "벨트 A42", "그리스 1kg", "호스 10mm", "클램프 25mm",
          "스위치 토글", "램프 24V", "센서 근접", "모터 브러시", "기어 20T", "패킹 고무", "스프링 압축", "핀 평행 6mm",
          "실리콘 실란트", "테이프 절연", "팬 80mm", "히트싱크 소", "다이오드 1N4007"]
D03_ITEMS = []
D03_ROWS = []
for i, nm in enumerate(_NAMES):
    code = f"P-{301 + i * 3}"
    safety = _r.randrange(40, 400, 10)
    D03_ITEMS.append((code, nm, safety))
    whs = ["본사창고"] if _r.random() < 0.45 else ["본사창고", "평택창고"]
    for w in whs:
        D03_ROWS.append([code, nm, w, None, safety])
# fill quantities so that totals land on both sides of safety stock
_tot = defaultdict(int)
for row in D03_ROWS:
    code, safety = row[0], row[4]
    n = sum(1 for x in D03_ROWS if x[0] == code)
    target = int(safety * _r.uniform(0.55, 1.6))
    row[3] = max(0, target // n + _r.randint(-15, 15))
    _tot[code] += row[3]
_short = {c: s - _tot[c] for c, nm, s in D03_ITEMS if _tot[c] < s}
T03 = {"count": len(_short), "shortage": sum(_short.values()), "item_codes": sorted(_short)}
assert all(_tot[c] != s for c, nm, s in D03_ITEMS)
tasks.append(_task("nt_03", "data", (
    "아래는 창고별 재고 현황(CSV)입니다. 안전재고는 품목 전체(모든 창고 합산) 기준 값이라 같은 품목의 행마다 반복해서 적혀 있습니다.\n\n" +
    _csv(["품목코드", "품목명", "창고", "현재고", "안전재고"], D03_ROWS) +
    "\n\n품목별로 모든 창고의 현재고를 합산한 값이 안전재고보다 작은(같으면 해당 없음) 품목을 찾아, 그 품목 수, "
    "부족 수량(안전재고 − 합산 재고)의 합계, 품목코드 목록을 알려주세요. "
    + JSON_RULE + '{"count": 품목 수, "shortage": 부족 수량 합계(정수), "item_codes": ["P-301", ...]}'),
    {"count": "int", "shortage": "int", "item_codes": "list"},
    lambda p: _eq_num(p, "count", T03["count"]) and _eq_num(p, "shortage", T03["shortage"])
    and _eq_codes(p, "item_codes", T03["item_codes"])))

# ---- nt_04 attendance: late (strictly after 09:00) and early leave (before 18:00)
_r = random.Random(404)
_EMP = [("E101", "강민서"), ("E102", "고태윤"), ("E103", "남궁하늘"), ("E104", "서예린"),
        ("E105", "안준호"), ("E106", "오세진"), ("E107", "유다은"), ("E108", "장현우")]
_DAYS = ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19"]
D04_ROWS = []
for d in _DAYS:
    for eid, nm in _EMP:
        late_prone = eid in ("E102", "E105", "E107")
        mins = 8 * 60 + _r.randint(25, 59)
        x = _r.random()
        if x < (0.35 if late_prone else 0.08):
            mins = 9 * 60 + _r.randint(1, 25)
        elif x < (0.45 if late_prone else 0.16):
            mins = 9 * 60  # exactly 09:00, not late
        out = 18 * 60 + _r.randint(0, 90) if _r.random() > 0.1 else 17 * 60 + _r.randint(10, 59)
        D04_ROWS.append((d, eid, nm, f"{mins // 60:02d}:{mins % 60:02d}", f"{out // 60:02d}:{out % 60:02d}"))
_late = defaultdict(int)
_early = 0
for d, eid, nm, i, o in D04_ROWS:
    if i > "09:00":
        _late[nm] += 1
    if o < "18:00":
        _early += 1
T04 = {"names": sorted(n for n, c in _late.items() if c >= 2), "late_total": sum(_late.values()), "early_leave": _early}
tasks.append(_task("nt_04", "data", (
    "아래는 10월 출퇴근 기록(CSV)입니다. 출근 시각이 09:00보다 늦으면 지각(09:00 정각은 정상), "
    "퇴근 시각이 18:00보다 이르면 조퇴(18:00 정각은 정상)입니다.\n\n" +
    _csv(["일자", "사번", "이름", "출근", "퇴근"], D04_ROWS) +
    "\n\n지각이 2회 이상인 직원 이름 목록, 전체 지각 건수, 전체 조퇴 건수를 알려주세요. "
    + JSON_RULE + '{"names": ["이름", ...], "late_total": 지각 건수, "early_leave": 조퇴 건수}'),
    {"names": "list", "late_total": "int", "early_leave": "int"},
    lambda p: _eq_names(p, "names", T04["names"]) and _eq_num(p, "late_total", T04["late_total"])
    and _eq_num(p, "early_leave", T04["early_leave"])))

# ---- nt_05 corporate card: Oct 2026 business use, monthly limit excess
_r = random.Random(505)
_USERS = ["윤성호", "임채원", "한지민", "배도경", "송유진"]
_MERCH = [("한솥도시락 역삼점", "식대"), ("스타벅스 강남R", "식대"), ("카카오T", "교통"), ("코레일", "교통"),
          ("오피스디포", "사무용품"), ("교보문고", "도서"), ("롯데호텔", "숙박"), ("GS25 선릉", "기타")]
D05_ROWS = []
for i in range(44):
    m = 9 if i % 8 == 5 else 10
    mc, cat = _r.choice(_MERCH)
    amt = _r.randrange(4_500, 60_000, 100) if cat in ("식대", "교통", "기타") else _r.randrange(20_000, 260_000, 100)
    D05_ROWS.append((_dt.date(2026, m, _r.randint(1, 30)).isoformat(), _r.choice(_USERS), mc, cat, amt,
                     "개인" if _r.random() < 0.15 else "업무"))
D05_ROWS.sort(key=lambda x: x[0])
_LIMIT = 340_000
_agg = defaultdict(int)
for d, u, mc, cat, amt, g in D05_ROWS:
    if d.startswith("2026-10") and g == "업무":
        _agg[u] += amt
_over = {u: a - _LIMIT for u, a in _agg.items() if a > _LIMIT}
assert 1 <= len(_over) < len(_USERS)
T05 = {"users": sorted(_over), "excess_total": sum(_over.values())}
tasks.append(_task("nt_05", "data", (
    "법인카드 사용 내역(CSV)입니다. 구분이 '개인'인 건은 개인 사용분이라 업무 한도 계산에서 빠집니다.\n\n" +
    _csv(["일자", "사용자", "가맹점", "업종", "금액", "구분"], D05_ROWS) +
    f"\n\n업무용 월 한도는 1인당 {_LIMIT:,}원입니다. 2026년 10월 사용분 중 구분이 '업무'인 건만 사용자별로 합산했을 때 "
    "한도를 초과한(같으면 초과 아님) 사용자 목록과, 그 사용자들의 초과액(합계 − 한도)의 총합을 알려주세요. 9월 사용분은 제외합니다. "
    + JSON_RULE + '{"users": ["이름", ...], "excess_total": 초과액 총합(원, 정수)}'),
    {"users": "list", "excess_total": "int"},
    lambda p: _eq_names(p, "users", T05["users"]) and _eq_num(p, "excess_total", T05["excess_total"])))

# ---- nt_06 receivables aging
_r = random.Random(606)
_CUST = ["(주)대성정밀", "한빛상사", "(주)미래에너지", "동방유통", "(주)세진테크", "그린푸드"]
_BASE = _dt.date(2026, 10, 31)
D06_ROWS = []
for i in range(36):
    inv = _dt.date(2026, 5, 1) + _dt.timedelta(days=_r.randint(0, 170))
    due = inv + _dt.timedelta(days=_r.choice([30, 45, 60]))
    amt = _r.randrange(500_000, 9_000_000, 1000)
    x = _r.random()
    paid = amt if x < 0.4 else (_r.randrange(0, amt, 1000) if x < 0.75 else 0)
    D06_ROWS.append((inv, due, _r.choice(_CUST), amt, paid))
D06_ROWS.append((_dt.date(2026, 9, 16), _BASE, "한빛상사", 4_180_000, 1_000_000))  # due on the base date: not overdue
D06_ROWS.sort(key=lambda x: x[0])
D06_ROWS = [(f"INV-{7101 + i}", c, a.isoformat(), b.isoformat(), amt, pd)
            for i, (a, b, c, amt, pd) in enumerate(D06_ROWS)]
_overdue = 0
_c60 = set()
for no, c, a, b, amt, pd in D06_ROWS:
    bal = amt - pd
    due = _dt.date.fromisoformat(b)
    if bal > 0 and due < _BASE:
        _overdue += bal
        if (_BASE - due).days > 100:
            _c60.add(c)
assert any(_dt.date.fromisoformat(r[3]) >= _BASE and r[4] > r[5] for r in D06_ROWS)
T06 = {"overdue_balance": _overdue, "customers_over_100": sorted(_c60)}
assert 0 < len(_c60) < len(_CUST) - 1
tasks.append(_task("nt_06", "data", (
    "매출채권 송장 목록(CSV)입니다. 잔액 = 청구액 − 입금액입니다.\n\n" +
    _csv(["송장번호", "거래처", "송장일", "만기일", "청구액", "입금액"], D06_ROWS) +
    "\n\n기준일은 2026-10-31입니다. 만기일이 기준일보다 앞서고(기준일 당일 만기는 연체 아님) 잔액이 0보다 큰 송장을 연체로 봅니다. "
    "연체 송장 잔액의 합계와, 연체일수(기준일 − 만기일, 일 단위)가 100일을 초과하는 연체 송장을 하나라도 가진 거래처 목록을 알려주세요. "
    + JSON_RULE + '{"overdue_balance": 연체 잔액 합계(원, 정수), "customers_over_100": ["거래처명", ...]}'),
    {"overdue_balance": "int", "customers_over_100": "list"},
    lambda p: _eq_num(p, "overdue_balance", T06["overdue_balance"]) and _eq_names(p, "customers_over_100", T06["customers_over_100"])))

# ---- nt_07 timesheet x grade rates
_r = random.Random(707)
D07_STAFF = [("문서현", "과장"), ("황보람", "대리"), ("노지훈", "사원"), ("구하은", "차장"),
             ("탁민재", "사원"), ("변소율", "대리"), ("엄태경", "과장")]
D07_RATE = {"사원": 35_000, "대리": 42_000, "과장": 55_000, "차장": 68_000}
_PROJ = ["ERP 고도화", "물류 대시보드", "보안 점검", "고객 포털"]
D07_ROWS = []
for i in range(50):
    d = _dt.date(2026, 10, 1) + _dt.timedelta(days=_r.randint(0, 27))
    while d.weekday() >= 5:
        d += _dt.timedelta(days=1)
    D07_ROWS.append((d.isoformat(), _r.choice(D07_STAFF)[0], _r.choice(_PROJ), _r.randint(2, 16) / 2))
D07_ROWS.sort(key=lambda x: x[0])
D07_ROWS = [(d, s, p, (int(h) if h.is_integer() else h)) for d, s, p, h in D07_ROWS]
_g = dict(D07_STAFF)
_agg = defaultdict(int)
for d, s, p, h in D07_ROWS:
    _agg[p] += int(h * D07_RATE[_g[s]])
_s = _unique_top(_agg)
T07 = {"project": _s[0][0], "cost": _s[0][1], "total_cost": sum(_agg.values())}
tasks.append(_task("nt_07", "data", (
    "프로젝트 투입 시간 기록입니다. 인건비 = 투입 시간 × 해당 직원 직급의 시간당 단가입니다.\n\n[직원 직급]\n" +
    _csv(["직원", "직급"], D07_STAFF) + "\n\n[직급별 시간당 단가(원)]\n" +
    _csv(["직급", "단가"], D07_RATE.items()) + "\n\n[투입 기록]\n" +
    _csv(["일자", "직원", "프로젝트", "시간"], D07_ROWS) +
    "\n\n프로젝트별 인건비를 계산해 인건비가 가장 큰 프로젝트와 그 금액, 그리고 전체 프로젝트 인건비 합계를 알려주세요. "
    + JSON_RULE + '{"project": 프로젝트명, "cost": 인건비(원, 정수), "total_cost": 전체 합계(원, 정수)}'),
    {"project": "str", "cost": "int", "total_cost": "int"},
    lambda p: _eq_name(p, "project", T07["project"]) and _eq_num(p, "cost", T07["cost"])
    and _eq_num(p, "total_cost", T07["total_cost"])))

# ---- nt_08 purchase orders: average per order by supplier, 2026 non-cancelled
_r = random.Random(808)
_SUP = ["(주)삼원산업", "대양부품", "(주)하나테크", "우성자재", "(주)신일금속"]
D08_ROWS = []
for i in range(46):
    y = 2025 if i % 10 == 6 else 2026
    d = _dt.date(y, _r.randint(1, 10) if y == 2026 else _r.randint(9, 12), _r.randint(1, 28))
    q = _r.randint(5, 120)
    u = _r.randrange(1_200, 48_000, 10)
    st = _r.choice(["입고완료", "입고완료", "입고완료", "부분입고", "취소"])
    D08_ROWS.append((d, _r.choice(_SUP), q, u, st))
D08_ROWS.sort(key=lambda x: x[0])
D08_ROWS = [(f"PO-{d.year % 100}{i + 1:03d}", d.isoformat(), s, q, u, st) for i, (d, s, q, u, st) in enumerate(D08_ROWS)]
_sum = defaultdict(int)
_n = defaultdict(int)
for no, d, s, q, u, st in D08_ROWS:
    if d.startswith("2026") and st != "취소":
        _sum[s] += q * u
        _n[s] += 1
_avg = {s: _sum[s] // _n[s] for s in _sum}
_s = _unique_top(_avg)
T08 = {"supplier": _s[0][0], "average": _s[0][1], "orders": sum(_n.values())}
tasks.append(_task("nt_08", "data", (
    "구매 발주 내역(CSV)입니다. 발주금액 = 수량 × 단가입니다.\n\n" +
    _csv(["발주번호", "발주일", "공급사", "수량", "단가", "상태"], D08_ROWS) +
    "\n\n2026년 발주 중 상태가 '취소'인 건을 제외하고(부분입고는 포함), 공급사별 건당 평균 발주금액"
    "(발주금액 합계 ÷ 발주 건수, 원 미만 버림)을 구했을 때 평균이 가장 높은 공급사와 그 평균, 그리고 대상 발주의 총 건수를 알려주세요. "
    "2025년 발주는 제외합니다. "
    + JSON_RULE + '{"supplier": 공급사명, "average": 건당 평균(원, 정수), "orders": 총 건수}'),
    {"supplier": "str", "average": "int", "orders": "int"},
    lambda p: _eq_name(p, "supplier", T08["supplier"]) and _eq_num(p, "average", T08["average"])
    and _eq_num(p, "orders", T08["orders"])))

# ================================================================= doc

# ---- nt_09 service contract + amendment
_C9 = dict(buyer="주식회사 한결테크", supplier="주식회사 다온시스템", start="2026-03-02", end0="2026-08-31",
           end1="2026-10-30", amt0=84_700_000, amt1=92_350_000, adv_pct=30, warranty=12, warranty_rejected=6)
_adv = _C9["amt0"] * _C9["adv_pct"] // 100
T09 = {"contract_amount": _C9["amt1"], "end_date": _C9["end1"], "balance": _C9["amt1"] - _adv,
       "warranty_months": _C9["warranty"], "supplier": "다온시스템"}
_doc9 = f"""[용역 계약서]
발주자 {_C9['buyer']}(이하 "갑")와 수급자 {_C9['supplier']}(이하 "을")는 다음과 같이 용역 계약을 체결한다.

제1조(목적) 본 계약은 "갑"의 사내 문서관리 시스템 고도화 용역(이하 "본 용역")의 수행에 필요한 사항을 정한다.
제2조(계약기간) 계약기간은 {_C9['start']}부터 {_C9['end0']}까지로 한다.
제3조(계약금액) 계약금액은 금 {_C9['amt0']:,}원(부가가치세 별도)으로 한다.
제4조(대금지급) ① "갑"은 계약 체결일로부터 14일 이내에 계약금액의 {_C9['adv_pct']}%를 선급금으로 지급한다.
② 잔금은 검수 완료 후 30일 이내에 지급하며, 잔금은 계약금액에서 이미 지급한 선급금을 뺀 금액으로 한다.
제5조(지체상금) "을"이 계약기간 내에 용역을 완료하지 못한 경우 지체일수 1일당 계약금액의 1,000분의 1을 지체상금으로 "갑"에게 납부한다.
제6조(하자보수) 하자보수 기간은 검수 완료일로부터 {_C9['warranty']}개월로 한다.
제7조(비밀유지) 양 당사자는 본 계약의 이행 과정에서 알게 된 상대방의 영업비밀을 계약 종료 후 3년간 제3자에게 누설하지 않는다.
제8조(분쟁해결) 본 계약에 관한 분쟁은 서울중앙지방법원을 제1심 관할 법원으로 한다.

[변경 합의서]  (체결일: 2026-07-15)
"갑"과 "을"은 위 용역 계약에 관하여 다음과 같이 합의한다.
1. 요구사항 추가에 따라 제2조의 계약 종료일을 {_C9['end1']}로 변경한다.
2. 제3조의 계약금액을 금 {_C9['amt1']:,}원(부가가치세 별도)으로 변경한다.
3. 선급금은 원계약에 따라 이미 지급되었으며 추가 선급금은 지급하지 않는다. 잔금은 제4조 ②항에 따라 변경 후 계약금액을 기준으로 산정한다.
4. "을"이 요청한 제6조 하자보수 기간 단축안({_C9['warranty_rejected']}개월)은 "갑"이 수용하지 않았으므로 제6조는 원계약대로 유지한다.
5. 이 합의서에서 정하지 않은 사항은 원계약에 따른다."""
tasks.append(_task("nt_09", "doc", (
    "아래 계약서와 변경 합의서를 읽고 현재 유효한 내용을 정리해 주세요.\n\n" + _doc9 +
    "\n\n변경 후 계약금액, 계약 종료일, 검수 후 지급할 잔금, 하자보수 기간(개월), 수급자(을) 회사명을 알려주세요. "
    + JSON_RULE + '{"contract_amount": 원(정수), "end_date": "YYYY-MM-DD", "balance": 잔금(원, 정수), '
    '"warranty_months": 개월(정수), "supplier": 회사명}'),
    {"contract_amount": "int", "end_date": "str", "balance": "int", "warranty_months": "int", "supplier": "str"},
    lambda p: _eq_num(p, "contract_amount", T09["contract_amount"]) and _eq_date(p, "end_date", T09["end_date"])
    and _eq_num(p, "balance", T09["balance"]) and _eq_num(p, "warranty_months", T09["warranty_months"])
    and _eq_name(p, "supplier", T09["supplier"])))

# ---- nt_10 meeting minutes: vendor selection with reversal, withdrawn action item
_M10 = dict(chosen="새길물류", quote0=13_600_000, fee=13_150_000, years=2, cap=14_000_000, next="2026-11-12",
            actions=[("기존 업체 계약 해지 통보", "구매팀 한상우", "2026-10-31", True),
                     ("물류센터 현장 실사", "물류팀 배수민", "2026-11-03", False),
                     ("계약서 초안 법무 검토", "법무팀 오지현", "2026-11-05", True),
                     ("보험 증권 사본 수령", "재무팀 문가은", "2026-11-07", True)])
T10 = {"vendor": _M10["chosen"], "monthly_fee": _M10["fee"], "contract_years": _M10["years"],
       "owners": [o.split()[1] for _, o, _, keep in _M10["actions"] if keep], "next_meeting": _M10["next"]}
_acts = "\n".join(f"  {i + 1}) {t} — 담당 {o}, 기한 {d}" for i, (t, o, d, _) in enumerate(_M10["actions"]))
_doc10 = f"""[회의록] 3자 물류(3PL) 협력사 선정 회의
일시: 2026-10-22 14:00~15:30 / 장소: 본사 7층 대회의실
참석: 물류팀 배수민 팀장, 구매팀 한상우 과장, 재무팀 문가은 대리, 법무팀 오지현 변호사

1. 후보 업체 검토
  - 한빛로지스: 월 12,400,000원. 화물 배상책임보험 미가입으로 지난 회의에서 이미 탈락 처리됨.
  - 동서운송: 월 11,800,000원. 단가가 가장 낮아 초반 논의에서 유력 후보로 거론됨.
  - {_M10['chosen']}: 최초 견적 월 {_M10['quote0']:,}원, 2차 협상 후 월 {_M10['fee']:,}원으로 조정됨.
2. 논의
  - 재무팀: 동서운송은 신용평가 결과 기준 등급(BB+) 미달로 확인되어 후보에서 제외할 것을 요청함. 참석자 전원 동의.
  - 예산 상한은 월 {_M10['cap']:,}원(부가세 별도)으로 확인. {_M10['chosen']} 2차 견적은 상한 이내임.
  - 계약기간은 3년 안과 {_M10['years']}년 안을 놓고 논의했으며, 3년 안은 중도 해지 위약금 부담으로 채택하지 않음.
3. 결정 사항
  - 협력사는 {_M10['chosen']}로 최종 선정하며, 월 이용료는 2차 협상 금액으로 계약한다. 계약기간은 {_M10['years']}년.
4. 후속 조치
{_acts}
  ※ 회의 말미에 물류센터 현장 실사는 지난주에 이미 완료된 것으로 확인되어 2)번 항목은 삭제함.
5. 다음 회의: {_M10['next']} 10:00, 계약 체결 결과 공유"""
tasks.append(_task("nt_10", "doc", (
    "아래 회의록을 읽고 결정된 내용을 정리해 주세요.\n\n" + _doc10 +
    "\n\n최종 선정된 협력사, 계약할 월 이용료, 계약기간(년), 유효한(삭제되지 않은) 후속 조치의 담당자 이름 목록, 다음 회의 날짜를 알려주세요. "
    + JSON_RULE + '{"vendor": 업체명, "monthly_fee": 원(정수), "contract_years": 년(정수), "owners": ["이름", ...], '
    '"next_meeting": "YYYY-MM-DD"}'),
    {"vendor": "str", "monthly_fee": "int", "contract_years": "int", "owners": "list", "next_meeting": "str"},
    lambda p: _eq_name(p, "vendor", T10["vendor"]) and _eq_num(p, "monthly_fee", T10["monthly_fee"])
    and _eq_num(p, "contract_years", T10["contract_years"])
    and _eq_names(p, "owners", T10["owners"]) and _eq_date(p, "next_meeting", T10["next_meeting"])))

# ---- nt_11 travel policy revision with a rejected item
_P11 = dict(lodging={"임원": 150_000, "부장": 120_000, "과장·대리": 100_000, "사원": 90_000},
            per_diem_exec=120, per_diem_staff=80, new_staff=95, rejected_exec=150, new_lodging_staff=100_000,
            pre0=3, pre1=2, effective="2026-11-01")
T11 = {"overseas_per_diem_exec": _P11["per_diem_exec"], "overseas_per_diem_staff": _P11["new_staff"],
       "lodging_cap_staff": _P11["new_lodging_staff"], "preapproval_days": _P11["pre1"], "effective_date": _P11["effective"]}
_lod = "\n".join(f"  - {k}: 1박 {v:,}원" for k, v in _P11["lodging"].items())
_doc11 = f"""[출장비 지급 규정] (현행)
제5조(국내 숙박비) 국내 출장 숙박비는 실비로 지급하되 직급별 상한은 다음과 같다.
{_lod}
제6조(국내 일비) 임원은 1일 50,000원, 그 외 직원은 1일 30,000원을 지급한다.
제7조(해외 일비) 해외 출장 일비는 임원 1일 USD {_P11['per_diem_exec']}, 부장 이하 1일 USD {_P11['per_diem_staff']}로 한다.
제8조(교통비) 철도·항공 등 교통비는 실비로 지급하며, 항공은 임원만 비즈니스석을 이용할 수 있다.
제9조(사전 승인) 출장 기간이 {_P11['pre0']}일 이상인 출장은 출발 전 소속 본부장의 승인을 받아야 한다.

[규정 개정안 심의 결과] (2026-10-15 경영회의)
제1안: 제7조 부장 이하 해외 일비를 USD {_P11['per_diem_staff']}에서 USD {_P11['new_staff']}로 인상 — 가결
제2안: 제7조 임원 해외 일비를 USD {_P11['per_diem_exec']}에서 USD {_P11['rejected_exec']}로 인상 — 부결
제3안: 제5조 사원 숙박비 상한을 과장·대리와 같은 {_P11['new_lodging_staff']:,}원으로 상향 — 가결
제4안: 제6조 국내 일비를 정액 대신 실비 정산으로 전환 — 부결
제5안: 제9조 사전 승인 대상을 출장 기간 {_P11['pre1']}일 이상으로 확대 — 가결
제6안: 제8조 부장급 항공 비즈니스석 허용 — 부결
가결된 안은 {_P11['effective']}부터 시행하고, 부결된 안에 해당하는 조항은 현행대로 유지한다."""
tasks.append(_task("nt_11", "doc", (
    "아래 출장비 규정과 개정안 심의 결과를 보고, 시행일 이후 적용되는 기준을 알려주세요.\n\n" + _doc11 +
    "\n\n시행일 이후 기준으로 임원 해외 일비(USD), 부장 이하 해외 일비(USD), 사원 국내 숙박비 상한(원), "
    "사전 승인이 필요한 최소 출장 기간(일), 시행일을 알려주세요. "
    + JSON_RULE + '{"overseas_per_diem_exec": 정수, "overseas_per_diem_staff": 정수, "lodging_cap_staff": 원(정수), '
    '"preapproval_days": 일(정수), "effective_date": "YYYY-MM-DD"}'),
    {"overseas_per_diem_exec": "int", "overseas_per_diem_staff": "int", "lodging_cap_staff": "int",
     "preapproval_days": "int", "effective_date": "str"},
    lambda p: all(_eq_num(p, k, T11[k]) for k in ("overseas_per_diem_exec", "overseas_per_diem_staff",
                                                   "lodging_cap_staff", "preapproval_days"))
    and _eq_date(p, "effective_date", T11["effective_date"])))

# ---- nt_12 office lease with special terms
_L12 = dict(deposit=50_000_000, rent0=3_300_000, rent1=3_450_000, mgmt=420_000, start="2026-01-01",
            end="2027-12-31", free_months=1, free_asked=2, notice=3)
T12 = {"deposit": _L12["deposit"], "rent_2026_total": _L12["rent0"] * (12 - _L12["free_months"]),
       "rent_2027_monthly": _L12["rent1"], "end_date": _L12["end"], "notice_months": _L12["notice"]}
_doc12 = f"""[사무실 임대차 계약서]
임대인 (주)청명빌딩관리(이하 "임대인")와 임차인 (주)루미나랩(이하 "임차인")은 서울 성동구 성수이로 12, 청명빌딩 5층 전체에 관하여 다음과 같이 계약한다.

제1조(보증금) 임대차 보증금은 금 {_L12['deposit']:,}원으로 하며 계약일에 전액 지급한다.
제2조(임대기간) 임대기간은 {_L12['start']}부터 {_L12['end']}까지 24개월로 한다.
제3조(차임) 월 차임은 금 {_L12['rent0']:,}원(부가가치세 별도)으로 하며 매월 말일에 지급한다.
제4조(관리비) 관리비는 차임과 별도로 월 {_L12['mgmt']:,}원을 지급한다.
제5조(해지) 임차인이 기간 만료 전 해지하려면 해지일 2개월 전까지 서면으로 통보하여야 한다.
제6조(원상복구) 임차인은 계약 종료 시 목적물을 원상으로 복구하여 반환한다. 다만 임대인의 사전 동의를 받아 설치한 칸막이는 원상복구 대상에서 제외한다.
제7조(전대 금지) 임차인은 임대인의 서면 동의 없이 목적물의 전부 또는 일부를 전대하거나 임차권을 양도할 수 없다.
제8조(보증금 반환) 임대인은 계약 종료 및 목적물 반환일로부터 14일 이내에 미납 차임과 관리비를 공제한 보증금을 반환한다.

[특약사항]
1. 임차인은 인테리어 공사 기간을 고려하여 {_L12['free_asked']}개월 차임 면제를 요청하였으나, 임대인과의 협의 결과 {_L12['free_months']}개월(2026년 1월분)만 차임을 면제한다. 관리비는 면제하지 않는다.
2. 제3조에도 불구하고 2027-01-01부터의 월 차임은 금 {_L12['rent1']:,}원(부가가치세 별도)으로 한다.
3. 제5조의 해지 통보 기한은 "해지일 {_L12['notice']}개월 전까지"로 변경한다.
4. 특약사항과 본문이 다를 경우 특약사항이 우선한다."""
tasks.append(_task("nt_12", "doc", (
    "아래 임대차 계약서를 읽고 정리해 주세요.\n\n" + _doc12 +
    "\n\n보증금, 2026년 한 해 동안 실제로 내야 하는 차임 합계(부가세·관리비 제외), 2027년 월 차임, 임대 종료일, "
    "중도 해지 시 통보 기한(몇 개월 전)을 알려주세요. "
    + JSON_RULE + '{"deposit": 원, "rent_2026_total": 원, "rent_2027_monthly": 원, "end_date": "YYYY-MM-DD", "notice_months": 정수}'),
    {"deposit": "int", "rent_2026_total": "int", "rent_2027_monthly": "int", "end_date": "str", "notice_months": "int"},
    lambda p: _eq_num(p, "deposit", T12["deposit"]) and _eq_num(p, "rent_2026_total", T12["rent_2026_total"])
    and _eq_num(p, "rent_2027_monthly", T12["rent_2027_monthly"]) and _eq_date(p, "end_date", T12["end_date"])
    and _eq_num(p, "notice_months", T12["notice_months"])))

# ---- nt_13 email thread: negotiated quote
_E13 = dict(q0=1_200, p0=18_500, ask=17_000, q1=1_500, p1=17_600, d0="2026-11-20", d1="2026-11-27",
            d2="2026-11-24", freight=350_000, pay="월말 마감 익월 말 현금")
T13 = {"unit_price": _E13["p1"], "quantity": _E13["q1"], "delivery_date": _E13["d2"],
       "total_amount": _E13["q1"] * _E13["p1"] + _E13["freight"]}
_doc13 = f"""----- 메일 1 -----
보낸 사람: 정예준(구매팀) / 받는 사람: 김하윤(대영필터 영업부) / 2026-10-02
산업용 필터 FX-200 {_E13['q0']:,}개 견적을 요청드립니다. 희망 납기는 11월 하순입니다.

----- 메일 2 -----
보낸 사람: 김하윤 / 받는 사람: 정예준 / 2026-10-05
FX-200 {_E13['q0']:,}개 기준 단가 {_E13['p0']:,}원(부가세 별도), 납기 {_E13['d0']}, 결제 조건은 {_E13['pay']}입니다.

----- 메일 3 -----
보낸 사람: 정예준 / 받는 사람: 김하윤 / 2026-10-08
수량을 {_E13['q1']:,}개로 늘릴 수 있습니다. 대신 단가를 {_E13['ask']:,}원으로 맞춰 주실 수 있을까요? 분할 납품(2회)도 검토 부탁드립니다.

----- 메일 4 -----
보낸 사람: 김하윤 / 받는 사람: 정예준 / 2026-10-10
{_E13['q1']:,}개 기준으로 단가 {_E13['p1']:,}원까지 가능하며 {_E13['ask']:,}원은 어렵습니다. 수량 증가로 납기는 {_E13['d1']}이 됩니다.

----- 메일 5 -----
보낸 사람: 정예준 / 받는 사람: 김하윤 / 2026-10-13
단가 {_E13['p1']:,}원, 수량 {_E13['q1']:,}개로 진행하겠습니다. 다만 납기를 {_E13['d2']}로 당겨 주시기 바랍니다. 분할 납품 요청은 철회합니다. 결제 조건은 기존 제안대로 하겠습니다.

----- 메일 6 -----
보낸 사람: 김하윤 / 받는 사람: 정예준 / 2026-10-14
{_E13['d2']} 납품 가능합니다. 다만 일정 단축으로 특송 운송비 {_E13['freight']:,}원(부가세 별도)이 1회 별도 청구되는 점 양해 부탁드립니다. 이 조건으로 발주서 보내주시면 확정하겠습니다.

----- 메일 7 -----
보낸 사람: 정예준 / 받는 사람: 김하윤 / 2026-10-15
운송비 조건 포함하여 동의합니다. 오늘 중 발주서 송부하겠습니다."""
tasks.append(_task("nt_13", "doc", (
    "아래는 견적 협상 메일 스레드입니다.\n\n" + _doc13 +
    "\n\n최종 확정된 단가, 수량, 납품일, 그리고 발주 총액(물품 대금 + 별도 청구 운송비, 부가세 제외)을 알려주세요. "
    + JSON_RULE + '{"unit_price": 원, "quantity": 개수, "delivery_date": "YYYY-MM-DD", "total_amount": 원}'),
    {"unit_price": "int", "quantity": "int", "delivery_date": "str", "total_amount": "int"},
    lambda p: _eq_num(p, "unit_price", T13["unit_price"]) and _eq_num(p, "quantity", T13["quantity"])
    and _eq_date(p, "delivery_date", T13["delivery_date"]) and _eq_num(p, "total_amount", T13["total_amount"])))

# ---- nt_14 audit findings with corrections
_F14 = [("A-01", "재무팀", "법인카드 사용 증빙 누락", "완료"), ("A-02", "구매팀", "수의계약 사유서 미첨부", "진행중"),
        ("A-03", "인사팀", "퇴직자 시스템 권한 미회수", "완료"), ("A-04", "구매팀", "단가 계약 갱신 지연", "완료"),
        ("A-05", "IT팀", "백업 복구 테스트 미실시", "미착수"), ("A-06", "재무팀", "가지급금 장기 미정산", "진행중"),
        ("A-07", "구매팀", "검수 담당자 분리 미흡", "진행중"), ("A-08", "IT팀", "관리자 계정 공유 사용", "완료"),
        ("A-09", "인사팀", "교육 이수 기록 누락", "보류"), ("A-10", "구매팀", "거래처 등록 서류 미비", "미착수"),
        ("A-11", "재무팀", "외화 환산 기준 미준수", "완료")]
_FIX14 = {"A-04": "진행중", "A-07": "완료", "A-08": "진행중"}
_cur = {i: _FIX14.get(i, s) for i, d, t, s in _F14}
_open = [i for i, d, t, s in _F14 if _cur[i] != "완료"]
_od = defaultdict(int)
for i, d, t, s in _F14:
    if _cur[i] != "완료":
        _od[d] += 1
T14 = {"open_ids": _open, "dept_most_open": _unique_top(_od)[0][0], "completed_count": len(_F14) - len(_open)}
_tbl = "\n".join(f"| {i} | {d} | {t} | {s} |" for i, d, t, s in _F14)
_doc14 = f"""[내부감사 지적사항 조치 현황] (2026-10-20 각 부서 보고 기준)
| 번호 | 담당 부서 | 지적 내용 | 조치 상태 |
|---|---|---|---|
{_tbl}

[감사팀 확인 의견] (2026-10-24)
- A-04: 구매팀은 '완료'로 보고했으나 갱신 계약서 날인본이 제출되지 않아 '진행중'으로 정정한다.
- A-07: 검수 담당자 분리 내역(인사 발령 공문)을 10-23에 제출받아 '완료'로 정정한다.
- A-08: IT팀 보고와 달리 공유 계정 2개가 아직 활성 상태로 확인되어 '진행중'으로 정정한다.
- A-09: 인사팀이 시스템 교체 일정을 이유로 '보류'를 요청한 것을 인정하되, 미완료 항목으로 계속 관리한다.
- 그 밖의 항목은 부서 보고 상태를 그대로 인정한다.
- 미완료 항목은 2026-12-15까지 조치 결과를 감사팀에 제출해야 하며, 기한 내 미제출 시 경영회의에 보고한다."""
tasks.append(_task("nt_14", "doc", (
    "아래 감사 지적사항 조치 현황과 감사팀 확인 의견을 보고 정리해 주세요.\n\n" + _doc14 +
    "\n\n감사팀 정정을 반영한 최종 상태 기준으로, '완료'가 아닌 항목(진행중·미착수·보류 모두 포함)의 번호 목록, "
    "미완료 항목이 가장 많은 부서, 완료 항목 수를 알려주세요. "
    + JSON_RULE + '{"open_ids": ["A-01", ...], "dept_most_open": 부서명, "completed_count": 정수}'),
    {"open_ids": "list", "dept_most_open": "str", "completed_count": "int"},
    lambda p: _eq_codes(p, "open_ids", T14["open_ids"]) and _eq_name(p, "dept_most_open", T14["dept_most_open"])
    and _eq_num(p, "completed_count", T14["completed_count"])))

# ================================================================= calc

# ---- nt_15 freelance withholding 3.3% with 10-won truncation and small-amount exemption
C15 = [("디자인 외주 박서아", 1_234_567), ("번역 이준서", 850_000), ("강의 최민아", 2_470_350),
       ("촬영 한도윤", 333_333), ("자문 오은채", 30_000), ("개발 외주 신태호", 1_999_990)]


def _wh(gross):
    inc = gross * 3 // 100 // 10 * 10
    if inc < 1_000:
        return 0, 0
    return inc, inc // 10 // 10 * 10


_w = [_wh(g) for _, g in C15]
T15 = {"total_withholding": sum(a + b for a, b in _w), "total_net": sum(g for _, g in C15) - sum(a + b for a, b in _w)}
tasks.append(_task("nt_15", "calc", (
    "프리랜서(사업소득) 지급 건별로 원천징수 후 실지급액을 계산해 주세요.\n\n" +
    "\n".join(f"- {n}: 지급액 {g:,}원" for n, g in C15) +
    "\n\n규칙(건별로 각각 적용):\n"
    "1) 소득세 = 지급액 × 3%, 10원 미만 버림\n"
    "2) 지방소득세 = 소득세 × 10%, 10원 미만 버림\n"
    "3) 소득세가 1,000원 미만이면 소액부징수로 소득세·지방소득세 모두 0원\n"
    "4) 실지급액 = 지급액 − 소득세 − 지방소득세\n\n"
    "전체 건의 원천징수 세액 합계(소득세+지방소득세)와 실지급액 합계를 알려주세요. "
    + JSON_RULE + '{"total_withholding": 원(정수), "total_net": 원(정수)}'),
    {"total_withholding": "int", "total_net": "int"},
    lambda p: _eq_num(p, "total_withholding", T15["total_withholding"]) and _eq_num(p, "total_net", T15["total_net"])))

# ---- nt_16 VAT: supply-price items, VAT-inclusive items, exempt items
C16 = [("복합기 토너", "과세", "공급가액", 384_500), ("사무용 의자 3개", "과세", "부가세 포함가", 1_067_500),
       ("생수 20박스", "과세", "부가세 포함가", 127_390), ("도서 12권", "면세", "금액", 213_600),
       ("노트북 거치대", "과세", "공급가액", 45_455), ("쌀 20kg(구내식당)", "면세", "금액", 68_900),
       ("회의실 다과", "과세", "부가세 포함가", 58_338), ("소프트웨어 구독", "과세", "공급가액", 1_299_999)]
_sup = _vat = _ex = 0
for _, kind, basis, v in C16:
    if kind == "면세":
        _ex += v
    elif basis == "공급가액":
        _sup += v
        _vat += v // 10
    else:
        s = v * 10 // 11
        _sup += s
        _vat += v - s
T16 = {"taxable_supply": _sup, "vat": _vat, "exempt": _ex, "grand_total": _sup + _vat + _ex}
tasks.append(_task("nt_16", "calc", (
    "이번 달 구매 품목의 공급가액·부가세를 정리하려고 합니다.\n\n" +
    "\n".join(f"- {n} | {k} | {b} {v:,}원" for n, k, b, v in C16) +
    "\n\n규칙(품목별로 각각 계산한 뒤 합산):\n"
    "1) 과세 품목이 '공급가액'으로 주어지면 부가세 = 공급가액 × 10%, 원 미만 버림\n"
    "2) 과세 품목이 '부가세 포함가'로 주어지면 공급가액 = 포함가 × 10 ÷ 11, 원 미만 버림, 부가세 = 포함가 − 공급가액\n"
    "3) 면세 품목은 부가세가 없고 공급가액 합계에도 넣지 않으며 면세 금액으로 따로 합산\n\n"
    "과세 공급가액 합계, 부가세 합계, 면세 금액 합계, 총액(세 가지의 합)을 알려주세요. "
    + JSON_RULE + '{"taxable_supply": 원, "vat": 원, "exempt": 원, "grand_total": 원}'),
    {"taxable_supply": "int", "vat": "int", "exempt": "int", "grand_total": "int"},
    lambda p: all(_eq_num(p, k, v) for k, v in T16.items())))

# ---- nt_17 installments: remainder to the first month
C17 = [("서버 랙", 7_345_678, 12, (2026, 11)), ("UPS 장비", 2_000_005, 6, (2027, 1)), ("보안 게이트", 999_999, 4, (2026, 12))]


def _months(start, n):
    y, m = start
    out = []
    for _ in range(n):
        out.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


_pay = defaultdict(int)
for _, total, n, st in C17:
    base, rem = divmod(total, n)
    for k, ym in enumerate(_months(st, n)):
        _pay[ym] += base + (rem if k == 0 else 0)
T17 = {"pay_2026_11": _pay[(2026, 11)], "pay_2027_01": _pay[(2027, 1)], "pay_2027_03": _pay[(2027, 3)],
       "last_month": "%04d-%02d" % max(_pay)}
tasks.append(_task("nt_17", "calc", (
    "장비 할부 계약 3건의 월별 납부액을 계산해 주세요.\n\n" +
    "\n".join(f"- {n}: 총액 {t:,}원, {k}개월 할부, 첫 납부월 {s[0]}년 {s[1]}월" for n, t, k, s in C17) +
    "\n\n규칙: 매월 납부액 = 총액 ÷ 할부 개월 수의 원 미만 버림 금액이고, 나누어떨어지지 않아 남는 금액(나머지)은 "
    "전부 첫 달 납부액에 더합니다. 이자는 없습니다.\n\n"
    "2026년 11월, 2027년 1월, 2027년 3월에 내야 하는 금액(3건 합계)과, 마지막 납부가 있는 달을 알려주세요. "
    + JSON_RULE + '{"pay_2026_11": 원, "pay_2027_01": 원, "pay_2027_03": 원, "last_month": "YYYY-MM"}'),
    {"pay_2026_11": "int", "pay_2027_01": "int", "pay_2027_03": "int", "last_month": "str"},
    lambda p: all(_eq_num(p, k, T17[k]) for k in ("pay_2026_11", "pay_2027_01", "pay_2027_03"))
    and _ym(_get(p, "last_month")) == T17["last_month"]))

# ---- nt_18 working days between two dates
C18 = dict(start="2026-09-14", end="2026-10-23", rate=187_500,
           holidays=["2026-09-24", "2026-09-25", "2026-09-26", "2026-10-03", "2026-10-05", "2026-10-09"])
_d = _dt.date.fromisoformat(C18["start"])
_wd = 0
while _d <= _dt.date.fromisoformat(C18["end"]):
    if _d.weekday() < 5 and _d.isoformat() not in C18["holidays"]:
        _wd += 1
    _d += _dt.timedelta(days=1)
T18 = {"workdays": _wd, "pay": _wd * C18["rate"]}
tasks.append(_task("nt_18", "calc", (
    f"파견 계약직의 근무 기간은 {C18['start']}(월)부터 {C18['end']}(금)까지이며 시작일과 종료일 모두 포함합니다. "
    "토요일·일요일과 아래 공휴일은 근무하지 않습니다(주말과 겹치는 공휴일도 목록에 있습니다).\n"
    "공휴일: " + ", ".join(C18["holidays"]) + "\n"
    "(참고: 2026-09-24는 목요일, 2026-10-03은 토요일, 2026-10-05는 월요일, 2026-10-09는 금요일입니다.)\n\n"
    f"일당은 {C18['rate']:,}원입니다. 실제 근무일수와 총 지급액(근무일수 × 일당)을 알려주세요. "
    + JSON_RULE + '{"workdays": 일수(정수), "pay": 원(정수)}'),
    {"workdays": "int", "pay": "int"},
    lambda p: _eq_num(p, "workdays", T18["workdays"]) and _eq_num(p, "pay", T18["pay"])))

# ---- nt_19 FX conversion, JPY quoted per 100 yen, floor per invoice
C19 = [("INV-US-0917", "USD", "12345.67", "1382.40"), ("INV-EU-0921", "EUR", "8910.05", "1498.75"),
       ("INV-JP-0925", "JPY", "1234567", "912.35"), ("INV-CN-0930", "CNY", "45678.90", "191.82"),
       ("INV-US-1002", "USD", "980.10", "1379.95")]
_krw = {}
for no, cur, amt, rate in C19:
    v = Decimal(amt) * Decimal(rate) / (100 if cur == "JPY" else 1)
    _krw[no] = int(v.to_integral_value(rounding=ROUND_FLOOR))
T19 = {"total_krw": sum(_krw.values()), "largest_invoice": _unique_top(_krw)[0][0]}
tasks.append(_task("nt_19", "calc", (
    "해외 매입 송장을 원화로 환산해 주세요.\n\n" +
    "\n".join(f"- {no}: {cur} {Decimal(a):,} (적용 환율 {Decimal(r):,}" + (" 원/100엔)" if cur == "JPY" else f" 원/{cur})")
              for no, cur, a, r in C19) +
    "\n\n규칙: 송장별 원화 금액 = 외화 금액 × 환율(엔화는 100엔당 환율이므로 ÷100), 송장마다 원 미만 버림 후 합산합니다.\n\n"
    "원화 환산 합계와, 원화 환산액이 가장 큰 송장번호를 알려주세요. "
    + JSON_RULE + '{"total_krw": 원(정수), "largest_invoice": 송장번호}'),
    {"total_krw": "int", "largest_invoice": "str"},
    lambda p: _eq_num(p, "total_krw", T19["total_krw"])
    and str(_get(p, "largest_invoice")).strip().upper() == T19["largest_invoice"]))

# ---- nt_20 straight-line depreciation, monthly proration
C20 = [("서버", 36_480_000, 0, 3, (2024, 4)), ("업무용 차량", 43_170_000, 2_500_000, 5, (2026, 7)),
       ("사무 가구", 9_870_000, 500_000, 5, (2021, 3))]


def _dep_year(cost, salvage, life, acq, year):
    start = acq[0] * 12 + acq[1] - 1
    end = start + life * 12  # exclusive
    lo, hi = max(start, year * 12), min(end, year * 12 + 12)
    months = max(0, hi - lo)
    return (cost - salvage) * months // (life * 12)


_dep = {n: _dep_year(c, s, l, a, 2026) for n, c, s, l, a in C20}
T20 = {"dep_2026_total": sum(_dep.values()), "vehicle_book_value": 43_170_000 - _dep["업무용 차량"],
       "furniture_dep_2026": _dep["사무 가구"]}
tasks.append(_task("nt_20", "calc", (
    "고정자산 3건의 2026년 감가상각비를 정액법으로 계산해 주세요.\n\n" +
    "\n".join(f"- {n}: 취득가 {c:,}원, 잔존가치 {s:,}원, 내용연수 {l}년, 취득(사용 개시) {a[0]}년 {a[1]}월"
              for n, c, s, l, a in C20) +
    "\n\n규칙: 월할 상각합니다. 취득월을 포함하여 그 달부터 상각하고, 내용연수(년 × 12개월)가 끝나면 더 상각하지 않습니다. "
    "자산별 2026년 상각비 = (취득가 − 잔존가치) × 2026년 중 상각 개월 수 ÷ (내용연수 × 12), 원 미만 버림.\n\n"
    "3건의 2026년 상각비 합계, 업무용 차량의 2026년 말 장부가액(취득가 − 2026년 말까지 누적 상각비), "
    "사무 가구의 2026년 상각비를 알려주세요. "
    + JSON_RULE + '{"dep_2026_total": 원, "vehicle_book_value": 원, "furniture_dep_2026": 원}'),
    {"dep_2026_total": "int", "vehicle_book_value": "int", "furniture_dep_2026": "int"},
    lambda p: all(_eq_num(p, k, v) for k, v in T20.items())))

# ================================================================= code

_PY_BLOCK = re.compile(r"```[ \t]*(?:python|py|python3)[ \t]*\r?\n(.*?)```", re.S | re.I)
_SENTINEL = "NT_HIDDEN_TESTS_PASSED_7f3a"


def extract_python(answer):
    m = _PY_BLOCK.search(answer or "")
    return m.group(1) if m else None


def _run_hidden(code, tests):
    """Run model code + hidden tests in a subprocess; True only if every test passed."""
    tmp = tempfile.mkdtemp(prefix="nt_code_")
    try:
        sol = Path(tmp) / "solution.py"
        sol.write_text(code, encoding="utf-8")
        runner = Path(tmp) / "run_tests.py"
        runner.write_text(
            "import sys\n"
            f"ns = {{'__name__': 'solution'}}\n"
            f"exec(compile(open({str(sol)!r}, encoding='utf-8').read(), 'solution.py', 'exec'), ns)\n"
            + tests + f"\nprint({_SENTINEL!r})\n", encoding="utf-8")
        r = subprocess.run([sys.executable, "-I", str(runner)], cwd=tmp, timeout=10,
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        return r.returncode == 0 and r.stdout.strip().endswith(_SENTINEL)
    except (subprocess.TimeoutExpired, OSError):
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _code_task(id, prompt, tests):
    def check(answer, parsed, ws):
        code = extract_python(answer)
        return bool(code) and _run_hidden(code, tests)
    return {"id": id, "split": "notool", "domain": "code", "tools": "none",
            "prompt": prompt + "\n\n표준 라이브러리만 사용하세요. 답에는 함수 전체를 ```python 코드 블록 하나에 담아 주세요"
            "(예시 실행 코드나 input() 호출은 넣지 마세요).",
            "contract": {"type": "text"}, "check": check}


tasks.append(_code_task("nt_21", (
    "파이썬 함수 `korean_amount(s)`를 작성하세요. 한국식 금액 문자열을 정수(원)로 바꿉니다.\n"
    "- 공백은 모두 무시합니다. 맨 끝의 '원'은 있어도 되고 없어도 됩니다.\n"
    "- 나머지는 '숫자 + 단위' 조각이 이어진 형태입니다. 숫자는 0-9와 쉼표(,)로 이루어지고(쉼표는 무시), "
    "단위는 '억'(10^8), '만'(10^4), '천'(10^3) 중 하나이거나 없을 수 있습니다(없으면 1배). 단위 없는 조각은 맨 마지막에만 올 수 있습니다.\n"
    "- 각 조각의 값(숫자 × 단위)을 모두 더한 값을 반환합니다.\n"
    "- 예: '1,234원' → 1234, '3만5천원' → 35000, '12억 3,400만 500원' → 1234000500, '2억' → 200000000, '1만2,000' → 12000\n"
    "- 빈 문자열(또는 '원'만 있는 경우), 숫자가 없는 단위(예: '만원'), 허용되지 않은 문자가 있으면 ValueError를 발생시킵니다."),
    r"""
f = ns['korean_amount']
assert f('1,234원') == 1234
assert f('3만5천원') == 35000
assert f('12억 3,400만 500원') == 1234000500
assert f('2억') == 200000000
assert f('1만2,000') == 12000
assert f('  7 만 원 ') == 70000
assert f('5천') == 5000
assert f('3억5,000만') == 350000000
assert f('0원') == 0
assert f('1억 2천') == 100002000
for bad in ['', '원', '만원', 'abc', '3만x', '12$', '억5천']:
    try:
        f(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(bad)
assert type(f('3만')) is int
"""))

tasks.append(_code_task("nt_22", (
    "파이썬 함수 `business_days(start, end, holidays)`를 작성하세요.\n"
    "- start, end는 'YYYY-MM-DD' 문자열, holidays는 'YYYY-MM-DD' 문자열들의 리스트입니다.\n"
    "- start부터 end까지(양 끝 포함) 날짜 중 토요일·일요일도 아니고 holidays에도 없는 날의 수를 int로 반환합니다.\n"
    "- holidays에 중복이 있거나 주말 날짜가 있어도 한 날짜를 두 번 빼지 않습니다.\n"
    "- start가 end보다 늦으면 0을 반환합니다."),
    r"""
import datetime as dt
f = ns['business_days']
def ref(s, e, h):
    a, b = dt.date.fromisoformat(s), dt.date.fromisoformat(e)
    hs = set(h); n = 0
    while a <= b:
        if a.weekday() < 5 and a.isoformat() not in hs:
            n += 1
        a += dt.timedelta(days=1)
    return n
H = ['2026-09-24', '2026-09-25', '2026-09-26', '2026-10-03', '2026-10-05', '2026-10-09', '2026-10-09']
cases = [('2026-09-14', '2026-10-23', H), ('2026-10-03', '2026-10-04', H), ('2026-10-05', '2026-10-05', H),
         ('2026-10-06', '2026-10-06', []), ('2026-12-20', '2027-01-10', ['2026-12-25', '2027-01-01']),
         ('2028-02-25', '2028-03-03', []), ('2026-10-10', '2026-10-01', []), ('2026-01-01', '2026-12-31', H)]
for s, e, h in cases:
    got = f(s, e, list(h))
    assert got == ref(s, e, h), (s, e, got, ref(s, e, h))
assert f('2026-10-06', '2026-10-06', []) == 1
assert f('2026-10-10', '2026-10-01', []) == 0
"""))

tasks.append(_code_task("nt_23", (
    "파이썬 함수 `split_installments(total, n)`를 작성하세요.\n"
    "- total(정수, 원)을 n개월(정수)로 나눈 월별 납부액 리스트(길이 n, 원소는 int)를 반환합니다.\n"
    "- 각 달은 total // n 이고, 나머지(total % n)는 전부 첫 달에 더합니다. 예: split_installments(10, 3) → [4, 3, 3], "
    "split_installments(5, 7) → [5, 0, 0, 0, 0, 0, 0]\n"
    "- n이 1 미만이거나 total이 음수이면 ValueError를 발생시킵니다.\n"
    "- 반환 리스트의 합은 항상 total과 같아야 합니다."),
    r"""
f = ns['split_installments']
assert f(10, 3) == [4, 3, 3]
assert f(5, 7) == [5, 0, 0, 0, 0, 0, 0]
assert f(7345678, 12) == [7345678 // 12 + 7345678 % 12] + [7345678 // 12] * 11
assert f(0, 4) == [0, 0, 0, 0]
assert f(999, 1) == [999]
assert f(2000005, 6) == [333335, 333334, 333334, 333334, 333334, 333334]
r = f(10 ** 12 + 7, 9)
assert sum(r) == 10 ** 12 + 7 and len(r) == 9 and all(type(x) is int for x in r)
for args in [(100, 0), (100, -2), (-1, 3)]:
    try:
        f(*args)
    except ValueError:
        pass
    else:
        raise AssertionError(args)
"""))

tasks.append(_code_task("nt_24", (
    "파이썬 함수 `is_valid_brn(s)`를 작성하세요. 사업자등록번호 형식과 검증번호를 확인해 True/False를 반환합니다.\n"
    "- s가 문자열이 아니면 False.\n"
    "- 앞뒤 공백은 제거한 뒤, 정확히 숫자 10자리('1234567890') 또는 3-2-5 하이픈 형식('123-45-67890')만 허용합니다. 그 외 형식은 False.\n"
    "- 숫자 10자리를 d1..d10이라 할 때, 가중치 [1,3,7,1,3,7,1,3,5]로 S = Σ(d_i × w_i) (i=1..9)를 구하고, "
    "S에 (d9 × 5) // 10 을 더합니다. 검증번호 = (10 − S % 10) % 10 이 d10과 같으면 True, 아니면 False."),
    r"""
f = ns['is_valid_brn']
W = [1, 3, 7, 1, 3, 7, 1, 3, 5]
def mk(nine):
    d = [int(c) for c in nine]
    s = sum(a * b for a, b in zip(d, W)) + d[8] * 5 // 10
    return nine + str((10 - s % 10) % 10)
import random
rng = random.Random(24)
for _ in range(40):
    v = mk(''.join(str(rng.randint(0, 9)) for _ in range(9)))
    assert f(v) is True or f(v) == True, v
    assert f(v[:3] + '-' + v[3:5] + '-' + v[5:]) == True, v
    assert f('  ' + v + ' ') == True
    bad = v[:9] + str((int(v[9]) + rng.randint(1, 9)) % 10)
    assert f(bad) == False, bad
for v in ['1238123456', mk('999999999'), mk('000000009'), mk('123456789')]:
    pass
assert f(mk('123456789')) == True
assert f(mk('000000009')) == True
assert f(mk('987654329')) == True
v = mk('220812345')
for bad in [v[:2] + '-' + v[2:], v[:3] + '-' + v[3:6] + '-' + v[6:], v + '0', v[:9], v[:3] + ' ' + v[3:5] + ' ' + v[5:],
            v[:3] + '--' + v[3:], 'abcdefghij', '', '12a4567890', v[:3] + '-' + v[3:5] + v[5:]]:
    assert f(bad) == False, bad
assert f(int(v)) == False
assert f(None) == False
"""))

tasks.append(_code_task("nt_25", (
    "파이썬 함수 `occupied_minutes(bookings)`를 작성하세요. 회의실 예약 목록에서 실제로 회의실이 사용 중인 총 시간(분)을 구합니다.\n"
    "- bookings는 (시작, 종료) 튜플의 리스트이고 각 값은 'HH:MM' 문자열입니다(00:00 ~ 24:00, '24:00'은 자정 끝).\n"
    "- 겹치거나 맞닿은 예약은 합쳐서 한 번만 셉니다(합집합의 길이).\n"
    "- 종료가 시작보다 같거나 이른 예약은 무시합니다.\n"
    "- 반환값은 int(분)입니다. 빈 리스트는 0."),
    r"""
f = ns['occupied_minutes']
assert f([]) == 0
assert f([('09:00', '10:00')]) == 60
assert f([('09:00', '10:00'), ('09:30', '11:15')]) == 135
assert f([('09:00', '10:00'), ('10:00', '10:30')]) == 90
assert f([('13:00', '14:00'), ('09:00', '09:45')]) == 105
assert f([('09:00', '12:00'), ('10:00', '11:00')]) == 180
assert f([('11:00', '10:00'), ('08:00', '08:00')]) == 0
assert f([('23:30', '24:00'), ('00:00', '00:15')]) == 45
assert f([('14:10', '15:05'), ('08:55', '09:20'), ('15:00', '15:40'), ('09:10', '09:15'), ('16:00', '16:01')]) == 25 + 90 + 1
import random
rng = random.Random(25)
for _ in range(30):
    bs = []
    for _ in range(rng.randint(1, 8)):
        a = rng.randint(0, 1440); b = rng.randint(0, 1440)
        bs.append(('%02d:%02d' % divmod(a, 60), '%02d:%02d' % divmod(b, 60)))
    used = set()
    for s, e in bs:
        a = int(s[:2]) * 60 + int(s[3:]); b = int(e[:2]) * 60 + int(e[3:])
        used.update(range(a, b))
    assert f(bs) == len(used), bs
"""))

# ================================================================= logic


def _make_puzzle(cands, hidden, pool, rng):
    """pool: list of (priority, text, pred). Add true clues one at a time until exactly one
    candidate is left, preferring low priority and clues that cut at most half of the
    remaining candidates (so several mixed clues are needed); then drop redundant ones."""
    pool = [c for c in pool if c[2](hidden)]
    chosen, alive = [], list(cands)
    while len(alive) > 1:
        opts = []
        for c in pool:
            if c in chosen:
                continue
            k = sum(1 for s in alive if c[2](s))
            if k < len(alive):
                opts.append((c, k))
        for lim in (1, 2, 3):
            tier = [(c, k) for c, k in opts if c[0] <= lim]
            if tier:
                break
        mild = [c for c, k in tier if 2 * k >= len(alive)]
        c = rng.choice(mild or [c for c, _ in tier])
        chosen.append(c)
        alive = [s for s in alive if c[2](s)]
    assert alive == [hidden]
    for c in list(chosen):
        rest = [x for x in chosen if x is not c]
        if sum(1 for s in cands if all(x[2](s) for x in rest)) == 1:
            chosen = rest
    rng.shuffle(chosen)
    return chosen


def _solutions(cands, clues):
    return [s for s in cands if all(c[2](s) for c in clues)]


def _clue_text(clues):
    return "\n".join(f"{i + 1}. {c[1]}" for i, c in enumerate(clues))


# ---- nt_26 meeting rooms with capacity and floor clues
_rng = random.Random(2626)
L26_ROOMS = [("301", 3, 6), ("302", 3, 10), ("401", 4, 8), ("402", 4, 12), ("501", 5, 14)]
L26_TEAMS = [("영업팀", 7), ("개발팀", 9), ("인사팀", 4), ("재무팀", 6), ("디자인팀", 3)]
_room = {r: (f, c) for r, f, c in L26_ROOMS}
_size = dict(L26_TEAMS)
_tn = [t for t, _ in L26_TEAMS]
L26_CANDS = [dict(zip(_tn, p)) for p in itertools.permutations([r for r, _, _ in L26_ROOMS])
             if all(_room[r][1] >= _size[t] for t, r in zip(_tn, p))]
_h26 = _rng.choice(L26_CANDS)
_pool = []
for a in _tn:
    for r in _room:
        _pool.append((1, f"{a}은 {r}호를 쓰지 않는다.", lambda s, a=a, r=r: s[a] != r))
        _pool.append((3, f"{a}은 {r}호를 쓴다.", lambda s, a=a, r=r: s[a] == r))
    for fl in (3, 4, 5):
        _pool.append((2, f"{a}은 {fl}층이 아닌 회의실을 쓴다.", lambda s, a=a, fl=fl: _room[s[a]][0] != fl))
    for b in _tn:
        if a < b:
            _pool.append((0, f"{a}과 {b}은 같은 층 회의실을 쓴다.", lambda s, a=a, b=b: _room[s[a]][0] == _room[s[b]][0]))
            _pool.append((0, f"{a}과 {b}은 서로 다른 층 회의실을 쓴다.", lambda s, a=a, b=b: _room[s[a]][0] != _room[s[b]][0]))
        if a != b:
            _pool.append((0, f"{a}은 {b}보다 높은 층 회의실을 쓴다.", lambda s, a=a, b=b: _room[s[a]][0] > _room[s[b]][0]))
            _pool.append((0, f"{a} 회의실의 수용 인원은 {b} 회의실보다 많다.", lambda s, a=a, b=b: _room[s[a]][1] > _room[s[b]][1]))
L26_CLUES = _make_puzzle(L26_CANDS, _h26, _pool, _rng)
T26 = _h26
tasks.append(_task("nt_26", "logic", (
    "다음 주 워크숍에서 다섯 팀에 회의실을 하나씩 배정하려 합니다. 각 회의실에는 한 팀만 들어갑니다.\n\n[회의실]\n" +
    "\n".join(f"- {r}호: {f}층, 수용 {c}명" for r, f, c in L26_ROOMS) + "\n\n[팀 인원]\n" +
    "\n".join(f"- {t}: {n}명" for t, n in L26_TEAMS) +
    "\n\n[조건]\n0. 각 팀은 인원 이상을 수용하는 회의실에만 들어갈 수 있다.\n" + _clue_text(L26_CLUES) +
    "\n\n조건을 모두 만족하는 배정은 하나뿐입니다. 팀별 회의실 번호를 알려주세요. "
    + JSON_RULE + "{" + ", ".join(f'"{t}": "호수"' for t in _tn) + "}"),
    {t: "str" for t in _tn},
    lambda p: all(re.sub(r"\D", "", str(_get(p, t))) == T26[t] for t in _tn)))

# ---- nt_27 shift roster: 6 people into 3 shifts of 2, one senior per shift
_rng = random.Random(2727)
L27_PEOPLE = [("민준", 7), ("서윤", 2), ("도윤", 5), ("하은", 1), ("지호", 9), ("수아", 3)]
L27_SHIFTS = ["오전", "오후", "야간"]
_pn = [p for p, _ in L27_PEOPLE]
_yrs = dict(L27_PEOPLE)
L27_CANDS = []
for combo in itertools.product(range(3), repeat=6):
    if all(combo.count(k) == 2 for k in range(3)) and all(
            sum(1 for p, k in zip(_pn, combo) if k == sh and _yrs[p] >= 5) == 1 for sh in range(3)):
        L27_CANDS.append(dict(zip(_pn, combo)))
_h27 = _rng.choice(L27_CANDS)
_pool = []
for a in _pn:
    for k, sh in enumerate(L27_SHIFTS):
        _pool.append((1, f"{a} 씨는 {sh}조가 아니다.", lambda s, a=a, k=k: s[a] != k))
        _pool.append((3, f"{a} 씨는 {sh}조다.", lambda s, a=a, k=k: s[a] == k))
    for b in _pn:
        if a < b:
            _pool.append((0, f"{a} 씨와 {b} 씨는 같은 조다.", lambda s, a=a, b=b: s[a] == s[b]))
            _pool.append((0, f"{a} 씨와 {b} 씨는 다른 조다.", lambda s, a=a, b=b: s[a] != s[b]))
        if a != b:
            _pool.append((0, f"{a} 씨는 {b} 씨보다 늦은 시간대 조다(오전 < 오후 < 야간).", lambda s, a=a, b=b: s[a] > s[b]))
L27_CLUES = _make_puzzle(L27_CANDS, _h27, _pool, _rng)
T27 = {sh: sorted(p for p in _pn if _h27[p] == k) for k, sh in enumerate(L27_SHIFTS)}
tasks.append(_task("nt_27", "logic", (
    "다음 달 근무 교대표를 짜야 합니다. 여섯 명을 오전·오후·야간 세 조에 2명씩 배정합니다.\n\n[직원 경력]\n" +
    "\n".join(f"- {p}: {y}년" for p, y in L27_PEOPLE) +
    "\n\n[조건]\n0. 각 조에는 경력 5년 이상인 사람이 정확히 1명 있어야 한다.\n" + _clue_text(L27_CLUES) +
    "\n\n조건을 모두 만족하는 배정은 하나뿐입니다. 조별 인원을 알려주세요. "
    + JSON_RULE + '{"오전": ["이름", "이름"], "오후": [...], "야간": [...]}'),
    {sh: "list" for sh in L27_SHIFTS},
    lambda p: all(_eq_names(p, sh, T27[sh]) for sh in L27_SHIFTS)))

# ---- nt_28 presentation order of 6
_rng = random.Random(2828)
L28_PEOPLE = ["가람", "나래", "다솜", "라온", "마루", "바다"]
L28_CANDS = [dict(zip(L28_PEOPLE, p)) for p in itertools.permutations(range(1, 7))]
_h28 = _rng.choice(L28_CANDS)
_pool = []
for a in L28_PEOPLE:
    for k in range(1, 7):
        _pool.append((1, f"{a} 씨는 {k}번째로 발표하지 않는다.", lambda s, a=a, k=k: s[a] != k))
        _pool.append((3, f"{a} 씨는 {k}번째로 발표한다.", lambda s, a=a, k=k: s[a] == k))
    for b in L28_PEOPLE:
        if a == b:
            continue
        _pool.append((0, f"{a} 씨는 {b} 씨보다 먼저 발표한다.", lambda s, a=a, b=b: s[a] < s[b]))
        _pool.append((0, f"{a} 씨는 {b} 씨 바로 다음 순서로 발표한다.", lambda s, a=a, b=b: s[a] == s[b] + 1))
        if a < b:
            _pool.append((0, f"{a} 씨와 {b} 씨는 연달아 발표하지 않는다.", lambda s, a=a, b=b: abs(s[a] - s[b]) != 1))
            for g in (1, 2, 3):
                _pool.append((0, f"{a} 씨와 {b} 씨 사이에는 정확히 {g}명이 발표한다.",
                              lambda s, a=a, b=b, g=g: abs(s[a] - s[b]) == g + 1))
L28_CLUES = _make_puzzle(L28_CANDS, _h28, _pool, _rng)
T28 = sorted(L28_PEOPLE, key=lambda x: _h28[x])
tasks.append(_task("nt_28", "logic", (
    "분기 성과 발표회에서 여섯 명(" + ", ".join(L28_PEOPLE) + ")이 한 명씩 차례로 발표합니다(1번째 ~ 6번째).\n\n[조건]\n" +
    _clue_text(L28_CLUES) +
    "\n\n조건을 모두 만족하는 발표 순서는 하나뿐입니다. 1번째부터 6번째까지 순서대로 이름을 알려주세요. "
    + JSON_RULE + '{"order": ["1번째 이름", ..., "6번째 이름"]}'),
    {"order": "list"},
    lambda p: isinstance(_get(p, "order"), list) and [_norm(x) for x in p["order"]] == T28))

# ---- nt_29 business trips: person -> (city, month)
_rng = random.Random(2929)
L29_PEOPLE = ["윤아", "태민", "소희", "준영"]
L29_CITIES = ["부산", "광주", "대전", "강릉"]
L29_MONTHS = [9, 10, 11, 12]
L29_CANDS = [{p: (c, m) for p, c, m in zip(L29_PEOPLE, cp, mp)}
             for cp in itertools.permutations(L29_CITIES) for mp in itertools.permutations(L29_MONTHS)]
_h29 = _rng.choice(L29_CANDS)


def _who_city(s, c):
    return next(p for p in s if s[p][0] == c)


_pool = []
for a in L29_PEOPLE:
    for c in L29_CITIES:
        _pool.append((1, f"{a} 씨는 {c}에 가지 않는다.", lambda s, a=a, c=c: s[a][0] != c))
        _pool.append((3, f"{a} 씨는 {c}에 간다.", lambda s, a=a, c=c: s[a][0] == c))
    for m in L29_MONTHS:
        _pool.append((1, f"{a} 씨는 {m}월에 출장 가지 않는다.", lambda s, a=a, m=m: s[a][1] != m))
        _pool.append((3, f"{a} 씨는 {m}월에 출장 간다.", lambda s, a=a, m=m: s[a][1] == m))
    for b in L29_PEOPLE:
        if a != b:
            _pool.append((0, f"{a} 씨는 {b} 씨보다 이른 달에 출장 간다.", lambda s, a=a, b=b: s[a][1] < s[b][1]))
            _pool.append((0, f"{a} 씨는 {b} 씨가 출장 간 바로 다음 달에 출장 간다.", lambda s, a=a, b=b: s[a][1] == s[b][1] + 1))
for c in L29_CITIES:
    for m in L29_MONTHS:
        _pool.append((0, f"{c} 출장은 {m}월이다.", lambda s, c=c, m=m: s[_who_city(s, c)][1] == m))
        _pool.append((1, f"{c} 출장은 {m}월이 아니다.", lambda s, c=c, m=m: s[_who_city(s, c)][1] != m))
    for d in L29_CITIES:
        if c != d:
            _pool.append((0, f"{c} 출장은 {d} 출장보다 이른 달이다.",
                          lambda s, c=c, d=d: s[_who_city(s, c)][1] < s[_who_city(s, d)][1]))
L29_CLUES = _make_puzzle(L29_CANDS, _h29, _pool, _rng)
T29 = _h29


def _trip_ok(v, exp):
    if not isinstance(v, str):
        return False
    cities = [c for c in L29_CITIES if c in v]
    months = [int(x) for x in re.findall(r"\d+", v)]
    return cities == [exp[0]] and months == [exp[1]]


tasks.append(_task("nt_29", "logic", (
    "네 명(" + ", ".join(L29_PEOPLE) + ")이 9월~12월에 한 달에 한 명씩, 서로 다른 도시(" + ", ".join(L29_CITIES) +
    ")로 한 번씩 출장을 갑니다. 같은 달에 두 명이 가거나 같은 도시에 두 명이 가는 일은 없습니다.\n\n[조건]\n" +
    _clue_text(L29_CLUES) +
    "\n\n조건을 모두 만족하는 일정은 하나뿐입니다. 사람별 출장 도시와 달을 '도시/월' 형식으로 알려주세요. "
    + JSON_RULE + "{" + ", ".join(f'"{p}": "도시/N월"' for p in L29_PEOPLE) + "}"),
    {p: "str" for p in L29_PEOPLE},
    lambda p: all(_trip_ok(_get(p, x), T29[x]) for x in L29_PEOPLE)))

# ---- nt_30 project staffing: 7 people into 알파(3), 베타(2), 감마(2), each with a developer
_rng = random.Random(3030)
L30_PEOPLE = [("현서", "개발"), ("시우", "개발"), ("예린", "개발"), ("주원", "디자인"), ("채윤", "디자인"),
              ("건우", "기획"), ("다인", "기획")]
L30_PROJ = [("알파", 3), ("베타", 2), ("감마", 2)]
_pn30 = [p for p, _ in L30_PEOPLE]
_role = dict(L30_PEOPLE)
L30_CANDS = []
for combo in itertools.product(range(3), repeat=7):
    if all(combo.count(k) == n for k, (_, n) in enumerate(L30_PROJ)) and all(
            any(_role[p] == "개발" and k == j for p, k in zip(_pn30, combo)) for j in range(3)):
        L30_CANDS.append(dict(zip(_pn30, combo)))
_h30 = _rng.choice(L30_CANDS)
_pool = []
for a in _pn30:
    for k, (pj, _) in enumerate(L30_PROJ):
        _pool.append((1, f"{a} 씨는 {pj} 프로젝트에 들어가지 않는다.", lambda s, a=a, k=k: s[a] != k))
        _pool.append((3, f"{a} 씨는 {pj} 프로젝트에 들어간다.", lambda s, a=a, k=k: s[a] == k))
    for b in _pn30:
        if a < b:
            _pool.append((0, f"{a} 씨와 {b} 씨는 같은 프로젝트에 들어간다.", lambda s, a=a, b=b: s[a] == s[b]))
            _pool.append((0, f"{a} 씨와 {b} 씨는 서로 다른 프로젝트에 들어간다.", lambda s, a=a, b=b: s[a] != s[b]))
for k, (pj, _) in enumerate(L30_PROJ):
    _pool.append((0, f"{pj} 프로젝트에는 디자인 담당이 없다.",
                  lambda s, k=k: not any(_role[p] == "디자인" and s[p] == k for p in _pn30)))
    _pool.append((0, f"{pj} 프로젝트에는 기획 담당이 적어도 1명 있다.",
                  lambda s, k=k: any(_role[p] == "기획" and s[p] == k for p in _pn30)))
L30_CLUES = _make_puzzle(L30_CANDS, _h30, _pool, _rng)
T30 = {pj: sorted(p for p in _pn30 if _h30[p] == k) for k, (pj, _) in enumerate(L30_PROJ)}
tasks.append(_task("nt_30", "logic", (
    "일곱 명을 세 프로젝트에 배치합니다. 정원은 알파 3명, 베타 2명, 감마 2명이며 모든 사람은 정확히 한 프로젝트에 들어갑니다.\n\n[직원 직무]\n" +
    "\n".join(f"- {p}: {r}" for p, r in L30_PEOPLE) +
    "\n\n[조건]\n0. 모든 프로젝트에는 개발 직무가 적어도 1명 있어야 한다.\n" + _clue_text(L30_CLUES) +
    "\n\n조건을 모두 만족하는 배치는 하나뿐입니다. 프로젝트별 인원을 알려주세요. "
    + JSON_RULE + '{"알파": ["이름", ...], "베타": [...], "감마": [...]}'),
    {pj: "list" for pj, _ in L30_PROJ},
    lambda p: all(_eq_names(p, pj, T30[pj]) for pj, _ in L30_PROJ)))

TASKS = tasks
assert len(TASKS) == 30 and len({t["id"] for t in TASKS}) == 30
