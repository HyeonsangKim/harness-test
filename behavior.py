"""Small behavior checks: multi-step, error recovery, parallel calls, tool choice, code edit, long context, JSON.
Uses probe.py (same env vars, same key prompt). run: python behavior.py --rep 3
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import probe as P

VOUCHERS = [  # (id, dept, month, status, amount)
    ("V1", "D10", 9, "open", 1200000), ("V2", "D20", 9, "open", 800000),
    ("V3", "D10", 9, "closed", 5000000), ("V4", "D20", 9, "open", 900000),
    ("V5", "D30", 9, "open", 1500000), ("V6", "D10", 8, "open", 3000000),
    ("V7", "D30", 9, "open", 100000)]
BACKUP = [("B1", "D10", 9, "open", 9900000), ("B2", "D30", 9, "open", 200000)]
TABLES = {
    "vouchers": [dict(zip(("id", "dept", "month", "status", "amount"), r)) for r in VOUCHERS],
    "vouchers_backup_2023": [dict(zip(("id", "dept", "month", "status", "amount"), r)) for r in BACKUP],
    "departments": [{"dept": "D10", "name": "영업팀"}, {"dept": "D20", "name": "구매팀"},
                    {"dept": "D30", "name": "생산팀"}]}

def fn(name, desc, props=None, required=None):
    return {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []}}

S = {"type": "string"}
ERP_TOOLS = [
    fn("list_tables", "List table names in the ERP database."),
    fn("describe_table", "Show column names of a table.", {"table": S}, ["table"]),
    fn("query", "Return rows of a table where every key in `where` equals the given value (max 50 rows).",
       {"table": S, "where": {"type": "object"}}, ["table"])]

def erp(name, args):
    args = args or {}
    if name == "list_tables":
        return list(TABLES)
    rows = TABLES.get(args.get("table"))
    if rows is None:
        return {"error": f"unknown table {args.get('table')!r}. Use list_tables."}
    if name == "describe_table":
        return list(rows[0])
    where = args.get("where") or {}
    bad = [k for k in where if k not in rows[0]]
    if bad:
        return {"error": f"unknown column {bad}. Columns: {list(rows[0])}"}
    return [r for r in rows if all(str(r[k]) == str(v) for k, v in where.items())][:50]

STOCK_TOOLS = [
    fn("get_stock", "Get stock quantity by item code.", {"item_code": S}, ["item_code"]),
    fn("search_items", "Search items by keyword in the item name.", {"keyword": S}, ["keyword"])]

def stock(name, args):
    args = args or {}
    if name == "search_items":
        return [{"item_code": "ITM-0100", "name": "볼트 M8"}, {"item_code": "ITM-0101", "name": "볼트 M10"}]
    if args.get("item_code") == "ITM-0100":
        return {"item_code": "ITM-0100", "qty": 42}
    return {"error": f"unknown item_code {args.get('item_code')!r}. Codes look like 'ITM-0100'. Use search_items."}

WEATHER = [fn("get_weather", "Get the current weather for a city.", {"city": S}, ["city"])]

def weather(name, args):
    city = str((args or {}).get("city", ""))
    return {"city": city, "temp_c": 22 if ("부산" in city or "Busan" in city) else 17}

DECOYS = ["get_weather", "send_email", "create_purchase_order", "get_exchange_rate", "list_employees",
          "book_meeting_room", "get_payroll", "translate_text", "get_stock", "approve_voucher",
          "get_vendor_contact", "create_invoice", "get_sales_report", "search_documents",
          "get_budget", "update_vendor", "get_payable", "list_vendors", "get_holiday"]
MANY = [fn(n, n.replace("_", " ") + ".", {"arg": S}) for n in DECOYS] + [
    fn("get_receivable", "Get outstanding accounts receivable balance for a customer.",
       {"customer": S}, ["customer"])]

def many(name, args):
    if name == "get_receivable":
        return {"customer": (args or {}).get("customer"), "balance": 3250000}
    return {"error": "not relevant"}

BUGGY = '''def average(values):
    """Return the mean of values. Return 0.0 for an empty list."""
    total = 0
    for v in values[1:]:
        total += v
    return total / len(values)
'''
TEST = '''from calc import average
assert average([2, 4, 6]) == 4, "average([2, 4, 6]) should be 4"
assert average([5]) == 5, "average([5]) should be 5"
assert average([]) == 0.0, "average([]) should be 0.0"
print("ALL PASS")
'''
EDIT_TOOLS = [
    fn("read_file", "Read a file in the project folder.", {"path": S}, ["path"]),
    fn("replace_in_file", "Replace text in a file. `old` must match the file content exactly and appear once.",
       {"path": S, "old": S, "new": S}, ["path", "old", "new"]),
    fn("run_tests", "Run the project tests and return the output.")]

def run_tests(folder):
    try:
        r = subprocess.run([sys.executable, "-E", "-s", "test_calc.py"], cwd=folder, capture_output=True,
                           text=True, timeout=10)
        return (r.stdout + r.stderr)[-1500:]
    except subprocess.TimeoutExpired:
        return "timeout after 10s"

def editor(folder, stats):
    def impl(name, args):
        args = args or {}
        if name == "run_tests":
            return run_tests(folder)
        path = folder / Path(str(args.get("path", ""))).name
        if not path.exists():
            return {"error": f"no such file. Files: {sorted(f.name for f in folder.iterdir())}"}
        text = path.read_text(encoding="utf-8")
        if name == "read_file":
            return text
        count = text.count(args.get("old") or "\0")
        if count != 1:
            stats["editfail"] += 1
            return {"error": f"`old` found {count} times; it must match exactly once. Use read_file to copy exact text."}
        path.write_text(text.replace(args["old"], str(args.get("new", ""))), encoding="utf-8")
        return "ok"
    return impl

FILLER = "회의록에 따르면 다음 분기 예산은 조금 늘어나며, 각 팀은 금요일까지 계획서를 내야 한다. "
NEEDLE = "참고로 이번 분기 신규 프로젝트의 암호명은 '푸른고래'로 정해졌다. "

def digits(text):
    return re.sub(r"[,\s원]", "", text or "")

def run(name, tools, impl, prompt, base, max_turns=8):
    msgs, calls, par = [{"role": "user", "content": prompt}], [], 0
    for turn in range(max_turns):
        rec = P.call(f"{name}_t{turn}", {**base, "tools": [{"type": "function", "function": f} for f in tools]},
                     messages=msgs, max_tokens=8192, timeout=600)
        msg = P.message(rec)
        if rec["status"] != 200 or msg is None:
            return {"answer": None, "calls": calls, "par": par, "err": f"http_{rec['status']}"}
        tcs = msg.get("tool_calls") or []
        msgs.append({**msg, "role": "assistant"})
        if not tcs:
            text = msg.get("content") or ""
            return {"answer": text, "calls": calls, "par": par,
                    "err": "txt" if "<tool_call>" in text else ""}
        par = max(par, len(tcs))
        for tc in tcs:
            f = tc.get("function") or {}
            try:
                args = json.loads(f.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = None
            calls.append(f.get("name"))
            out = impl(f.get("name"), args) if args is not None else {"error": "arguments are not valid JSON"}
            msgs.append({"role": "tool", "tool_call_id": tc.get("id"), "content": json.dumps(out, ensure_ascii=False)})
    return {"answer": None, "calls": calls, "par": par, "err": "max_turns"}

TESTS = {
    "multi": (ERP_TOOLS, erp, "9월 미결(open) 전표 합계가 가장 큰 부서의 이름과 그 합계 금액을 알려줘. 현재 전표 테이블 기준이야.",
              lambda a: "구매팀" in a and "1700000" in digits(a)),
    "recover": (STOCK_TOOLS, stock, "볼트 M8 재고 몇 개 남았어? 품목코드는 A-100이었던 것 같아. 재고 조회해서 알려줘.",
                lambda a: "42" in a),
    "parallel": (WEATHER, weather, "서울이랑 부산 지금 날씨 둘 다 도구로 확인해서 알려줘.",
                 lambda a: "17" in a and "22" in a),
    "pick": (MANY, many, "거래처 '한빛상사'의 미수금 잔액이 얼마인지 조회해줘.",
             lambda a: "3250000" in digits(a)),
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rep", type=int, default=3, help="repeats per test")
    parser.add_argument("--effort", default="low", help="low/high/max, or none")
    parser.add_argument("--ctx", default="8000,32000", help="needle test lengths in tokens")
    args = parser.parse_args()
    P.OUT = Path("probe_out") / ("behavior-" + time.strftime("%Y%m%d-%H%M%S"))
    P.OUT.mkdir(parents=True)
    base = {"tool_choice": "auto"}
    if args.effort != "none":
        base["reasoning_effort"] = args.effort
    report, lines = {"base": base}, []
    for name, (tools, impl, prompt, ok) in TESTS.items():
        res = [run(f"{name}_{i}", tools, impl, prompt, base) for i in range(args.rep)]
        for r in res:
            r["pass"] = bool(r["answer"]) and ok(r["answer"])
        report[name] = res
        passed = sum(r["pass"] for r in res)
        extra = ("par=" + ",".join(str(r["par"]) for r in res)) if name == "parallel" else \
                ("first=" + ",".join((r["calls"] or ["-"])[0][:14] for r in res)) if name == "pick" else \
                ("calls=" + ",".join(str(len(r["calls"])) for r in res))
        errs = ",".join(r["err"] for r in res if r["err"])
        lines.append(f"B-{name} {passed}/{args.rep} {extra}" + (f" err={errs}" if errs else ""))
        print(lines[-1])
    edit = []
    for i in range(args.rep):
        folder = P.OUT / f"edit_{i}"
        folder.mkdir()
        (folder / "calc.py").write_text(BUGGY, encoding="utf-8")
        (folder / "test_calc.py").write_text(TEST, encoding="utf-8")
        stats = {"editfail": 0}
        r = run(f"edit_{i}", EDIT_TOOLS, editor(folder, stats),
                "calc.py의 average 함수가 테스트를 통과하지 못해. 파일을 읽고 고친 다음 run_tests로 통과를 확인해줘.", base)
        r["pass"] = "ALL PASS" in run_tests(folder)
        edit.append({**r, **stats})
    report["edit"] = edit
    errs = ",".join(r["err"] for r in edit if r["err"])
    lines.append(f"B-edit {sum(r['pass'] for r in edit)}/{args.rep} calls=" + ",".join(str(len(r["calls"])) for r in edit)
                 + " editfail=" + ",".join(str(r["editfail"]) for r in edit) + (f" err={errs}" if errs else ""))
    print(lines[-1])
    needle = []
    for size in [int(x) for x in args.ctx.split(",") if x]:
        n = int(size * 1.2 / len(FILLER))
        text = FILLER * (n // 2) + NEEDLE + FILLER * (n - n // 2)
        rec = P.call(f"needle_{size}", {k: v for k, v in base.items() if k != "tool_choice"},
                     prompt=text + "\n\n위 글에서 이번 분기 신규 프로젝트의 암호명은? 이름만 답해.",
                     max_tokens=4096, timeout=600)
        msg = P.message(rec) or {}
        got = "Y" if "푸른고래" in (msg.get("content") or "") else ("N" if rec["status"] == 200 else f"http_{rec['status']}")
        needle.append(f"{size}={got}/{P.prompt_tokens(rec)}tok/{rec['seconds']}s")
    lines.append("B-needle " + " ".join(needle))
    print(lines[-1])
    js = []
    for i in range(args.rep):
        rec = P.call(f"json_{i}", {k: v for k, v in base.items() if k != "tool_choice"},
                     prompt='다음 전표 3건을 JSON 배열로만 출력해. 키는 id, dept, amount(숫자). 설명이나 코드블록 없이 JSON만.\n'
                            'V1 영업팀 120만원 / V2 구매팀 80만원 / V3 생산팀 150만원', max_tokens=4096)
        text = ((P.message(rec) or {}).get("content") or "").strip()
        try:
            data = json.loads(text)
            js.append("Y" if isinstance(data, list) and len(data) == 3
                      and [d.get("amount") for d in data] == [1200000, 800000, 1500000] else "shape")
        except json.JSONDecodeError:
            js.append("fence" if text.startswith("```") else "bad")
    lines.append("B-json " + ",".join(js))
    print(lines[-1])
    lines.append(P.rl_line())
    print(lines[-1])
    (P.OUT / "behavior.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (P.OUT / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("saved:", P.OUT.resolve())
    print("== copy these lines")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
