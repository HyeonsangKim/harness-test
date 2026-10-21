"""HumanEval+ (EvalPlus v0.1.10): light code writing, all 164 problems, graded with the plus tests.

Data: bench/ext/humanevalplus-v0.1.10.jsonl.gz (not committed), the HumanEvalPlus.jsonl.gz asset of the
evalplus/humanevalplus_release v0.1.10 release (the version evalplus uses by default). EvalPlus is Apache-2.0
(bench/ext/EVALPLUS_LICENSE); the HumanEval problems are MIT (bench/ext/HUMANEVAL_LICENSE).

Grading follows evalplus.eval.unsafe_execute: the expected outputs come from running the canonical solution
(prompt + canonical_solution) on deep copies of base_input + plus_input, as evalplus.evaluate.get_groundtruth
does; here that runs in the same subprocess before the model's code. Each output is compared as evalplus does:
exact ==, or, for float results (or a task atol), same type and length and np.allclose(rtol=1e-7, atol)
reimplemented with the standard library; find_zero (HumanEval/32) uses the |poly(xs, x)| <= atol oracle.
The model's code runs in a namespace that already holds the prompt's code (imports and helper functions such
as poly / encode_cyclic), so a reply that leaves those out still works. Pass only if every base and plus
input passes. One subprocess (python -I, fresh temp dir, stdin closed) with a 30 s total timeout per answer (canonical run included),
instead of evalplus's per-input limits. EXCLUDED lists problems left out (163 remain). Standard library only.
"""
import gzip
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXT = Path(__file__).resolve().parent / "ext"
DATA = EXT / "humanevalplus-v0.1.10.jsonl.gz"
TIMEOUT = 30   # whole subprocess; canonical + correct answer on he_139 take ~10 s on an M-series Mac
SENTINEL = "HE_PLUS_TESTS_PASSED_5c1e"
_PY_BLOCK = re.compile(r"```[ \t]*(?:python|py|python3)[ \t]*\r?\n(.*?)```", re.S | re.I)   # as tasks_notool
# Problems whose canonical solution fails its own plus check here; excluded so every item is passable.
EXCLUDED = {"HumanEval/32": "canonical find_zero misses |poly(xs, x)| <= 1e-4 on 6 of 888 plus inputs "
                            "(Newton's method stops at |f(x)| < 1e-5 or diverges on ill-conditioned polynomials)"}

_RUNNER = r'''
import copy, io, json, math, sys
spec = json.load(open(sys.argv[1], encoding="utf-8"))
entry, atol = spec["entry_point"], spec["atol"]
inputs = spec["base_input"] + spec["plus_input"]

def load(code):
    ns = {"__name__": "solution"}
    exec(compile(spec["prompt"], "prompt.py", "exec"), ns)
    if code is not None:
        exec(compile(code, "solution.py", "exec"), ns)
    return ns[entry]

def is_floats(x):
    if isinstance(x, float):
        return True
    if isinstance(x, (list, tuple)) and x:
        return all(isinstance(i, float) for i in x)
    return False

def allclose(a, b, rtol, atol):
    if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
        if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
            return len(a) == len(b) and all(allclose(x, y, rtol, atol) for x, y in zip(a, b))
        seq, one = (a, b) if isinstance(a, (list, tuple)) else (b, a)
        return all(allclose(x, one, rtol, atol) if seq is a else allclose(one, x, rtol, atol) for x in seq)
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("not numeric")
    a, b = float(a), float(b)
    if math.isnan(a) or math.isnan(b):
        return False
    if math.isinf(a) or math.isinf(b):
        return a == b
    return abs(a - b) <= atol + rtol * abs(b)

def poly(xs, x):
    return sum([coeff * math.pow(x, i) for i, coeff in enumerate(xs)])

ref = load(spec["canonical"])
expected = [ref(*copy.deepcopy(inp)) for inp in inputs]
code = open(sys.argv[2], encoding="utf-8").read()
real_stdout = sys.stdout
sys.stdout = io.StringIO()
fn = load(code)
for inp, exp in zip(inputs, expected):
    out = fn(*copy.deepcopy(inp))
    sys.stdout = io.StringIO()
    if entry == "find_zero":
        assert abs(poly(*inp, out)) <= atol
        continue
    tol = 1e-6 if atol == 0 and is_floats(exp) else atol
    if not out == exp and tol != 0:
        assert type(out) == type(exp)
        if isinstance(exp, (list, tuple)):
            assert len(out) == len(exp)
        assert allclose(out, exp, 1e-07, tol)
    else:
        assert out == exp
sys.stdout = real_stdout
print(SENTINEL)
'''.replace("SENTINEL", repr(SENTINEL))


def extract_python(answer):
    m = _PY_BLOCK.search(answer or "")
    return m.group(1) if m else None


def run_plus(problem, code, timeout=TIMEOUT):
    """True only if `code` passes every base and plus input of `problem`."""
    tmp = tempfile.mkdtemp(prefix="he_plus_")
    try:
        d = Path(tmp)
        spec = {k: problem[k] for k in ("entry_point", "atol", "base_input", "plus_input", "prompt")}
        spec["canonical"] = problem["prompt"] + problem["canonical_solution"]
        (d / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        (d / "solution.py").write_text(code, encoding="utf-8")
        (d / "run_tests.py").write_text(_RUNNER, encoding="utf-8")
        r = subprocess.run([sys.executable, "-I", str(d / "run_tests.py"), str(d / "spec.json"),
                            str(d / "solution.py")], cwd=tmp, timeout=timeout, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL)
        return r.returncode == 0 and r.stdout.strip().endswith(SENTINEL)
    except (subprocess.TimeoutExpired, OSError):
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def load_problems():
    with gzip.open(DATA, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _tasks():
    tasks = []
    for p in load_problems():
        if p["task_id"] in EXCLUDED:
            continue
        n = int(p["task_id"].split("/")[1])
        prompt = (p["prompt"].rstrip() + "\n\nComplete this function. Reply with the whole function in one "
                  "```python code block (standard library only, no example calls, no input()).")

        def check(answer, parsed, ws, p=p):
            code = extract_python(answer)
            return bool(code) and run_plus(p, code)

        tasks.append({"id": f"he_{n}", "split": "humaneval", "domain": "humaneval", "prompt": prompt,
                      "tools": "none", "contract": {"type": "text"}, "check": check})
    return tasks


TASKS = _tasks()
