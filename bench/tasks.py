"""A/B bench task set: ERP lookups, small code fixes/features, document extraction.

Each task: id, split (dev/eval), domain, prompt (Korean, states the answer format), tools,
contract, check(answer, parsed, ws). ERP ground truth is computed from env.DB at import time.
Document ground truth comes from the same Python values the documents are rendered from.
Standard library only.
"""
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import env
import grade

# ================================================================= helpers

def _norm(s):
    """Company / person / dept name: drop spaces and corporate markers."""
    s = str(s if s is not None else "")
    for t in ("주식회사", "(주)", "㈜", "（주）"):
        s = s.replace(t, "")
    return re.sub(r"\s+", "", s)


def _date(s):
    """'2026-11-30', '2026.11.30', '2026년 11월 30일' -> '2026-11-30'. None if not a date."""
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", str(s or ""))
    return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}" if m else None


def _code(s):
    return re.sub(r"\s+", "", str(s if s is not None else "")).upper()


def _codes(lst):
    if not isinstance(lst, list):
        return None
    return sorted(_code(x) for x in lst)


def _get(parsed, key):
    return parsed.get(key) if isinstance(parsed, dict) else None


def _eq_num(parsed, key, expected):
    v = grade.num(_get(parsed, key))
    return v is not None and v == expected


def _eq_name(parsed, key, expected):
    v = _get(parsed, key)
    return isinstance(v, str) and _norm(v) == _norm(expected)


def _eq_date(parsed, key, expected):
    return _date(_get(parsed, key)) == expected


def _eq_codes(parsed, key, expected):
    got = _codes(_get(parsed, key))
    return got is not None and got == sorted(_code(x) for x in expected)


def _all(*conds):
    return all(conds)


def _json_check(fn):
    """Wrap a parsed-dict check so None / non-dict -> False and any exception -> False."""
    def check(answer, parsed, ws):
        if not isinstance(parsed, dict):
            return False
        try:
            return bool(fn(parsed))
        except Exception:
            return False
    return check


def _code_check(visible, hidden_src):
    """visible: {filename: original test text}. Restore it (guards against edited tests),
    run the project's tests, then run a hidden test."""
    def check(answer, parsed, ws):
        if ws is None:
            return False
        root = Path(ws.root)
        for name, text in visible.items():
            (root / name).write_text(text, encoding="utf-8")
        if ws.run_tests()["exit_code"] != 0:
            return False
        hidden = root / "hidden_test.py"
        hidden.write_text(hidden_src, encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, "-E", "-s", "hidden_test.py"], cwd=root,
                               capture_output=True, text=True, timeout=20)
            return r.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        finally:
            hidden.unlink(missing_ok=True)
    return check


JSON_RULE = "답은 다른 설명 없이 JSON 한 줄로만 주세요: "

# ================================================================= ERP ground truth

V = env.DB["vouchers"]["rows"]
B = env.DB["vouchers_backup_2023"]["rows"]
DEPT = {d["dept_id"]: d["name"] for d in env.DB["departments"]["rows"]}
DEPT_ID = {n: d for d, n in DEPT.items()}
VEND = {v["vendor_id"]: v for v in env.DB["vendors"]["rows"]}
VEND_ID = {_norm(v["name"]): k for k, v in VEND.items()}
ITEMS = {i["item_code"]: i for i in env.DB["items"]["rows"]}
STOCK = env.DB["stock"]["rows"]
RECV = env.DB["receivables"]["rows"]
SUSPENDED = {k for k, v in VEND.items() if v["status"] == "suspended"}


def _vsum(rows, **conds):
    return sum(r["amount"] for r in rows if all(r[k] == v for k, v in conds.items()))


def _vcount(rows, **conds):
    return sum(1 for r in rows if all(r[k] == v for k, v in conds.items()))


def _in(d, a, b):
    return a <= d <= b


# --- dev
ERP_D01 = _vcount(V, status="반려")
ERP_D02 = sum(r["amount"] for r in V if r["dept_id"] == DEPT_ID["영업팀"] and r["status"] == "승인"
              and _in(r["date"], "2026-01-01", "2026-03-31"))
ERP_D03 = sorted(k for k, i in ITEMS.items() if i["unit_price"] >= 50000)

# --- eval
E01 = _vcount(V, dept_id=DEPT_ID["구매팀"], status="승인")

_q3 = defaultdict(int)
for r in V:
    if r["status"] == "승인" and _in(r["date"], "2026-07-01", "2026-09-30"):
        _q3[r["dept_id"]] += r["amount"]
_q3s = sorted(_q3.items(), key=lambda x: -x[1])
assert _q3s[0][1] != _q3s[1][1]
E02 = (DEPT[_q3s[0][0]], _q3s[0][1])

E03 = sorted(r["voucher_id"] for r in V if r["vendor_id"] in SUSPENDED and r["status"] == "미결")

_tot = defaultdict(int)
for s in STOCK:
    _tot[s["item_code"]] += s["qty"]
E04 = sorted(k for k, i in ITEMS.items() if _tot[k] < i["safety_stock"])

E05 = sum(r["amount"] - r["paid_amount"] for r in RECV if r["customer"] == "(주)대한모터스")

_od = [r for r in RECV if r["due_date"] <= "2026-09-30" and r["amount"] > r["paid_amount"]]
E06 = (len(_od), sum(r["amount"] - r["paid_amount"] for r in _od))

E07 = _vsum(V, dept_id=DEPT_ID["생산팀"], account="접대비", status="승인")
E07_TRAP = E07 + _vsum(B, dept_id=DEPT_ID["생산팀"], account="접대비", status="승인")
assert E07_TRAP != E07

_appr = [r for r in V if r["status"] == "승인"]
_mx = max(r["amount"] for r in _appr)
E08 = (_mx, sorted(r["voucher_id"] for r in _appr if r["amount"] == _mx))

E09 = sum(s["qty"] * ITEMS[s["item_code"]]["unit_price"] for s in STOCK if s["warehouse"] == "평택창고")

E10 = VEND[VEND_ID[_norm("(주)서진정밀")]]

E11_26 = _vsum(V, dept_id=DEPT_ID["생산팀"], account="수선비")
E11_23 = _vsum(B, dept_id=DEPT_ID["생산팀"], account="수선비")

_pend = defaultdict(int)
for r in V:
    if r["status"] == "미결":
        _pend[r["vendor_id"]] += r["amount"]
_pend_active = sorted(((k, v) for k, v in _pend.items() if k not in SUSPENDED), key=lambda x: -x[1])
assert _pend_active[2][1] != _pend_active[3][1]
E12 = [VEND[k]["name"] for k, _ in _pend_active[:3]]
_pend_all = sorted(_pend.items(), key=lambda x: -x[1])
assert any(k in SUSPENDED for k, _ in _pend_all[:3])  # the exclusion actually matters

_hq = [s for s in STOCK if s["warehouse"] == "본사창고" and s["qty"] < ITEMS[s["item_code"]]["safety_stock"]]
E13 = (sorted(s["item_code"] for s in _hq),
       sum((ITEMS[s["item_code"]]["safety_stock"] - s["qty"]) * ITEMS[s["item_code"]]["unit_price"] for s in _hq))

_bal = defaultdict(int)
for r in RECV:
    _bal[r["customer"]] += r["amount"] - r["paid_amount"]
_bals = sorted(_bal.items(), key=lambda x: -x[1])
assert _bals[0][1] != _bals[1][1]
E14 = _bals[0]

ERP_TASKS = [
    # ------------------------------------------------ dev
    dict(id="erp_d01", split="dev", prompt=(
        "올해 지출 전표 중에 반려된 게 총 몇 건이에요? " + JSON_RULE + '{"count": 건수(정수)}'),
        contract={"type": "json", "keys": {"count": "int"}},
        check=_json_check(lambda p: _eq_num(p, "count", ERP_D01))),
    dict(id="erp_d02", split="dev", prompt=(
        "영업팀 1분기(2026-01-01 ~ 2026-03-31, 양 끝 날짜 포함) 승인된 지출 전표 금액 합계 좀 뽑아주세요. "
        + JSON_RULE + '{"total": 합계(원, 정수)}'),
        contract={"type": "json", "keys": {"total": "int"}},
        check=_json_check(lambda p: _eq_num(p, "total", ERP_D02))),
    dict(id="erp_d03", split="dev", prompt=(
        "품목 마스터에서 단가가 5만원 이상(50,000원 포함)인 품목코드를 전부 알려주세요. "
        + JSON_RULE + '{"item_codes": ["ITM-0001", ...]}'),
        contract={"type": "json", "keys": {"item_codes": "list"}},
        check=_json_check(lambda p: _eq_codes(p, "item_codes", ERP_D03))),
    # ------------------------------------------------ eval
    dict(id="erp_e01", split="eval", prompt=(
        "구매팀에서 올해 승인 완료된 지출 전표가 몇 건인지 확인 부탁드려요. " + JSON_RULE + '{"count": 건수(정수)}'),
        contract={"type": "json", "keys": {"count": "int"}},
        check=_json_check(lambda p: _eq_num(p, "count", E01))),
    dict(id="erp_e02", split="eval", prompt=(
        "3분기(2026-07-01 ~ 2026-09-30, 양 끝 날짜 포함)에 승인된 지출 전표 금액을 부서별로 합쳤을 때 "
        "가장 많이 쓴 부서와 그 합계를 알려주세요. 미결·반려 전표는 빼고요. "
        + JSON_RULE + '{"dept": 부서명, "total": 합계(원, 정수)}'),
        contract={"type": "json", "keys": {"dept": "str", "total": "int"}},
        check=_json_check(lambda p: _eq_name(p, "dept", E02[0]) and _eq_num(p, "total", E02[1]))),
    dict(id="erp_e03", split="eval", prompt=(
        "거래중지(suspended)된 거래처들한테 아직 미결 상태로 남아 있는 올해 전표가 있으면 정리해야 해서요. "
        "해당 전표번호를 전부 뽑아주세요. " + JSON_RULE + '{"voucher_ids": ["JV-2026-0001", ...]}'),
        contract={"type": "json", "keys": {"voucher_ids": "list"}},
        check=_json_check(lambda p: _eq_codes(p, "voucher_ids", E03))),
    dict(id="erp_e04", split="eval", prompt=(
        "본사창고와 평택창고 재고를 품목별로 합쳤을 때, 합계가 안전재고보다 적은(미만) 품목이 뭐가 있는지 봐주세요. "
        + JSON_RULE + '{"item_codes": ["ITM-0001", ...]}'),
        contract={"type": "json", "keys": {"item_codes": "list"}},
        check=_json_check(lambda p: _eq_codes(p, "item_codes", E04))),
    dict(id="erp_e05", split="eval", prompt=(
        "(주)대한모터스 미수금이 지금 얼마 남았죠? 청구액에서 입금액 뺀 잔액을 그 고객 건 전부 합쳐서 알려주세요. "
        + JSON_RULE + '{"customer": 고객명, "balance": 미수잔액 합계(원, 정수)}'),
        contract={"type": "json", "keys": {"customer": "str", "balance": "int"}},
        check=_json_check(lambda p: _eq_name(p, "customer", "(주)대한모터스") and _eq_num(p, "balance", E05))),
    dict(id="erp_e06", split="eval", prompt=(
        "9월 말 기준 연체 채권 현황이 필요해요. 만기일(due_date)이 2026-09-30 이하이면서 잔액(청구액 - 입금액)이 "
        "0보다 큰 매출채권의 건수와 잔액 합계를 알려주세요. "
        + JSON_RULE + '{"count": 건수(정수), "total_balance": 잔액 합계(원, 정수)}'),
        contract={"type": "json", "keys": {"count": "int", "total_balance": "int"}},
        check=_json_check(lambda p: _eq_num(p, "count", E06[0]) and _eq_num(p, "total_balance", E06[1]))),
    dict(id="erp_e07", split="eval", prompt=(
        "생산팀 올해 접대비, 승인된 전표 기준으로 총 얼마 썼는지 알려주세요. "
        + JSON_RULE + '{"total": 합계(원, 정수)}'),
        contract={"type": "json", "keys": {"total": "int"}},
        check=_json_check(lambda p: _eq_num(p, "total", E07))),
    dict(id="erp_e08", split="eval", prompt=(
        "올해 승인된 지출 전표 중 금액이 가장 큰 건을 확인하고 싶어요. 최고 금액과, 그 금액인 전표가 여러 건이면 "
        "전표번호를 모두 알려주세요. " + JSON_RULE + '{"amount": 최고 금액(원, 정수), "voucher_ids": ["JV-2026-0001", ...]}'),
        contract={"type": "json", "keys": {"amount": "int", "voucher_ids": "list"}},
        check=_json_check(lambda p: _eq_num(p, "amount", E08[0]) and _eq_codes(p, "voucher_ids", E08[1]))),
    dict(id="erp_e09", split="eval", prompt=(
        "평택창고 재고 금액 합계가 얼마인지 알려주세요. 품목별로 평택창고 수량 × 품목 마스터 단가를 구해서 전부 더하면 됩니다. "
        + JSON_RULE + '{"warehouse": "평택창고", "total": 재고금액 합계(원, 정수)}'),
        contract={"type": "json", "keys": {"warehouse": "str", "total": "int"}},
        check=_json_check(lambda p: _eq_num(p, "total", E09))),
    dict(id="erp_e10", split="eval", prompt=(
        "거래처 (주)서진정밀 사업자등록번호랑 현재 거래 상태 좀 알려주세요. 상태는 시스템 값 그대로(active 또는 suspended) 적어주세요. "
        + JSON_RULE + '{"biz_no": "000-00-00000", "status": 상태값}'),
        contract={"type": "json", "keys": {"biz_no": "str", "status": "str"}},
        check=_json_check(lambda p: str(_get(p, "biz_no")).strip() == E10["biz_no"]
                          and str(_get(p, "status")).strip().lower() == E10["status"])),
    dict(id="erp_e11", split="eval", prompt=(
        "생산팀 수선비가 예전보다 얼마나 늘었는지 보려고 해요. 2023년 전표 백업본과 올해(2026년) 전표에서 각각 "
        "생산팀 수선비 금액 합계를 구해주세요. 이건 상태 상관없이(미결·승인·반려 전부 포함) 합쳐주세요. "
        "diff는 2026년 합계 - 2023년 합계입니다. "
        + JSON_RULE + '{"total_2023": 정수, "total_2026": 정수, "diff": 정수}'),
        contract={"type": "json", "keys": {"total_2023": "int", "total_2026": "int", "diff": "int"}},
        check=_json_check(lambda p: _eq_num(p, "total_2023", E11_23) and _eq_num(p, "total_2026", E11_26)
                          and _eq_num(p, "diff", E11_26 - E11_23))),
    dict(id="erp_e12", split="eval", prompt=(
        "올해 미결 전표 금액 합계가 큰 거래처 순으로 상위 3곳을 알려주세요. 단, 거래중지(suspended) 거래처는 빼고 "
        "거래 중(active)인 곳만 봐주세요. 거래처명으로, 금액 큰 순서대로 적어주세요. "
        + JSON_RULE + '{"vendors": ["1위 거래처명", "2위 거래처명", "3위 거래처명"]}'),
        contract={"type": "json", "keys": {"vendors": "list"}},
        check=_json_check(lambda p: isinstance(_get(p, "vendors"), list)
                          and [_norm(x) for x in p["vendors"]] == [_norm(x) for x in E12])),
    dict(id="erp_e13", split="eval", prompt=(
        "본사창고만 기준으로, 본사창고 수량이 품목 안전재고보다 적은(미만) 품목을 찾아서 안전재고까지 채우려면 "
        "발주 금액이 얼마나 드는지 알려주세요. 품목별 부족 수량 = 안전재고 - 본사창고 수량, "
        "발주 금액 = 부족 수량 × 단가, 그걸 전부 더한 값입니다. 평택창고 재고는 고려하지 않습니다. "
        + JSON_RULE + '{"item_codes": ["ITM-0001", ...], "order_total": 발주금액 합계(원, 정수)}'),
        contract={"type": "json", "keys": {"item_codes": "list", "order_total": "int"}},
        check=_json_check(lambda p: _eq_codes(p, "item_codes", E13[0]) and _eq_num(p, "order_total", E13[1]))),
    dict(id="erp_e14", split="eval", prompt=(
        "매출채권 기준으로 미수잔액(청구액 - 입금액)이 가장 많이 남은 고객이 어디인지, 그 고객의 잔액 합계와 함께 알려주세요. "
        + JSON_RULE + '{"customer": 고객명, "balance": 잔액 합계(원, 정수)}'),
        contract={"type": "json", "keys": {"customer": "str", "balance": "int"}},
        check=_json_check(lambda p: _eq_name(p, "customer", E14[0]) and _eq_num(p, "balance", E14[1]))),
]
for _t in ERP_TASKS:
    _t.update(domain="erp", tools="erp")

# ================================================================= code tasks

TEXT = {"type": "text"}
CODE_DONE = " 다 되면 무엇을 바꿨는지 한두 줄로 알려주세요(답 형식은 자유 텍스트)."

# ---------------------------------------------------------------- dev: weekend bug
D01_SRC = '''"""영업일 계산 유틸."""
from datetime import date, timedelta


def is_weekend(d):
    """토요일·일요일이면 True."""
    return d.weekday() >= 6


def business_days(start, end):
    """start부터 end까지(양 끝 포함) 주말을 뺀 날 수."""
    n, d = 0, start
    while d <= end:
        if not is_weekend(d):
            n += 1
        d += timedelta(days=1)
    return n
'''
D01_TEST = '''from datetime import date
from workdays import is_weekend, business_days

assert is_weekend(date(2026, 10, 17)), "2026-10-17 is Saturday"
assert is_weekend(date(2026, 10, 18)), "2026-10-18 is Sunday"
assert not is_weekend(date(2026, 10, 16))
assert business_days(date(2026, 10, 12), date(2026, 10, 25)) == 10
print("ok")
'''
D01_HIDDEN = '''from datetime import date
from workdays import is_weekend, business_days
assert is_weekend(date(2026, 1, 3)) and is_weekend(date(2026, 1, 4)) and not is_weekend(date(2026, 1, 5))
assert business_days(date(2026, 2, 1), date(2026, 2, 28)) == 20
assert business_days(date(2026, 3, 7), date(2026, 3, 8)) == 0
print("hidden ok")
'''

# ---------------------------------------------------------------- dev: mask biz no (feature)
D02_SRC = '''"""거래처 정보 표시용 함수."""


def display_name(name, status):
    """거래중지 거래처는 이름 뒤에 ' (거래중지)'를 붙인다."""
    return name + " (거래중지)" if status == "suspended" else name
'''
D02_TEST = '''from vendor_fmt import display_name, mask_biz_no

assert display_name("대성산업", "active") == "대성산업"
assert display_name("동해물산", "suspended") == "동해물산 (거래중지)"
assert mask_biz_no("221-50-75865") == "221-50-*****"
assert mask_biz_no("2215075865") == "221-50-*****"
print("ok")
'''
D02_HIDDEN = '''from vendor_fmt import mask_biz_no
assert mask_biz_no("624-92-23452") == "624-92-*****"
assert mask_biz_no(" 6249223452 ") == "624-92-*****"
for bad in ("12-34-5678", "abc-de-fghij", "62492234520"):
    try:
        mask_biz_no(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for " + bad)
print("hidden ok")
'''

# ---------------------------------------------------------------- dev: discount tier boundary
D03_SRC = '''"""주문 금액별 할인율."""

TIERS = [(1000000, 5), (3000000, 8), (5000000, 10)]   # (기준 금액 이상, 할인율 %)


def discount_pct(amount):
    """amount가 기준 금액 '이상'이면 그 구간 할인율. 가장 높은 구간을 적용."""
    pct = 0
    for threshold, p in TIERS:
        if amount > threshold:
            pct = p
    return pct


def pay_amount(amount):
    """할인 후 결제 금액(원 미만 버림)."""
    return amount * (100 - discount_pct(amount)) // 100
'''
D03_TEST = '''from discount import discount_pct, pay_amount

assert discount_pct(999999) == 0
assert discount_pct(1000000) == 5
assert discount_pct(3000000) == 8
assert pay_amount(5000000) == 4500000
print("ok")
'''
D03_HIDDEN = '''from discount import discount_pct, pay_amount
assert discount_pct(2999999) == 5 and discount_pct(4999999) == 8 and discount_pct(9000000) == 10
assert pay_amount(1000000) == 950000 and pay_amount(123) == 123
print("hidden ok")
'''

# ---------------------------------------------------------------- e01: invoice discount ignored
E01_SRC = '''"""거래명세서 금액 계산."""
VAT_RATE = 10  # %


def line_supply(qty, unit_price, discount_pct=0):
    """한 줄의 공급가액: 수량 x 단가에서 할인율(%)을 적용한 금액, 원 미만 버림."""
    return qty * unit_price * (100 - discount_pct) // 100


def invoice_total(lines):
    """lines: [{"qty": 수량, "unit_price": 단가, "discount_pct": 할인율}] (discount_pct는 없을 수 있음, 없으면 0)
    반환: {"supply": 공급가액 합계, "vat": 공급가액 합계의 10%(원 미만 버림), "total": supply + vat}"""
    supply = 0
    for ln in lines:
        supply += line_supply(ln["qty"], ln["unit_price"])
    vat = supply * VAT_RATE // 100
    return {"supply": supply, "vat": vat, "total": supply + vat}
'''
E01_TEST = '''from invoice import invoice_total, line_supply

assert line_supply(3, 15000) == 45000
assert line_supply(7, 1350, 15) == 8032
r = invoice_total([{"qty": 3, "unit_price": 15000}, {"qty": 7, "unit_price": 1350, "discount_pct": 15}])
assert r == {"supply": 53032, "vat": 5303, "total": 58335}, r
print("ok")
'''
E01_HIDDEN = '''from invoice import invoice_total
r = invoice_total([{"qty": 10, "unit_price": 9900, "discount_pct": 5}, {"qty": 1, "unit_price": 777},
                   {"qty": 4, "unit_price": 2500, "discount_pct": 0}])
assert r == {"supply": 104827, "vat": 10482, "total": 115309}, r
assert invoice_total([{"qty": 2, "unit_price": 50000}]) == {"supply": 100000, "vat": 10000, "total": 110000}
assert invoice_total([]) == {"supply": 0, "vat": 0, "total": 0}
print("hidden ok")
'''

# ---------------------------------------------------------------- e02: CSV parser breaks on quoted amounts
E02_SRC = '''"""전표 CSV 읽기.
첫 줄은 헤더(전표번호,일자,계정,금액,상태). 금액은 1200000 또는 "1,200,000"처럼
큰따옴표 안에 쉼표가 들어간 형태로 올 수 있다. 빈 줄은 건너뛴다."""


def parse(text):
    """CSV 문자열 -> [{"voucher_id", "date", "account", "amount"(int), "status"}]"""
    rows = []
    lines = text.strip().splitlines()
    for line in lines[1:]:
        vid, date, account, amount, status = line.split(",")
        rows.append({"voucher_id": vid, "date": date, "account": account,
                     "amount": int(amount), "status": status})
    return rows


def total(rows, status=None):
    """status가 주어지면 그 상태인 전표만 합산."""
    return sum(r["amount"] for r in rows if status is None or r["status"] == status)
'''
E02_TEST = '''from voucher_csv import parse, total

CSV = """전표번호,일자,계정,금액,상태
JV-2026-0001,2026-02-20,수선비,"3,790,000",미결

JV-2026-0002,2026-05-19,소모품비,720000,승인
JV-2026-0003,2026-05-04,접대비,"1,050,000",승인
"""
rows = parse(CSV)
assert len(rows) == 3, rows
assert rows[0] == {"voucher_id": "JV-2026-0001", "date": "2026-02-20", "account": "수선비",
                   "amount": 3790000, "status": "미결"}, rows[0]
assert total(rows) == 5560000
assert total(rows, "승인") == 1770000
print("ok")
'''
E02_HIDDEN = '''from voucher_csv import parse, total
CSV = """전표번호,일자,계정,금액,상태


JV-2026-0100,2026-09-01,외주용역비,"12,000,000",반려
JV-2026-0101,2026-09-02,여비교통비,"85,000",승인
JV-2026-0102,2026-09-03,지급수수료,5000,승인

"""
rows = parse(CSV)
assert [r["amount"] for r in rows] == [12000000, 85000, 5000], rows
assert [r["status"] for r in rows] == ["반려", "승인", "승인"]
assert total(rows, "승인") == 90000 and total(rows, "미결") == 0
assert parse("전표번호,일자,계정,금액,상태\\n") == []
print("hidden ok")
'''

# ---------------------------------------------------------------- e03: add_months month-end / year rollover
E03_SRC = '''"""날짜 유틸."""
from datetime import date, timedelta


def add_months(d, n):
    """d에서 n개월 뒤의 같은 날(n이 음수면 n개월 전). 그 달에 같은 날이 없으면 그 달의 말일."""
    return d.replace(month=d.month + n)


def due_date(issue, months=1):
    """발행일 기준 결제 기한: months개월 뒤."""
    return add_months(issue, months)


def next_business_day(d):
    """d가 주말이면 다음 월요일, 아니면 d."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d
'''
E03_TEST = '''from datetime import date
from dates import add_months, due_date, next_business_day

assert add_months(date(2026, 3, 15), 2) == date(2026, 5, 15)
assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
assert due_date(date(2026, 12, 31)) == date(2027, 1, 31)
assert next_business_day(date(2026, 10, 17)) == date(2026, 10, 19)
print("ok")
'''
E03_HIDDEN = '''from datetime import date
from dates import add_months
assert add_months(date(2026, 5, 31), -15) == date(2025, 2, 28)
assert add_months(date(2026, 12, 31), 12) == date(2027, 12, 31)
assert add_months(date(2026, 8, 31), 1) == date(2026, 9, 30)
assert add_months(date(2026, 1, 15), -1) == date(2025, 12, 15)
assert add_months(date(2026, 7, 9), 0) == date(2026, 7, 9)
assert add_months(date(2027, 2, 28), 24) == date(2029, 2, 28)
assert add_months(date(2026, 10, 31), 40) == date(2030, 2, 28)
print("hidden ok")
'''

# ---------------------------------------------------------------- e04: reorder list (three bugs)
E04_SRC = '''"""재고 보충(발주) 대상 계산."""


def total_qty(stock):
    """stock: [{"item_code", "warehouse", "qty"}] -> {item_code: 전 창고 수량 합계}"""
    totals = {}
    for s in stock:
        totals[s["item_code"]] = s["qty"]
    return totals


def reorder_list(items, stock):
    """items: [{"item_code", "safety_stock", "lot"}]
    전 창고 합계가 안전재고 미만인 품목만, 안전재고까지 채우는 데 필요한 수량을 lot(발주 단위)의
    배수로 올림해서 [(item_code, 발주수량)]으로 반환. item_code 순 정렬.
    stock에 기록이 없는 품목은 재고 0으로 본다."""
    totals = total_qty(stock)
    out = []
    for it in items:
        have = totals[it["item_code"]]
        if have < it["safety_stock"]:
            need = it["safety_stock"] - have
            lots = need // it["lot"]
            out.append((it["item_code"], lots * it["lot"]))
    return sorted(out)
'''
E04_TEST = '''from inventory import total_qty, reorder_list

STOCK = [
    {"item_code": "ITM-0002", "warehouse": "본사창고", "qty": 30},
    {"item_code": "ITM-0002", "warehouse": "평택창고", "qty": 25},
    {"item_code": "ITM-0001", "warehouse": "본사창고", "qty": 12},
    {"item_code": "ITM-0001", "warehouse": "평택창고", "qty": 3},
]
ITEMS = [
    {"item_code": "ITM-0002", "safety_stock": 50, "lot": 10},
    {"item_code": "ITM-0001", "safety_stock": 40, "lot": 10},
    {"item_code": "ITM-0003", "safety_stock": 20, "lot": 12},
]
assert total_qty(STOCK) == {"ITM-0002": 55, "ITM-0001": 15}
assert reorder_list(ITEMS, STOCK) == [("ITM-0001", 30), ("ITM-0003", 24)], reorder_list(ITEMS, STOCK)
print("ok")
'''
E04_HIDDEN = '''from inventory import reorder_list
STOCK = [{"item_code": "A", "warehouse": "w1", "qty": 5}, {"item_code": "A", "warehouse": "w2", "qty": 5},
         {"item_code": "A", "warehouse": "w3", "qty": 5}, {"item_code": "B", "warehouse": "w1", "qty": 99},
         {"item_code": "C", "warehouse": "w2", "qty": 0}]
ITEMS = [{"item_code": "C", "safety_stock": 7, "lot": 7}, {"item_code": "B", "safety_stock": 100, "lot": 50},
         {"item_code": "A", "safety_stock": 15, "lot": 5}, {"item_code": "D", "safety_stock": 1, "lot": 100}]
assert reorder_list(ITEMS, STOCK) == [("B", 50), ("C", 7), ("D", 100)], reorder_list(ITEMS, STOCK)
assert reorder_list([], STOCK) == []
print("hidden ok")
'''

# ---------------------------------------------------------------- e05: installment split remainder + year rollover
E05_SRC = '''"""분할 청구 금액과 일정."""


def split_amount(total, n):
    """total원을 n회로 나눈 금액 리스트. 합계는 total과 정확히 같아야 하며,
    나누어떨어지지 않는 나머지는 앞 회차부터 1원씩 더 얹는다."""
    base = total // n
    return [base] * n


def schedule(total, n, first_month):
    """[("YYYY-MM", 금액), ...] n회. first_month는 "YYYY-MM", 매달 1회씩."""
    y, m = map(int, first_month.split("-"))
    out = []
    for amt in split_amount(total, n):
        out.append((f"{y}-{m:02d}", amt))
        m += 1
        if m > 12:
            y, m = y + 1, 0
    return out
'''
E05_TEST = '''from installment import split_amount, schedule

assert split_amount(90000, 3) == [30000, 30000, 30000]
assert split_amount(100000, 3) == [33334, 33333, 33333]
assert split_amount(10, 4) == [3, 3, 2, 2]
assert schedule(100000, 3, "2026-11") == [("2026-11", 33334), ("2026-12", 33333), ("2027-01", 33333)]
print("ok")
'''
E05_HIDDEN = '''from installment import split_amount, schedule
for total, n in [(1, 3), (999999, 7), (12000000, 12), (5, 5), (7, 1)]:
    parts = split_amount(total, n)
    assert sum(parts) == total and len(parts) == n and max(parts) - min(parts) <= 1, (total, n, parts)
    assert parts == sorted(parts, reverse=True)
s = schedule(2500000, 15, "2026-12")
assert [m for m, _ in s][:3] == ["2026-12", "2027-01", "2027-02"] and s[-1][0] == "2028-02", s
assert s[13][0] == "2028-01"
print("hidden ok")
'''

# ---------------------------------------------------------------- e06: feature - withholding tax
E06_SRC = '''"""외주·프리랜서 지급액 계산."""


def floor10(x):
    """10원 미만 버림."""
    return x // 10 * 10


def gross_from_hours(hours, hourly_rate):
    """작업 시간 x 시간당 단가."""
    return hours * hourly_rate
'''
E06_TEST = '''from payroll import floor10, gross_from_hours, withholding

assert floor10(1239) == 1230
assert gross_from_hours(12, 45000) == 540000
assert withholding(1000000) == {"income_tax": 30000, "local_tax": 3000, "net": 967000}
assert withholding(1234567) == {"income_tax": 37030, "local_tax": 3700, "net": 1193837}
print("ok")
'''
E06_HIDDEN = '''from payroll import withholding
assert withholding(540000) == {"income_tax": 16200, "local_tax": 1620, "net": 522180}
assert withholding(33333) == {"income_tax": 990, "local_tax": 90, "net": 32253}
assert withholding(300) == {"income_tax": 0, "local_tax": 0, "net": 300}
assert withholding(0) == {"income_tax": 0, "local_tax": 0, "net": 0}
r = withholding(87654321)
assert r == {"income_tax": 2629620, "local_tax": 262960, "net": 84761741}, r
print("hidden ok")
'''

# ---------------------------------------------------------------- e07: feature - summarize by account (2 files)
E07_SRC = '''"""전표 목록 다루기. 전표: {"voucher_id", "date": "YYYY-MM-DD", "account", "amount", "status"}"""


def in_period(v, start, end):
    """전표 일자가 start~end(양 끝 포함, "YYYY-MM-DD")에 들어가면 True."""
    return start <= v["date"] <= end


def by_status(vouchers, status):
    return [v for v in vouchers if v["status"] == status]
'''
E07_REPORT = '''"""계정별 합계를 보고서 문자열로."""


def render(summary):
    """summary: {계정: 금액} -> 금액 큰 순(같으면 계정명 순)으로 '계정: 1,234원' 줄들."""
    items = sorted(summary.items(), key=lambda kv: (-kv[1], kv[0]))
    return "\\n".join(f"{k}: {v:,}원" for k, v in items)
'''
E07_TEST = '''from vouchers import summarize
from report import render

VS = [
    {"voucher_id": "JV-1", "date": "2026-07-01", "account": "소모품비", "amount": 120000, "status": "승인"},
    {"voucher_id": "JV-2", "date": "2026-07-15", "account": "소모품비", "amount": 30000, "status": "미결"},
    {"voucher_id": "JV-3", "date": "2026-07-20", "account": "접대비", "amount": 500000, "status": "반려"},
    {"voucher_id": "JV-4", "date": "2026-07-31", "account": "수선비", "amount": 200000, "status": "승인"},
    {"voucher_id": "JV-5", "date": "2026-08-01", "account": "수선비", "amount": 900000, "status": "승인"},
]
s = summarize(VS, "2026-07-01", "2026-07-31")
assert s == {"소모품비": 150000, "수선비": 200000}, s
assert render(s) == "수선비: 200,000원\\n소모품비: 150,000원"
print("ok")
'''
E07_HIDDEN = '''from vouchers import summarize
VS = [
    {"voucher_id": "a", "date": "2026-01-01", "account": "X", "amount": 1, "status": "승인"},
    {"voucher_id": "b", "date": "2026-12-31", "account": "X", "amount": 10, "status": "미결"},
    {"voucher_id": "c", "date": "2025-12-31", "account": "X", "amount": 100, "status": "승인"},
    {"voucher_id": "d", "date": "2026-06-30", "account": "Y", "amount": 1000, "status": "반려"},
    {"voucher_id": "e", "date": "2026-06-30", "account": "Z", "amount": 5, "status": "승인"},
]
s = summarize(VS, "2026-01-01", "2026-12-31")
assert s == {"X": 11, "Z": 5}, s
assert summarize(VS, "2027-01-01", "2027-12-31") == {}
assert len(VS) == 5 and VS[0]["amount"] == 1
print("hidden ok")
'''

# ---------------------------------------------------------------- e08: feature - format/parse KRW
E08_SRC = '''"""금액 표시 유틸."""


def to_man(n):
    """원 -> 만원 단위 정수(버림). 예: 1,234,000 -> 123"""
    return n // 10000
'''
E08_TEST = '''from money import to_man, format_krw, parse_krw

assert to_man(1234000) == 123
assert format_krw(1234000) == "1,234,000원"
assert format_krw(-1500) == "-1,500원"
assert format_krw(0) == "0원"
assert parse_krw("1,234,000원") == 1234000
assert parse_krw(" 500 원 ") == 500
assert parse_krw("-1,500원") == -1500
try:
    parse_krw("일천원")
except ValueError:
    pass
else:
    raise AssertionError("parse_krw must raise ValueError on non-numeric text")
print("ok")
'''
E08_HIDDEN = '''from money import format_krw, parse_krw
assert format_krw(999) == "999원" and format_krw(1000) == "1,000원" and format_krw(-1234567890) == "-1,234,567,890원"
for n in (0, 7, 10000, 98765432, -42):
    assert parse_krw(format_krw(n)) == n
assert parse_krw("70000") == 70000
for bad in ("", "원", "12a원", "1,2,3x"):
    try:
        parse_krw(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for " + repr(bad))
print("hidden ok")
'''


def _code_task(id, split, prompt, files, test_file, hidden):
    return dict(id=id, split=split, domain="code", tools="code", prompt=prompt + CODE_DONE,
                files=files, test_cmd=[test_file], contract=TEXT,
                check=_code_check({test_file: files[test_file]}, hidden))


CODE_TASKS = [
    _code_task("code_d01", "dev",
               "workdays.py 영업일 계산이 토요일을 영업일로 치는 것 같아요. test_workdays.py가 실패합니다. 고쳐주세요.",
               {"workdays.py": D01_SRC, "test_workdays.py": D01_TEST}, "test_workdays.py", D01_HIDDEN),
    _code_task("code_d02", "dev",
               "vendor_fmt.py에 사업자등록번호 마스킹 함수 mask_biz_no(biz_no)를 추가해주세요. 하이픈이 있든 없든(앞뒤 공백 무시) "
               "숫자 10자리를 받아서 '221-50-*****'처럼 앞 3자리-가운데 2자리-뒤 5자리는 *로 바꾼 문자열을 돌려주고, "
               "숫자가 10자리가 아니거나 숫자 아닌 글자가 섞여 있으면(하이픈 제외) ValueError를 내야 합니다. "
               "test_vendor_fmt.py가 통과해야 해요.",
               {"vendor_fmt.py": D02_SRC, "test_vendor_fmt.py": D02_TEST}, "test_vendor_fmt.py", D02_HIDDEN),
    _code_task("code_d03", "dev",
               "discount.py 할인율이 기준 금액 딱 맞을 때(예: 정확히 100만원) 적용이 안 됩니다. 기준 금액 '이상'이면 적용돼야 해요. "
               "test_discount.py 통과하게 고쳐주세요.",
               {"discount.py": D03_SRC, "test_discount.py": D03_TEST}, "test_discount.py", D03_HIDDEN),
    _code_task("code_e01", "eval",
               "거래명세서 합계가 이상하게 나와요. 할인 들어간 품목이 있는데 할인이 반영이 안 되는 것 같습니다. "
               "invoice.py 고쳐서 test_invoice.py 통과하게 해주세요. 할인율이 없는 줄도 있으니 그것도 돌아가야 해요.",
               {"invoice.py": E01_SRC, "test_invoice.py": E01_TEST}, "test_invoice.py", E01_HIDDEN),
    _code_task("code_e02", "eval",
               "전표 CSV 읽는 voucher_csv.py가 금액에 쉼표 들어간 줄(\"3,790,000\"처럼 따옴표로 감싼 것)이나 빈 줄이 있으면 "
               "터집니다. 표준 라이브러리만 써서 고쳐주세요. test_voucher_csv.py가 통과해야 합니다.",
               {"voucher_csv.py": E02_SRC, "test_voucher_csv.py": E02_TEST}, "test_voucher_csv.py", E02_HIDDEN),
    _code_task("code_e03", "eval",
               "dates.py의 add_months가 1월 31일에 한 달 더하면 에러가 나고, 연도 넘어가는 경우도 안 됩니다. "
               "docstring대로(그 달에 같은 날이 없으면 말일, n은 음수도 가능, 몇 년을 넘어가도 됨) 동작하게 고쳐주세요. "
               "test_dates.py가 통과해야 해요.",
               {"dates.py": E03_SRC, "test_dates.py": E03_TEST}, "test_dates.py", E03_HIDDEN),
    _code_task("code_e04", "eval",
               "inventory.py의 발주 대상 계산 결과가 실제랑 안 맞아요. 창고가 여러 개인 품목, 재고 기록이 아예 없는 품목, "
               "발주 단위(lot) 처리 쪽을 docstring 기준으로 확인하고 고쳐주세요. test_inventory.py가 통과해야 합니다.",
               {"inventory.py": E04_SRC, "test_inventory.py": E04_TEST}, "test_inventory.py", E04_HIDDEN),
    _code_task("code_e05", "eval",
               "installment.py로 분할 청구서를 만들었더니 회차 금액 합이 청구 총액보다 모자라고, 12월 다음 달이 이상하게 찍힙니다. "
               "docstring대로 고쳐서 test_installment.py가 통과하게 해주세요.",
               {"installment.py": E05_SRC, "test_installment.py": E05_TEST}, "test_installment.py", E05_HIDDEN),
    _code_task("code_e06", "eval",
               "payroll.py에 프리랜서 지급액 원천징수 계산 함수 withholding(amount)를 추가해주세요. amount는 지급액(원, 정수)입니다. "
               "소득세 = 지급액의 3%를 10원 미만 버림, 지방소득세 = 소득세의 10%를 10원 미만 버림, "
               "실지급액 net = 지급액 - 소득세 - 지방소득세. 반환값은 {\"income_tax\": 소득세, \"local_tax\": 지방소득세, \"net\": 실지급액} "
               "dict이고 값은 모두 int여야 합니다. 이미 있는 floor10을 써도 됩니다. test_payroll.py가 통과해야 해요.",
               {"payroll.py": E06_SRC, "test_payroll.py": E06_TEST}, "test_payroll.py", E06_HIDDEN),
    _code_task("code_e07", "eval",
               "vouchers.py에 summarize(vouchers, start, end) 함수를 추가해주세요. 전표 일자가 start~end(양 끝 포함, "
               "\"YYYY-MM-DD\" 문자열) 안에 있고 상태가 '반려'가 아닌 전표만 골라서 계정별 금액 합계를 {계정: 합계} dict로 "
               "돌려주면 됩니다. 해당 전표가 하나도 없는 계정은 dict에 넣지 마세요. 입력 리스트는 바꾸면 안 됩니다. "
               "report.py의 render와 같이 쓰는 테스트 test_summary.py가 통과해야 해요.",
               {"vouchers.py": E07_SRC, "report.py": E07_REPORT, "test_summary.py": E07_TEST}, "test_summary.py", E07_HIDDEN),
    _code_task("code_e08", "eval",
               "money.py에 금액 표시 함수 두 개를 추가해주세요. format_krw(n): 정수 n을 천 단위 쉼표와 '원'을 붙인 문자열로 "
               "(예: 1234000 -> '1,234,000원', -1500 -> '-1,500원', 0 -> '0원'). parse_krw(s): 그 반대로, 앞뒤·중간 공백과 "
               "쉼표, 끝의 '원'은 무시하고 정수로 바꿉니다(음수 부호 허용). 숫자로 해석할 수 없으면(빈 문자열 포함) ValueError를 "
               "내야 합니다. test_money.py가 통과해야 합니다.",
               {"money.py": E08_SRC, "test_money.py": E08_TEST}, "test_money.py", E08_HIDDEN),
]

# ================================================================= document tasks

BOILER = [
    ("비밀유지", "각 당사자는 본 계약의 체결 및 이행 과정에서 알게 된 상대방의 영업상·기술상 정보를 상대방의 사전 서면 동의 없이 "
     "제3자에게 누설하거나 본 계약의 목적 외의 용도로 사용하여서는 아니 된다. 다만, 법령 또는 관할 관청의 적법한 요구에 따라 "
     "공개하는 경우에는 그러하지 아니하되, 이 경우 공개 전에 상대방에게 그 사실을 지체 없이 통지하여야 한다."),
    ("권리·의무의 양도 금지", "각 당사자는 상대방의 사전 서면 동의 없이 본 계약상의 지위 또는 본 계약에 따른 권리·의무의 전부 또는 "
     "일부를 제3자에게 양도하거나 담보로 제공할 수 없다."),
    ("불가항력", "천재지변, 전쟁, 내란, 법령의 제정·개폐, 감염병의 대유행 등 당사자의 합리적인 통제 범위를 벗어난 사유로 본 계약의 "
     "전부 또는 일부를 이행할 수 없는 경우, 해당 당사자는 그 사유가 지속되는 기간 동안 이행 지체의 책임을 지지 아니한다. "
     "이 경우 해당 당사자는 그 사유의 발생 및 종료를 상대방에게 지체 없이 서면으로 통지하여야 한다."),
    ("계약의 해제·해지", "각 당사자는 상대방이 본 계약상의 중대한 의무를 위반하고 서면으로 시정을 요구받은 날부터 14일 이내에 이를 "
     "시정하지 아니하는 경우 서면 통지로써 본 계약을 해제 또는 해지할 수 있다. 상대방에게 파산, 회생절차 개시의 신청, "
     "어음·수표의 부도 등 정상적인 계약 이행이 어렵다고 인정되는 사유가 발생한 경우에도 같다."),
    ("손해배상", "각 당사자는 자신의 귀책사유로 본 계약을 위반하여 상대방에게 손해를 입힌 경우 그 손해를 배상하여야 한다. "
     "다만, 간접손해 및 특별손해는 그 발생 가능성을 알았거나 알 수 있었던 경우에 한하여 배상한다."),
    ("통지", "본 계약에 따른 통지는 계약서에 기재된 주소 또는 전자우편 주소로 서면 또는 전자우편으로 하며, 상대방에게 도달한 때에 "
     "효력이 발생한다. 주소 등이 변경된 당사자는 변경일부터 7일 이내에 이를 상대방에게 통지하여야 한다."),
    ("분쟁의 해결", "본 계약과 관련하여 분쟁이 발생한 경우 당사자는 상호 협의하여 원만히 해결하도록 노력하며, 협의가 이루어지지 "
     "아니하는 경우 서울중앙지방법원을 제1심 전속 관할 법원으로 한다."),
    ("계약의 변경", "본 계약의 내용은 당사자 쌍방이 기명날인 또는 서명한 서면 합의에 의하여만 변경할 수 있으며, 변경 계약서는 "
     "본 계약서의 일부를 구성한다. 변경 계약서와 본 계약서의 내용이 서로 다른 경우에는 변경 계약서의 내용이 우선한다."),
    ("준거법", "본 계약은 대한민국 법률에 따라 해석되고 규율된다."),
    ("기타", "본 계약에 정하지 아니한 사항이나 해석상 이견이 있는 사항은 관계 법령 및 일반 상관례에 따르되, 당사자 간 상호 "
     "협의하여 정한다. 본 계약의 체결을 증명하기 위하여 계약서 2부를 작성하여 각 당사자가 기명날인한 후 각 1부씩 보관한다."),
]


def _articles(specific, start=1, boiler=BOILER):
    out, n = [], start
    for title, body in list(specific) + list(boiler):
        out.append(f"제{n}조({title}) {body}")
        n += 1
    return "\n\n".join(out)


# ---------------------------------------------------------------- dev docs
DD01 = {"total": 4_730_000, "valid": "2026-11-20"}
DOC_D01 = {"QT-2026-118": ("(주)온누리IT 견적서 - 회의실 영상장비", (
    "견 적 서\n\n견적번호: QT-2026-118\n견적일자: 2026년 10월 21일\n수신: 경영지원팀 귀중\n발신: (주)온누리IT 영업2팀\n\n"
    "아래와 같이 견적합니다.\n\n"
    "| 품명 | 규격 | 수량 | 단가 | 금액 |\n"
    "| 회의실 PTZ 카메라 | 4K, 12배 줌 | 2 | 1,250,000 | 2,500,000 |\n"
    "| 천장형 마이크 | 빔포밍 | 2 | 640,000 | 1,280,000 |\n"
    "| 설치비 | 배선·설정 포함 | 1식 | 520,000 | 520,000 |\n\n"
    "공급가액: 4,300,000원\n부가세(10%): 430,000원\n"
    f"합계 금액(부가세 포함): {DD01['total']:,}원\n\n"
    "※ 본 견적의 유효기간은 2026년 11월 20일까지입니다. 유효기간 경과 후에는 환율 및 재고 상황에 따라 금액이 변동될 수 있습니다.\n"
    "※ 납품은 발주 후 3주 이내, 대금은 설치 완료 후 익월 말 현금 지급 조건입니다.\n"))}

DD02 = {"days": 60}
DOC_D02 = {"CT-SVC-031": ("청솔인쇄 인쇄물 제작 기본계약서", (
    "인쇄물 제작 기본계약서\n\n(주)위그텍(이하 \"갑\")과 청솔인쇄(이하 \"을\")는 갑이 의뢰하는 인쇄물의 제작에 관하여 다음과 같이 계약을 체결한다.\n\n"
    + _articles([
        ("목적", "본 계약은 갑이 개별 발주서로 의뢰하는 인쇄물을 을이 제작·납품하는 데 필요한 기본 사항을 정함을 목적으로 한다."),
        ("계약기간", "본 계약의 기간은 2026년 1월 1일부터 2026년 12월 31일까지로 한다. 기간 만료 30일 전까지 어느 당사자도 "
         "서면으로 종료 의사를 표시하지 않으면 동일 조건으로 1년씩 자동 연장된다."),
        ("중도 해지", f"각 당사자는 해지 희망일 {DD02['days']}일 전까지 상대방에게 서면으로 통보함으로써 본 계약을 중도 해지할 수 있다. "
         "이 경우 해지 통보 전에 발주된 건은 정상적으로 이행한다."),
    ], boiler=BOILER[5:8])))}

# ---------------------------------------------------------------- e01: supply contract with amendment (long)
DE01 = {"orig_amount": 120_000_000, "amount": 132_000_000, "orig_due": "2026-11-30", "due": "2026-12-15", "rate": 0.15}
_de01_main = (
    "물품공급계약서\n\n계약번호: PC-2026-0412\n\n(주)위그텍(이하 \"구매자\")과 (주)서진정밀(이하 \"공급자\")은 아래 물품의 공급에 관하여 "
    "다음과 같이 계약을 체결한다.\n\n"
    + _articles([
        ("목적", "본 계약은 공급자가 구매자에게 정밀 가공 지그(JIG) 및 부속품(이하 \"계약물품\")을 공급하고, 구매자가 그 대금을 "
         "지급하는 데 필요한 사항을 정함을 목적으로 한다."),
        ("계약물품", "계약물품의 품명, 규격, 수량은 별첨 1(물품 명세서)에 따르며, 별첨 1에 정하지 아니한 세부 사양은 구매자가 승인한 "
         "도면에 따른다."),
        ("계약금액", f"계약금액은 금 {DE01['orig_amount']:,}원(부가가치세 별도)으로 한다. 계약금액에는 계약물품의 제작, 포장, "
         "운반 및 구매자 지정 장소까지의 하역 비용이 포함된다."),
        ("대금 지급", "구매자는 계약물품의 검수 완료 후 공급자가 발행한 적법한 세금계산서를 받은 날이 속한 달의 다음 달 말일까지 "
         "계약금액을 현금으로 지급한다."),
        ("납품", f"공급자는 계약물품을 {DE01['orig_due'][:4]}년 {int(DE01['orig_due'][5:7])}월 {int(DE01['orig_due'][8:])}일까지 "
         "구매자의 평택 사업장에 납품하여야 한다. 분할 납품은 구매자의 사전 서면 승인을 받은 경우에 한하여 허용된다."),
        ("검수", "구매자는 납품일부터 10영업일 이내에 계약물품을 검수하고 그 결과를 공급자에게 서면으로 통지한다. 검수 결과 "
         "불합격된 물품에 대하여 공급자는 통지를 받은 날부터 7일 이내에 보완하거나 대체품을 납품하여야 한다."),
        ("소유권 및 위험의 이전", "계약물품의 소유권 및 위험 부담은 검수에 합격한 때에 공급자로부터 구매자에게 이전된다."),
        ("하자보증", "공급자는 검수 합격일부터 12개월간 계약물품의 하자에 대하여 무상으로 보수 또는 교체할 책임을 진다."),
        ("품질관리", "공급자는 계약물품의 제작 전 공정에 대하여 품질관리 계획서를 작성하여 착수 전에 구매자의 승인을 받아야 하며, "
         "주요 치수 및 경도에 대한 자체 검사 성적서를 납품 시 함께 제출하여야 한다. 구매자는 필요한 경우 사전 통지 후 "
         "공급자의 제작 현장을 방문하여 공정 및 품질 상태를 확인할 수 있다."),
        ("하도급의 제한", "공급자는 구매자의 사전 서면 승인 없이 계약물품 제작의 전부 또는 주요 부분을 제3자에게 하도급할 수 없다. "
         "승인을 받아 하도급한 경우에도 공급자는 하도급자의 행위에 대하여 구매자에게 직접 책임을 진다."),
        ("지식재산권", "구매자가 제공한 도면, 사양서 및 그 밖의 기술자료에 관한 권리는 구매자에게 귀속되며, 공급자는 이를 "
         "본 계약의 이행 외의 목적으로 사용하거나 복제할 수 없다. 공급자는 계약 종료 시 해당 자료를 지체 없이 반환하거나 "
         "구매자의 지시에 따라 폐기하여야 한다."),
        ("안전·보건", "공급자의 임직원이 납품 또는 설치를 위하여 구매자의 사업장에 출입하는 경우 구매자의 안전·보건 규정을 "
         "준수하여야 하며, 출입 전 구매자가 실시하는 안전 교육을 이수하여야 한다."),
        ("지체상금", f"공급자가 제5조의 납품기한까지 계약물품을 납품하지 못한 경우, 지체 1일마다 계약금액의 {DE01['rate']}%에 해당하는 "
         "금액을 지체상금으로 구매자에게 지급하여야 한다. 지체상금의 총액은 계약금액의 10%를 한도로 한다."),
    ])
    + "\n\n2026년 4월 12일\n\n구매자: (주)위그텍 대표이사 (인)\n공급자: (주)서진정밀 대표이사 (인)\n\n"
    "[별첨 1] 물품 명세서\n1. 정밀 가공 지그 A형 - 40조\n2. 정밀 가공 지그 B형 - 25조\n3. 교체용 클램프 세트 - 130세트\n"
)
_de01_amend = (
    "\n\n제1차 변경계약서\n\n(주)위그텍과 (주)서진정밀은 2026년 4월 12일 체결한 물품공급계약(계약번호 PC-2026-0412, 이하 \"원계약\")을 "
    "다음과 같이 변경한다.\n\n"
    "1. 변경 사유: 구매자의 설계 변경 요청에 따른 지그 B형 수량 증가(25조 → 31조) 및 이에 따른 제작 기간 연장\n"
    f"2. 계약금액: 원계약 제3조의 계약금액 금 {DE01['orig_amount']:,}원(부가가치세 별도)을 금 {DE01['amount']:,}원"
    "(부가가치세 별도)으로 변경한다.\n"
    f"3. 납품기한: 원계약 제5조의 납품기한을 {DE01['due'][:4]}년 {int(DE01['due'][5:7])}월 {int(DE01['due'][8:])}일까지로 변경한다.\n"
    "4. 그 밖의 사항: 본 변경계약서에서 정하지 아니한 사항은 원계약에 따른다. 지체상금률 및 하자보증 기간은 원계약과 같다.\n\n"
    "2026년 9월 3일\n\n구매자: (주)위그텍 대표이사 (인)\n공급자: (주)서진정밀 대표이사 (인)\n"
)
DOC_E01 = {"PC-2026-0412": ("(주)서진정밀 물품공급계약서 (변경계약 포함)", _de01_main + _de01_amend)}
assert len(_de01_main) > 3000

# ---------------------------------------------------------------- e02: meeting minutes, revised budget
DE02 = {"budget": 42_000_000, "owner": "박지현", "go_live": "2027-03-02"}
DOC_E02 = {"MIN-2026-1007": ("그룹웨어 교체 검토 회의록 (2026-10-07)", (
    "그룹웨어 교체 검토 회의록\n\n일시: 2026년 10월 7일(수) 14:00~15:30\n장소: 본사 7층 대회의실\n"
    "참석: 경영지원팀 최도윤 팀장, 정보전략팀 박지현 책임, 정보전략팀 강민호 선임, 구매팀 오세린 과장, 영업팀 윤태경 차장\n"
    "작성: 정보전략팀 강민호\n\n"
    "1. 안건\n- 현 그룹웨어(2019년 도입) 유지보수 종료(2027년 6월)에 따른 교체 방안\n- 교체 예산 및 일정\n\n"
    "2. 논의 내용\n"
    "- 강민호 선임: 클라우드형 3개 제품 비교 결과 보고. 전자결재 양식 이관 비용 차이가 가장 큼.\n"
    "- 박지현 책임: 1차 검토안으로 교체 예산 3,800만원(라이선스 1년분 + 이관 용역)을 제안. 오픈 목표일은 2027년 2월 1일로 제시.\n"
    "- 오세린 과장: 3,800만원에는 전자결재 양식 이관 중 구매 품의 양식(42종) 재작성 비용이 빠져 있음. 견적 기준 약 400만원 추가 필요.\n"
    "- 윤태경 차장: 2월 초는 영업 결산 기간과 겹쳐 사용자 교육이 어려움. 3월 오픈 희망.\n"
    "- 최도윤 팀장: 양식 재작성 비용 포함하여 예산 증액하고, 오픈은 결산 이후로 조정하는 것에 동의.\n\n"
    "3. 결정 사항\n"
    f"- 그룹웨어 교체 예산을 {DE02['budget'] // 10000:,}만원(부가세 별도)으로 최종 확정함. (1차 제안 3,800만원은 폐기)\n"
    f"- 오픈 목표일: {DE02['go_live'][:4]}년 {int(DE02['go_live'][5:7])}월 {int(DE02['go_live'][8:])}일(화). 2월 1일안은 채택하지 않음.\n"
    f"- 사업 총괄 담당: 정보전략팀 {DE02['owner']} 책임\n\n"
    "4. 후속 조치\n- 강민호 선임: 제품 2개로 압축한 비교표 작성 (10월 16일까지)\n- 오세린 과장: 양식 재작성 견적 정식 접수 (10월 14일까지)\n"
    "- 다음 회의: 2026년 10월 21일(수) 14:00\n"))}

# ---------------------------------------------------------------- e03: purchase spec, compute total from table
DE03_LINES = [("산업용 PC", "i5급, 16GB, SSD 512GB, 팬리스", 6, 1_380_000),
              ("23인치 산업용 모니터", "IP65 전면 방진방수", 6, 420_000),
              ("무정전전원장치(UPS)", "1kVA, 라인인터랙티브", 3, 515_000),
              ("바코드 스캐너", "2D, 유선 USB", 12, 168_000),
              ("설치 및 시운전", "현장 설치, 라인 연동 시험", 1, 1_900_000)]
DE03 = {"total": sum(q * p for _, _, q, p in DE03_LINES), "place": "평택"}
DOC_E03 = {"SPEC-PRD-2026-07": ("생산라인 3호기 공정 단말 구매사양서", (
    "구매사양서\n\n문서번호: SPEC-PRD-2026-07\n요청부서: 생산팀\n건명: 생산라인 3호기 공정 단말 교체\n\n"
    "1. 구매 목적\n생산라인 3호기의 노후 공정 단말(2017년 도입)을 교체하여 MES 연동 오류를 줄이고 작업 실적 입력을 자동화한다.\n\n"
    "2. 구매 품목 (단가는 부가세 별도, 사전 견적 기준 예정 단가)\n"
    "| 번호 | 품명 | 규격 | 수량 | 예정 단가(원) |\n"
    + "".join(f"| {i + 1} | {n} | {s} | {q} | {p:,} |\n" for i, (n, s, q, p) in enumerate(DE03_LINES))
    + "\n3. 납품 조건\n- 납품 장소: 평택 사업장 생산동 2층 3호기 라인\n- 납품 기한: 발주 후 4주 이내\n- 설치 시간: 생산 중단을 피하기 위해 토요일 08:00~17:00\n\n"
    "4. 기술 요구사항\n- 산업용 PC는 기존 MES 클라이언트(Windows 기반)와 호환되어야 한다.\n"
    "- 바코드 스캐너는 기존 라벨(QR, Data Matrix) 판독률 99% 이상이어야 한다.\n- 하자보증: 검수 후 24개월\n\n"
    "5. 비고\n- 기존 단말은 경영지원팀 자산 담당과 협의하여 폐기한다.\n"))}

# ---------------------------------------------------------------- e04: travel policy, old vs revised table (long)
GRADES = ["임원", "부장", "차장·과장", "대리 이하"]
OLD = {"daily": [40000, 30000, 20000, 20000], "seoul": [150000, 110000, 90000, 80000],
       "metro": [130000, 90000, 80000, 70000], "other": [110000, 80000, 70000, 60000]}
NEW = {"daily": [50000, 35000, 25000, 25000], "seoul": [180000, 130000, 110000, 100000],
       "metro": [150000, 110000, 100000, 90000], "other": [130000, 100000, 90000, 80000]}
DE04 = {"daily_total": NEW["daily"][2] * 3, "lodging_total": NEW["metro"][2] * 2}


def _rate_table(t):
    rows = ["| 직급 | 일비(1일) | 숙박비 상한 - 서울특별시(1박) | 숙박비 상한 - 광역시(1박) | 숙박비 상한 - 그 밖의 지역(1박) |"]
    for i, g in enumerate(GRADES):
        rows.append(f"| {g} | {t['daily'][i]:,}원 | {t['seoul'][i]:,}원 | {t['metro'][i]:,}원 | {t['other'][i]:,}원 |")
    return "\n".join(rows)


_de04_body = (
    "국내 출장 여비 규정\n\n제정 2021. 3. 1.\n개정 2025. 1. 1.\n개정 2026. 7. 1.\n\n"
    "제1장 총칙\n\n"
    "제1조(목적) 이 규정은 임직원이 회사 업무로 국내 출장을 하는 경우 지급하는 여비의 기준과 정산 절차를 정함을 목적으로 한다.\n\n"
    "제2조(적용 범위) 이 규정은 회사의 모든 임직원과 회사가 업무를 위탁한 파견 인력에게 적용한다. 다만, 해외 출장은 별도의 "
    "해외 출장 여비 규정에 따른다.\n\n"
    "제3조(용어의 정의) 이 규정에서 사용하는 용어의 뜻은 다음과 같다.\n1. \"출장\"이란 소속 사업장 소재지를 벗어나 업무를 수행하는 것을 말한다.\n"
    "2. \"일비\"란 출장 중 현지 교통비, 통신비 등 잡비를 충당하기 위하여 출장 일수에 따라 정액으로 지급하는 금액을 말한다.\n"
    "3. \"숙박비\"란 출장 중 숙박 시설 이용에 실제로 든 비용을 말하며, 별표 1의 상한액 범위에서 실비로 지급한다.\n"
    "4. \"광역시\"란 부산, 대구, 인천, 광주, 대전, 울산광역시를 말한다.\n"
    "5. \"그 밖의 지역\"이란 서울특별시와 광역시를 제외한 지역을 말하며, 세종특별자치시와 제주특별자치도를 포함한다.\n"
    "6. \"직급\"이란 출장 출발일 현재 인사 기록상의 직급을 말하며, 직책 수당 대상자라도 직급을 기준으로 한다.\n"
    "7. \"귀임일\"이란 출장을 마치고 소속 사업장 또는 자택에 도착한 날을 말한다.\n\n"
    "제2장 출장 신청과 승인\n\n"
    "제4조(출장 신청) 출장자는 출발 3영업일 전까지 그룹웨어 전자결재로 출장 신청서를 제출하여야 한다. 긴급한 경우에는 "
    "구두로 소속 부서장의 승인을 받고 출장 후 3영업일 이내에 사후 신청할 수 있다.\n\n"
    "제5조(승인권자) 출장 승인권자는 소속 부서장으로 한다. 다만, 출장 기간이 5일을 넘거나 출장자가 부서장인 경우에는 "
    "차상위 직책자의 승인을 받아야 한다.\n\n"
    "제6조(출장 일수의 계산) 출장 일수는 출발일과 귀임일을 모두 포함하여 계산한다. 숙박 일수는 실제 숙박한 밤의 수로 한다.\n\n"
    "제6조의2(출장의 변경·취소) 출장 일정이나 출장지가 변경된 경우 출장자는 변경 사실을 안 날부터 1영업일 이내에 "
    "변경 신청을 하여야 한다. 출장이 취소되어 발생한 예약 취소 수수료는 회사 사정에 의한 경우 회사가 부담하고, 출장자의 "
    "개인 사정에 의한 경우 출장자가 부담한다.\n\n"
    "제6조의3(출장 보고) 출장자는 귀임 후 5영업일 이내에 출장 목적, 수행 내용, 후속 조치를 적은 출장 보고서를 승인권자에게 "
    "제출하여야 한다. 다만, 같은 거래처를 정기적으로 방문하는 출장은 월 1회 일괄 보고로 갈음할 수 있다.\n\n"
    "제3장 여비의 지급\n\n"
    "제7조(교통비) 교통비는 실비로 지급하되, 철도는 일반실, 항공은 일반석을 기준으로 한다. 자가용 차량을 이용한 경우에는 "
    "왕복 거리 1km당 250원과 통행료 실비를 지급한다. 택시 이용은 대중교통 이용이 곤란한 경우로 한정한다.\n\n"
    "제8조(일비) 일비는 출장 일수에 별표 1의 직급별 일비를 곱한 금액으로 하며, 증빙 없이 정액으로 지급한다. 회사 차량을 "
    "이용하거나 출장지에서 교통편을 제공받은 날에는 일비의 2분의 1을 지급한다.\n\n"
    "제9조(숙박비) 숙박비는 숙박 일수에 출장지 구분에 따른 별표 1의 직급별 1박 상한액을 곱한 금액의 범위에서 실비로 "
    "지급한다. 상한액을 초과한 금액은 출장자가 부담한다. 친지 집 등에 숙박하여 숙박비를 지출하지 아니한 경우에는 "
    "1박당 30,000원을 지급한다.\n\n"
    "제10조(식비) 식비는 별도로 지급하지 아니하며, 일비에 포함된 것으로 본다. 다만, 고객사와의 업무 식사는 접대비 "
    "규정에 따라 처리한다.\n\n"
    "제11조(동행 출장) 직급이 다른 임직원이 같은 목적으로 함께 출장하여 같은 숙소를 이용하는 경우에는 상위 직급자의 "
    "숙박비 상한액을 적용할 수 있다.\n\n"
    "제12조(휴일 출장) 토요일 또는 공휴일에 출장하는 경우에도 일비와 숙박비는 이 규정에 따라 지급하며, 휴일 근무에 대한 "
    "보상은 취업규칙 및 근로기준법에서 정하는 바에 따른다.\n\n"
    "제13조(교육·연수 출장) 사외 교육이나 연수에 참가하기 위한 출장으로서 주최 측이 숙식을 제공하는 경우에는 숙박비를 "
    "지급하지 아니하고, 일비의 2분의 1을 지급한다. 교육비는 교육 훈련 규정에 따라 별도로 처리한다.\n\n"
    "제14조(장기 출장) 같은 지역에 연속하여 15일을 넘게 출장하는 경우, 16일째부터는 일비의 10분의 8을 지급하고, 숙박비는 "
    "월 단위 임차 숙소 비용이 더 적으면 그 금액의 범위에서 실비로 지급한다.\n\n"
    "제15조(출장 중 질병 등) 출장 중 질병이나 사고로 예정보다 출장 기간이 늘어난 경우 출장자는 그 사실을 지체 없이 소속 "
    "부서장에게 보고하여야 하며, 늘어난 기간에 대하여도 이 규정에 따라 여비를 지급한다.\n\n"
    "제16조(여비의 부서 예산 처리) 여비는 출장자가 소속된 부서의 여비교통비 예산으로 집행한다. 다른 부서의 업무를 지원하기 "
    "위한 출장은 지원을 요청한 부서의 예산으로 집행할 수 있다.\n\n"
    "제4장 정산\n\n"
    "제17조(정산 기한) 출장자는 귀임 후 7일 이내에 여비 정산서를 제출하여야 하며, 숙박비와 교통비는 영수증 또는 "
    "카드 매출전표를 첨부하여야 한다.\n\n"
    "제18조(가지급금) 출장 기간이 3일 이상인 경우 출장자는 예상 여비의 80% 범위에서 가지급금을 신청할 수 있으며, "
    "정산 시 차액을 반납하거나 추가로 지급받는다.\n\n"
    "제19조(부정 수급) 허위 증빙으로 여비를 받은 경우에는 그 금액을 환수하고 취업규칙에 따라 징계할 수 있다.\n\n"
    "부칙 <2025. 1. 1.>\n이 규정은 2025년 1월 1일부터 시행한다.\n\n"
    "[별표 1 (구)] 직급별 여비 지급 기준 — 2025. 1. 1. 시행, 2026. 6. 30. 이전에 출발한 출장에 적용\n"
    + _rate_table(OLD) + "\n\n"
)
_de04_tail = (
    "부칙 <2026. 7. 1.>\n제1조(시행일) 이 규정은 2026년 7월 1일부터 시행한다.\n"
    "제2조(경과 조치) 2026년 6월 30일 이전에 출발한 출장에 대하여는 종전의 별표 1(구)을 적용한다.\n\n"
    "[별표 1] 직급별 여비 지급 기준 — 2026. 7. 1. 이후 출발한 출장부터 적용\n"
    + _rate_table(NEW) + "\n\n※ 직급 구분에서 차장과 과장은 같은 기준을 적용한다.\n"
)
DOC_E04 = {"REG-HR-012": ("국내 출장 여비 규정", _de04_body + _de04_tail)}
assert len(_de04_body) > 3000

# ---------------------------------------------------------------- e05: three NDAs, compare confidentiality periods
NDA_YEARS = {"NDA-2026-01": ("(주)미래테크", 2, None), "NDA-2026-02": ("(주)금강화학", 3, 6), "NDA-2026-03": ("신라물류", 5, None)}


def _nda(party, years, override):
    specific = [
        ("목적", f"본 계약은 갑과 을이 공동 사업 검토를 위하여 상호 제공하는 비밀정보의 보호에 관한 사항을 정한다."),
        ("비밀정보의 범위", "비밀정보란 일방이 상대방에게 서면, 전자파일, 구두 등 형태를 불문하고 제공한 기술, 영업, 재무 정보로서 "
         "제공 시 비밀임을 표시하였거나 그 성질상 비밀로 인정되는 정보를 말한다."),
        ("비밀유지 기간", f"수령자의 비밀유지 의무는 본 계약의 종료일부터 {years}년간 존속한다."),
    ]
    text = (f"비밀유지계약서\n\n(주)위그텍(이하 \"갑\")과 {party}(이하 \"을\")은 다음과 같이 비밀유지계약을 체결한다.\n\n"
            + _articles(specific, boiler=[BOILER[1], BOILER[6]]) + "\n")
    if override:
        text += (f"\n[특약사항]\n1. 제3조에도 불구하고, 수령자의 비밀유지 의무는 본 계약의 종료일부터 {override}년간 존속한다. "
                 "이 특약은 본문의 해당 조항에 우선한다.\n")
    return text + "\n2026년 5월 20일\n"


DOCS_E05 = {d: (f"{p} 비밀유지계약서", _nda(p, y, o)) for d, (p, y, o) in NDA_YEARS.items()}
_eff = {d: (o or y) for d, (_, y, o) in NDA_YEARS.items()}
DE05 = max(_eff.items(), key=lambda x: x[1])
assert sorted(_eff.values())[-1] != sorted(_eff.values())[-2]

# ---------------------------------------------------------------- e06: office lease
DE06 = {"deposit": 300_000_000, "rent": 18_500_000, "start": "2027-01-01", "end": "2028-12-31"}
DOC_E06 = {"LS-2026-09": ("판교 사무실 임대차계약서", (
    "사무실 임대차계약서\n\n임대인: (주)한빛상사 (이하 \"임대인\")\n임차인: (주)위그텍 (이하 \"임차인\")\n\n"
    "임대인과 임차인은 아래 표시 부동산에 관하여 다음과 같이 임대차계약을 체결한다.\n\n"
    "1. 부동산의 표시\n- 소재지: 경기도 성남시 분당구 판교역로 000, 한빛타워 9층 전체\n- 면적: 전용 812.4㎡\n- 용도: 업무시설(사무실)\n\n"
    "2. 계약 조건\n"
    + _articles([
        ("보증금", f"임대차 보증금은 금 {DE06['deposit']:,}원으로 하며, 계약 체결 시 10%, 잔액은 임대차 개시일에 지급한다."),
        ("차임", f"월 차임은 금 {DE06['rent']:,}원(부가가치세 별도)으로 하며, 매월 말일까지 임대인 지정 계좌로 지급한다. "
         "관리비는 차임과 별도로 관리규약에 따라 부과한다."),
        ("임대차 기간", f"임대차 기간은 {DE06['start'][:4]}년 {int(DE06['start'][5:7])}월 {int(DE06['start'][8:])}일부터 "
         f"{DE06['end'][:4]}년 {int(DE06['end'][5:7])}월 {int(DE06['end'][8:])}일까지로 한다."),
        ("원상복구", "임차인은 임대차 종료 시 임차인이 설치한 시설물을 철거하고 원상으로 복구하여 반환한다. 다만, 임대인이 "
         "인수에 동의한 시설물은 그러하지 아니하다."),
    ], boiler=BOILER[4:7])
    + "\n\n3. 특약사항\n"
    "- 본 계약 협의 과정에서 임대인이 최초 제시한 조건(보증금 4억원, 월 차임 2,000만원)은 본 계약으로 대체되어 효력이 없다.\n"
    "- 임대차 개시일 이전 1개월간(2026년 12월) 인테리어 공사를 위한 무상 사용을 허용한다. 이 기간은 임대차 기간에 포함하지 아니한다.\n"
    "\n2026년 10월 2일\n\n임대인: (주)한빛상사 (인)\n임차인: (주)위그텍 (인)\n"))}

# ---------------------------------------------------------------- e07: long production meeting minutes, action items
_people = ["이서연", "정우성", "한지민", "김도현", "박소율"]
AGENDA = [
    ("1. 지난 회의 조치사항 점검",
     "생산관리팀 정우성 과장이 지난 회의(9월 30일) 조치사항 진행 상황을 보고했다. 지난 회의에서 배정된 항목은 "
     "총 3건이며, 담당자들은 각 항목의 결과물을 공유 폴더에 올려 두었다고 설명했다. 이서연 과장은 금형 교체 후 첫 로트의 "
     "치수 측정 결과가 모두 공차 안에 들어왔다고 덧붙였고, 야간조 충원은 인사팀에서 11월 1일자로 2명을 배치하기로 회신을 "
     "받았다고 보고했다. 아래 항목은 모두 완료되어 이번 회의에서 "
     "종결 처리한다. 3호기 금형 교체 건은 예정보다 이틀 앞당겨 완료되었고, 불량 분석 보고서는 품질팀 회람까지 끝났다.",
     [("3호기 금형 교체 일정 확정", "이서연", "2026-10-02", "완료"),
      ("8월 불량 분석 보고서 회람", "한지민", "2026-10-05", "완료"),
      ("야간조 인력 충원 요청서 제출", "이서연", "2026-10-06", "완료")]),
    ("2. 10월 생산 실적 및 11월 계획",
     "10월 1~2주 생산 실적은 계획 대비 96.4%로 집계되었다. 2호기 정지 시간(누적 11시간) 영향이 가장 컸고, 원인은 "
     "서보모터 과열 알람으로 확인되었다. 김도현 대리는 11월 수주 물량이 10월 대비 8% 늘어날 것으로 보고했으며, "
     "현재 인원으로는 토요일 특근 2회가 필요하다는 의견을 냈다. 참석자들은 특근 계획을 먼저 수립하고, 인원 충원은 "
     "12월 물량을 확인한 뒤 결정하기로 했다. 박소율 사원은 MES 실적 집계와 수기 일보 간 차이가 2호기에서 반복된다고 "
     "보고했고, 바코드 스캐너 교체 전까지는 반장이 교대 시점에 수기로 대조하기로 했다. 이서연 과장은 2호기 "
     "서보모터 알람이 주로 오후 2시~4시 사이에 집중된다는 점을 들어 제어반 내부 온도와의 관련성을 의심했고, 제어반 냉각팬 "
     "점검을 함께 진행하겠다고 했다. 정우성 과장은 서보 드라이브의 파라미터가 작년 개조 이후 기본값으로 되돌아갔을 가능성도 "
     "확인해 달라고 요청했다.",
     [("11월 토요일 특근 계획(안) 작성", "김도현", "2026-10-24"),
      ("2호기 서보모터 과열 원인 분석 및 대책 보고", "이서연", "2026-10-30"),
      ("MES-일보 차이 대조표 양식 배포", "박소율", "2026-10-22")]),
    ("3. 품질 이슈: 고객사 클레임 대응",
     "삼원전자에서 9월 출하분 브라켓 제품의 버(burr) 관련 클레임이 2건 접수되었다. 한지민 대리는 해당 로트의 검사 기록을 "
     "확인한 결과 출하 검사 샘플 수가 기준보다 적었던 날이 있었다고 보고했다. 품질팀은 출하 검사 샘플 수를 로트당 5개에서 "
     "8개로 늘리는 방안을 제안했고, 생산팀은 검사 시간 증가에 따른 출하 지연 가능성을 우려했다. 논의 끝에 11월 한 달간 "
     "시범 적용 후 효과를 보고 결정하기로 했다. 고객사 회신은 영업팀과 협의하여 품질팀이 작성한다. 디버링 공정의 공구 "
     "교체 주기를 현행 5,000타에서 3,500타로 단축하는 것도 함께 검토하기로 했다.",
     [("삼원전자 클레임 회신서(8D) 작성", "한지민", "2026-10-28"),
      ("디버링 공구 교체 주기 단축 시 비용 산출", "이서연", "2026-11-04"),
      ("출하 검사 샘플 확대 시범 적용 계획 수립", "정우성", "2026-10-27")]),
    ("4. 4호기 신규 라인 레이아웃 검토",
     "김도현 대리가 내년 상반기 설치 예정인 4호기 라인의 1차 레이아웃(안)을 설명했다. 기존 3호기 옆 자재 적치 구역을 "
     "라인 설치 공간으로 쓰는 안으로, 자재 적치 구역은 생산동 1층 북측으로 옮기게 된다. 참석자들은 지게차 동선이 3호기 "
     "출하 동선과 겹치는 구간이 생긴다는 점을 지적했고, 박소율 사원은 MES 단말 위치를 작업자 동선 쪽으로 옮기면 실적 입력 "
     "누락이 줄 것이라는 의견을 냈다. 정우성 과장은 압축공기 배관 용량이 4호기까지 감당하기 어려울 수 있으므로 설비팀의 "
     "검토가 필요하다고 했다. 레이아웃(안)은 이번 의견을 반영해 2차안으로 다시 보고하기로 했다.",
     [("4호기 레이아웃 2차안 작성(지게차 동선 분리 반영)", "김도현", "2026-11-11"),
      ("4호기 MES 단말 배치안 작성", "박소율", "2026-11-06")]),
    ("5. 설비 보전 및 안전",
     "보전 담당 정우성 과장은 4분기 정기 보전 일정(11월 셋째 주 토요일)을 공유했다. 에어 컴프레서 2호기는 누설이 커서 "
     "정기 보전 전에 부품 교체가 필요하다는 의견이 있었다. 안전 관련해서는 지게차 통로 바닥 표시가 지워진 구간이 "
     "있어 재도색을 하기로 했고, 10월 안전 점검 결과 보안경 미착용 사례가 3건 적발되어 교육을 다시 실시하기로 했다. "
     "김도현 대리는 근접센서 예비품 재고가 안전재고 아래로 떨어졌다고 보고했고, 구매 요청은 생산팀에서 바로 올리기로 했다.",
     [("에어 컴프레서 2호기 부품 교체 발주", "정우성", "2026-10-23"),
      ("지게차 통로 바닥 표시 재도색", "박소율", "2026-11-07"),
      ("보안경 착용 재교육 실시 및 결과 보고", "이서연", "2026-11-12"),
      ("근접센서 예비품 구매 요청", "김도현", "2026-10-22")]),
    ("6. 기타",
     "다음 회의는 2026년 10월 28일(수) 09:00, 생산동 회의실에서 진행한다. 회의 말미에 업무량을 고려하여 일부 조치사항의 "
     "담당자를 조정했다. 또한 11월부터는 회의 자료를 회의 전날 17시까지 공유 폴더에 올리기로 했고, 각 안건 담당자는 "
     "지난 조치사항의 진행률을 회의 자료 첫 장에 표로 정리하기로 했다. 구매팀 오세린 과장은 3번 안건 논의 후 퇴장하면서 "
     "근접센서와 서보모터 예비품의 납기가 현재 3~4주 걸린다고 공유했다.",
     []),
]
REASSIGN = {"디버링 공구 교체 주기 단축 시 비용 산출": "한지민"}
_new_items = [(t, REASSIGN.get(t, who), due) for _, _, items in AGENDA[1:] for (t, who, due, *rest) in items]
_sy = [due for t, who, due in _new_items if who == "이서연"]
DE07 = {"count": len(_sy), "latest_due": max(_sy)}


def _minutes():
    head = ("주간 생산회의 회의록\n\n일시: 2026년 10월 14일(수) 09:00~11:10\n장소: 평택 사업장 생산동 2층 회의실\n"
            "참석: 생산팀 이서연 과장, 생산관리팀 정우성 과장, 품질팀 한지민 대리, 생산팀 김도현 대리, 생산팀 박소율 사원, "
            "구매팀 오세린 과장(3번 안건만)\n작성: 생산팀 박소율\n\n"
            "※ 조치사항 표기: [조치] 내용 / 담당: 이름 / 기한: YYYY-MM-DD\n\n")
    parts = [head]
    for title, body, items in AGENDA:
        parts.append(f"{title}\n{body}\n")
        for it in items:
            line = f"- [조치] {it[0]} / 담당: {it[1]} / 기한: {it[2]}"
            if len(it) > 3:
                line += f" / 상태: {it[3]}"
            parts.append(line + "\n")
        parts.append("\n")
    for t, who in REASSIGN.items():
        orig = next(i[1] for _, _, its in AGENDA for i in its if i[0] == t)
        parts.append(f"- 담당자 변경: '{t}' 조치사항의 담당자를 {orig}에서 {who}으로 변경함. 기한은 그대로 유지.\n")
    parts.append("\n이상.\n")
    return "".join(parts)


DOC_E07 = {"MIN-PRD-1014": ("주간 생산회의 회의록 (2026-10-14)", _minutes())}

# ---------------------------------------------------------------- e08: spec with revision history in one doc (long)
DE08 = {"warranty": 36, "qty": 48, "defect": 0.3}
_de08_v12 = (
    "공압 실린더 구매 사양서\n\n문서번호: SPEC-PUR-2026-21\n\n"
    "[개정 이력]\n- Rev 1.0 (2026-06-10): 최초 작성\n- Rev 1.2 (2026-08-05): 수량, 보증 조건 변경\n"
    "- Rev 1.3 (2026-09-22): 수량, 보증 기간, 검수 기준 변경 — 현행 유효 버전\n\n"
    "※ 이 문서에는 Rev 1.2 본문이 참고용으로 남아 있으며, 실제 발주에는 문서 뒷부분의 Rev 1.3 본문만 적용한다.\n\n"
    "==== Rev 1.2 본문 (참고용, 효력 없음) ====\n\n"
    "1. 개요\n조립라인 2·3호기의 노후 에어실린더를 교체하기 위한 구매 사양을 정한다. 대상 실린더는 2014년 설치분으로 "
    "로드 실 마모로 인한 누설과 동작 속도 저하가 반복되고 있다.\n\n"
    "2. 구매 수량: 40개 (2호기 20개, 3호기 20개)\n\n"
    "3. 규격\n- 형식: 복동형, 보어 32mm, 스트로크 100mm\n- 사용 압력: 0.1~1.0MPa\n- 쿠션: 양측 에어 쿠션\n"
    "- 오토스위치 홈: 4면\n- 로드 끝 나사: M10×1.25\n- 사용 유체: 공기(급유 불필요형)\n- 사용 온도 범위: -10~60℃(동결 없을 것)\n"
    "- 피스톤 속도: 50~750mm/s\n- 포트 크기: Rc 1/8\n- 설치 형식: 풋(LB) 브래킷, 로드 끝 단일 클레비스 포함\n"
    "- 튜브 재질: 알루미늄 합금(경질 아노다이징), 피스톤 로드 재질: 스테인리스강\n"
    "- 호환성: 기존 설비의 브래킷 및 배관을 변경하지 않고 장착할 수 있을 것\n\n"
    "4. 보증 조건\n- 보증 기간: 검수 완료일부터 24개월\n- 보증 기간 중 제품 결함으로 인한 고장은 공급자가 무상 교체한다.\n\n"
    "5. 검수 기준\n- 전수 외관 검사 및 샘플 동작 시험(로트당 5개)\n- 허용 불량률: 0.5% 이하\n\n"
    "6. 납품\n- 납품 장소: 평택 사업장 자재창고\n- 납품 기한: 발주 후 6주 이내\n\n"
    "7. 공급자 요구사항\n- 최근 3년 이내 동종 제품 납품 실적 2건 이상\n- 국내 A/S 거점 보유\n"
    "- 납품 전 견본 2개를 제출하여 구매자의 장착 시험을 통과할 것\n- 단종 예정 모델이 아닐 것(납품일부터 5년 이상 생산 유지 확약)\n\n"
)
_de08_filler = (
    "7.1 공급자는 납품 후 6개월간 월 1회 현장을 방문하여 설치 상태와 동작 이상 여부를 점검하고 점검 결과를 구매팀에 제출한다.\n"
    "7.2 공급자는 보증 기간 동안 실 키트, 쿠션 니들 등 소모성 예비품을 주문일부터 5영업일 이내에 공급할 수 있어야 한다.\n"
    "7.3 고장 접수 시 공급자는 24시간 이내에 원인 파악을 위한 1차 회신을 하고, 72시간 이내에 수리 또는 교체를 완료한다.\n\n"
    "8. 시험 방법\n8.1 동작 시험은 0.5MPa 공급 압력에서 무부하 상태로 전진·후진을 각 100회 반복하여 실시하며, 동작 중 "
    "끼임, 이상음, 속도 편차가 없어야 한다.\n8.2 누설 시험은 1.0MPa에서 로드를 전진 끝단에 고정하고 3분간 유지하여 "
    "누설량이 규정치 이하인지 확인한다.\n8.3 내압 시험은 사용 최고 압력의 1.5배에서 1분간 유지하여 변형이나 파손이 "
    "없어야 한다.\n8.4 오토스위치 동작 확인은 각 홈에 스위치를 장착하여 전진·후진 끝단에서 신호가 정상 출력되는지 확인한다.\n"
    "8.5 쿠션 성능 시험은 0.5MPa, 최대 피스톤 속도에서 행정 끝단 충격음과 반발이 없는지 확인하며, 쿠션 니들 조정 범위 안에서 "
    "충격 흡수가 가능해야 한다.\n8.6 시험 기록은 로트 번호별로 작성하여 공급자가 5년간 보관하고, 구매자가 요청하면 "
    "7일 이내에 사본을 제출한다.\n8.7 구매자는 필요하다고 인정하는 경우 공급자의 시험에 입회할 수 있으며, 입회 시험에서 "
    "불합격된 로트는 납품할 수 없다.\n\n"
    "8.8 시험 장비는 국가공인 교정기관에서 1년 이내에 교정을 받은 것을 사용하여야 하며, 교정 성적서 사본을 시험 성적서에 "
    "첨부한다. 교정 유효기간이 지난 장비로 시험한 결과는 인정하지 아니한다.\n\n"
    "9. 포장 및 표시\n9.1 실린더는 개별 포장하고, 포트에는 이물질 유입 방지용 캡을 씌운다.\n9.2 포장 외면에는 품명, 규격, "
    "수량, 제조 로트 번호, 제조 일자를 표시한다.\n9.3 시험 성적서는 로트별로 1부씩 납품 시 함께 제출한다.\n\n"
    "10. 제출 서류\n- 납품 전: 승인용 도면, 부품 목록, 시험 계획서\n- 납품 시: 시험 성적서, 거래명세서, 취급 설명서(국문)\n\n"
    "11. 품질보증 체계\n11.1 공급자는 ISO 9001 또는 이와 동등한 품질경영체계 인증을 유지하여야 한다.\n11.2 공급자는 "
    "주요 부품(튜브, 피스톤 로드, 실)의 공급처를 변경하려는 경우 변경 30일 전까지 구매자에게 서면으로 알리고 승인을 받아야 "
    "한다.\n11.3 동일 로트에서 같은 원인의 불량이 2회 이상 발생하면 공급자는 원인 분석과 재발 방지 대책을 담은 시정조치 "
    "보고서를 14일 이내에 제출한다.\n\n"
    "12. 설계 변경 관리\n12.1 구매자의 승인 도면과 다른 사양으로 제작하는 것은 허용하지 않는다.\n12.2 공급자가 성능 "
    "개선을 위하여 설계를 변경하려는 경우 변경 내용, 사유, 호환성 검토 결과를 제출하여 구매자의 사전 승인을 받아야 한다.\n\n"
    "13. 안전 및 환경\n13.1 계약물품에는 RoHS 제한 물질이 기준치 이상 포함되어서는 안 된다.\n13.2 납품 차량의 사업장 "
    "출입 시 구내 제한 속도(시속 10km)와 지정 하역 구역을 준수한다.\n13.3 포장재는 가능한 한 재활용 가능한 재질을 사용하고, "
    "목재 팔레트는 열처리(HT) 표시가 있는 것을 사용한다.\n\n"
    "14. 교육 및 기술 지원\n14.1 공급자는 납품 시 보전 담당자를 대상으로 분해·조립, 실 교체, 쿠션 조정 방법에 관한 "
    "현장 교육을 2시간 이상 실시한다.\n14.2 교육 자료는 국문으로 작성하여 사전에 제출하며, 교육 참석자 명단과 결과를 "
    "기록하여 납품 서류와 함께 제출한다.\n\n"
    "15. 보증 청구 절차\n15.1 구매자는 보증 대상 고장이 발생하면 고장 일시, 설비 번호, 증상, 사진을 첨부하여 공급자에게 "
    "전자우편으로 통지한다.\n15.2 공급자는 고장품을 회수하여 원인을 분석하고, 분석 결과 사용자 과실로 판명된 경우에는 수리 "
    "비용을 구매자에게 청구할 수 있다. 이 경우 분석 보고서를 함께 제출하여야 한다.\n\n"
    "16. 기타\n16.1 이 사양서에 정하지 아니한 사항은 물품공급계약서 및 구매자의 구매 관리 규정에 따른다.\n16.2 이 사양서의 "
    "해석에 이견이 있는 경우 구매팀과 요청부서(생산팀)가 협의하여 정한다.\n\n"
)
_de08_v13 = (
    "==== Rev 1.3 본문 (현행 유효) ====\n\n"
    "1. 개요\nRev 1.2와 같다. 다만 1호기 일부 공정이 교체 대상에 추가되었다.\n\n"
    f"2. 구매 수량: {DE08['qty']}개 (1호기 8개, 2호기 20개, 3호기 20개)\n\n"
    "3. 규격\nRev 1.2와 같다.\n\n"
    f"4. 보증 조건\n- 보증 기간: 검수 완료일부터 {DE08['warranty']}개월\n- 보증 기간 중 제품 결함으로 인한 고장은 공급자가 무상 교체하며, "
    "교체에 드는 운송비도 공급자가 부담한다.\n\n"
    f"5. 검수 기준\n- 전수 외관 검사 및 샘플 동작 시험(로트당 8개)\n- 허용 불량률: {DE08['defect']}% 이하\n\n"
    "6. 납품\nRev 1.2와 같다.\n\n7. 공급자 요구사항\nRev 1.2와 같다.\n\n8.~16.\nRev 1.2와 같다.\n"
)
DOC_E08 = {"SPEC-PUR-2026-21": ("공압 실린더 구매 사양서 (Rev 1.3)", _de08_v12 + _de08_filler + _de08_v13)}
assert len(_de08_v12 + _de08_filler) > 3000


def _doc_task(id, split, prompt, docs, keys, fn):
    return dict(id=id, split=split, domain="doc", tools="doc", prompt=prompt, docs=docs,
                contract={"type": "json", "keys": keys}, check=_json_check(fn))


def _close(parsed, key, expected):
    v = grade.num(_get(parsed, key))
    return v is not None and abs(float(v) - float(expected)) < 1e-9


DOC_TASKS = [
    _doc_task("doc_d01", "dev",
              "온누리IT에서 받은 회의실 영상장비 견적서 있죠? 부가세 포함 합계 금액이랑 견적 유효기간 마지막 날 알려주세요. "
              + JSON_RULE + '{"total": 부가세 포함 합계(원, 정수), "valid_until": "YYYY-MM-DD"}',
              DOC_D01, {"total": "int", "valid_until": "str"},
              lambda p: _eq_num(p, "total", DD01["total"]) and _eq_date(p, "valid_until", DD01["valid"])),
    _doc_task("doc_d02", "dev",
              "청솔인쇄랑 맺은 인쇄물 기본계약, 중간에 해지하려면 해지 희망일 며칠 전까지 통보해야 하는지 찾아주세요. "
              + JSON_RULE + '{"notice_days": 일수(정수)}',
              DOC_D02, {"notice_days": "int"},
              lambda p: _eq_num(p, "notice_days", DD02["days"])),
    _doc_task("doc_e01", "eval",
              "서진정밀 물품공급계약 건으로 지금 효력 있는 조건을 정리해야 해요. 변경계약이 있었으면 변경된 내용 기준으로, "
              "계약금액(부가세 별도), 납품기한, 지체상금률(1일당, % 숫자만)을 알려주세요. "
              + JSON_RULE + '{"amount": 계약금액(원, 정수), "due_date": "YYYY-MM-DD", "penalty_rate_pct": 숫자}',
              DOC_E01, {"amount": "int", "due_date": "str", "penalty_rate_pct": "float"},
              lambda p: _eq_num(p, "amount", DE01["amount"]) and _eq_date(p, "due_date", DE01["due"])
              and _close(p, "penalty_rate_pct", DE01["rate"])),
    _doc_task("doc_e02", "eval",
              "10월 7일 그룹웨어 교체 회의에서 최종 확정된 예산, 오픈 목표일, 사업 총괄 담당자 이름을 회의록에서 찾아주세요. "
              "예산은 원 단위 정수로 바꿔서 적어주세요. "
              + JSON_RULE + '{"budget": 예산(원, 정수), "go_live": "YYYY-MM-DD", "owner": 담당자 이름}',
              DOC_E02, {"budget": "int", "go_live": "str", "owner": "str"},
              lambda p: _eq_num(p, "budget", DE02["budget"]) and _eq_date(p, "go_live", DE02["go_live"])
              and isinstance(_get(p, "owner"), str) and _norm(p["owner"]).startswith(DE02["owner"])),
    _doc_task("doc_e03", "eval",
              "생산라인 3호기 공정 단말 구매사양서 기준으로 예산 잡으려고 해요. 사양서에 있는 모든 품목의 수량 × 예정 단가를 "
              "합친 총액(부가세 별도)과 납품 장소의 사업장 이름(예: '본사')을 알려주세요. "
              + JSON_RULE + '{"total": 총액(원, 정수), "site": 사업장 이름}',
              DOC_E03, {"total": "int", "site": "str"},
              lambda p: _eq_num(p, "total", DE03["total"]) and DE03["place"] in str(_get(p, "site"))),
    _doc_task("doc_e04", "eval",
              "과장 한 명이 2026년 10월 12일 출발해서 10월 14일 귀임하는 부산 출장(2박 3일, 호텔 2박)을 갑니다. 회사 차량이나 "
              "교통편 제공은 없어요. 여비 규정상 받을 수 있는 일비 총액과 숙박비 상한 총액을 계산해주세요. "
              + JSON_RULE + '{"daily_total": 일비 총액(원, 정수), "lodging_limit_total": 숙박비 상한 총액(원, 정수)}',
              DOC_E04, {"daily_total": "int", "lodging_limit_total": "int"},
              lambda p: _eq_num(p, "daily_total", DE04["daily_total"])
              and _eq_num(p, "lodging_limit_total", DE04["lodging_total"])),
    _doc_task("doc_e05", "eval",
              "올해 맺은 비밀유지계약서들 중에서 계약 종료 후 비밀유지 의무 기간이 가장 긴 건 어느 문서인지, 그 기간이 몇 년인지 "
              "알려주세요. 특약이 있으면 특약 기준입니다. "
              + JSON_RULE + '{"doc_id": 문서 ID, "years": 년수(정수)}',
              DOCS_E05, {"doc_id": "str", "years": "int"},
              lambda p: _code(_get(p, "doc_id")) == _code(DE05[0]) and _eq_num(p, "years", DE05[1])),
    _doc_task("doc_e06", "eval",
              "판교 사무실 임대차계약서에서 보증금, 월 차임(부가세 별도 금액), 임대차 시작일과 종료일을 뽑아주세요. "
              + JSON_RULE + '{"deposit": 보증금(원, 정수), "monthly_rent": 월 차임(원, 정수), "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}',
              DOC_E06, {"deposit": "int", "monthly_rent": "int", "start": "str", "end": "str"},
              lambda p: _eq_num(p, "deposit", DE06["deposit"]) and _eq_num(p, "monthly_rent", DE06["rent"])
              and _eq_date(p, "start", DE06["start"]) and _eq_date(p, "end", DE06["end"])),
    _doc_task("doc_e07", "eval",
              "10월 14일 주간 생산회의록에서 이서연 과장 앞으로 이번 회의에서 새로 배정된 조치사항이 몇 건이고, 그중 기한이 "
              "가장 늦은 날짜가 언제인지 알려주세요. 지난 회의에서 넘어와 이미 완료 처리된 항목은 빼고, 회의 중에 담당자가 "
              "바뀐 항목은 바뀐 최종 담당자 기준으로 세어주세요. "
              + JSON_RULE + '{"count": 건수(정수), "latest_due": "YYYY-MM-DD"}',
              DOC_E07, {"count": "int", "latest_due": "str"},
              lambda p: _eq_num(p, "count", DE07["count"]) and _eq_date(p, "latest_due", DE07["latest_due"])),
    _doc_task("doc_e08", "eval",
              "공압 실린더 구매 사양서 현행 유효 버전 기준으로 구매 수량, 보증 기간(개월), 허용 불량률(% 숫자만)을 알려주세요. "
              + JSON_RULE + '{"qty": 수량(정수), "warranty_months": 개월(정수), "defect_rate_pct": 숫자}',
              DOC_E08, {"qty": "int", "warranty_months": "int", "defect_rate_pct": "float"},
              lambda p: _eq_num(p, "qty", DE08["qty"]) and _eq_num(p, "warranty_months", DE08["warranty"])
              and _close(p, "defect_rate_pct", DE08["defect"])),
]

# ================================================================= all

TASKS = ERP_TASKS + CODE_TASKS + DOC_TASKS

assert len({t["id"] for t in TASKS}) == len(TASKS)
