"""A/B bench task set 2: generation tasks (game logic, small apps, slide decks, design docs).

Each task: id, split ("gen"), domain, prompt (Korean, names the deliverable files and rules), tools ("code"),
files, test_cmd, contract, check(answer, parsed, ws). Grading uses files only: the visible test is
restored to its original and must pass, then a hidden check runs. Model code runs only in a subprocess
inside ws.root (20 s); decks and documents are read as data. Standard library only.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import env  # noqa: F401  (Workspace is created by the runner)
import grade

TEXT = {"type": "text"}
DONE = " 다 되면 무엇을 했는지 한두 줄로 알려주세요(답 형식은 자유 텍스트)."

# ================================================================= helpers


def _restore(root, files):
    for name, text in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def _check(restore, hidden_src=None, pycheck=None):
    """restore: {path: original text} written back before grading (tests, specs, source material).
    The visible test must pass; then hidden_src runs as a subprocess in ws.root and/or
    pycheck(root) inspects the deliverable files (no model code is imported)."""
    def check(answer, parsed, ws):
        if ws is None:
            return False
        root = Path(ws.root)
        try:
            _restore(root, restore)
            if ws.run_tests()["exit_code"] != 0:
                return False
            if pycheck is not None and not pycheck(root):
                return False
        except Exception:
            return False
        if hidden_src is None:
            return True
        hidden = root / "hidden_gen_test.py"
        hidden.write_text(hidden_src, encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, "-E", "-s", "-X", "utf8", hidden.name], cwd=root,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
            return r.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        finally:
            hidden.unlink(missing_ok=True)
    return check


_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")


def _nums(text):
    """Number-like tokens as normalized numbers: '1,240' -> 1240, '8.7' -> 8.7, '07' -> 7."""
    out = set()
    for tok in _NUM_RE.findall(str(text)):
        tok = tok.rstrip(".,")
        v = grade.num(tok.replace(",", ""))
        if v is not None:
            out.add(v)
    return out


def _task(id, domain, prompt, files, test_file, restore_names, hidden_src=None, pycheck=None):
    restore = {n: files[n] for n in restore_names}
    return dict(id=id, split="gen", domain=domain, tools="code", prompt=prompt + DONE, files=files,
                test_cmd=[test_file], contract=TEXT, check=_check(restore, hidden_src, pycheck))


# ================================================================= game: 2048

G1_SRC = '''"""2048 게임 이동 로직.

보드는 N x N 정수 리스트의 리스트입니다(N >= 2, 4로 고정 아님). 0은 빈 칸이고 나머지는 2의 거듭제곱입니다.

move(board, direction) -> (new_board, gained)
    direction: "left", "right", "up", "down" 중 하나. 그 밖의 값이면 ValueError.
    - 모든 타일을 그 방향 끝까지 민다.
    - 같은 값의 두 타일이 만나면 하나(두 배 값)로 합친다.
    - 한 번의 move에서 이미 합쳐져 생긴 타일은 같은 move 안에서 다시 합쳐지지 않는다.
        [2, 2, 2, 2] 왼쪽  -> [4, 4, 0, 0]
        [4, 4, 8, 0] 왼쪽  -> [8, 8, 0, 0]
    - 같은 값이 세 개 이어지면 미는 방향 쪽 두 개가 먼저 합쳐진다.
        [2, 2, 2, 0] 왼쪽  -> [4, 2, 0, 0]
        [2, 2, 2, 0] 오른쪽 -> [0, 0, 2, 4]
    - gained는 이번 move에서 합쳐져 새로 생긴 타일 값의 합(합쳐진 게 없으면 0).
    - 입력 board는 바꾸지 않고 새 보드를 돌려준다.

can_move(board) -> bool
    네 방향 중 하나라도 움직였을 때 보드가 달라지면 True, 아니면 False.
"""


def move(board, direction):
    raise NotImplementedError


def can_move(board):
    raise NotImplementedError
'''

G1_TEST = '''from game2048 import move, can_move

b = [[2, 0, 2, 0],
     [0, 0, 0, 0],
     [4, 4, 0, 0],
     [0, 0, 0, 8]]
nb, g = move(b, "left")
assert [list(r) for r in nb] == [[4, 0, 0, 0], [0, 0, 0, 0], [8, 0, 0, 0], [8, 0, 0, 0]], nb
assert g == 12, g
assert can_move(b)
print("ok")
'''

G1_HIDDEN = r'''import copy, random
from game2048 import move, can_move

def ref_line(line):
    tiles = [v for v in line if v]
    out, gained, i = [], 0, 0
    while i < len(tiles):
        if i + 1 < len(tiles) and tiles[i] == tiles[i + 1]:
            out.append(tiles[i] * 2); gained += tiles[i] * 2; i += 2
        else:
            out.append(tiles[i]); i += 1
    return out + [0] * (len(line) - len(out)), gained

def ref_move(board, d):
    n = len(board)
    b = [list(r) for r in board]
    g = 0
    if d in ("left", "right"):
        for r in range(n):
            line = b[r] if d == "left" else b[r][::-1]
            new, x = ref_line(line); g += x
            b[r] = new if d == "left" else new[::-1]
    else:
        for c in range(n):
            col = [b[r][c] for r in range(n)]
            if d == "down":
                col = col[::-1]
            new, x = ref_line(col); g += x
            if d == "down":
                new = new[::-1]
            for r in range(n):
                b[r][c] = new[r]
    return b, g

def norm(nb):
    return [list(r) for r in nb]

def row(line, d):
    nb, g = move([list(line)] + [[0] * len(line) for _ in range(len(line) - 1)], d)
    return list(nb[0]), g

assert row([2, 2, 2, 2], "left") == ([4, 4, 0, 0], 8)
assert row([4, 4, 8, 0], "left") == ([8, 8, 0, 0], 8)
assert row([2, 2, 2, 0], "left") == ([4, 2, 0, 0], 4)
assert row([2, 2, 2, 0], "right") == ([0, 0, 2, 4], 4)
assert row([2, 0, 0, 2], "right") == ([0, 0, 0, 4], 4)
assert row([8, 8, 8, 8], "right") == ([0, 0, 16, 16], 32)
assert row([2, 4, 2, 4], "left") == ([2, 4, 2, 4], 0)
assert row([0, 0, 0, 0], "left") == ([0, 0, 0, 0], 0)

b = [[2, 0], [2, 4]]
snap = copy.deepcopy(b)
assert norm(move(b, "up")[0]) == [[4, 4], [0, 0]]
assert norm(move(b, "down")[0]) == [[0, 0], [4, 4]]
assert b == snap, "input board must not change"

for bad in ("LEFT", "north", "", None):
    try:
        move([[0, 2], [2, 0]], bad)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for %r" % (bad,))

assert not can_move([[2, 4], [4, 2]])
assert not can_move([[2, 4, 8], [4, 8, 2], [8, 2, 4]])
assert can_move([[2, 4, 8], [2, 8, 4], [8, 4, 2]])          # vertical merge only
assert can_move([[2, 4], [8, 0]])
assert can_move([[2, 2], [4, 8]])

rnd = random.Random(2048)
for _ in range(400):
    n = rnd.randint(2, 6)
    board = [[rnd.choice([0, 0, 0, 2, 2, 4, 4, 8, 16]) for _ in range(n)] for _ in range(n)]
    snap = copy.deepcopy(board)
    for d in ("left", "right", "up", "down"):
        nb, g = move(board, d)
        exp_b, exp_g = ref_move(board, d)
        assert norm(nb) == exp_b and g == exp_g, (board, d, nb, g)
    assert board == snap
    exp_can = any(ref_move(board, d)[0] != board for d in ("left", "right", "up", "down"))
    assert bool(can_move(board)) == exp_can, board
print("hidden ok")
'''

# ================================================================= game: omok

G2_SRC = '''"""오목 판정과 한 수 앞 보기.

보드: 문자열 리스트, N x N 정사각형(5 <= N <= 19). '.' 빈 칸, 'X' 흑, 'O' 백.
보드[r][c]는 r행 c열.

winner(board) -> 'X' | 'O' | None
    가로, 세로, 두 대각선(↘, ↙) 중 어느 방향이든 같은 돌이 "정확히 5개" 이어져 있으면 그 돌이 승리.
    6개 이상 이어진 줄(장목)은 승리가 아니다.
    입력 보드에는 승자가 많아야 한 명이라고 가정해도 된다.

best_move(board, player) -> (r, c) | None
    player는 'X' 또는 'O'. 그 밖의 값이면 ValueError.
    1) player가 빈 칸 하나에 두어 바로 이길 수 있으면(두고 난 보드에서 winner가 player) 그 자리.
    2) 1이 없고, 상대가 다음 수에 바로 이길 수 있는 빈 칸이 있으면 그 자리(막기).
    3) 둘 다 없으면 None.
    후보가 여러 개면 (r, c)가 가장 작은 것(r 먼저, 같으면 c).
    입력 board는 바꾸지 않는다.
"""


def winner(board):
    raise NotImplementedError


def best_move(board, player):
    raise NotImplementedError
'''

G2_TEST = '''from omok import winner, best_move

b = [".......",
     ".XXXXX.",
     ".OOOO..",
     ".......",
     ".......",
     ".......",
     "......."]
assert winner(b) == "X"
b2 = [".......",
      ".XXXX..",
      ".OOO...",
      ".......",
      ".......",
      ".......",
      "......."]
assert winner(b2) is None
assert best_move(b2, "X") == (1, 0)
print("ok")
'''

G2_HIDDEN = r'''import random
from omok import winner, best_move

DIRS = ((0, 1), (1, 0), (1, 1), (1, -1))

def ref_winner(b):
    n = len(b)
    for r in range(n):
        for c in range(n):
            s = b[r][c]
            if s == ".":
                continue
            for dr, dc in DIRS:
                pr, pc = r - dr, c - dc
                if 0 <= pr < n and 0 <= pc < n and b[pr][pc] == s:
                    continue
                k, rr, cc = 0, r, c
                while 0 <= rr < n and 0 <= cc < n and b[rr][cc] == s:
                    k += 1; rr += dr; cc += dc
                if k == 5:
                    return s
    return None

def place(b, r, c, p):
    return [row if i != r else row[:c] + p + row[c + 1:] for i, row in enumerate(b)]

def ref_best(b, p):
    o = "O" if p == "X" else "X"
    n = len(b)
    for who in (p, o):
        for r in range(n):
            for c in range(n):
                if b[r][c] == "." and ref_winner(place(b, r, c, who)) == who:
                    return (r, c)
    return None

def grid(n, stones):
    b = [["."] * n for _ in range(n)]
    for r, c, s in stones:
        b[r][c] = s
    return ["".join(x) for x in b]

def bm(b, p):
    m = best_move(b, p)
    return None if m is None else tuple(m)

# exactly five, not six
six = grid(9, [(4, c, "X") for c in range(1, 7)])
assert winner(six) is None, "six in a row is not a win"
assert winner(grid(9, [(r, 3, "O") for r in range(4, 9)])) == "O"        # vertical to edge
assert winner(grid(9, [(r, r, "X") for r in range(0, 5)])) == "X"        # main diagonal from corner
assert winner(grid(9, [(r, 8 - r, "O") for r in range(2, 7)])) == "O"    # anti-diagonal
assert winner(grid(5, [(r, 4 - r, "X") for r in range(5)])) == "X"       # 5x5 anti-diagonal
assert winner(grid(9, [(0, c, "X") for c in range(4)] + [(0, 4, "O")])) is None
assert winner(grid(9, [(r, r, "X") for r in range(0, 6)])) is None       # diagonal six
assert winner(grid(19, [])) is None

# placing that would make six is not a win -> no winning move there
b = grid(9, [(4, c, "X") for c in (0, 1, 2, 4, 5)] + [(0, 0, "O")])
# filling (4,3) gives six -> not a win; no other winning cell for X
assert bm(b, "X") is None, bm(b, "X")

# win beats block
b = grid(9, [(0, c, "O") for c in range(4)] + [(8, c, "X") for c in range(1, 5)])
assert bm(b, "X") == (8, 0)
assert bm(b, "O") == (0, 4)
# block when cannot win
b = grid(9, [(2, 2, "O"), (3, 3, "O"), (4, 4, "O"), (5, 5, "O"), (0, 8, "X")])
assert bm(b, "X") == (1, 1)
assert bm(grid(9, [(4, 4, "X")]), "O") is None

snap = list(b)
best_move(b, "X")
assert b == snap
for bad in ("x", "", None, "Z"):
    try:
        best_move(b, bad)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for %r" % (bad,))

rnd = random.Random(55)
checked = 0
while checked < 60:
    n = rnd.choice([7, 9, 11, 15])
    b = [[rnd.choice("XO.....") for _ in range(n)] for _ in range(n)]
    b = ["".join(x) for x in b]
    if ref_winner(b) is not None:
        continue
    w = winner(b)
    assert w is None, (b, w)
    for p in "XO":
        assert bm(b, p) == ref_best(b, p), (b, p)
    checked += 1
print("hidden ok")
'''

# ================================================================= game: minesweeper

G3_SRC = '''"""지뢰찾기 로직.

grid: 문자열 리스트, R x C 직사각형(1 <= R, C <= 200). '*'는 지뢰, '.'는 안전한 칸.
이웃은 상하좌우와 대각선 8칸이다.

counts(grid) -> list[list[int]]
    각 칸 주변 지뢰 수. 지뢰 칸은 -1.

reveal(grid, opened, r, c) -> (new_opened, status)
    opened: 이미 열린 칸 (r, c) 튜플의 set. 이 set은 바꾸지 않고 새 set을 돌려준다.
    (r, c)가 보드 밖이면(음수 포함) ValueError.
    - 지뢰 칸을 열면 그 칸만 열린다.
    - 주변 지뢰가 1개 이상인 칸은 그 칸만 열린다.
    - 주변 지뢰가 0인 칸을 열면 이웃 8칸도 열리고, 그렇게 열린 칸 중 0인 칸에서 다시 퍼진다(연쇄).
      지뢰는 연쇄로 열리지 않는다.
    - 이미 열린 칸이면 아무것도 새로 열지 않는다.
    status: 열린 칸 중 지뢰가 있으면 "lose", 지뢰 아닌 칸이 모두 열렸으면 "win", 그 밖에는 "playing".
"""


def counts(grid):
    raise NotImplementedError


def reveal(grid, opened, r, c):
    raise NotImplementedError
'''

G3_TEST = '''from mines import counts, reveal

g = ["*..",
     "...",
     "..*"]
assert counts(g) == [[-1, 1, 0], [1, 2, 1], [0, 1, -1]], counts(g)
opened, status = reveal(g, set(), 1, 1)
assert opened == {(1, 1)} and status == "playing", (opened, status)
print("ok")
'''

G3_HIDDEN = r'''import random
from mines import counts, reveal

def ref_counts(g):
    R, C = len(g), len(g[0])
    out = []
    for r in range(R):
        row = []
        for c in range(C):
            if g[r][c] == "*":
                row.append(-1); continue
            k = 0
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = r + dr, c + dc
                    if (dr or dc) and 0 <= rr < R and 0 <= cc < C and g[rr][cc] == "*":
                        k += 1
            row.append(k)
        out.append(row)
    return out

def ref_reveal(g, opened, r, c):
    R, C = len(g), len(g[0])
    cnt = ref_counts(g)
    new = set(opened)
    if (r, c) not in new:
        stack = [(r, c)]
        new.add((r, c))
        while stack:
            a, b = stack.pop()
            if cnt[a][b] != 0:
                continue
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = a + dr, b + dc
                    if 0 <= rr < R and 0 <= cc < C and (rr, cc) not in new and g[rr][cc] != "*":
                        new.add((rr, cc)); stack.append((rr, cc))
    if any(g[a][b] == "*" for a, b in new):
        st = "lose"
    elif sum(row.count(".") for row in g) == len(new):
        st = "win"
    else:
        st = "playing"
    return new, st

def rv(g, o, r, c):
    new, st = reveal(g, o, r, c)
    return set(map(tuple, new)), st

g = ["....",
     ".*..",
     "....",
     "...*"]
assert [list(x) for x in counts(g)] == ref_counts(g)
o, st = rv(g, set(), 0, 3)
assert (o, st) == ref_reveal(g, set(), 0, 3), o
assert (2, 2) in o and (1, 1) not in o and (3, 3) not in o

# mine
o, st = rv(g, {(0, 0)}, 1, 1)
assert st == "lose" and o == {(0, 0), (1, 1)}

# out of board, including negatives
for r, c in ((-1, 0), (0, -1), (4, 0), (0, 4)):
    try:
        reveal(g, set(), r, c)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for %r" % ((r, c),))

# input set untouched; already opened -> nothing new
base = {(0, 0)}
o, st = rv(g, base, 0, 0)
assert base == {(0, 0)} and o == {(0, 0)} and st == "playing"
o, _ = rv(g, base, 3, 0)
assert base == {(0, 0)}

# win
g2 = ["*.", ".."]
o, st = rv(g2, {(0, 1), (1, 0)}, 1, 1)
assert st == "win"

# 1-row and 1-col boards
assert rv([".....*"], set(), 0, 0) == ref_reveal([".....*"], set(), 0, 0)
col = ["."] * 7
assert rv(col, set(), 3, 0)[1] == "win"

# big empty board (no recursion limit tricks)
big = ["." * 200] * 200
o, st = rv(big, set(), 100, 100)
assert len(o) == 40000 and st == "win"
big2 = ["." * 150 for _ in range(149)] + ["." * 149 + "*"]
o, st = rv(big2, set(), 0, 0)
assert st == "win" and len(o) == 150 * 150 - 1

rnd = random.Random(77)
for _ in range(150):
    R, C = rnd.randint(1, 12), rnd.randint(1, 12)
    g = ["".join(rnd.choice("*.....") for _ in range(C)) for _ in range(R)]
    assert [list(x) for x in counts(g)] == ref_counts(g), g
    opened = set()
    for _ in range(4):
        r, c = rnd.randrange(R), rnd.randrange(C)
        exp = ref_reveal(g, opened, r, c)
        got = rv(g, opened, r, c)
        assert got == exp, (g, opened, r, c, got, exp)
        if exp[1] != "playing":
            break
        opened = exp[0]
print("hidden ok")
'''

# ================================================================= app: expense CLI

A1_README = '''# 가계부 CLI (app.py)

```
python app.py [--db 파일경로] <명령> [인자...]
```

- `--db`는 명령 앞에 온다. 생략하면 현재 폴더의 `ledger.json`.
- 파일이 없으면 빈 가계부로 본다. 저장할 때 파일을 만든다.
- 저장 형식(UTF-8 JSON):
  `{"entries": [{"id": 1, "date": "2026-10-03", "category": "식비", "amount": 12000, "memo": "점심"}]}`
- 출력은 UTF-8. 테스트는 `python -X utf8 app.py ...`로 실행한다.

## add 날짜 분류 금액 [메모]

- 날짜: `YYYY-MM-DD` 형식의 실제 있는 날짜(2026-02-30은 안 됨).
- 금액: 1 이상의 정수. `12,000`처럼 쉼표가 있어도 된다. 0, 음수, 소수, 숫자 아닌 값은 안 됨.
- 메모를 생략하면 빈 문자열.
- 새 id = 지금 있는 항목의 id 최댓값 + 1 (항목이 없으면 1).
- 성공: 표준출력에 `added <id>` 한 줄, 종료 코드 0.
- 날짜나 금액이 잘못되면 표준오류에 메시지, 종료 코드 2, 파일은 바뀌지 않는다.

## list [--month YYYY-MM] [--category 분류]

- 한 줄에 한 항목: `<id>\\t<date>\\t<category>\\t<amount>\\t<memo>` (탭 구분, amount는 쉼표 없는 정수).
- 날짜 오름차순, 날짜가 같으면 id 오름차순.
- 두 조건을 다 주면 둘 다 맞는 항목만. 맞는 게 없으면 아무것도 출력하지 않는다(종료 코드 0).

## summary --month YYYY-MM

- 그 달의 분류별 합계를 한 줄씩: `<category>\\t<합계>`. 합계 큰 순, 같으면 분류 이름 오름차순(파이썬 문자열 정렬).
- 마지막 줄: `합계\\t<그 달 전체 합계>`. 그 달 항목이 없으면 `합계\\t0` 한 줄만.
- `--month`가 없으면 종료 코드 2.

## delete id

- 성공: 표준출력에 `deleted <id>`, 종료 코드 0.
- 없는 id: 표준오류에 메시지, 종료 코드 1, 파일은 바뀌지 않는다.

## 그 밖

- 알 수 없는 명령이나 인자가 모자라면 종료 코드 2.
'''

A1_SRC = '''"""가계부 CLI. 명세는 README.md."""
import sys


def main(argv):
    print("not implemented", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

A1_TEST = '''import json, os, subprocess, sys

DB = "test_ledger.json"


def run(*args):
    r = subprocess.run([sys.executable, "-X", "utf8", "app.py", "--db", DB, *args],
                       capture_output=True, text=True, encoding="utf-8", timeout=10)
    return r.returncode, r.stdout


if os.path.exists(DB):
    os.remove(DB)
try:
    assert run("add", "2026-10-03", "식비", "12000", "점심") == (0, "added 1\\n"), run("list")
    code, out = run("list")
    assert code == 0 and out == "1\\t2026-10-03\\t식비\\t12000\\t점심\\n", repr(out)
    data = json.load(open(DB, encoding="utf-8"))
    assert data["entries"][0]["amount"] == 12000
    print("ok")
finally:
    if os.path.exists(DB):
        os.remove(DB)
'''

A1_HIDDEN = r'''import json, os, subprocess, sys

DB = "hidden_ledger.json"

def run(*args, db=DB):
    pre = ["--db", db] if db else []
    r = subprocess.run([sys.executable, "-X", "utf8", "app.py", *pre, *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    return r.returncode, r.stdout

def lines(out):
    return [l for l in out.splitlines() if l.strip()]

def entries():
    return json.load(open(DB, encoding="utf-8"))["entries"]

for f in (DB, "ledger.json"):
    if os.path.exists(f):
        os.remove(f)
try:
    # empty / missing file
    assert run("list") == (0, "")
    assert lines(run("summary", "--month", "2026-10")[1]) == ["합계\t0"]

    assert run("add", "2026-10-05", "교통", "1,250") == (0, "added 1\n")
    assert run("add", "2026-10-03", "식비", "12000", "점심 김밥") == (0, "added 2\n")
    assert run("add", "2026-09-30", "식비", "8000", "저녁") == (0, "added 3\n")
    assert run("add", "2026-10-03", "교통", "3200", "택시") == (0, "added 4\n")
    assert run("add", "2026-10-20", "문화", "11250") == (0, "added 5\n")
    e = {x["id"]: x for x in entries()}
    assert e[1]["amount"] == 1250 and isinstance(e[1]["amount"], int)
    assert e[5]["memo"] == "" and e[2]["memo"] == "점심 김밥"

    # validation -> exit 2, file unchanged
    before = open(DB, encoding="utf-8").read()
    for bad in (("2026-02-30", "식비", "1000"), ("2026/10/01", "식비", "1000"), ("2026-10-01", "식비", "0"),
                ("2026-10-01", "식비", "-500"), ("2026-10-01", "식비", "12.5"), ("2026-10-01", "식비", "abc"),
                ("26-10-01", "식비", "100")):
        code, out = run("add", *bad)
        assert code == 2, (bad, code, out)
    assert run("add", "2026-10-01")[0] == 2
    assert open(DB, encoding="utf-8").read() == before

    # list order and filters
    code, out = run("list")
    assert code == 0
    assert [l.split("\t")[0] for l in lines(out)] == ["3", "2", "4", "1", "5"], out
    assert lines(out)[0] == "3\t2026-09-30\t식비\t8000\t저녁"
    assert lines(out)[3] == "1\t2026-10-05\t교통\t1250\t"
    assert out.splitlines()[3] == "1\t2026-10-05\t교통\t1250\t"
    assert [l.split("\t")[0] for l in lines(run("list", "--month", "2026-10")[1])] == ["2", "4", "1", "5"]
    assert [l.split("\t")[0] for l in lines(run("list", "--category", "식비")[1])] == ["3", "2"]
    assert [l.split("\t")[0] for l in lines(run("list", "--month", "2026-10", "--category", "식비")[1])] == ["2"]
    assert run("list", "--month", "2026-11") == (0, "")

    # summary: total desc, tie by name, final total line
    run("add", "2026-10-28", "교통", "6800")          # 교통 = 1250+3200+6800 = 11250 ties 문화 11250
    code, out = run("summary", "--month", "2026-10")
    assert code == 0
    assert lines(out) == ["식비\t12000", "교통\t11250", "문화\t11250", "합계\t34500"], out
    assert lines(run("summary", "--month", "2026-09")[1]) == ["식비\t8000", "합계\t8000"]
    assert run("summary")[0] == 2

    # delete
    assert run("delete", "6") == (0, "deleted 6\n")
    before = open(DB, encoding="utf-8").read()
    assert run("delete", "99")[0] == 1
    assert open(DB, encoding="utf-8").read() == before
    assert run("add", "2026-10-29", "기타", "500") == (0, "added 6\n")
    assert run("delete", "2") == (0, "deleted 2\n")
    assert run("add", "2026-10-30", "기타", "700") == (0, "added 7\n")
    assert sorted(x["id"] for x in entries()) == [1, 3, 4, 5, 6, 7]

    # unknown command
    assert run("export")[0] == 2

    # default db path
    assert run("add", "2026-01-01", "식비", "100", db=None) == (0, "added 1\n")
    assert os.path.exists("ledger.json")
finally:
    for f in (DB, "ledger.json"):
        if os.path.exists(f):
            os.remove(f)
print("hidden ok")
'''

# ================================================================= app: meeting-room booking

A2_SPEC = '''# 회의실 예약 모듈 (booking.py) 명세

```python
class BookingError(Exception): ...

class Scheduler:
    def __init__(self, rooms): ...          # rooms = {"회의실 이름": 수용 인원(int)}
    def book(self, room, date, start, end, people, title="") -> str
    def cancel(self, booking_id) -> None
    def bookings(self, room, date) -> list[dict]
    def free_slots(self, room, date) -> list[tuple[str, str]]
    def suggest(self, date, start, end, people) -> list[str]
```

- 날짜는 "YYYY-MM-DD", 시각은 두 자리 "HH:MM" 문자열이다(형식 자체는 검사하지 않아도 된다).
- 운영 시간은 09:00~18:00이다. 예약은 30분 단위다(분이 00 또는 30).

## book

다음 중 하나라도 해당하면 `BookingError`를 낸다.

1. 없는 회의실
2. start >= end
3. 운영 시간 밖 (start가 09:00보다 이르거나 end가 18:00보다 늦음)
4. start나 end가 30분 단위가 아님
5. people이 1보다 작거나 회의실 수용 인원보다 많음
6. 같은 회의실, 같은 날짜에 시간이 겹치는 예약이 있음. 한 예약의 끝과 다른 예약의 시작이 같으면
   (10:00~11:00 과 11:00~12:00) 겹치지 않는다.

성공하면 예약 ID를 "B1", "B2", "B3" ... 순서로 발급해 돌려준다. 실패한 시도는 번호를 쓰지 않고,
취소된 번호는 다시 쓰지 않는다.

## cancel

예약을 취소한다. 없는 ID거나 이미 취소된 ID면 `KeyError`.

## bookings

그 회의실, 그 날짜의 예약 목록을 시작 시각 순으로 돌려준다. 각 항목은
`{"id", "room", "date", "start", "end", "people", "title"}` 키를 가진 dict. 없는 회의실이면 `BookingError`.

## free_slots

그 회의실, 그 날짜에서 09:00~18:00 중 예약이 없는 구간을 시작 순으로 돌려준다.
예: `[("09:00", "10:00"), ("11:30", "18:00")]`. 길이가 0인 구간은 넣지 않는다. 없는 회의실이면 `BookingError`.

## suggest

그 날짜, 그 시간에 지금 예약할 수 있는(위 규칙을 모두 통과하는) 회의실 이름 목록.
수용 인원이 작은 순, 같으면 이름 순. 시간 자체가 규칙 2~4를 어기면 `BookingError`.
'''

A2_SRC = '''"""회의실 예약 모듈. 명세는 SPEC.md."""


class BookingError(Exception):
    pass


class Scheduler:
    def __init__(self, rooms):
        raise NotImplementedError
'''

A2_TEST = '''from booking import Scheduler, BookingError

s = Scheduler({"소회의실": 4, "대회의실": 12})
bid = s.book("소회의실", "2026-10-21", "10:00", "11:00", 3, "주간회의")
assert bid == "B1", bid
try:
    s.book("소회의실", "2026-10-21", "10:30", "11:30", 2)
except BookingError:
    pass
else:
    raise AssertionError("overlap must raise BookingError")
assert s.free_slots("소회의실", "2026-10-21") == [("09:00", "10:00"), ("11:00", "18:00")]
print("ok")
'''

A2_HIDDEN = r'''from booking import Scheduler, BookingError

def raises(exc, fn, *a, **k):
    try:
        fn(*a, **k)
    except exc:
        return True
    except Exception as e:
        raise AssertionError("expected %s, got %r" % (exc.__name__, e))
    return False

rooms = {"B룸": 6, "A룸": 6, "소회의실": 4, "대회의실": 12}
s = Scheduler(rooms)
D = "2026-10-21"

assert s.book("A룸", D, "10:00", "11:00", 5, "x") == "B1"
assert s.book("A룸", D, "11:00", "12:00", 5) == "B2"         # touching is fine
assert s.book("A룸", D, "09:00", "10:00", 6) == "B3"
assert s.book("A룸", "2026-10-22", "10:00", "11:00", 2) == "B4"   # other date
assert s.book("B룸", D, "10:00", "11:00", 2) == "B5"            # other room

# rule violations
assert raises(BookingError, s.book, "없는방", D, "13:00", "14:00", 2)
assert raises(BookingError, s.book, "A룸", D, "14:00", "14:00", 2)
assert raises(BookingError, s.book, "A룸", D, "15:00", "14:00", 2)
assert raises(BookingError, s.book, "A룸", D, "08:30", "09:30", 2)
assert raises(BookingError, s.book, "A룸", D, "17:30", "18:30", 2)
assert raises(BookingError, s.book, "A룸", D, "13:15", "14:00", 2)
assert raises(BookingError, s.book, "A룸", D, "13:00", "13:45", 2)
assert raises(BookingError, s.book, "A룸", D, "13:00", "14:00", 7)
assert raises(BookingError, s.book, "A룸", D, "13:00", "14:00", 0)
assert raises(BookingError, s.book, "A룸", D, "09:30", "11:30", 2)     # covers several
assert raises(BookingError, s.book, "A룸", D, "08:00", "18:00", 2)
assert raises(BookingError, s.book, "A룸", D, "10:00", "12:00", 2)
assert raises(BookingError, s.book, "A룸", D, "11:30", "12:30", 2)
# failed attempts do not consume ids; edges of opening hours are fine
assert s.book("A룸", D, "17:00", "18:00", 1) == "B6"

assert [b["id"] for b in s.bookings("A룸", D)] == ["B3", "B1", "B2", "B6"]
b0 = s.bookings("A룸", D)[1]
assert b0["room"] == "A룸" and b0["date"] == D and b0["start"] == "10:00" and b0["end"] == "11:00"
assert b0["people"] == 5 and b0["title"] == "x"
assert s.bookings("소회의실", D) == []
assert raises(BookingError, s.bookings, "없는방", D)

assert [tuple(x) for x in s.free_slots("A룸", D)] == [("12:00", "17:00")]
assert [tuple(x) for x in s.free_slots("대회의실", D)] == [("09:00", "18:00")]
assert raises(BookingError, s.free_slots, "없는방", D)

# cancel
s.cancel("B1")
assert raises(KeyError, s.cancel, "B1")
assert raises(KeyError, s.cancel, "B99")
assert [tuple(x) for x in s.free_slots("A룸", D)] == [("10:00", "11:00"), ("12:00", "17:00")]
assert s.book("A룸", D, "10:00", "10:30", 2) == "B7"          # ids not reused
assert [tuple(x) for x in s.free_slots("A룸", D)] == [("10:30", "11:00"), ("12:00", "17:00")]
s.cancel("B3"); s.cancel("B7"); s.cancel("B2"); s.cancel("B6")
assert [tuple(x) for x in s.free_slots("A룸", D)] == [("09:00", "18:00")]

# suggest
s2 = Scheduler(rooms)
s2.book("A룸", D, "14:00", "15:00", 2)
assert s2.suggest(D, "14:00", "15:00", 5) == ["B룸", "대회의실"]
assert s2.suggest(D, "14:00", "15:00", 3) == ["소회의실", "B룸", "대회의실"]
assert s2.suggest(D, "14:30", "16:00", 4) == ["소회의실", "B룸", "대회의실"]
assert s2.suggest(D, "15:00", "16:00", 5) == ["A룸", "B룸", "대회의실"]
assert s2.suggest(D, "09:00", "10:00", 13) == []
assert raises(BookingError, s2.suggest, D, "15:00", "15:00", 2)
assert raises(BookingError, s2.suggest, D, "17:30", "19:00", 2)
assert raises(BookingError, s2.suggest, D, "10:10", "11:00", 2)
print("hidden ok")
'''

# ================================================================= slides (shared)

DECK_FORMAT = '''# 발표 자료 형식 (deck.json)

deck.json은 UTF-8 JSON 파일이다.

```json
{
  "title": "발표 제목",
  "slides": [
    {"title": "슬라이드 제목", "bullets": ["항목", "항목"], "notes": "발표자 메모"}
  ]
}
```

- `title`: 비어 있지 않은 문자열.
- `slides`: 슬라이드 목록. 각 슬라이드의 `title`은 비어 있지 않은 문자열, `bullets`는 문자열 목록,
  `notes`는 비어 있지 않은 문자열.
- 첫 슬라이드는 표지다. 표지의 bullets는 0~5개, 나머지 슬라이드는 1~5개.
- bullet 하나는 60자 이하(공백 포함).
- 장수 제한은 과제 안내를 따른다. `python check_deck.py`로 형식만 확인할 수 있다(내용은 확인하지 않는다).
'''


def _check_deck_py(lo, hi):
    return '''"""deck.json 형식 검사(내용은 보지 않음)."""
import json
import sys

MIN_SLIDES, MAX_SLIDES = %d, %d
errors = []
try:
    with open("deck.json", encoding="utf-8") as f:
        deck = json.load(f)
except FileNotFoundError:
    print("deck.json 파일이 없습니다")
    sys.exit(1)
except ValueError as e:
    print("deck.json이 올바른 JSON이 아닙니다:", e)
    sys.exit(1)

if not isinstance(deck, dict):
    print("최상위는 객체여야 합니다")
    sys.exit(1)
if not isinstance(deck.get("title"), str) or not deck["title"].strip():
    errors.append("title이 비어 있거나 문자열이 아닙니다")
slides = deck.get("slides")
if not isinstance(slides, list):
    errors.append("slides가 목록이 아닙니다")
    slides = []
elif not MIN_SLIDES <= len(slides) <= MAX_SLIDES:
    errors.append("슬라이드는 %%d~%%d장이어야 합니다(지금 %%d장)" %% (MIN_SLIDES, MAX_SLIDES, len(slides)))
for i, s in enumerate(slides, 1):
    if not isinstance(s, dict):
        errors.append("%%d번 슬라이드가 객체가 아닙니다" %% i)
        continue
    if not isinstance(s.get("title"), str) or not s["title"].strip():
        errors.append("%%d번 슬라이드 title이 비어 있습니다" %% i)
    b = s.get("bullets")
    if not isinstance(b, list) or not all(isinstance(x, str) for x in b):
        errors.append("%%d번 슬라이드 bullets가 문자열 목록이 아닙니다" %% i)
    else:
        lo = 0 if i == 1 else 1
        if not lo <= len(b) <= 5:
            errors.append("%%d번 슬라이드 bullets 개수는 %%d~5개여야 합니다(지금 %%d개)" %% (i, lo, len(b)))
        for x in b:
            if len(x) > 60:
                errors.append("%%d번 슬라이드 bullet이 60자를 넘습니다: %%s" %% (i, x[:20]))
    if not isinstance(s.get("notes"), str) or not s["notes"].strip():
        errors.append("%%d번 슬라이드 notes가 비어 있습니다" %% i)

if errors:
    print("\\n".join(errors))
    sys.exit(1)
print("형식 ok (%%d장)" %% len(slides))
''' % (lo, hi)


def _load_deck(root):
    deck = json.loads((root / "deck.json").read_text(encoding="utf-8"))
    slides = deck["slides"]
    return deck, slides


def _deck_text(deck):
    parts = [deck["title"]]
    for s in deck["slides"]:
        parts += [s["title"], *s["bullets"], s["notes"]]
    return "\n".join(parts)


def _t(s):
    return re.sub(r"\s+", "", s["title"])


def _find(slides, title):
    idx = [i for i, s in enumerate(slides) if _t(s) == re.sub(r"\s+", "", title)]
    return idx[0] if len(idx) == 1 else None


def _fabricated(deck, allowed):
    return _nums(_deck_text(deck)) - allowed


# ---------------------------------------------------------------- slides 1: quarterly report

S1_REPORT = '''# 2026년 3분기 실적 보고 — 스마트팩토리사업부

작성: 경영기획팀 / 보고일: 2026-10-12

## 1. 3분기 핵심 실적

| 지표 | 3분기 | 2분기 |
|---|---|---|
| 매출 | 412억 원 | 377억 원 |
| 영업이익률 | 8.7% | 7.9% |
| 신규 고객사 | 1,240곳 | 1,105곳 |

## 2. 주요 성과

- 평택 2공장 자동화 라인이 9월부터 가동을 시작했다.
- 북미 유통 파트너 2곳과 공급 계약을 맺었다.
- 고객 불만 처리 시간이 평균 4.2일에서 2.6일로 줄었다.

## 3. 리스크

- 원자재(알루미늄) 단가 상승: 4분기 원가 부담이 커질 것으로 예상된다.
- 핵심 개발 인력 3명 퇴사: 차세대 컨트롤러 개발 일정이 늦어질 수 있다.

## 4. 4분기 조치 계획

| 조치 | 담당 | 기한 |
|---|---|---|
| 알루미늄 장기 공급 계약 재협상 | 김지훈 구매팀장 | 2026-11-15 |
| 개발 인력 충원(5명) | 박서연 인사팀장 | 2026-12-31 |
| 북미 첫 출하 품질 점검 | 이도윤 품질팀장 | 2026-11-30 |
'''

S1_ALLOWED = _nums(S1_REPORT)


def _s1_check(root):
    deck, slides = _load_deck(root)
    if not 5 <= len(slides) <= 7 or "3분기" not in deck["title"]:
        return False
    k, rk, last = _find(slides, "핵심 지표"), _find(slides, "리스크"), len(slides) - 1
    if k is None or rk is None or not (1 <= k < rk < last) or _t(slides[last]) != "다음단계":
        return False
    kb = _nums("\n".join(slides[k]["bullets"]))
    if not {412, 8.7, 1240} <= kb or kb & {377, 7.9, 1105}:
        return False
    rb = "\n".join(slides[rk]["bullets"])
    if "알루미늄" not in rb or "인력" not in rb:
        return False
    nb = slides[last]["bullets"]
    names = ["김지훈", "박서연", "이도윤"]
    if len(nb) != 3 or sorted(sum(n in b for n in names) for b in nb) != [1, 1, 1] \
            or not all(any(n in b for b in nb) for n in names):
        return False
    return not _fabricated(deck, S1_ALLOWED)


# ---------------------------------------------------------------- slides 2: sales CSV

S2_CSV = '''월,서울,부산,대구,광주
2026-07,1250,860,880,410
2026-08,1310,820,905,455
2026-09,1402,905,925,498
'''
S2_BRIEF = '''# 영업본부장 보고 요청 (10/20)

3분기 지역별 매출을 짧은 발표 자료로 정리해 주세요. 데이터는 data/sales_q3.csv(단위: 만원)입니다.

- 지역별 3분기 합계를 보여 주세요. 숫자는 만원 단위 그대로 씁니다.
- 3분기 전체 합계도 넣어 주세요.
- 마지막에는 다음 단계로 아래 두 가지를 넣습니다.
  - 부산 지역 판촉 계획 재검토 — 최유진 과장
  - 광주 대리점 추가 모집 — 정하늘 대리
'''
_S2_ROWS = [line.split(",") for line in S2_CSV.strip().splitlines()]
S2_TOTALS = {region: sum(int(r[i]) for r in _S2_ROWS[1:]) for i, region in enumerate(_S2_ROWS[0]) if i}
S2_GRAND = sum(S2_TOTALS.values())
S2_ORDER = sorted(S2_TOTALS, key=lambda k: -S2_TOTALS[k])
S2_ALLOWED = _nums(S2_CSV) | _nums(S2_BRIEF) | set(S2_TOTALS.values()) | {S2_GRAND}


def _s2_check(root):
    deck, slides = _load_deck(root)
    if not 4 <= len(slides) <= 6:
        return False
    k, last = _find(slides, "지역별 3분기 매출"), len(slides) - 1
    if k is None or not 1 <= k < last or _t(slides[last]) != "다음단계":
        return False
    rb = slides[k]["bullets"]
    if len(rb) != 4:
        return False
    for b, region in zip(rb, S2_ORDER):
        others = [x for x in S2_TOTALS if x != region]
        if region not in b or any(o in b for o in others) or S2_TOTALS[region] not in _nums(b):
            return False
    if S2_GRAND not in _nums(_deck_text(deck)):
        return False
    nb = "\n".join(slides[last]["bullets"])
    if "최유진" not in nb or "정하늘" not in nb:
        return False
    return not _fabricated(deck, S2_ALLOWED)


# ---------------------------------------------------------------- slides 3: meeting minutes

S3_MEETING = '''# 사내 메신저 전환 TF 2차 회의록

- 일시: 2026-10-14(화) 14:00~15:30
- 장소: 본관 3층 소회의실
- 참석: 한지민(TF장), 오세훈, 윤가람, 서민재, 장예린

## 논의

1. 도입 도구: 후보 A(설치형)와 후보 B(클라우드형)를 비교했다. 보안팀 검토 결과 사외 클라우드에 대화 기록을
   두는 방식은 허용되지 않는다는 의견이 나왔다.
2. 전환 방식: 12월 1일 전사 일괄 전환안과 부서별 단계 전환안을 놓고 논의했다. 일괄 전환은 교육 부담이 커서
   단계 전환으로 의견이 모였다.
3. 기존 메신저: 대화 기록 조회 요구가 많아 한동안 읽기 전용으로 남기기로 했다.

## 결정 사항

- D1. 설치형 후보 A를 도입한다.
- D2. 11월 17일부터 부서별로 단계 전환한다(1단계 경영지원팀, 2단계 연구소, 3단계 전 부서).
- D3. 기존 메신저는 2027-01-31까지 읽기 전용으로 유지한 뒤 종료한다.

## 보류·폐기된 안

- 클라우드형 후보 B 도입: 보안 심사 불통과로 폐기.
- 12월 1일 전사 일괄 전환: 폐기.

## 조치 사항

| 담당 | 할 일 | 기한 |
|---|---|---|
| 윤가람 | 설치형 서버 견적 3곳 받기 | 2026-10-24 |
| 장예린 | 사용자 교육 자료 작성 | 2026-11-07 |
| 서민재 | 부서별 전환 일정표 초안 작성 | 2026-10-21 |
| 오세훈 | 보안 점검 체크리스트 확정 | 2026-10-31 |

다음 회의: 2026-10-28(화) 14:00
'''
S3_ACTIONS = [("서민재", 10, 21), ("윤가람", 10, 24), ("오세훈", 10, 31), ("장예린", 11, 7)]
S3_ALLOWED = _nums(S3_MEETING)


def _s3_check(root):
    deck, slides = _load_deck(root)
    if not 4 <= len(slides) <= 6:
        return False
    d, last = _find(slides, "결정 사항"), len(slides) - 1
    if d is None or not 1 <= d < last or _t(slides[last]) != "다음단계":
        return False
    db = slides[d]["bullets"]
    joined = "\n".join(db)
    if len(db) != 3 or "설치형" not in joined or "읽기 전용" not in joined.replace("읽기전용", "읽기 전용"):
        return False
    if not any({11, 17} <= _nums(b) for b in db):
        return False
    if any(w in joined for w in ("클라우드", "후보 B", "일괄")):
        return False
    nb = slides[last]["bullets"]
    if len(nb) != 4:
        return False
    for b, (name, m, dd) in zip(nb, S3_ACTIONS):
        if name not in b or any(o in b for o, _, _ in S3_ACTIONS if o != name) or not {m, dd} <= _nums(b):
            return False
    return not _fabricated(deck, S3_ALLOWED)


# ================================================================= design docs (shared)


def _check_doc_py(headings):
    return '''"""DESIGN.md 제목 검사(내용은 보지 않음)."""
import sys

REQUIRED = %r
try:
    with open("DESIGN.md", encoding="utf-8") as f:
        lines = [l.strip() for l in f.read().splitlines()]
except FileNotFoundError:
    print("DESIGN.md 파일이 없습니다")
    sys.exit(1)
missing = [h for h in REQUIRED if h not in lines]
if missing:
    print("빠진 제목:", ", ".join(missing))
    sys.exit(1)
print("제목 ok")
''' % (headings,)


def _sections(text):
    out, cur = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            out[cur] = ""
        elif cur is not None:
            out[cur] += line + "\n"
    return out


_METHOD_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\b")
_PATH_RE = re.compile(r"/[A-Za-z0-9_{}/\-]+")


def _endpoints(section):
    """(METHOD, path) pairs from markdown table rows; {anything} -> {}."""
    out = set()
    for line in section.splitlines():
        line = line.strip().replace("`", "")
        if not line.startswith("|"):
            continue
        m, p = _METHOD_RE.search(line), _PATH_RE.search(line)
        if m and p:
            out.add((m.group(1), re.sub(r"\{[^}]*\}", "{}", p.group(0)).rstrip("/")))
    return out


def _items(section):
    n = 0
    for line in section.splitlines():
        s = line.strip()
        if re.match(r"^([-*+]|\d+[.)])\s+\S", s):
            n += 1
        elif s.startswith("|") and not re.match(r"^\|[\s:|-]+\|?$", s):
            n += 1
    rows = [l for l in section.splitlines() if l.strip().startswith("|")]
    if rows:
        n -= 1          # table header row
    return n


def _req_ids(section, n):
    return all(re.search(r"R%d(?!\d)" % i, section) for i in range(1, n + 1))


def _has_fields(section, fields):
    return all(re.search(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(f), section) for f in fields)


# ---------------------------------------------------------------- doc 1: approval workflow

D1_REQ = '''# 전자결재 승인 워크플로 요구사항

## 요구사항

- R1. 기안자는 제목, 금액, 결재선(승인자 목록)을 지정해 결재를 올린다.
- R2. 결재선의 승인 단계는 최대 3단계다.
- R3. 금액이 1,000만 원 이상이면 결재선은 2단계 이상이어야 한다.
- R4. 승인자는 자기 차례일 때만 승인하거나 반려할 수 있다.
- R5. 반려하면 결재는 바로 끝나고 기안자에게 알림이 간다. 반려 사유는 필수다.
- R6. 마지막 단계가 승인되면 결재 상태가 approved가 된다.
- R7. 기안자는 첫 승인이 나기 전까지만 결재를 회수할 수 있다.
- R8. 모든 승인·반려·회수 기록은 감사 로그로 5년 보관한다.

## 상태 값

draft, pending, approved, rejected, withdrawn

## 제약

- 사용자 식별자는 인사 DB의 사번(employee_id)을 그대로 쓴다.
- 알림은 사내 메일 API로만 보낸다.

## 반드시 제공할 API

- POST /approvals — 결재 올리기
- GET /approvals/{id} — 결재 1건 조회
- POST /approvals/{id}/approve — 현재 단계 승인
- POST /approvals/{id}/reject — 반려(사유 필수)
- POST /approvals/{id}/withdraw — 회수
- GET /approvals — 목록(상태로 거르기)

## approval 데이터 필드

id, title, amount, drafter_id, approver_ids, current_step, status, reject_reason, created_at, updated_at
'''
D1_HEADINGS = ["## 개요", "## 요구사항 대응", "## API", "## 데이터 모델", "## 상태 전이", "## 위험과 대안"]
D1_ENDPOINTS = {("POST", "/approvals"), ("GET", "/approvals/{}"), ("POST", "/approvals/{}/approve"),
                ("POST", "/approvals/{}/reject"), ("POST", "/approvals/{}/withdraw"), ("GET", "/approvals")}
D1_FIELDS = ["id", "title", "amount", "drafter_id", "approver_ids", "current_step", "status", "reject_reason",
             "created_at", "updated_at"]
D1_STATES = ["draft", "pending", "approved", "rejected", "withdrawn"]


def _d1_check(root):
    text = (root / "DESIGN.md").read_text(encoding="utf-8")
    if len(text) > 8000:
        return False
    sec = _sections(text)
    if not all(h[3:] in sec for h in D1_HEADINGS):
        return False
    if not _req_ids(sec["요구사항 대응"], 8):
        return False
    if not D1_ENDPOINTS <= _endpoints(sec["API"]):
        return False
    if not _has_fields(sec["데이터 모델"], D1_FIELDS):
        return False
    if not all(s in sec["상태 전이"] for s in D1_STATES):
        return False
    if _items(sec["위험과 대안"]) < 2:
        return False
    # constraints stated with the right numbers
    steps = [int(x) for x in re.findall(r"최대\s*(\d+)\s*단계", text) + re.findall(r"(\d+)\s*단계\s*(?:까지|이하)", text)]
    if not steps or any(x != 3 for x in steps):
        return False
    man = [grade.num(x) for x in re.findall(r"(\d[\d,]*)\s*만\s*원", text)]
    won = [grade.num(x) for x in re.findall(r"(\d{1,3}(?:,\d{3}){2,}|\d{7,})\s*원", text)]
    if not (man or won or "1천만" in text) or any(x != 1000 for x in man) or any(x != 10000000 for x in won):
        return False
    keep = [int(x) for line in text.splitlines() if "보관" in line for x in re.findall(r"(\d+)\s*년", line)]
    return bool(keep) and all(x == 5 for x in keep)


# ---------------------------------------------------------------- doc 2: share-link expiry

D2_REQ = '''# 파일 공유 링크 만료 기능 요구사항

## 요구사항

- R1. 사용자는 파일마다 공유 링크를 만들 수 있다. 링크는 추측할 수 없는 토큰으로 식별한다.
- R2. 만료 기간을 지정하지 않으면 기본 7일이고, 지정할 수 있는 최대 만료 기간은 30일이다.
- R3. 다운로드 횟수 제한을 1~100회 사이로 걸 수 있다(선택).
- R4. 링크에 비밀번호를 걸 수 있다(선택). 비밀번호는 해시로만 저장하고 평문은 저장하지 않는다.
- R5. 만료되었거나 다운로드 횟수를 다 쓴 링크로 접근하면 HTTP 410을 돌려준다.
- R6. 링크 소유자와 관리자는 링크를 즉시 만료시킬 수 있다.
- R7. 사외 이메일로 공유하는 링크는 부서장 승인을 받아야 활성화된다.
- R8. 링크 생성·접근·만료 이력은 1년 보관한다.

## 반드시 제공할 API

- POST /links — 링크 만들기
- GET /links/{token} — 링크로 파일 받기
- POST /links/{id}/expire — 즉시 만료
- POST /links/{id}/approve — 사외 공유 승인(부서장)
- GET /links — 내 링크 목록

## share_link 데이터 필드

id, token, file_id, owner_id, expires_at, max_downloads, download_count, password_hash, is_external,
approved_by, created_at
'''
D2_HEADINGS = ["## 배경", "## 요구사항 추적", "## API 설계", "## 데이터 모델", "## 보안 고려사항", "## 위험과 대안"]
D2_ENDPOINTS = {("POST", "/links"), ("GET", "/links/{}"), ("POST", "/links/{}/expire"),
                ("POST", "/links/{}/approve"), ("GET", "/links")}
D2_FIELDS = ["id", "token", "file_id", "owner_id", "expires_at", "max_downloads", "download_count",
             "password_hash", "is_external", "approved_by", "created_at"]


def _d2_check(root):
    text = (root / "DESIGN.md").read_text(encoding="utf-8")
    if len(text) > 8000:
        return False
    sec = _sections(text)
    if not all(h[3:] in sec for h in D2_HEADINGS):
        return False
    if not _req_ids(sec["요구사항 추적"], 8):
        return False
    if not D2_ENDPOINTS <= _endpoints(sec["API 설계"]):
        return False
    dm = sec["데이터 모델"]
    if not _has_fields(dm, D2_FIELDS) or re.search(r"(?<![A-Za-z0-9_])password(?![A-Za-z0-9_])", dm):
        return False
    if _items(sec["위험과 대안"]) < 2 or "410" not in text:
        return False
    days = [int(x) for line in text.splitlines() if "만료" in line and ("기본" in line or "최대" in line)
            for x in re.findall(r"(\d+)\s*일", line)]
    if any(x not in (7, 30) for x in days) or not re.search(r"(?<!\d)7\s*일", text) \
            or not re.search(r"(?<!\d)30\s*일", text):
        return False
    keep = [(int(x), u) for line in text.splitlines() if "보관" in line
            for x, u in re.findall(r"(\d+)\s*(년|개월)", line)]
    return bool(keep) and all((x, u) in ((1, "년"), (12, "개월")) for x, u in keep)


# ================================================================= tasks

DOC_RULE_COMMON = ("각 제목은 '## 제목' 형태의 줄로 정확히 써 주세요. API는 마크다운 표로, 한 줄에 메서드와 경로가 함께 "
                   "들어가게 써 주세요. 요구사항 문서의 수치(제한값, 기간, 기준 금액 등)는 바꾸지 말고 그대로 적어야 합니다. "
                   "check_doc.py는 제목만 확인합니다(run_tests로 실행).")

TASKS = [
    _task("gen_01", "game",
          "2048 게임의 이동 로직을 game2048.py에 구현해 주세요. 함수 move와 can_move의 규칙은 파일 맨 위 docstring에 "
          "있습니다. 보드 크기는 4x4로 고정이 아니고, 한 번 이동에서 합쳐진 타일이 또 합쳐지면 안 되는 등 docstring의 "
          "규칙을 모두 지켜야 합니다. test_game2048.py는 간단한 확인용이고, 테스트에 없는 경우도 docstring대로 동작해야 합니다.",
          {"game2048.py": G1_SRC, "test_game2048.py": G1_TEST}, "test_game2048.py", ["test_game2048.py"], G1_HIDDEN),
    _task("gen_02", "game",
          "오목 판정 모듈 omok.py를 완성해 주세요. winner(board)는 정확히 5개가 이어진 줄만 승리로 치고(6개 이상은 승리 아님), "
          "best_move(board, player)는 바로 이기는 수가 있으면 그 수, 없으면 상대가 바로 이기는 자리를 막는 수, 둘 다 없으면 "
          "None을 돌려줍니다. 자세한 규칙은 파일 docstring에 있습니다. test_omok.py는 간단한 확인용이고, 가로·세로·두 대각선, "
          "보드 가장자리 같은 경우도 docstring대로 동작해야 합니다.",
          {"omok.py": G2_SRC, "test_omok.py": G2_TEST}, "test_omok.py", ["test_omok.py"], G2_HIDDEN),
    _task("gen_03", "game",
          "지뢰찾기 로직 mines.py를 완성해 주세요. counts는 칸마다 주변 지뢰 수를, reveal은 칸을 열고(0인 칸은 연쇄로 퍼짐) "
          "새로 열린 칸 집합과 게임 상태를 돌려줍니다. 규칙은 파일 docstring에 있습니다. 보드는 최대 200x200까지 들어올 수 "
          "있고, 보드 밖 좌표(음수 포함)는 ValueError입니다. test_mines.py는 간단한 확인용이고, 테스트에 없는 경우도 "
          "docstring대로 동작해야 합니다.",
          {"mines.py": G3_SRC, "test_mines.py": G3_TEST}, "test_mines.py", ["test_mines.py"], G3_HIDDEN),
    _task("gen_04", "app",
          "README.md 명세대로 가계부 CLI app.py를 만들어 주세요(표준 라이브러리만). add, list, summary, delete 명령과 "
          "--db 옵션, 출력 형식(탭 구분), 정렬 순서, 잘못된 입력일 때의 종료 코드를 명세 그대로 지켜야 합니다. "
          "test_app.py는 가장 기본적인 경우만 확인합니다.",
          {"README.md": A1_README, "app.py": A1_SRC, "test_app.py": A1_TEST}, "test_app.py",
          ["README.md", "test_app.py"], A1_HIDDEN),
    _task("gen_05", "app",
          "SPEC.md 명세대로 회의실 예약 모듈 booking.py를 완성해 주세요(표준 라이브러리만). 예약 규칙 위반 시 BookingError, "
          "예약 ID 발급 방식, 빈 시간 계산(free_slots), 회의실 추천(suggest)의 정렬까지 명세 그대로여야 합니다. "
          "test_booking.py는 가장 기본적인 경우만 확인합니다.",
          {"SPEC.md": A2_SPEC, "booking.py": A2_SRC, "test_booking.py": A2_TEST}, "test_booking.py",
          ["SPEC.md", "test_booking.py"], A2_HIDDEN),
    _task("gen_06", "slides",
          "docs/q3_report.md를 바탕으로 경영진 보고용 발표 자료를 deck.json으로 만들어 주세요. 형식은 SLIDES_SPEC.md를 "
          "따릅니다. 규칙: 전체 5~7장. 발표 제목(title)에 '3분기'를 넣을 것. 첫 장은 표지. 표지 다음 어딘가에 제목이 정확히 "
          "'핵심 지표'인 슬라이드를 두고 3분기 매출·영업이익률·신규 고객사 수를 원문 숫자 그대로 넣되, 2분기 수치는 이 "
          "슬라이드에 넣지 말 것. 그 뒤에 제목이 '리스크'인 슬라이드에 두 가지 리스크를 넣을 것. 마지막 장은 제목이 "
          "'다음 단계'이고 4분기 조치 3건을 bullet 하나에 한 건씩(담당자 이름 포함) 정확히 3개로 쓸 것. 원문에 없는 숫자는 "
          "어디에도(notes 포함) 쓰지 말 것 — 직접 계산한 증감률 같은 값도 안 됩니다. 슬라이드 제목에 번호를 붙이지 마세요. "
          "check_deck.py(run_tests)는 형식만 확인합니다.",
          {"docs/q3_report.md": S1_REPORT, "SLIDES_SPEC.md": DECK_FORMAT, "check_deck.py": _check_deck_py(5, 7)},
          "check_deck.py", ["docs/q3_report.md", "SLIDES_SPEC.md", "check_deck.py"], pycheck=_s1_check),
    _task("gen_07", "slides",
          "docs/brief.md의 요청대로 data/sales_q3.csv(단위 만원)를 정리한 발표 자료를 deck.json으로 만들어 주세요. 형식은 "
          "SLIDES_SPEC.md를 따릅니다. 규칙: 전체 4~6장, 첫 장은 표지. 제목이 정확히 '지역별 3분기 매출'인 슬라이드에 "
          "지역마다 bullet 하나씩(정확히 4개), 3분기 합계가 큰 지역부터 순서대로, 각 bullet에 지역 이름과 그 지역 3분기 "
          "합계(만원, 숫자 그대로)를 쓸 것. 3분기 전체 합계도 자료 어딘가에 넣을 것. 마지막 장은 제목이 '다음 단계'이고 "
          "brief.md의 두 가지 조치를 담당자 이름과 함께 쓸 것. CSV와 brief.md에 있는 숫자, 그리고 지역별 합계와 전체 합계 "
          "외의 숫자(비율, 억 단위 환산 등)는 쓰지 말 것. 슬라이드 제목에 번호를 붙이지 마세요. "
          "check_deck.py(run_tests)는 형식만 확인합니다.",
          {"docs/brief.md": S2_BRIEF, "data/sales_q3.csv": S2_CSV, "SLIDES_SPEC.md": DECK_FORMAT,
           "check_deck.py": _check_deck_py(4, 6)},
          "check_deck.py", ["docs/brief.md", "data/sales_q3.csv", "SLIDES_SPEC.md", "check_deck.py"], pycheck=_s2_check),
    _task("gen_08", "slides",
          "docs/meeting_1014.md 회의록을 공유용 발표 자료 deck.json으로 만들어 주세요. 형식은 SLIDES_SPEC.md를 따릅니다. "
          "규칙: 전체 4~6장, 첫 장은 표지. 제목이 정확히 '결정 사항'인 슬라이드에 이번 회의에서 결정된 것만 정확히 3개 "
          "bullet로 쓸 것(보류·폐기된 안은 넣지 말 것). 마지막 장은 제목이 '다음 단계'이고 조치 사항 4건을 기한이 빠른 순서로 "
          "bullet 하나에 한 건씩, 각 bullet에 담당자 이름과 기한(월·일)을 넣을 것. 원문에 없는 숫자는 어디에도(notes 포함) "
          "쓰지 말 것. 슬라이드 제목에 번호를 붙이지 마세요. check_deck.py(run_tests)는 형식만 확인합니다.",
          {"docs/meeting_1014.md": S3_MEETING, "SLIDES_SPEC.md": DECK_FORMAT, "check_deck.py": _check_deck_py(4, 6)},
          "check_deck.py", ["docs/meeting_1014.md", "SLIDES_SPEC.md", "check_deck.py"], pycheck=_s3_check),
    _task("gen_09", "design_doc",
          "docs/requirements.md(전자결재 승인 워크플로 요구사항)를 보고 설계 문서 DESIGN.md를 써 주세요. 규칙: 제목은 "
          "'## 개요', '## 요구사항 대응', '## API', '## 데이터 모델', '## 상태 전이', '## 위험과 대안' 6개를 반드시 포함. "
          "'요구사항 대응'에서 R1~R8을 하나도 빠짐없이 ID로 언급하며 어떻게 충족하는지 쓸 것. 'API'에는 요구사항 문서의 "
          "엔드포인트 6개를 모두 표로. '데이터 모델'에는 approval 필드 10개를 모두 필드 이름 그대로. '상태 전이'에는 상태 값 "
          "5개를 모두 쓰고 전이 조건을 설명. '위험과 대안'에는 위험 2개 이상을 목록으로. 전체 8000자 이하. "
          + DOC_RULE_COMMON,
          {"docs/requirements.md": D1_REQ, "check_doc.py": _check_doc_py(D1_HEADINGS)},
          "check_doc.py", ["docs/requirements.md", "check_doc.py"], pycheck=_d1_check),
    _task("gen_10", "design_doc",
          "docs/requirements.md(파일 공유 링크 만료 기능 요구사항)를 보고 설계 문서 DESIGN.md를 써 주세요. 규칙: 제목은 "
          "'## 배경', '## 요구사항 추적', '## API 설계', '## 데이터 모델', '## 보안 고려사항', '## 위험과 대안' 6개를 반드시 "
          "포함. '요구사항 추적'에서 R1~R8을 하나도 빠짐없이 ID로 언급할 것. 'API 설계'에는 요구사항 문서의 엔드포인트 5개를 "
          "모두 표로. '데이터 모델'에는 share_link 필드 11개를 모두 필드 이름 그대로 쓰고, 평문 비밀번호 필드는 두지 말 것. "
          "'위험과 대안'에는 위험 2개 이상을 목록으로. 전체 8000자 이하. " + DOC_RULE_COMMON,
          {"docs/requirements.md": D2_REQ, "check_doc.py": _check_doc_py(D2_HEADINGS)},
          "check_doc.py", ["docs/requirements.md", "check_doc.py"], pycheck=_d2_check),
]

assert len({t["id"] for t in TASKS}) == len(TASKS) == 10
