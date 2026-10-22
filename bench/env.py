"""Fake work environment for the A/B bench: ERP database, code workspace, documents.

Tools behave like ordinary internal APIs: on bad input they raise a normal Python
exception. How that error reaches the model is the harness's job, not the tool's.
Standard library only.
"""
import ast
import csv
import io
import os
import re
import operator
import random
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------- ERP data

def build_db(seed=2026):
    rnd = random.Random(seed)
    depts = [("D10", "영업팀"), ("D20", "구매팀"), ("D30", "생산팀"), ("D40", "연구소"), ("D50", "경영지원팀")]
    vendor_names = ["(주)한빛상사", "대성산업", "(주)미래테크", "동해물산", "(주)서진정밀", "우리오피스",
                    "(주)태광기공", "신라물류", "(주)온누리IT", "청솔인쇄", "(주)금강화학", "백두건설"]
    vendors = [{"vendor_id": f"V{i + 1:03d}", "name": n, "biz_no": f"{rnd.randint(100, 899)}-{rnd.randint(10, 99)}-{rnd.randint(10000, 99999)}",
                "status": "suspended" if i in (3, 9) else "active"} for i, n in enumerate(vendor_names)]
    accounts = ["소모품비", "외주용역비", "여비교통비", "접대비", "수선비", "지급수수료"]

    def vouchers(year, n, prefix):
        rows = []
        for i in range(n):
            month = rnd.randint(1, 9)
            rows.append({
                "voucher_id": f"{prefix}-{year}-{i + 1:04d}",
                "date": f"{year}-{month:02d}-{rnd.randint(1, 28):02d}",
                "dept_id": rnd.choice(depts)[0],
                "vendor_id": rnd.choice(vendors)["vendor_id"],
                "account": rnd.choice(accounts),
                "amount": rnd.randint(5, 500) * 10000,
                "status": rnd.choices(["미결", "승인", "반려"], [3, 6, 1])[0],
            })
        return rows

    item_names = ["볼트 M8", "볼트 M10", "너트 M8", "너트 M10", "와셔 8mm", "베어링 6204", "베어링 6205",
                  "V벨트 A42", "체인 #40", "스프로킷 40T", "오일씰 30x47", "O링 P20", "그리스 2kg",
                  "절삭유 18L", "드릴 5mm", "드릴 8mm", "엔드밀 10mm", "장갑 코팅", "안전화 260", "보안경",
                  "케이블타이 200mm", "절연테이프", "퓨즈 10A", "릴레이 24V", "근접센서 M12", "PLC 입력모듈",
                  "서보모터 400W", "감속기 1:10", "에어실린더 32x100", "솔레노이드밸브 5포트"]
    items = [{"item_code": f"ITM-{i + 1:04d}", "name": n, "unit_price": rnd.randint(2, 900) * 100,
              "safety_stock": rnd.choice([10, 20, 30, 50, 100])} for i, n in enumerate(item_names)]
    stock = [{"item_code": it["item_code"], "warehouse": w, "qty": rnd.randint(0, 120)}
             for it in items for w in ("본사창고", "평택창고")]
    customers = ["삼원전자", "(주)대한모터스", "한결식품", "(주)새봄유통", "태성건설", "(주)누리바이오", "동방기계"]
    receivables = []
    for i in range(28):
        m = rnd.randint(3, 9)
        amount = rnd.randint(10, 900) * 10000
        paid = rnd.choice([0, 0, amount, amount, rnd.randint(1, amount // 10000) * 10000])
        receivables.append({"invoice_id": f"INV-{i + 1:04d}", "customer": rnd.choice(customers),
                            "issue_date": f"2026-{m:02d}-{rnd.randint(1, 28):02d}",
                            "due_date": f"2026-{min(m + 1, 12):02d}-{rnd.randint(1, 28):02d}",
                            "amount": amount, "paid_amount": paid})
    return {
        "departments": {"desc": "부서 코드와 부서명", "rows": [{"dept_id": d, "name": n} for d, n in depts]},
        "vendors": {"desc": "거래처 목록 (status: active / suspended)", "rows": vendors},
        "vouchers": {"desc": "2026년 지출 전표 (status: 미결 / 승인 / 반려, amount: 원)", "rows": vouchers(2026, 240, "JV")},
        "vouchers_backup_2023": {"desc": "2023년 전표 백업본 (조회 전용, 현재 업무에 쓰지 않음)", "rows": vouchers(2023, 60, "JV")},
        "items": {"desc": "품목 마스터 (unit_price: 원, safety_stock: 안전재고 수량)", "rows": items},
        "stock": {"desc": "창고별 현재 재고 수량", "rows": stock},
        "receivables": {"desc": "2026년 매출채권 (amount: 청구액, paid_amount: 입금액, 원)", "rows": receivables},
    }


DB = build_db()

OPS = {"=": operator.eq, "!=": operator.ne, ">": operator.gt, ">=": operator.ge, "<": operator.lt,
       "<=": operator.le, "contains": lambda a, b: str(b) in str(a), "startswith": lambda a, b: str(a).startswith(str(b))}


def _match(row, filters):
    for f in filters or []:
        col, op, val = f["column"], f["op"], f["value"]
        cell = row[col]                     # KeyError on unknown column
        if isinstance(cell, int) and not isinstance(val, int):
            val = int(val)                  # ValueError on non-numeric text
        if not OPS[op](cell, val):          # KeyError on unknown op
            return False
    return True


def _rows(table, filters):
    return [r for r in DB[table]["rows"] if _match(r, filters)]   # KeyError on unknown table


def list_tables():
    return [{"table": t, "description": v["desc"], "rows": len(v["rows"])} for t, v in DB.items()]


def describe_table(table):
    return {"table": table, "columns": list(DB[table]["rows"][0])}


def query(table, filters=None, columns=None, order_by=None, descending=False, limit=20, offset=0):
    limit = int(limit)
    if limit > 20:
        raise ValueError("limit must be <= 20")
    rows = _rows(table, filters)
    if order_by:
        rows = sorted(rows, key=lambda r: r[order_by], reverse=bool(descending))
    page = rows[int(offset):int(offset) + limit]
    if columns:
        page = [{c: r[c] for c in columns} for r in page]
    nxt = int(offset) + limit
    return {"rows": page, "total": len(rows), "next_offset": nxt if nxt < len(rows) else None}


def aggregate(table, op, column=None, filters=None, group_by=None):
    rows = _rows(table, filters)
    groups = {}
    for r in rows:
        groups.setdefault(r[group_by] if group_by else "all", []).append(r)
    out = []
    for g, rs in sorted(groups.items()):
        vals = [r[column] for r in rs] if column else []
        value = {"count": lambda: len(rs), "sum": lambda: sum(vals), "avg": lambda: round(sum(vals) / len(vals), 2),
                 "max": lambda: max(vals), "min": lambda: min(vals)}[op]()
        out.append({"group": g, "value": value})
    return out


_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}


def calculate(expression):
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp):
            return _BIN[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -ev(n.operand)
        raise ValueError("unsupported expression")
    return ev(ast.parse(str(expression).replace(",", ""), mode="eval"))


STR, INT = {"type": "string"}, {"type": "integer"}
FILTERS = {"type": "array", "description": "Conditions combined with AND.",
           "items": {"type": "object", "properties": {
               "column": STR, "op": {"type": "string", "enum": list(OPS)}, "value": {}},
               "required": ["column", "op", "value"]}}


def spec(name, desc, props=None, required=None):
    return {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []}}


ERP_TOOLS = {
    "list_tables": (spec("list_tables", "List ERP tables with a short description."), list_tables),
    "describe_table": (spec("describe_table", "Show the column names of a table.", {"table": STR}, ["table"]), describe_table),
    "query": (spec("query", "Read rows from a table. Returns at most `limit` (<=20) rows plus `total` and `next_offset` for paging.",
                   {"table": STR, "filters": FILTERS, "columns": {"type": "array", "items": STR},
                    "order_by": STR, "descending": {"type": "boolean"}, "limit": INT, "offset": INT}, ["table"]), query),
    "aggregate": (spec("aggregate", "Compute count/sum/avg/max/min of a column over rows matching filters, optionally grouped by a column.",
                       {"table": STR, "op": {"type": "string", "enum": ["count", "sum", "avg", "max", "min"]},
                        "column": STR, "filters": FILTERS, "group_by": STR}, ["table", "op"]), aggregate),
    "calculate": (spec("calculate", "Evaluate an arithmetic expression such as '1200000*0.1+300'.", {"expression": STR}, ["expression"]), calculate),
}

# ---------------------------------------------------------------- code workspace

class Workspace:
    """A throwaway project folder. Model-written code runs only here, 20 s limit."""

    def __init__(self, root, files, test_cmd):
        self.root = Path(root)
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        for rel, text in files.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text, encoding="utf-8")
        self.test_cmd = test_cmd
        self.edit_failures = 0

    def _path(self, path):
        p = (self.root / str(path)).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise PermissionError("path outside the project")
        return p

    def list_files(self):
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts)

    def read_file(self, path):
        return self._path(path).read_text(encoding="utf-8")   # FileNotFoundError

    def replace_in_file(self, path, old, new):
        p = self._path(path)
        text = p.read_text(encoding="utf-8")
        n = text.count(old) if old else 0
        if n != 1:
            self.edit_failures += 1
            raise ValueError(f"old text found {n} times, must be exactly 1")
        p.write_text(text.replace(old, new), encoding="utf-8")
        return "ok"

    def write_file(self, path, content):
        p = self._path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return "ok"

    def run_tests(self):
        try:
            r = subprocess.run([sys.executable, "-E", "-s", *self.test_cmd], cwd=self.root,
                               capture_output=True, text=True, timeout=20)
            return {"exit_code": r.returncode, "output": (r.stdout + r.stderr)[-2000:]}
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "output": "timeout after 20s"}

    def tools(self):
        return {
            "list_files": (spec("list_files", "List files in the project."), self.list_files),
            "read_file": (spec("read_file", "Read a text file in the project.", {"path": STR}, ["path"]), self.read_file),
            "replace_in_file": (spec("replace_in_file", "Replace `old` with `new` in a file. `old` must appear exactly once.",
                                     {"path": STR, "old": STR, "new": STR}, ["path", "old", "new"]), self.replace_in_file),
            "write_file": (spec("write_file", "Create or overwrite a file with the given content.",
                                {"path": STR, "content": STR}, ["path", "content"]), self.write_file),
            "run_tests": (spec("run_tests", "Run the project's tests. Returns exit_code (0 = pass) and output."), self.run_tests),
        }

# ---------------------------------------------------------------- documents

def doc_tools(docs):
    """docs: {doc_id: (title, text)}"""
    def list_documents():
        return [{"doc_id": d, "title": t} for d, (t, _) in docs.items()]

    def read_document(doc_id, offset=0, length=3000):
        text = docs[doc_id][1]                      # KeyError on unknown id
        offset, length = int(offset), min(int(length), 3000)
        chunk = text[offset:offset + length]
        nxt = offset + length
        return {"doc_id": doc_id, "text": chunk, "next_offset": nxt if nxt < len(text) else None}

    return {
        "list_documents": (spec("list_documents", "List available documents."), list_documents),
        "read_document": (spec("read_document", "Read a document. Long documents come in chunks; use next_offset to continue.",
                               {"doc_id": STR, "offset": INT, "length": INT}, ["doc_id"]), read_document),
    }


# ---------------------------------------------------------------- one general tool: run Python

_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def extract_tables(text, min_rows=3, clean=False):
    """Tables pasted into a message: runs of consecutive lines that split into the same number (>= 3) of
    cells on one delimiter (comma, tab or |), whose first line looks like a header of short names.
    Returns [(delimiter, [lines])]. Rule-based, no model call.
    clean=True: commas inside numbers (1,234) do not count as delimiters, and lines already taken by a
    tab or | table are not taken again as a comma table."""
    found = []
    lines = (text or "").splitlines()
    taken = set()
    for d in (("\t", "|", ",") if clean else (",", "\t", "|")):
        run = []
        for i, line in enumerate(lines + [""]):
            if clean and d == ",":
                line = "" if i in taken else _THOUSANDS.sub("", line)
            n = line.count(d)
            if n >= 2 and (not run or run[0].count(d) == n):
                run.append(line.strip(" \r"))       # keep leading/trailing delimiters (empty first cell)
                continue
            header = [c.strip() for c in run[0].strip(d).split(d)] if run else []
            named = [c for c in header if c]          # an empty top-left cell is common in report tables
            ok = len(named) >= 2 and all(len(c) <= 40 and not re.search(r"\d,\d{3}|:", c) for c in named)
            if len(run) >= min_rows and ok:
                found.append((d, run))
                taken.update(range(i - len(run), i))
            run = [line.strip(" \r")] if n >= 2 else []
    return found


_NUM = re.compile(r"[\s$₩(−-]*[\d.,]+\s*%?\)?\s*(원)?")


def normalize_table(d, rows, out=","):
    """One clean CSV (delimiter `out`) from an extracted table: cells stripped, outer | and markdown alignment rows
    removed, header rows above the data (no number cells, or an empty first cell) merged into one name per
    column, empty names filled as col1, col2, ... and duplicates numbered. Returns (header, csv_text)."""
    cells = []
    for line in rows:
        if d == "|":
            line = line.strip()
            line = line[1:] if line.startswith("|") else line
            line = line[:-1] if line.endswith("|") else line
        row = [c.strip() for c in line.split(d)]
        if d == "|" and all(re.fullmatch(r":?-{2,}:?", c) for c in row if c) and any(row):
            continue
        cells.append(row)
    width = max(len(r) for r in cells)
    cells = [r + [""] * (width - len(r)) for r in cells]
    k = 1
    while k < min(4, len(cells) - 1):
        row = cells[k]
        if row[0] and any(_NUM.fullmatch(c) for c in row if c):
            break
        if row[0] and cells[k - 1][0]:
            break
        k += 1
    head = cells[:k]
    for r in head[:-1]:                              # a group name spans the empty cells to its right
        for j in range(1, width):
            if not r[j] and r[j - 1] and j > 1:
                r[j] = r[j - 1]
    names, seen = [], {}
    for j in range(width):
        name = " ".join(r[j] for r in head if r[j]) or f"col{j + 1}"
        seen[name] = seen.get(name, 0) + 1
        names.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=out, lineterminator="\n")
    w.writerow(names)
    w.writerows(r for r in cells[k:] if any(r))
    return names, buf.getvalue()


def python_tool(workdir, input_text=None, finish_hint=False, tables=False, clean_tables=False, helpers=False):
    """A single general-purpose action for tasks without domain tools.
    Runs a standard-library Python program in its own folder with a 20 s limit, no inherited
    environment variables (so no keys), isolated mode (-I). This prevents accidents; it is not a security sandbox."""
    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    counter = {"n": 0}
    if input_text is not None:   # the user's message, so the model reads data instead of retyping it
        (root / "input.txt").write_text(input_text, encoding="utf-8")
    if helpers:                  # num() and norm() for amounts and names written the way people write them
        (root / "helpers.py").write_text((Path(__file__).with_name("helpers_lib.py")).read_text(encoding="utf-8"),
                                         encoding="utf-8")
    keep = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if k in os.environ}
    # seconds per program: stops runaway loops, not model thinking. Grows with the size of the data handed over,
    # so one default fits every model; LLM_PY_TIMEOUT overrides it.
    data_mb = len((input_text or "").encode("utf-8")) / 1e6
    limit = float(os.getenv("LLM_PY_TIMEOUT", "0")) or 20 + 10 * data_mb
    cap = int(os.getenv("LLM_PY_OUTPUT", "4000"))

    def clip(text, n):
        if len(text) <= n:
            return text
        head, tail = n // 3, n - n // 3
        return (text[:head] + f"\n[harness] ... {len(text) - n} characters omitted; print only the values you need ...\n"
                + text[-tail:])

    def run_python(code):
        counter["n"] += 1
        path = root / f"snippet_{counter['n']:02d}.py"
        code = str(code)
        if helpers and not code.lstrip().startswith("from __future__"):
            # isolated mode leaves the working folder off sys.path; add it on the first line so line numbers match
            code = "import sys as _h; _h.path.insert(0, ''); del _h; " + code.lstrip("\n") if code.strip() else code
        path.write_text(code, encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, "-I", "-X", "utf8", path.name], cwd=root, env=keep,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=limit)
            return {"exit_code": r.returncode, "stdout": clip(r.stdout, cap), "stderr": clip(r.stderr, cap // 2)}
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": f"timeout after {limit:.0f}s: the program did not finish. "
                    "Check for endless loops; process the data in one pass."}

    desc = ("Run a Python 3 program (standard library only) and return its exit code, "
            "stdout and stderr. Use print() to show results. Each call starts fresh.")
    if clean_tables and input_text is not None:
        # clean_tables="keep": a tab table stays tab-separated, because users who paste from Excel say "tab-separated"
        # and the model then passes delimiter='\t' whatever the file holds. True: every table becomes comma CSV.
        keep_tab = clean_tables == "keep"
        found = []
        for d, rows in extract_tables(input_text, clean=True):
            out = "\t" if keep_tab and d == "\t" else ","
            found.append((out, *normalize_table(d, rows, out)))
        for i, (out, names, body) in enumerate(found, 1):
            (root / f"table_{i}.csv").write_text(body, encoding="utf-8")
        if found and keep_tab:
            desc += (" Tables from the user's message are already saved as files with one header row; read them "
                     "with csv.DictReader(open(name, encoding='utf-8'), delimiter=...) using the delimiter given "
                     "here: " + "; ".join(
                         f"table_{i}.csv ({body.count(chr(10)) - 1} data rows, delimiter "
                         f"{'tab' if out == chr(9) else 'comma'}, columns: {names})"
                         for i, (out, names, body) in enumerate(found, 1)) + ".")
        elif found:
            desc += (" Tables from the user's message are already saved as comma-separated files with one "
                     "header row; read them with csv.DictReader(open(name, encoding='utf-8')): " + "; ".join(
                         f"table_{i}.csv ({body.count(chr(10)) - 1} data rows, columns: {names})"
                         for i, (out, names, body) in enumerate(found, 1)) + ".")
    elif tables and input_text is not None:
        found = extract_tables(input_text)
        names = {",": "comma", "\t": "tab", "|": "|"}
        for i, (d, rows) in enumerate(found, 1):
            (root / f"table_{i}.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
        if found:
            desc += (" Tables from the user's message are already saved as files; read them with "
                     "csv.DictReader(open(name, encoding='utf-8'), delimiter=...): " + "; ".join(
                         f"table_{i}.csv ({len(rows) - 1} data rows, delimiter {names[d]}, columns: {rows[0]})"
                         for i, (d, rows) in enumerate(found, 1)) + ".")
    if input_text is not None:
        desc += (" The user's whole message, including any pasted data, is saved as the file input.txt in the "
                 "working directory: read it with open('input.txt', encoding='utf-8').read() instead of "
                 "copying the data into your code.")
    if helpers:
        desc += (" A helper module is in the folder: from helpers import num, norm. num(text) reads a number "
                 "written the way people write it ('2억6천만원', '(1,234)', '$5.2', '12.5%', '1,597,000원'); "
                 "norm(text) gives a key for comparing names (spaces removed, case-folded, (주) dropped).")
    if finish_hint:
        desc += (" When the program computes the final result, make its last printed line the final answer in "
                 "exactly the format the user asked for; that line is then used as your reply.")
    return {"run_python": (spec("run_python", desc,
                                {"code": STR}, ["code"]), run_python)}
