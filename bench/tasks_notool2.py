"""Confirmation task set (notool2): everything the model needs is pasted into the prompt.

30 tasks: data 8, doc 6, calc 6, code 5, logic 5. Each task: id, split, domain, prompt (Korean,
states the answer format), tools, contract, check(answer, parsed, ws). Ground truth is computed
at import time from the same values the prompts are rendered from. Code answers run in a
subprocess, never in-process. Standard library only.
"""
import calendar
import math
import os
import random
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from fractions import Fraction
from itertools import permutations

import grade

# ================================================================= helpers

JSON_RULE = "답은 다른 설명 없이 JSON 한 줄로만 주세요: "
TEXT = {"type": "text"}


def _norm(s):
    """Names: drop spaces, corporate markers, honorifics, quotes."""
    s = str(s if s is not None else "")
    for t in ("주식회사", "(주)", "㈜", "（주）", "님", '"', "'"):
        s = s.replace(t, "")
    return re.sub(r"\s+", "", s)


def _date(s):
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", str(s or ""))
    return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}" if m else None


def _get(p, k):
    return p.get(k) if isinstance(p, dict) else None


def _num(x):
    """grade.num plus trailing Korean unit words ('9명', '105분', '3일')."""
    if isinstance(x, str):
        x = re.sub(r"[가-힣\s]+$", "", x.strip())
    return grade.num(x)


def _eq_num(p, k, expected, tol=0):
    v = _num(_get(p, k))
    return v is not None and abs(v - expected) <= tol


def _eq_name(p, k, expected):
    v = _get(p, k)
    return isinstance(v, (str, int)) and _norm(v) == _norm(expected)


def _eq_date(p, k, expected):
    return _date(_get(p, k)) == expected


def _eq_list_ordered(p, k, expected):
    v = _get(p, k)
    return isinstance(v, list) and [_norm(x) for x in v] == [_norm(x) for x in expected]


def _eq_list_set(p, k, expected):
    v = _get(p, k)
    return isinstance(v, list) and grade.same_set([_norm(x) for x in v], [_norm(x) for x in expected])


def _json_check(fn):
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


def _seeded(base, gen, ok, tries=500):
    """First seed from `base` whose generated rows satisfy `ok` (deterministic)."""
    for seed in range(base, base + tries):
        rows = gen(random.Random(seed))
        if ok(rows):
            return rows
    raise RuntimeError(f"no seed satisfied conditions from {base}")


def _rank(d):
    return sorted(d.items(), key=lambda x: (-x[1], x[0]))


def _strict_top(d, n=1):
    """Top-n keys if the first n+1 values are strictly separated, else None."""
    r = _rank(d)
    if len(r) <= n:
        return None
    for i in range(n):
        if r[i][1] == r[i + 1][1]:
            return None
    return [k for k, _ in r[:n]]


def _d(s):
    return date.fromisoformat(s)


# ================================================================= data

# ---------------------------------------------------------------- d01 물류 배송 실적
_REG = ["수도권", "충청", "호남", "영남", "강원"]
_DRV = ["권태식", "남궁민", "배상우", "서동철", "엄기현", "유재석", "조성훈", "편민호"]


def _gen_d01(rng):
    rows = []
    for _ in range(46):
        d = date(2026, 9, 21) + timedelta(days=rng.randrange(41))
        st = rng.choices(["완료", "지연", "취소"], [68, 16, 16])[0]
        rows.append([d.isoformat(), rng.choice(_REG), rng.choice(_DRV), rng.randint(5, 60), st])
    rows.sort(key=lambda r: r[0])
    return [[f"DL-{1001 + i}"] + r for i, r in enumerate(rows)]


def _d01_sum(rows, oct_only=True, drop_cancel=True):
    s = defaultdict(int)
    for r in rows:
        if oct_only and not r[1].startswith("2026-10"):
            continue
        if drop_cancel and r[5] == "취소":
            continue
        s[r[2]] += r[4]
    return s


def _ok_d01(rows):
    good = _strict_top(_d01_sum(rows))
    if not good:
        return False
    s = _d01_sum(rows)
    return (s[good[0]] != _d01_sum(rows, drop_cancel=False)[good[0]]
            and s[good[0]] != _d01_sum(rows, oct_only=False)[good[0]])


D01 = _seeded(101, _gen_d01, _ok_d01)
_s = _d01_sum(D01)
D01_REGION = _strict_top(_s)[0]
D01_BOXES = _s[D01_REGION]
D01_DELAYED = sum(1 for r in D01 if r[1].startswith("2026-10") and r[5] == "지연")

# ---------------------------------------------------------------- d02 콜센터 응대 로그
_AG = ["김하늘", "이도윤", "박서연", "최민준", "정유나", "한지호"]


def _gen_d02(rng):
    rows = []
    for i in range(42):
        res = rng.choices(["해결", "이관", "포기"], [58, 25, 17])[0]
        talk = 0 if res == "포기" else rng.randint(90, 900)
        rows.append([f"CS{26100 + i}", rng.choice(_AG), rng.choice(["전화", "채팅"]),
                     rng.randint(5, 300), talk, res])
    return rows


def _d02_avg(rows, drop_abandon=True):
    tot, cnt = defaultdict(int), defaultdict(int)
    for r in rows:
        if drop_abandon and r[5] == "포기":
            continue
        tot[r[1]] += r[4]
        cnt[r[1]] += 1
    return {a: Fraction(tot[a], cnt[a]) for a in cnt}


def _ok_d02(rows):
    a = _d02_avg(rows)
    r = _rank(a)
    if len(a) < 6 or r[0][1] - r[1][1] < 5:
        return False
    avg = r[0][1]
    if abs((avg - math.floor(avg)) - Fraction(1, 2)) < Fraction(1, 10):
        return False
    return _strict_top(_d02_avg(rows, False)) != [r[0][0]]


D02 = _seeded(201, _gen_d02, _ok_d02)
D02_AGENT = _rank(_d02_avg(D02))[0][0]
D02_AVG = _d02_avg(D02)[D02_AGENT]
D02_RESOLVED = sum(1 for r in D02 if r[1] == D02_AGENT and r[5] == "해결")

# ---------------------------------------------------------------- d03 설비 점검 기록
_LINES = ["1라인", "2라인", "3라인", "4라인", "5라인"]


def _gen_d03(rng):
    rows = []
    for _ in range(50):
        d = date(2025, 10, 1) + timedelta(days=rng.randrange(365))
        j = rng.choices(["정상", "주의", "불량"], [50, 25, 25])[0]
        dt = 0 if j == "정상" else (rng.randint(0, 40) if j == "주의" else rng.randint(30, 240))
        line = rng.choice(_LINES)
        rows.append([d.isoformat(), line, f"EQ-{_LINES.index(line) + 1}{rng.randint(1, 4):02d}", j, dt])
    rows.sort(key=lambda r: r[0])
    return [[f"IN-{i + 1:03d}"] + r for i, r in enumerate(rows)]


def _d03_sum(rows, h1=True, only_bad=True):
    s = defaultdict(int)
    for r in rows:
        if h1 and not ("2026-01-01" <= r[1] <= "2026-06-30"):
            continue
        if only_bad and r[4] != "불량":
            continue
        if r[4] == "정상":
            continue
        s[r[2]] += r[5]
    return s


def _ok_d03(rows):
    t = _strict_top(_d03_sum(rows), 2)
    return bool(t) and t != _strict_top(_d03_sum(rows, h1=False), 2) \
        and t != _strict_top(_d03_sum(rows, only_bad=False), 2)


D03 = _seeded(301, _gen_d03, _ok_d03)
D03_TOP2 = _strict_top(_d03_sum(D03), 2)
D03_DEFECTS = sum(1 for r in D03 if "2026-01-01" <= r[1] <= "2026-06-30" and r[4] == "불량")

# ---------------------------------------------------------------- d04 교육 이수 현황
_DEPT4 = ["재무팀", "생산관리팀", "품질팀", "영업지원팀", "연구소"]
_COURSE_REQ = ["정보보안 기본", "산업안전 보건", "직장 내 괴롭힘 예방", "개인정보 보호"]
_COURSE_OPT = ["엑셀 데이터 분석", "비즈니스 글쓰기", "리더십 기초"]


def _gen_d04(rng):
    rows = []
    for i in range(52):
        req = rng.random() < 0.65
        course = rng.choice(_COURSE_REQ if req else _COURSE_OPT)
        done = "Y" if rng.random() < (0.72 if req else 0.5) else "N"
        rows.append([f"E{2301 + i}", rng.choice(_DEPT4), course, "필수" if req else "선택", done])
    return rows


def _d04_rate(rows, req_only=True):
    tot, ok = defaultdict(int), defaultdict(int)
    for r in rows:
        if req_only and r[3] != "필수":
            continue
        tot[r[1]] += 1
        ok[r[1]] += r[4] == "Y"
    return {d: Fraction(ok[d], tot[d]) for d in tot}


def _ok_d04(rows):
    a = _d04_rate(rows)
    if len(a) < 5:
        return False
    if min(sum(1 for r in rows if r[1] == d and r[3] == "필수") for d in _DEPT4) < 4:
        return False
    low = sorted(a.items(), key=lambda x: x[1])
    if low[0][1] == low[1][1]:
        return False
    b = sorted(_d04_rate(rows, False).items(), key=lambda x: x[1])
    return b[0][0] != low[0][0]


D04 = _seeded(401, _gen_d04, _ok_d04)
D04_DEPT = sorted(_d04_rate(D04).items(), key=lambda x: x[1])[0][0]
D04_INCOMPLETE = sum(1 for r in D04 if r[1] == D04_DEPT and r[3] == "필수" and r[4] == "N")

# ---------------------------------------------------------------- d05 출장 경비 정산
_DEPT5 = ["해외영업팀", "기술지원팀", "구매팀", "품질보증팀", "설치시공팀", "경영기획팀"]
_EMP5 = ["고은비", "나태준", "도민혁", "류지아", "마성진", "백하윤", "석준우", "양소희", "육재민", "진다인"]
_ITEM5 = {"교통": (15000, 320000), "숙박": (60000, 180000), "식대": (8000, 60000), "기타": (5000, 90000)}


def _gen_d05(rng):
    rows = []
    for i in range(45):
        it = rng.choice(list(_ITEM5))
        lo, hi = _ITEM5[it]
        st = rng.choices(["승인", "반려", "취소"], [68, 16, 16])[0]
        rows.append([f"TR-26{i + 101:04d}", rng.choice(_EMP5), rng.choice(_DEPT5), it,
                     rng.randint(lo // 100, hi // 100) * 100, st])
    return rows


def _d05_sum(rows, approved_only=True):
    s = defaultdict(int)
    for r in rows:
        if approved_only and r[5] != "승인":
            continue
        s[r[2]] += r[4]
    return s


def _ok_d05(rows):
    t = _strict_top(_d05_sum(rows), 3)
    lodging = [r for r in rows if r[3] == "숙박"]
    return (bool(t) and t != _strict_top(_d05_sum(rows, False), 3)
            and any(r[5] != "승인" for r in lodging) and any(r[5] == "승인" for r in lodging))


D05 = _seeded(501, _gen_d05, _ok_d05)
D05_TOP3 = _strict_top(_d05_sum(D05), 3)
D05_LODGING = sum(r[4] for r in D05 if r[5] == "승인" and r[3] == "숙박")

# ---------------------------------------------------------------- d06 구독 매출
_PLAN = {"Basic": 19000, "Pro": 49000, "Enterprise": 199000}


def _gen_d06(rng):
    rows = []
    for _ in range(48):
        m = rng.choice(["2026-06", "2026-07", "2026-08", "2026-09", "2026-10"])
        p = rng.choices(list(_PLAN), [45, 40, 15])[0]
        seats = rng.randint(1, 3) if p == "Enterprise" else rng.randint(1, 12)
        st = rng.choices(["정상", "환불"], [84, 16])[0]
        rows.append([m, f"C{rng.randint(1, 16):03d}", p, seats, _PLAN[p] * seats, st])
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows


def _d06_sum(rows, q3=True, drop_refund=True):
    s = defaultdict(int)
    for r in rows:
        if q3 and r[0] not in ("2026-07", "2026-08", "2026-09"):
            continue
        if drop_refund and r[5] == "환불":
            continue
        s[r[2]] += r[4]
    return s


def _ok_d06(rows):
    t = _strict_top(_d06_sum(rows))
    if not t:
        return False
    v = _d06_sum(rows)[t[0]]
    return (_strict_top(_d06_sum(rows, drop_refund=False)) != t
            and v != _d06_sum(rows, q3=False)[t[0]]
            and sum(1 for r in rows if r[0] in ("2026-07", "2026-08", "2026-09") and r[5] == "환불") >= 3)


D06 = _seeded(601, _gen_d06, _ok_d06)
D06_PLAN = _strict_top(_d06_sum(D06))[0]
D06_REV = _d06_sum(D06)[D06_PLAN]
D06_REFUND_CUST = len({r[1] for r in D06 if r[0] in ("2026-07", "2026-08", "2026-09") and r[5] == "환불"})

# ---------------------------------------------------------------- d07 반품 처리
_SKU = {"HB-201": 32900, "HB-305": 18500, "KT-110": 64000, "KT-220": 27800, "MG-050": 9900, "MG-090": 45500}


def _gen_d07(rng):
    rows = []
    for i in range(40):
        d = date(2026, 8, 1) + timedelta(days=rng.randrange(61))
        sku = rng.choice(list(_SKU))
        why = rng.choices(["불량", "단순변심", "오배송"], [40, 35, 25])[0]
        st = rng.choices(["완료", "보류", "취소"], [70, 15, 15])[0]
        rows.append([d.isoformat(), sku, why, rng.randint(1, 8), _SKU[sku], st])
    rows.sort(key=lambda r: r[0])
    return [[f"RT-{8801 + i}"] + r for i, r in enumerate(rows)]


def _d07_sum(rows, done_only=True):
    s = defaultdict(int)
    for r in rows:
        if r[3] != "불량" or (done_only and r[6] != "완료"):
            continue
        s[r[2]] += r[4] * r[5]
    return s


def _ok_d07(rows):
    t = _strict_top(_d07_sum(rows))
    return bool(t) and _strict_top(_d07_sum(rows, False)) != t


D07 = _seeded(701, _gen_d07, _ok_d07)
D07_SKU = _strict_top(_d07_sum(D07))[0]
D07_REFUND = _d07_sum(D07)[D07_SKU]
D07_MISSHIP = sum(r[4] for r in D07 if r[3] == "오배송" and r[6] == "완료")

# ---------------------------------------------------------------- d08 프로젝트 마일스톤
_PROJ = ["알파", "베가", "시리우스", "오리온", "카노푸스", "리겔"]
_TEAM = ["플랫폼팀", "데이터팀", "모바일팀", "인프라팀"]
_MS = ["요구사항 확정", "설계 리뷰", "개발 완료", "통합 테스트", "사용자 테스트", "오픈"]
D08_ASOF = "2026-10-15"


def _gen_d08(rng):
    rows = []
    for p in _PROJ:
        for m in rng.sample(_MS, 6):
            due = date(2026, 8, 1) + timedelta(days=rng.randrange(92))
            fin = ""
            if rng.random() < 0.75:
                f = due + timedelta(days=rng.randint(-6, 9))
                if f <= _d(D08_ASOF):
                    fin = f.isoformat()
            note = "취소" if rng.random() < 0.1 else ""
            rows.append([p, m, rng.choice(_TEAM), due.isoformat(), fin, note])
    rng.shuffle(rows)
    return rows[:40]


def _d08_late(r, count_open=True):
    if r[4]:
        return r[4] > r[3]
    return count_open and r[3] < D08_ASOF


def _d08_cnt(rows, count_open=True, drop_cancel=True):
    s = defaultdict(int)
    for r in rows:
        if drop_cancel and r[5] == "취소":
            continue
        if _d08_late(r, count_open):
            s[r[2]] += 1
    return s


def _ok_d08(rows):
    t = _strict_top(_d08_cnt(rows))
    if not t:
        return False
    tot = sum(_d08_cnt(rows).values())
    return (tot != sum(_d08_cnt(rows, count_open=False).values())
            and tot != sum(_d08_cnt(rows, drop_cancel=False).values())
            and _strict_top(_d08_cnt(rows, count_open=False)) != t
            and any(r[3] == D08_ASOF and not r[4] for r in rows))


D08 = _seeded(801, _gen_d08, _ok_d08)
D08_TEAM = _strict_top(_d08_cnt(D08))[0]
D08_TOTAL = sum(_d08_cnt(D08).values())

DATA_TASKS = [
    dict(id="nt2_01", domain="data", prompt=(
        "물류팀 배송 실적 시트를 붙여 넣습니다. 2026년 10월(10-01 ~ 10-31) 배송만 보고, 상태가 '취소'인 건은 빼 주세요"
        "(완료·지연은 포함). 이 기준으로 권역별 박스수 합계가 가장 큰 권역과 그 합계, 그리고 10월에 상태가 '지연'인 "
        "배송 건수를 알려 주세요. 9월 말 데이터도 섞여 있으니 주의하세요.\n\n"
        + _csv(["배송번호", "일자", "권역", "기사", "박스수", "상태"], D01) + "\n\n"
        + JSON_RULE + '{"region": 권역명, "boxes": 박스수 합계(정수), "delayed": 지연 건수(정수)}'),
        contract={"type": "json", "keys": {"region": "str", "boxes": "int", "delayed": "int"}},
        check=_json_check(lambda p: _eq_name(p, "region", D01_REGION) and _eq_num(p, "boxes", D01_BOXES)
                          and _eq_num(p, "delayed", D01_DELAYED))),
    dict(id="nt2_02", domain="data", prompt=(
        "콜센터 응대 로그입니다. 결과가 '포기'인 건(고객이 연결 전에 끊음, 통화초 0)은 제외하고, 상담원별 평균 통화시간"
        "(통화초의 평균)을 구했을 때 평균이 가장 긴 상담원, 그 평균(초, 소수점 첫째 자리에서 반올림한 정수), "
        "그리고 그 상담원의 결과 '해결' 건수를 알려 주세요.\n\n"
        + _csv(["접수ID", "상담원", "채널", "대기초", "통화초", "결과"], D02) + "\n\n"
        + JSON_RULE + '{"agent": 상담원 이름, "avg_sec": 평균 통화초(정수), "resolved": 해결 건수(정수)}'),
        contract={"type": "json", "keys": {"agent": "str", "avg_sec": "int", "resolved": "int"}},
        check=_json_check(lambda p: _eq_name(p, "agent", D02_AGENT) and _eq_num(p, "avg_sec", float(D02_AVG), 1)
                          and _eq_num(p, "resolved", D02_RESOLVED))),
    dict(id="nt2_03", domain="data", prompt=(
        "생산기술팀 설비 점검 기록입니다. 2026년 상반기(2026-01-01 ~ 2026-06-30) 점검 중 판정이 '불량'인 건만 대상으로, "
        "라인별 다운타임(분) 합계를 구해 합계가 큰 순서로 상위 2개 라인을 알려 주세요. 판정 '주의'는 넣지 마세요. "
        "또 같은 기간 '불량' 판정 건수도 알려 주세요.\n\n"
        + _csv(["점검번호", "점검일", "라인", "설비", "판정", "다운타임분"], D03) + "\n\n"
        + JSON_RULE + '{"top_lines": [1위 라인, 2위 라인], "defects": 불량 건수(정수)}'),
        contract={"type": "json", "keys": {"top_lines": "list", "defects": "int"}},
        check=_json_check(lambda p: _eq_list_ordered(p, "top_lines", D03_TOP2) and _eq_num(p, "defects", D03_DEFECTS))),
    dict(id="nt2_04", domain="data", prompt=(
        "인사팀 교육 이수 현황입니다. 구분이 '필수'인 과정만 대상으로, 부서별 이수율(이수 Y 건수 ÷ 해당 부서 필수 과정 "
        "전체 건수)을 계산해 이수율이 가장 낮은 부서와, 그 부서의 필수 과정 미이수(N) 건수를 알려 주세요. "
        "'선택' 과정은 계산에서 빼야 합니다.\n\n"
        + _csv(["사번", "부서", "과정", "구분", "이수"], D04) + "\n\n"
        + JSON_RULE + '{"dept": 부서명, "incomplete": 미이수 건수(정수)}'),
        contract={"type": "json", "keys": {"dept": "str", "incomplete": "int"}},
        check=_json_check(lambda p: _eq_name(p, "dept", D04_DEPT) and _eq_num(p, "incomplete", D04_INCOMPLETE))),
    dict(id="nt2_05", domain="data", prompt=(
        "출장 경비 정산 신청 목록입니다. 상태가 '승인'인 건만 집계해 주세요('반려'·'취소'는 제외). 부서별 승인 금액 "
        "합계가 큰 순서로 상위 3개 부서를 순서대로, 그리고 항목이 '숙박'인 승인 건의 금액 합계를 알려 주세요.\n\n"
        + _csv(["신청번호", "직원", "부서", "항목", "금액", "상태"], D05) + "\n\n"
        + JSON_RULE + '{"top3": [1위 부서, 2위 부서, 3위 부서], "lodging": 숙박 승인 합계(원, 정수)}'),
        contract={"type": "json", "keys": {"top3": "list", "lodging": "int"}},
        check=_json_check(lambda p: _eq_list_ordered(p, "top3", D05_TOP3) and _eq_num(p, "lodging", D05_LODGING))),
    dict(id="nt2_06", domain="data", prompt=(
        "SaaS 구독 청구 내역입니다. 3분기(청구월 2026-07, 2026-08, 2026-09)만 보고, 상태 '환불'인 행은 매출에서 "
        "제외합니다. 플랜별 매출(금액 합계)이 가장 큰 플랜과 그 매출, 그리고 3분기에 '환불' 행이 하나라도 있는 "
        "고객ID 수(중복 없이)를 알려 주세요. 6월·10월 행도 섞여 있습니다.\n\n"
        + _csv(["청구월", "고객ID", "플랜", "좌석수", "금액", "상태"], D06) + "\n\n"
        + JSON_RULE + '{"plan": 플랜명, "revenue": 매출(원, 정수), "refund_customers": 고객 수(정수)}'),
        contract={"type": "json", "keys": {"plan": "str", "revenue": "int", "refund_customers": "int"}},
        check=_json_check(lambda p: _norm(_get(p, "plan")).lower() == D06_PLAN.lower()
                          and _eq_num(p, "revenue", D06_REV) and _eq_num(p, "refund_customers", D06_REFUND_CUST))),
    dict(id="nt2_07", domain="data", prompt=(
        "CS팀 반품 처리 대장입니다. 처리상태가 '완료'인 건만 봅니다('보류'·'취소' 제외). 사유가 '불량'인 반품의 환불액"
        "(수량 × 단가)을 상품코드별로 합쳐 가장 큰 상품코드와 그 금액, 그리고 사유 '오배송'인 완료 건의 수량 합계를 "
        "알려 주세요.\n\n"
        + _csv(["반품번호", "접수일", "상품코드", "사유", "수량", "단가", "처리상태"], D07) + "\n\n"
        + JSON_RULE + '{"sku": 상품코드, "refund": 환불액 합계(원, 정수), "misship_qty": 오배송 수량 합계(정수)}'),
        contract={"type": "json", "keys": {"sku": "str", "refund": "int", "misship_qty": "int"}},
        check=_json_check(lambda p: _norm(_get(p, "sku")).upper() == D07_SKU and _eq_num(p, "refund", D07_REFUND)
                          and _eq_num(p, "misship_qty", D07_MISSHIP))),
    dict(id="nt2_08", domain="data", prompt=(
        f"PMO 마일스톤 현황입니다. 기준일은 {D08_ASOF}입니다. 비고가 '취소'인 마일스톤은 제외합니다. 지연의 정의: "
        "완료일이 있으면 완료일이 예정일보다 늦은 경우(같은 날은 지연 아님), 완료일이 비어 있으면 예정일이 기준일보다 "
        "이전인 경우(예정일이 기준일 당일이거나 이후면 지연 아님). 담당팀별 지연 마일스톤 수가 가장 많은 팀과, "
        "전체 지연 마일스톤 수를 알려 주세요.\n\n"
        + _csv(["프로젝트", "마일스톤", "담당팀", "예정일", "완료일", "비고"], D08) + "\n\n"
        + JSON_RULE + '{"team": 팀명, "delayed_total": 전체 지연 수(정수)}'),
        contract={"type": "json", "keys": {"team": "str", "delayed_total": "int"}},
        check=_json_check(lambda p: _eq_name(p, "team", D08_TEAM) and _eq_num(p, "delayed_total", D08_TOTAL))),
]

# ================================================================= doc

# ---------------------------------------------------------------- doc01 MOU
M_TOTAL = 1_860_000_000
M_SHARE_DRAFT, M_SHARE_FINAL = 60, 55
M_SIGN = date(2026, 11, 18)
M_TERM_DRAFT, M_TERM_FINAL = 2, 3
M_START = date(M_SIGN.year + (M_SIGN.month == 12), M_SIGN.month % 12 + 1, 1)
M_END = date(M_START.year + M_TERM_FINAL, M_START.month, 1) - timedelta(days=1)
M_A_AMOUNT = M_TOTAL * M_SHARE_FINAL // 100
DOC01 = f"""[업무협약서(MOU) — 서명본 검토용]

주식회사 한빛에너지(이하 "갑")와 주식회사 그린모빌리티랩(이하 "을")은 전기버스 충전 인프라 공동 실증 사업(이하 "본 사업")을 위하여 다음과 같이 업무협약을 체결한다.

제1조(목적) 본 협약은 갑과 을이 본 사업을 공동 수행하는 데 필요한 역할과 비용 분담을 정함을 목적으로 한다.
제2조(역할) 갑은 충전 설비 부지와 전력 계통 연계를 제공하고, 을은 충전 관제 소프트웨어와 차량 데이터 연동을 담당한다.
제3조(사업비) 본 사업의 총 사업비는 금 {M_TOTAL:,}원(부가가치세 별도)으로 한다.
제4조(비용 분담) 총 사업비는 갑 {M_SHARE_DRAFT}%, 을 {100 - M_SHARE_DRAFT}%의 비율로 분담한다.
제5조(협약기간) 협약기간은 효력 발생일로부터 {M_TERM_DRAFT}년으로 한다.
제6조(효력 발생) 본 협약은 양 당사자가 서명한 날이 속한 달의 다음 달 1일부터 효력이 발생한다.
제7조(비밀유지) 양 당사자는 본 사업 수행 중 알게 된 상대방의 영업비밀을 제3자에게 누설하지 아니한다.

서명일: {M_SIGN.year}년 {M_SIGN.month}월 {M_SIGN.day}일

---- 실무 협의 메모 (서명 직전, 양사 법무 확인 완료) ----
1. 을 측이 제안한 '을 50% 분담안'은 갑 이사회에서 부결되었음. 대신 제4조를 갑 {M_SHARE_FINAL}%, 을 {100 - M_SHARE_FINAL}%로 수정하는 것으로 최종 합의함.
2. 제5조 협약기간은 실증 데이터 축적 기간을 고려해 {M_TERM_FINAL}년으로 수정함.
3. 제6조는 원안대로 유지함.
4. 위 수정 사항은 서명본에 반영됨."""

# ---------------------------------------------------------------- doc02 하도급 계약
S_AMOUNT = 742_000_000
S_VAT_INCL = S_AMOUNT * 11 // 10
S_ADV_REQ, S_ADV_FINAL = 30, 20
S_ADVANCE = S_VAT_INCL * S_ADV_FINAL // 100
S_RATE_DRAFT, S_RATE_FINAL = "0.15", "0.1"
S_DUE, S_DONE = date(2027, 3, 31), date(2027, 4, 14)
S_DELAY = (S_DONE - S_DUE).days
S_PENALTY = min(S_VAT_INCL * S_DELAY // 1000, S_VAT_INCL // 10)
DOC02 = f"""[건설공사 하도급 계약 주요 조건 및 협상 경과]

원사업자: (주)대성건설
수급사업자: (주)동해설비
공사명: 판교 R&D센터 신축공사 중 기계설비공사

1. 하도급 계약금액: 금 {S_AMOUNT:,}원 (부가가치세 별도). 부가가치세는 10%이며, 아래 2·4항의 '계약금액'은 부가가치세를 포함한 금액을 말한다.
2. 선급금: 수급사업자는 계약금액의 {S_ADV_REQ}%를 선급금으로 요청하였으나 원사업자는 자금 집행 계획상 수용하지 않았고, 양측은 계약금액의 {S_ADV_FINAL}%로 확정하였다.
3. 공사기간: 2026년 11월 2일 착공, 준공 예정일 {S_DUE.year}년 {S_DUE.month}월 {S_DUE.day}일.
4. 지체상금: 초안에는 1일당 계약금액의 {S_RATE_DRAFT}%로 기재되었으나, 표준하도급계약서 기준에 맞춰 1일당 계약금액의 {S_RATE_FINAL}%로 정정한다. 지체상금 총액은 계약금액의 10%를 한도로 한다. 지체일수는 준공 예정일 다음 날부터 실제 준공일까지의 일수로 한다.
5. 하자담보책임기간: 준공일로부터 2년.

[준공 결과 보고]
실제 준공일은 {S_DONE.year}년 {S_DONE.month}월 {S_DONE.day}일로 확인되었으며, 공기 연장 승인 내역은 없다. 지체상금은 원 단위 미만을 버린다."""

# ---------------------------------------------------------------- doc03 인사 공지 + 정정
H_ORIG = {"차장": ["오세훈", "김민정"], "과장": ["이준호", "박지훈", "최수아", "정다은"],
          "대리": ["한결", "윤서진", "강도현"]}
H_FINAL = {"차장": ["오세훈", "김민정"], "과장": ["이준호", "박지환", "정다은"],
           "대리": ["한결", "윤서진", "강도현", "문채원"]}
H_DATE_ORIG, H_DATE_FINAL = "2027-01-01", "2027-01-04"
H_TOTAL = sum(len(v) for v in H_FINAL.values())
DOC03 = f"""[인사 공지] 2027년 정기 승진 발령 안내

2027년 정기 승진 심사 결과를 아래와 같이 발령합니다.
발령일: 2027년 1월 1일

■ 차장 승진: {", ".join(H_ORIG["차장"])}
■ 과장 승진: {", ".join(H_ORIG["과장"])}
■ 대리 승진: {", ".join(H_ORIG["대리"])}

승진자 여러분께 축하의 말씀을 드립니다. — 인사팀

==========

[정정 공지] 2027년 정기 승진 발령 안내 정정

앞서 게시한 승진 발령 공지에 일부 오류가 있어 다음과 같이 정정합니다.
1. 발령일: 1월 1일은 공휴일이고 이어지는 주말을 고려하여 2027년 1월 4일(월)로 정정합니다.
2. 과장 승진자 '박지훈'은 '박지환'의 오기입니다.
3. 과장 승진 대상자 중 최수아 님은 해외 법인 파견 일정에 따라 본인 요청으로 승진 심사가 다음 회차로 보류되었습니다. 이번 발령 명단에서 제외합니다.
4. 대리 승진 명단에 문채원 님이 누락되어 추가합니다.
그 외 내용은 기존 공지와 같습니다. — 인사팀"""

# ---------------------------------------------------------------- doc04 보안 사고 보고서
B_DETECT = datetime(2026, 9, 3, 2, 47)
B_LOCK = datetime(2026, 9, 3, 4, 5)
B_BLOCK = datetime(2026, 9, 3, 4, 32)
B_MIN = int((B_BLOCK - B_DETECT).total_seconds() // 60)
B_EST, B_DEDUP, B_TEST = 12_400, 8_315, 215
B_CUST = B_DEDUP - B_TEST
B_SEV = "1등급" if B_CUST >= 10_000 else "2등급"
DOC04 = f"""[보안 사고 보고서 — 1차]
작성: 정보보호팀 / 2026-09-03 09:30

1. 개요: 고객 포인트 조회 API에 대한 비정상 대량 조회가 발생함.
2. 최초 탐지: {B_DETECT:%Y-%m-%d %H:%M} (SIEM 임계치 알림)
3. 조치: {B_LOCK:%H:%M} 공격에 사용된 API 계정 잠금, 같은 시각 차단 완료로 판단.
4. 유출 의심 레코드: 접근 로그 기준 약 {B_EST:,}건(추정).
5. 민감정보 포함 여부: 조사 중.

[보안 사고 보고서 — 2차(정정)]
작성: 정보보호팀 / 2026-09-05 17:00

1차 보고 내용 중 다음 사항을 정정합니다.
- 차단 시각: {B_LOCK:%H:%M}은 API 계정 잠금 시각이며, 공격자가 다른 세션 토큰으로 계속 조회한 사실이 확인되었습니다. 방화벽에서 출발지 IP 대역을 차단해 조회가 실제로 멈춘 시각은 {B_BLOCK:%H:%M}입니다. 노출 시간은 최초 탐지 시각부터 실제 차단 시각까지로 산정합니다.
- 유출 의심 레코드: 포렌식 결과 중복 조회를 제거하면 {B_DEDUP:,}건이며, 이 중 {B_TEST:,}건은 QA용 테스트 계정이므로 고객 레코드에서 제외합니다.
- 민감정보 포함 여부: 이름과 포인트 잔액만 조회되었고 주민등록번호·카드번호 등 민감정보는 포함되지 않았습니다.

[참고: 사내 보안사고 등급 기준]
- 1등급: 영향받은 고객 레코드 10,000건 이상이거나 민감정보 포함
- 2등급: 영향받은 고객 레코드 10,000건 미만이고 민감정보 미포함"""

# ---------------------------------------------------------------- doc05 고객 클레임 메일 스레드
C_ORDER, C_QTY, C_PRICE = "PO-2026-08817", 1200, 4350
C_DEF_FIRST, C_DEF_FINAL = 40, 36
C_CREDIT = C_DEF_FINAL * C_PRICE * 12 // 10
C_OCT = 9_860_000
C_OCT_NET = C_OCT - C_CREDIT
DOC05 = f"""보낸사람: 정해린 (세림푸드 구매팀)
받는사람: 오태경 (청우패키징 품질팀)
제목: [클레임] {C_ORDER} 용기 뚜껑 변형 건
9월 22일 입고된 {C_ORDER} (식품 용기 {C_QTY:,}개, 단가 {C_PRICE:,}원) 중 뚜껑 변형 불량이 {C_DEF_FIRST}개 발견되었습니다. 처리 방안 부탁드립니다.

---
보낸사람: 오태경 (청우패키징 품질팀)
제목: RE: [클레임] {C_ORDER} 용기 뚜껑 변형 건
불편을 드려 죄송합니다. 두 가지 안을 드립니다.
A안: 불량 수량만큼 10월 둘째 주에 재납품
B안: 재납품 대신 불량 수량 × 단가의 120%를 크레딧으로 제공(원 미만 절사), 다음 달 청구서에서 차감

---
보낸사람: 정해린 (세림푸드 구매팀)
제목: RE: RE: [클레임] {C_ORDER} 용기 뚜껑 변형 건
A안은 저희 생산 일정상 10월 둘째 주 입고가 어려워 진행이 곤란합니다. B안으로 진행하겠습니다.
그리고 저희가 재검수해 보니 처음 보고한 {C_DEF_FIRST}개 중 {C_DEF_FIRST - C_DEF_FINAL}개는 운송 중 생긴 외부 박스 손상이라 제품 불량이 아니었습니다. 최종 불량 수량은 {C_DEF_FINAL}개로 정정합니다.

---
보낸사람: 오태경 (청우패키징 품질팀)
제목: RE: RE: RE: [클레임] {C_ORDER} 용기 뚜껑 변형 건
확인 감사합니다. 정정된 수량 기준 B안으로 처리하겠습니다. 10월 청구 예정액 {C_OCT:,}원에서 크레딧을 차감해 청구서를 발행하겠습니다."""

# ---------------------------------------------------------------- doc06 규정 개정 대비표
R_PER_DIEM_OLD, R_PER_DIEM_NEW = 25_000, 30_000
R_MEAL_OLD, R_MEAL_NEW = 30_000, 36_000          # withdrawn
R_SEOUL_OLD, R_SEOUL_PROP, R_SEOUL_FINAL = 100_000, 120_000, 110_000
R_OTHER_OLD, R_OTHER_NEW = 80_000, 90_000
R_EFF_PROP, R_EFF_FINAL = "2027-01-01", "2027-02-01"
R_AMENDED = ["제5조", "제7조", "제9조", "제11조"]
R_TRIP = R_PER_DIEM_NEW * 3 + R_MEAL_OLD * 3 + R_SEOUL_FINAL * 2
DOC06 = f"""[국내외 출장여비 규정 개정(안) 신·구 대비표]

| 조항 | 현행 | 개정안 | 비고 |
| 제5조(국내 일비) | 1일 {R_PER_DIEM_OLD:,}원 | 1일 {R_PER_DIEM_NEW:,}원 | 물가 반영 |
| 제6조(국내 식비) | 1일 {R_MEAL_OLD:,}원 | 1일 {R_MEAL_NEW:,}원 | 법인카드 식대와 중복 검토 필요 |
| 제7조(국내 숙박비) | 서울 1박 {R_SEOUL_OLD:,}원 / 그 외 1박 {R_OTHER_OLD:,}원 | 서울 1박 {R_SEOUL_PROP:,}원 / 그 외 1박 {R_OTHER_NEW:,}원 | 실비 상한 |
| 제9조(정산 기한) | 출장 종료 후 14일 이내 | 출장 종료 후 10영업일 이내 | |
| 제11조(해외 일비) | 1일 USD 50 | 1일 USD 60 | |
| 부칙(시행일) | - | {R_EFF_PROP} | |

[규정심의위원회 의결 결과]
1. 제6조 개정안은 법인카드 식대와 중복 지급 우려로 철회한다(현행 유지).
2. 제7조 서울 숙박비는 개정안 {R_SEOUL_PROP:,}원 대신 {R_SEOUL_FINAL:,}원으로 수정 의결한다. 그 외 지역은 개정안대로 한다.
3. 시행일은 전산 반영 일정을 고려해 {R_EFF_FINAL}로 변경한다.
4. 나머지 조항은 개정안대로 의결한다."""

DOC_TASKS = [
    dict(id="nt2_09", domain="doc", prompt=(
        "아래 MOU 서명본 검토 자료를 보고 최종 확정된 내용으로 답해 주세요. 협약 상대방(을)의 회사명, 갑이 부담할 "
        "사업비(원), 협약 효력 발생일, 협약 종료일(효력 발생일부터 협약기간이 끝나는 전날)을 알려 주세요.\n\n"
        + DOC01 + "\n\n"
        + JSON_RULE + '{"partner": 을 회사명, "party_a_cost": 갑 부담액(원, 정수), "start_date": "YYYY-MM-DD", '
        '"end_date": "YYYY-MM-DD"}'),
        contract={"type": "json", "keys": {"partner": "str", "party_a_cost": "int", "start_date": "str", "end_date": "str"}},
        check=_json_check(lambda p: _eq_name(p, "partner", "그린모빌리티랩") and _eq_num(p, "party_a_cost", M_A_AMOUNT)
                          and _eq_date(p, "start_date", M_START.isoformat())
                          and _eq_date(p, "end_date", M_END.isoformat()))),
    dict(id="nt2_10", domain="doc", prompt=(
        "하도급 계약 검토 자료입니다. 확정된 조건 기준으로 선급금 금액, 지체일수, 지체상금 금액을 계산해 주세요. "
        "수급사업자 회사명도 함께 알려 주세요.\n\n"
        + DOC02 + "\n\n"
        + JSON_RULE + '{"subcontractor": 회사명, "advance": 선급금(원, 정수), "delay_days": 지체일수(정수), '
        '"penalty": 지체상금(원, 정수)}'),
        contract={"type": "json", "keys": {"subcontractor": "str", "advance": "int", "delay_days": "int", "penalty": "int"}},
        check=_json_check(lambda p: _eq_name(p, "subcontractor", "동해설비") and _eq_num(p, "advance", S_ADVANCE)
                          and _eq_num(p, "delay_days", S_DELAY) and _eq_num(p, "penalty", S_PENALTY))),
    dict(id="nt2_11", domain="doc", prompt=(
        "인사 공지와 정정 공지를 함께 붙입니다. 정정 내용을 반영한 최종 기준으로 발령일, 과장 승진자 명단, "
        "전체 승진자 수(모든 직급 합계)를 알려 주세요.\n\n"
        + DOC03 + "\n\n"
        + JSON_RULE + '{"effective_date": "YYYY-MM-DD", "managers": ["이름", ...], "total_promoted": 인원(정수)}'),
        contract={"type": "json", "keys": {"effective_date": "str", "managers": "list", "total_promoted": "int"}},
        check=_json_check(lambda p: _eq_date(p, "effective_date", H_DATE_FINAL)
                          and _eq_list_set(p, "managers", H_FINAL["과장"])
                          and _eq_num(p, "total_promoted", H_TOTAL))),
    dict(id="nt2_12", domain="doc", prompt=(
        "보안 사고 보고서 1차·2차를 붙입니다. 정정된 내용을 기준으로 최초 탐지 시각, 노출 시간(분), 영향받은 고객 "
        "레코드 수, 사내 기준에 따른 사고 등급을 알려 주세요.\n\n"
        + DOC04 + "\n\n"
        + JSON_RULE + '{"detected_at": "YYYY-MM-DD HH:MM", "exposure_minutes": 분(정수), '
        '"customer_records": 건수(정수), "severity": "1등급" 또는 "2등급"}'),
        contract={"type": "json", "keys": {"detected_at": "str", "exposure_minutes": "int",
                                           "customer_records": "int", "severity": "str"}},
        check=_json_check(lambda p: re.sub(r"\D", "", str(_get(p, "detected_at")))[:12] == f"{B_DETECT:%Y%m%d%H%M}"
                          and _eq_num(p, "exposure_minutes", B_MIN) and _eq_num(p, "customer_records", B_CUST)
                          and re.sub(r"\D", "", str(_get(p, "severity"))) == B_SEV[0])),
    dict(id="nt2_13", domain="doc", prompt=(
        "고객 클레임 메일 스레드입니다. 최종 합의 기준으로 주문번호, 최종 불량 수량, 합의된 처리안(A 또는 B), "
        "크레딧 금액, 크레딧 차감 후 10월 청구액을 알려 주세요.\n\n"
        + DOC05 + "\n\n"
        + JSON_RULE + '{"order_no": 주문번호, "defect_qty": 수량(정수), "option": "A" 또는 "B", '
        '"credit": 크레딧(원, 정수), "october_invoice": 차감 후 청구액(원, 정수)}'),
        contract={"type": "json", "keys": {"order_no": "str", "defect_qty": "int", "option": "str",
                                           "credit": "int", "october_invoice": "int"}},
        check=_json_check(lambda p: _norm(_get(p, "order_no")).upper() == C_ORDER
                          and _eq_num(p, "defect_qty", C_DEF_FINAL)
                          and re.sub(r"[^AB]", "", str(_get(p, "option")).upper().replace("안", "")) == "B"
                          and _eq_num(p, "credit", C_CREDIT) and _eq_num(p, "october_invoice", C_OCT_NET))),
    dict(id="nt2_14", domain="doc", prompt=(
        "출장여비 규정 개정 대비표와 심의 결과입니다. 의결 결과를 반영한 최종 기준으로 (1) 시행일, (2) 실제로 개정되는 "
        "조항 목록(철회된 조항과 부칙은 제외, 예: \"제5조\"), (3) 개정 규정 기준 서울 2박 3일 국내 출장 1건의 여비 "
        "합계(일비 3일 + 식비 3일 + 숙박 2박)를 알려 주세요.\n\n"
        + DOC06 + "\n\n"
        + JSON_RULE + '{"effective_date": "YYYY-MM-DD", "amended": ["제5조", ...], "trip_total": 합계(원, 정수)}'),
        contract={"type": "json", "keys": {"effective_date": "str", "amended": "list", "trip_total": "int"}},
        check=_json_check(lambda p: _eq_date(p, "effective_date", R_EFF_FINAL)
                          and isinstance(_get(p, "amended"), list)
                          and sorted(re.sub(r"\(.*", "", _norm(x)) for x in p["amended"]) == sorted(R_AMENDED)
                          and _eq_num(p, "trip_total", R_TRIP))),
]

# ================================================================= calc

# ---------------------------------------------------------------- c01 연차 수당
A_BASE, A_POS, A_MEAL, A_OT = 3_240_000, 150_000, 200_000, 380_000
A_GRANT, A_EXTRA, A_USED = 15, 1, Fraction(19, 2)
A_MONTHLY = A_BASE + A_POS + A_MEAL
A_HOURLY = A_MONTHLY // 209
A_DAILY = A_HOURLY * 8
A_UNUSED = A_GRANT + A_EXTRA - A_USED
A_PAY = int(A_DAILY * A_UNUSED) // 10 * 10

# ---------------------------------------------------------------- c02 4대보험 근사
I_WAGE = 6_812_345
I_CAP = 6_370_000
I_PBASE = min(I_WAGE // 1000 * 1000, I_CAP)
I_PENSION = I_PBASE * 45 // 1000 // 10 * 10
I_HEALTH = I_WAGE * 3545 // 100000 // 10 * 10
I_CARE = I_HEALTH * 1295 // 10000 // 10 * 10
I_EMP = I_WAGE * 9 // 1000 // 10 * 10
I_TOTAL = I_PENSION + I_HEALTH + I_CARE + I_EMP

# ---------------------------------------------------------------- c03 복리 이자
K_PRINCIPAL, K_MONTHS = 25_000_000, 18
_bal = K_PRINCIPAL
for _ in range(K_MONTHS):
    _bal += _bal * 3 // 1000
K_INTEREST = _bal - K_PRINCIPAL
K_TAX = K_INTEREST * 154 // 1000 // 10 * 10
K_NET = K_PRINCIPAL + K_INTEREST - K_TAX
_simple = K_PRINCIPAL * 36 * K_MONTHS // 12 // 1000
assert _simple != K_INTEREST

# ---------------------------------------------------------------- c04 분할 납부 연체이자
L_EACH = 600_000
L_DUE = [date(2026, m, 25) for m in range(3, 9)]
L_PAID = [date(2026, 3, 25), date(2026, 4, 30), date(2026, 5, 26), date(2026, 6, 25),
          date(2026, 7, 27), date(2026, 8, 31)]


def _adj(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


L_LATE = [(p - _adj(d)).days for d, p in zip(L_DUE, L_PAID)]
L_INT = [L_EACH * 12 * max(n, 0) // 36500 for n in L_LATE]
L_COUNT = sum(1 for n in L_LATE if n > 0)
L_TOTAL = sum(L_INT)
_naive = sum(1 for d, p in zip(L_DUE, L_PAID) if p > d)
assert _naive != L_COUNT

# ---------------------------------------------------------------- c05 이동평균 단가
W_OPEN = (200, 1500)
W_TX = [("입고", 300, 1620), ("출고", 250, None), ("입고", 150, 1710), ("출고", 280, None),
        ("입고", 100, 1580), ("출고", 120, None)]
_q, _v, W_COGS = W_OPEN[0], W_OPEN[0] * W_OPEN[1], 0
for _kind, _n, _p in W_TX:
    if _kind == "입고":
        _q, _v = _q + _n, _v + _n * _p
    else:
        _c = _n * _v // _q
        W_COGS += _c
        _q, _v = _q - _n, _v - _c
W_END_QTY, W_END_VAL = _q, _v

# ---------------------------------------------------------------- c06 배송비 구간 요율
P_PARCELS = [  # no, kg, (w, d, h) cm, region, order amount
    (1, Fraction("1.4"), (30, 20, 15), "서울", 32_000),
    (2, Fraction("3.2"), (40, 30, 30), "부산", 58_000),
    (3, Fraction("8.7"), (50, 40, 30), "제주", 41_000),
    (4, Fraction("12.3"), (45, 35, 25), "서울", 120_000),
    (5, Fraction("23.4"), (60, 40, 40), "도서산간", 49_900),
    (6, Fraction("0.8"), (25, 20, 10), "제주", 50_000),
]


def _ship(kg, dims, region, order):
    vol = Fraction(dims[0] * dims[1] * dims[2], 6000)
    vol = Fraction(math.ceil(vol * 10), 10)
    w = max(kg, vol)
    if w <= 2:
        base = 4000
    elif w <= 5:
        base = 5500
    elif w <= 10:
        base = 7500
    elif w <= 20:
        base = 11000
    else:
        base = 11000 + math.ceil(w - 20) * 600
    free = order >= 50_000
    extra = {"제주": 3000, "도서산간": 5000}.get(region, 0)
    return (0 if free else base) + extra, free


P_FEES = {no: _ship(kg, dims, rg, od) for no, kg, dims, rg, od in P_PARCELS}
P_TOTAL = sum(f for f, _ in P_FEES.values())
P_FREE = sum(1 for _, fr in P_FEES.values() if fr)
P_MAX = _strict_top({k: v[0] for k, v in P_FEES.items()})[0]
_parcel_lines = "\n".join(
    f"{no}번: 실중량 {float(kg)}kg, 가로×세로×높이 {d[0]}×{d[1]}×{d[2]}cm, 도착지 {rg}, 주문금액 {od:,}원"
    for no, kg, d, rg, od in P_PARCELS)

CALC_TASKS = [
    dict(id="nt2_15", domain="calc", prompt=(
        "퇴사 예정자의 미사용 연차수당을 계산해 주세요. 규칙은 아래와 같습니다.\n"
        f"- 월 급여 항목: 기본급 {A_BASE:,}원, 직책수당 {A_POS:,}원(고정), 식대 {A_MEAL:,}원(고정), "
        f"연장근로수당 {A_OT:,}원(매월 변동)\n"
        "- 월 통상임금 = 고정 항목(기본급·직책수당·식대)의 합. 변동 항목은 넣지 않습니다.\n"
        "- 통상시급 = 월 통상임금 ÷ 209, 원 미만 버림\n"
        "- 1일 통상임금 = 통상시급 × 8\n"
        f"- 올해 연차: 기본 {A_GRANT}일 + 근속 가산 {A_EXTRA}일, 사용 {float(A_USED)}일(반차 포함)\n"
        "- 연차수당 = 1일 통상임금 × 미사용 일수, 10원 미만 버림\n\n"
        + JSON_RULE + '{"hourly": 통상시급(원, 정수), "daily": 1일 통상임금(원, 정수), '
        '"unused_days": 미사용 일수(숫자), "allowance": 연차수당(원, 정수)}'),
        contract={"type": "json", "keys": {"hourly": "int", "daily": "int", "unused_days": "float", "allowance": "int"}},
        check=_json_check(lambda p: _eq_num(p, "hourly", A_HOURLY) and _eq_num(p, "daily", A_DAILY)
                          and _eq_num(p, "unused_days", float(A_UNUSED)) and _eq_num(p, "allowance", A_PAY))),
    dict(id="nt2_16", domain="calc", prompt=(
        f"월 보수 {I_WAGE:,}원인 직원의 4대보험 근로자 부담분을 아래 규칙으로 근사 계산해 주세요"
        "(실제 고시 요율과 다를 수 있으니 이 규칙만 따르세요).\n"
        f"- 국민연금: 기준소득월액 = 월 보수에서 1,000원 미만을 버린 금액, 단 상한 {I_CAP:,}원. "
        "보험료 = 기준소득월액 × 4.5%\n"
        "- 건강보험: 월 보수 × 3.545%\n"
        "- 장기요양보험: (위에서 확정된) 건강보험료 × 12.95%\n"
        "- 고용보험: 월 보수 × 0.9%\n"
        "- 각 보험료는 계산 후 10원 미만을 버립니다.\n\n"
        + JSON_RULE + '{"pension": 국민연금(원), "health": 건강보험(원), "care": 장기요양(원), '
        '"employment": 고용보험(원), "total": 합계(원)}  (모두 정수)'),
        contract={"type": "json", "keys": {"pension": "int", "health": "int", "care": "int",
                                           "employment": "int", "total": "int"}},
        check=_json_check(lambda p: _eq_num(p, "pension", I_PENSION) and _eq_num(p, "health", I_HEALTH)
                          and _eq_num(p, "care", I_CARE) and _eq_num(p, "employment", I_EMP)
                          and _eq_num(p, "total", I_TOTAL))),
    dict(id="nt2_17", domain="calc", prompt=(
        f"사내 복지기금 정기예치금 {K_PRINCIPAL:,}원을 연 3.6%, 월복리로 {K_MONTHS}개월 예치합니다. 규칙:\n"
        "- 매월 이자 = 그 달 시작 시점 잔액 × 0.3%, 원 미만 버림. 이자는 매월 잔액에 더해집니다.\n"
        f"- {K_MONTHS}개월째 이자까지 더한 뒤 만기입니다.\n"
        "- 이자소득세 = 총이자 × 15.4%, 10원 미만 버림\n"
        "- 세후 수령액 = 원금 + 총이자 - 이자소득세\n\n"
        + JSON_RULE + '{"interest": 총이자(원, 정수), "tax": 이자소득세(원, 정수), "net": 세후 수령액(원, 정수)}'),
        contract={"type": "json", "keys": {"interest": "int", "tax": "int", "net": "int"}},
        check=_json_check(lambda p: _eq_num(p, "interest", K_INTEREST) and _eq_num(p, "tax", K_TAX)
                          and _eq_num(p, "net", K_NET))),
    dict(id="nt2_18", domain="calc", prompt=(
        f"거래처가 미수금을 6회 분할(회당 {L_EACH:,}원)로 갚고 있습니다. 회차별 연체이자를 계산해 주세요.\n"
        "- 납기일은 매월 25일입니다. 단, 납기일이 토요일·일요일이면 그다음 월요일이 납기일입니다(공휴일은 고려하지 않음).\n"
        "- 연체일수 = 실제 납부일 - 납기일(일). 0 이하이면 연체가 아닙니다.\n"
        "- 회차별 연체이자 = 회당 금액 × 연 12% × 연체일수 ÷ 365, 원 미만 버림. 합계는 회차별 이자의 합입니다.\n\n"
        + "\n".join(f"{i + 1}회차: 원래 납기 {d.isoformat()}, 실제 납부 {p.isoformat()}"
                    for i, (d, p) in enumerate(zip(L_DUE, L_PAID))) + "\n\n"
        + JSON_RULE + '{"late_count": 연체 회차 수(정수), "total_interest": 연체이자 합계(원, 정수)}'),
        contract={"type": "json", "keys": {"late_count": "int", "total_interest": "int"}},
        check=_json_check(lambda p: _eq_num(p, "late_count", L_COUNT) and _eq_num(p, "total_interest", L_TOTAL))),
    dict(id="nt2_19", domain="calc", prompt=(
        "자재 '실링 가스켓'의 10월 수불을 이동평균법으로 계산해 주세요.\n"
        "- 이동평균 단가 = 현재 재고금액 ÷ 현재 재고수량 (단가 자체는 반올림하지 않음)\n"
        "- 출고원가 = 출고수량 × 그 시점 이동평균 단가, 원 미만 버림. 재고금액에서 출고원가를 뺍니다.\n"
        "- 입고 시 재고금액에 입고수량 × 입고단가를 더합니다.\n\n"
        f"기초: {W_OPEN[0]}개, 단가 {W_OPEN[1]:,}원\n"
        + "\n".join(f"{i + 1}. {k} {n}개" + (f" (단가 {p:,}원)" if p else "")
                    for i, (k, n, p) in enumerate(W_TX)) + "\n\n"
        + JSON_RULE + '{"total_cogs": 출고원가 합계(원, 정수), "end_qty": 기말 수량(정수), "end_value": 기말 재고금액(원, 정수)}'),
        contract={"type": "json", "keys": {"total_cogs": "int", "end_qty": "int", "end_value": "int"}},
        check=_json_check(lambda p: _eq_num(p, "total_cogs", W_COGS) and _eq_num(p, "end_qty", W_END_QTY)
                          and _eq_num(p, "end_value", W_END_VAL))),
    dict(id="nt2_20", domain="calc", prompt=(
        "택배 6건의 배송비를 아래 요율표로 계산해 주세요.\n"
        "- 부피중량(kg) = 가로×세로×높이(cm) ÷ 6000, 0.1kg 단위로 올림\n"
        "- 청구중량 = 실중량과 부피중량 중 큰 값\n"
        "- 기본요금: 청구중량 2kg 이하 4,000원 / 5kg 이하 5,500원 / 10kg 이하 7,500원 / 20kg 이하 11,000원 / "
        "20kg 초과는 11,000원 + 20kg 초과분 1kg당 600원(1kg 미만은 1kg으로 올림)\n"
        "- 주문금액 50,000원 이상이면 기본요금 면제(할증은 그대로 부과)\n"
        "- 할증: 제주 3,000원, 도서산간 5,000원, 그 외 없음\n"
        "- 건별 배송비 = 기본요금(면제 시 0) + 할증\n\n"
        + _parcel_lines + "\n\n"
        + JSON_RULE + '{"total": 6건 배송비 합계(원, 정수), "free_count": 기본요금 면제 건수(정수), '
        '"max_parcel": 배송비가 가장 큰 건 번호(정수)}'),
        contract={"type": "json", "keys": {"total": "int", "free_count": "int", "max_parcel": "int"}},
        check=_json_check(lambda p: _eq_num(p, "total", P_TOTAL) and _eq_num(p, "free_count", P_FREE)
                          and _eq_num(p, "max_parcel", P_MAX))),
]

# ================================================================= code

SENTINEL = "NT2-HIDDEN-TESTS-PASSED"
_FENCE = re.compile(r"```[ \t]*(?:python|py)[ \t]*\r?\n(.*?)```", re.S | re.I)

_RUNNER = """import importlib.util, os, sys
_spec = importlib.util.spec_from_file_location("solution", os.path.join(os.path.dirname(os.path.abspath(__file__)), "solution.py"))
_mod = importlib.util.module_from_spec(_spec)
try:
    _spec.loader.exec_module(_mod)
except BaseException:
    sys.exit(3)
{fn} = getattr(_mod, {fn!r})
"""


def _py_block(answer):
    m = _FENCE.search(answer or "")
    return m.group(1) if m else None


def _code_check(fn, tests):
    """tests: assert lines using `fn`. Model code goes to solution.py; a runner imports it and
    runs the asserts in a fresh isolated interpreter, then prints the sentinel with a per-run
    nonce (so model code cannot fake a pass by printing it and exiting)."""

    def check(answer, parsed, ws):
        code = _py_block(answer)
        if not code:
            return False
        token = f"{SENTINEL}-{secrets.token_hex(8)}"
        script = _RUNNER.format(fn=fn) + tests + f"\nprint({token!r})\n"
        tmp = tempfile.mkdtemp(prefix="nt2_")
        try:
            with open(os.path.join(tmp, "solution.py"), "w", encoding="utf-8") as f:
                f.write(code)
            path = os.path.join(tmp, "run_tests.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write(script)
            r = subprocess.run([sys.executable, "-I", path], cwd=tmp, capture_output=True,
                               text=True, timeout=10, stdin=subprocess.DEVNULL)
            lines = r.stdout.strip().splitlines()
            return r.returncode == 0 and bool(lines) and lines[-1].strip() == token
        except Exception:
            return False
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return check


def _tests(fn, cases):
    """cases: list of (args tuple, expected). Expected values come from the reference."""
    return "\n".join(f"assert {fn}(*{a!r}) == {e!r}, {a!r}" for a, e in cases)


CODE_RULE = ("표준 라이브러리만 쓰고, 답에는 함수 전체를 ```python 코드 블록 하나에 담아 주세요"
             "(입력을 받거나 파일을 읽는 코드는 넣지 마세요).")


# ---------------------------------------------------------------- k01 business_days
def ref_business_days(start, end, holidays):
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    hs = {date.fromisoformat(h) for h in holidays}
    n = 0
    while s <= e:
        if s.weekday() < 5 and s not in hs:
            n += 1
        s += timedelta(days=1)
    return n


K01_CASES = [(a, ref_business_days(*a)) for a in [
    ("2026-10-01", "2026-10-31", ["2026-10-03", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-09"]),
    ("2026-10-05", "2026-10-05", []),
    ("2026-10-10", "2026-10-11", []),
    ("2026-10-12", "2026-10-09", []),
    ("2026-12-28", "2027-01-08", ["2027-01-01", "2027-01-01", "2026-12-25"]),
    ("2028-02-25", "2028-03-03", ["2028-03-01"]),
    ("2026-01-01", "2026-12-31", []),
]]

# ---------------------------------------------------------------- k02 korean_amount
def ref_korean_amount(n):
    if n == 0:
        return "0원"
    parts = []
    for unit, size in (("조", 10 ** 12), ("억", 10 ** 8), ("만", 10 ** 4)):
        g = n // size % 10000
        if g:
            parts.append(f"{g}{unit}")
    if n % 10000:
        parts.append(str(n % 10000))
    return " ".join(parts) + "원"


K02_CASES = [((a,), ref_korean_amount(a)) for a in [
    0, 7, 30000, 12345678, 100000000, 100005000, 1200003400005, 99990000, 10001, 5000000000000000 - 1]]

# ---------------------------------------------------------------- k03 covered_minutes
def ref_covered_minutes(intervals):
    def m(s):
        h, mi = s.split(":")
        return int(h) * 60 + int(mi)
    segs = sorted((m(a), m(b)) for a, b in intervals if m(b) > m(a))
    total, cur_s, cur_e = 0, None, None
    for a, b in segs:
        if cur_e is None or a > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = a, b
        else:
            cur_e = max(cur_e, b)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


K03_CASES = [((a,), ref_covered_minutes(a)) for a in [
    [],
    [("09:00", "10:30")],
    [("09:00", "10:00"), ("09:30", "11:00"), ("13:00", "13:45")],
    [("14:00", "15:00"), ("15:00", "15:30")],
    [("08:00", "18:00"), ("09:00", "10:00"), ("12:00", "12:30")],
    [("10:00", "09:00"), ("11:00", "11:00"), ("07:05", "07:50")],
    [("13:10", "14:00"), ("08:15", "09:05"), ("08:50", "08:55"), ("23:00", "23:59")],
]]

# ---------------------------------------------------------------- k04 aging_buckets
_BUCKETS = ["current", "1-30", "31-60", "61-90", "90+"]


def ref_aging_buckets(invoices, as_of):
    out = {k: 0 for k in _BUCKETS}
    a = date.fromisoformat(as_of)
    for inv in invoices:
        bal = inv["amount"] - inv["paid"]
        if bal <= 0:
            continue
        d = (a - date.fromisoformat(inv["due"])).days
        k = "current" if d <= 0 else "1-30" if d <= 30 else "31-60" if d <= 60 else "61-90" if d <= 90 else "90+"
        out[k] += bal
    return out


_INV = [
    {"due": "2026-10-31", "amount": 500000, "paid": 0},
    {"due": "2026-10-20", "amount": 300000, "paid": 100000},
    {"due": "2026-09-20", "amount": 800000, "paid": 0},
    {"due": "2026-09-19", "amount": 120000, "paid": 0},
    {"due": "2026-08-21", "amount": 450000, "paid": 450000},
    {"due": "2026-07-22", "amount": 990000, "paid": 90000},
    {"due": "2026-07-21", "amount": 70000, "paid": 0},
    {"due": "2026-01-05", "amount": 250000, "paid": 300000},
]
K04_CASES = [((a, b), ref_aging_buckets(a, b)) for a, b in [
    (_INV, "2026-10-20"), ([], "2026-10-20"), (_INV[:3], "2027-01-01")]]

# ---------------------------------------------------------------- k05 billing_dates
def ref_billing_dates(start, n):
    s = date.fromisoformat(start)
    out = []
    for i in range(n):
        y, m = divmod(s.month - 1 + i, 12)
        y, m = s.year + y, m + 1
        out.append(date(y, m, min(s.day, calendar.monthrange(y, m)[1])).isoformat())
    return out


K05_CASES = [(a, ref_billing_dates(*a)) for a in [
    ("2026-01-31", 4), ("2026-10-15", 5), ("2027-11-30", 5), ("2026-03-01", 0),
    ("2027-12-29", 3), ("2026-08-31", 14)]]

CODE_TASKS = [
    dict(id="nt2_21", domain="code", prompt=(
        "근태 정산용으로 파이썬 함수 `business_days(start, end, holidays)`를 작성해 주세요.\n"
        "- start, end: 'YYYY-MM-DD' 문자열. 두 날짜를 모두 포함한 기간의 영업일 수(정수)를 돌려줍니다.\n"
        "- 영업일 = 월~금 중 holidays 목록에 없는 날. holidays는 'YYYY-MM-DD' 문자열 리스트이며 중복이나 주말 날짜가 "
        "섞여 있을 수 있습니다(주말인 공휴일을 두 번 빼면 안 됩니다).\n"
        "- start가 end보다 늦으면 0을 돌려줍니다.\n"
        "예: business_days('2026-10-05', '2026-10-05', []) == 1, business_days('2026-10-10', '2026-10-11', []) == 0\n"
        + CODE_RULE),
        contract=TEXT, check=_code_check("business_days", _tests("business_days", K01_CASES))),
    dict(id="nt2_22", domain="code", prompt=(
        "견적서 금액을 한글 단위로 표기하는 파이썬 함수 `korean_amount(n)`을 작성해 주세요.\n"
        "- n: 0 이상 10**16 미만의 정수. 문자열을 돌려줍니다.\n"
        "- 숫자를 뒤에서부터 4자리씩 끊어 '조', '억', '만', (단위 없음) 자리로 나눕니다. 값이 0인 자리는 생략하고, "
        "각 자리 숫자는 앞자리 0 없이 쉼표 없이 씁니다. 자리 사이는 공백 한 칸, 맨 끝에 '원'을 공백 없이 붙입니다.\n"
        "- n이 0이면 '0원'.\n"
        "예: 12345678 → '1234만 5678원', 100000000 → '1억원', 100005000 → '1억 5000원', "
        "1200003400005 → '1조 2000억 340만 5원', 30000 → '3만원'\n"
        + CODE_RULE),
        contract=TEXT, check=_code_check("korean_amount", _tests("korean_amount", K02_CASES))),
    dict(id="nt2_23", domain="code", prompt=(
        "회의실 사용 기록에서 실제로 회의실이 사용된 총 시간을 구하는 파이썬 함수 `covered_minutes(intervals)`를 "
        "작성해 주세요.\n"
        "- intervals: (시작, 종료) 튜플의 리스트. 각 값은 같은 날의 'HH:MM' 문자열(00:00~23:59).\n"
        "- 겹치거나 맞닿은 구간은 한 번만 셉니다(합집합의 길이). 결과는 분 단위 정수.\n"
        "- 종료가 시작과 같거나 이른 구간은 잘못된 기록이므로 무시합니다. 빈 리스트는 0.\n"
        "예: covered_minutes([('09:00','10:00'), ('09:30','11:00')]) == 120\n"
        + CODE_RULE),
        contract=TEXT, check=_code_check("covered_minutes", _tests("covered_minutes", K03_CASES))),
    dict(id="nt2_24", domain="code", prompt=(
        "매출채권 연령 분석용 파이썬 함수 `aging_buckets(invoices, as_of)`를 작성해 주세요.\n"
        "- invoices: {'due': 'YYYY-MM-DD', 'amount': 정수, 'paid': 정수} 딕셔너리의 리스트. as_of: 기준일 'YYYY-MM-DD'.\n"
        "- 잔액 = amount - paid. 잔액이 0 이하인 건은 건너뜁니다.\n"
        "- 경과일 = as_of - due (일). 경과일 0 이하 → 'current', 1~30 → '1-30', 31~60 → '31-60', "
        "61~90 → '61-90', 91 이상 → '90+'.\n"
        "- 다섯 개 키('current', '1-30', '31-60', '61-90', '90+')를 모두 가진 딕셔너리를 돌려주고, 값은 해당 구간 잔액 "
        "합계(정수, 해당 건이 없으면 0)입니다.\n"
        + CODE_RULE),
        contract=TEXT, check=_code_check("aging_buckets", _tests("aging_buckets", K04_CASES))),
    dict(id="nt2_25", domain="code", prompt=(
        "구독 결제일 목록을 만드는 파이썬 함수 `billing_dates(start, n)`을 작성해 주세요.\n"
        "- start: 첫 결제일 'YYYY-MM-DD'. n: 만들 결제일 개수(0 이상 정수). 'YYYY-MM-DD' 문자열 n개의 리스트를 돌려줍니다.\n"
        "- i번째(0부터) 결제일은 start로부터 i개월 뒤 달의, start와 같은 '일'입니다. 그 달에 그 날짜가 없으면 그 달의 "
        "마지막 날로 합니다. 이 조정은 항상 start의 '일'을 기준으로 하며, 앞 결제일에서 이어서 계산하지 않습니다.\n"
        "예: billing_dates('2026-01-31', 4) == ['2026-01-31', '2026-02-28', '2026-03-31', '2026-04-30']\n"
        + CODE_RULE),
        contract=TEXT, check=_code_check("billing_dates", _tests("billing_dates", K05_CASES))),
]

# ================================================================= logic

def _unique(space, conds):
    sols = [s for s in space if all(c(s) for c in conds)]
    assert len(sols) == 1, len(sols)
    return sols[0]


# ---------------------------------------------------------------- l01 좌석
G1 = ["민수", "지은", "태호", "서윤", "경민", "하린"]
_C1 = [
    ("민수와 지은은 바로 옆자리다.", lambda s: abs(s["민수"] - s["지은"]) == 1),
    ("태호는 맨 끝자리(1번 또는 6번)다.", lambda s: s["태호"] in (1, 6)),
    ("서윤은 경민보다 번호가 큰 자리다.", lambda s: s["서윤"] > s["경민"]),
    ("하린과 태호 사이의 자리 번호 차이는 3 이상이다.", lambda s: abs(s["하린"] - s["태호"]) >= 3),
    ("지은은 짝수 번호 자리다.", lambda s: s["지은"] % 2 == 0),
    ("경민은 태호 바로 옆자리다.", lambda s: abs(s["경민"] - s["태호"]) == 1),
    ("민수는 3번 자리가 아니다.", lambda s: s["민수"] != 3),
    ("하린은 지은보다 번호가 작은 자리다.", lambda s: s["하린"] < s["지은"]),
]
_S1 = _unique(({n: i + 1 for i, n in enumerate(p)} for p in permutations(G1)), [c for _, c in _C1])
L01 = sorted(_S1, key=_S1.get)

# ---------------------------------------------------------------- l02 발표 순서
G2 = ["영업", "마케팅", "개발", "재무", "인사"]
_C2 = [
    ("개발팀은 재무팀보다 먼저 발표한다.", lambda s: s["개발"] < s["재무"]),
    ("영업팀은 첫 번째도 마지막도 아니다.", lambda s: s["영업"] not in (1, 5)),
    ("마케팅팀은 영업팀 바로 앞 순서다.", lambda s: s["마케팅"] == s["영업"] - 1),
    ("인사팀과 개발팀 사이에는 정확히 한 팀이 발표한다.", lambda s: abs(s["인사"] - s["개발"]) == 2),
    ("재무팀은 마지막 순서가 아니다.", lambda s: s["재무"] != 5),
]
_S2 = _unique(({n: i + 1 for i, n in enumerate(p)} for p in permutations(G2)), [c for _, c in _C2])
L02 = sorted(_S2, key=_S2.get)

# ---------------------------------------------------------------- l03 당직
G3 = ["강민호", "노지수", "도경태", "류선영", "문하준"]
_DAYS = ["월", "화", "수", "목", "금"]
_C3 = [
    ("강민호는 월요일과 금요일에는 당직을 서지 않는다.", lambda d: d["강민호"] not in (0, 4)),
    ("노지수는 도경태 바로 다음 날 당직이다.", lambda d: d["노지수"] == d["도경태"] + 1),
    ("류선영은 강민호보다 앞선 요일에 당직이다.", lambda d: d["류선영"] < d["강민호"]),
    ("문하준은 월요일 당직이 아니다.", lambda d: d["문하준"] != 0),
    ("문하준과 강민호의 당직일은 이틀 이상 떨어져 있다(요일 차이 2 이상).", lambda d: abs(d["문하준"] - d["강민호"]) >= 2),
]
_S3 = _unique(({n: i for i, n in enumerate(p)} for p in permutations(G3)), [c for _, c in _C3])
L03 = sorted(_S3, key=_S3.get)

# ---------------------------------------------------------------- l04 업무 배정
G4 = ["윤채영", "장우진", "임소라", "신동혁"]
_PR4 = ["물류", "결제", "검색", "보안"]
_C4 = [
    ("윤채영은 보안 프로젝트를 맡지 않는다.", lambda a: a["윤채영"] != "보안"),
    ("장우진은 결제나 검색 중 하나를 맡는다.", lambda a: a["장우진"] in ("결제", "검색")),
    ("임소라는 물류도 결제도 맡지 않는다.", lambda a: a["임소라"] not in ("물류", "결제")),
    ("신동혁은 검색을 맡지 않는다.", lambda a: a["신동혁"] != "검색"),
    ("윤채영이 물류를 맡는 경우에만(그리고 그 경우에는 반드시) 장우진이 검색을 맡는다.",
     lambda a: (a["윤채영"] == "물류") == (a["장우진"] == "검색")),
    ("신동혁은 물류를 맡지 않는다.", lambda a: a["신동혁"] != "물류"),
]
L04 = _unique((dict(zip(G4, p)) for p in permutations(_PR4)), [c for _, c in _C4])

# ---------------------------------------------------------------- l05 회의실 배정
G5 = ["주간보고", "채용면접", "고객미팅", "예산검토", "교육", "워크숍"]
_SLOTS = [r + "-" + t for t in ("오전", "오후") for r in "ABC"]
_C5 = [
    ("고객미팅은 A실에서 한다.", lambda a: a["고객미팅"][0] == "A"),
    ("채용면접은 오전에 한다.", lambda a: a["채용면접"][2:] == "오전"),
    ("워크숍은 오후에 하며 A실이 아니다.", lambda a: a["워크숍"][2:] == "오후" and a["워크숍"][0] != "A"),
    ("예산검토와 주간보고는 같은 회의실을 쓴다.", lambda a: a["예산검토"][0] == a["주간보고"][0]),
    ("교육과 고객미팅은 다른 시간대(오전/오후)에 한다.", lambda a: a["교육"][2:] != a["고객미팅"][2:]),
    ("채용면접은 C실이 아니다.", lambda a: a["채용면접"][0] != "C"),
    ("주간보고는 오전에 한다.", lambda a: a["주간보고"][2:] == "오전"),
    ("교육은 C실에서 한다.", lambda a: a["교육"][0] == "C"),
]
L05 = _unique((dict(zip(G5, p)) for p in permutations(_SLOTS)), [c for _, c in _C5])


def _slot(x):
    s = re.sub(r"\s+", "", str(x or "")).upper().replace("실", "").replace("룸", "")
    m = re.search(r"([ABC]).*?(오전|오후)|(오전|오후).*?([ABC])", s)
    if not m:
        return None
    return (m[1] or m[4]) + "-" + (m[2] or m[3])


def _rules(cs):
    return "\n".join(f"{i + 1}. {t}" for i, (t, _) in enumerate(cs))


LOGIC_TASKS = [
    dict(id="nt2_26", domain="logic", prompt=(
        "워크숍 버스 맨 앞줄 좌석 1~6번(왼쪽부터 일렬)에 6명(" + ", ".join(G1) + ")이 한 명씩 앉습니다. "
        "조건을 모두 만족하는 배치는 하나뿐입니다.\n" + _rules(_C1) + "\n\n"
        + JSON_RULE + '{"seats": [1번 자리 이름, 2번, 3번, 4번, 5번, 6번]}'),
        contract={"type": "json", "keys": {"seats": "list"}},
        check=_json_check(lambda p: _eq_list_ordered(p, "seats", L01))),
    dict(id="nt2_27", domain="logic", prompt=(
        "분기 실적 보고회에서 5개 팀(" + ", ".join(G2) + ")이 한 번씩 순서대로 발표합니다. 조건을 모두 만족하는 "
        "순서는 하나뿐입니다.\n" + _rules(_C2) + "\n\n"
        + JSON_RULE + '{"order": [첫 번째 팀, 두 번째, 세 번째, 네 번째, 다섯 번째]}  (팀 이름은 "영업"처럼 표기)'),
        contract={"type": "json", "keys": {"order": "list"}},
        check=_json_check(lambda p: isinstance(_get(p, "order"), list)
                          and [_norm(x).replace("팀", "") for x in p["order"]] == L02)),
    dict(id="nt2_28", domain="logic", prompt=(
        "다음 주 월~금 야간 당직을 5명(" + ", ".join(G3) + ")이 하루씩 맡습니다. 조건을 모두 만족하는 배정은 "
        "하나뿐입니다.\n" + _rules(_C3) + "\n\n"
        + JSON_RULE + '{"duty": [월요일 담당, 화요일, 수요일, 목요일, 금요일]}'),
        contract={"type": "json", "keys": {"duty": "list"}},
        check=_json_check(lambda p: _eq_list_ordered(p, "duty", L03))),
    dict(id="nt2_29", domain="logic", prompt=(
        "4명(" + ", ".join(G4) + ")에게 신규 프로젝트 4개(" + ", ".join(_PR4) + ")를 한 명당 하나씩 배정합니다. "
        "조건을 모두 만족하는 배정은 하나뿐입니다.\n" + _rules(_C4) + "\n\n"
        + JSON_RULE + "{" + ", ".join(f'"{n}": 프로젝트명' for n in G4) + "}"),
        contract={"type": "json", "keys": {n: "str" for n in G4}},
        check=_json_check(lambda p: all(_norm(_get(p, n)).replace("프로젝트", "") == L04[n] for n in G4))),
    dict(id="nt2_30", domain="logic", prompt=(
        "목요일 회의 6건(" + ", ".join(G5) + ")을 회의실 A·B·C와 시간대 오전·오후 조합 6칸에 한 건씩 배정합니다"
        "(한 칸에 한 건). 조건을 모두 만족하는 배정은 하나뿐입니다.\n" + _rules(_C5) + "\n\n"
        + JSON_RULE + "{" + ", ".join(f'"{n}": "A-오전" 형식' for n in G5) + "}"),
        contract={"type": "json", "keys": {n: "str" for n in G5}},
        check=_json_check(lambda p: all(_slot(_get(p, n)) == L05[n] for n in G5))),
]

# ================================================================= assemble

TASKS = DATA_TASKS + DOC_TASKS + CALC_TASKS + CODE_TASKS + LOGIC_TASKS
for _t in TASKS:
    _t["split"] = "notool2"
    _t["tools"] = "none"
assert len(TASKS) == 30 and len({t["id"] for t in TASKS}) == 30
