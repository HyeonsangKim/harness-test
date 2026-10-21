"""BFCL v4 multi_turn_base A/B: same model, harness conditions B / C / H, graded by BFCL's own checker.

Needs the official package (Mac dev machine only, not for the closed network):
    uv venv .venv && uv pip install --python .venv/bin/python bfcl-eval

selftest: python bfcl_ab.py selftest                   (ground-truth calls through hx.run must pass, empty run must fail)
run:      python bfcl_ab.py run --out runs/bfcl --conds B,C,H --n 50 --seed 0 --workers 2
report:   python bfcl_ab.py report --out runs/bfcl
env: LLM_URL, LLM_MODEL, optional LLM_API_KEY, LLM_CA_FILE, LLM_EXTRA (JSON merged into every request)

Procedure mirrors bfcl_eval BaseHandler.inference_multi_turn_FC + OpenAICompletionsHandler:
tools from convert_to_tool(GORILLA_TO_OPENAPI, OPENAI_COMPLETIONS); each call is turned into the string
convert_to_function_call() makes and run by execute_multi_turn_func_call() on this conversation's instances;
a user turn ends when the model answers without tool calls; more than MAXIMUM_STEP_LIMIT tool steps in one
turn force-quits the conversation; grading is multi_turn_checker() on the calls that were really executed.
See BFCL_NOTES.md for the deviations.
"""
import argparse
import ast
import concurrent.futures as cf
import hashlib
import json
import os
import random
import re
import statistics
import threading
import time
import uuid
from pathlib import Path

import ab
import hx

from bfcl_eval.constants.default_prompts import MAXIMUM_STEP_LIMIT
from bfcl_eval.constants.enums import ModelStyle
from bfcl_eval.constants.eval_config import POSSIBLE_ANSWER_PATH, PROMPT_PATH
from bfcl_eval.constants.executable_backend_config import CLASS_FILE_PATH_MAPPING
from bfcl_eval.constants.type_mappings import GORILLA_TO_OPENAPI
from bfcl_eval.eval_checker.multi_turn_eval import multi_turn_utils
from bfcl_eval.eval_checker.multi_turn_eval.multi_turn_checker import multi_turn_checker
from bfcl_eval.eval_checker.multi_turn_eval.multi_turn_utils import execute_multi_turn_func_call
from bfcl_eval.model_handler.utils import convert_to_function_call, convert_to_tool
from bfcl_eval.utils import load_dataset_entry, load_ground_truth_entry

CATEGORY = "multi_turn_base"
SYSTEM = "You are a helpful assistant. Use the available tools to complete the user's requests."
MAX_TURNS = MAXIMUM_STEP_LIMIT + 1   # BFCL: at most MAXIMUM_STEP_LIMIT tool steps, then one plain answer
DATA_FILE = PROMPT_PATH / f"BFCL_v4_{CATEGORY}.json"
ANSWER_FILE = POSSIBLE_ANSWER_PATH / f"BFCL_v4_{CATEGORY}.json"
_lock = threading.Lock()


def load():
    entries = {e["id"]: e for e in load_dataset_entry(CATEGORY)}
    answers = {a["id"]: a["ground_truth"] for a in load_ground_truth_entry(CATEGORY)}
    for e in entries.values():
        assert "missed_function" not in e, "base category has no holdout turns"
        assert all(len(t) == 1 and t[0]["role"] == "user" for t in e["question"])
        assert len(e["question"]) == len(answers[e["id"]])
    for mod in {CLASS_FILE_PATH_MAPPING[c] for e in entries.values() for c in e["involved_classes"]}:
        __import__(mod)                                    # import once before threads start
    return entries, answers


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _forget(prefix):
    """Drop the backend instances BFCL keeps in multi_turn_utils globals for one run."""
    g = vars(multi_turn_utils)
    with _lock:
        for k in [k for k in g if k.startswith(prefix)]:
            del g[k]


class Conversation:
    """Model-side BFCL instances for one test entry plus the record of executed calls."""

    def __init__(self, entry, tag):
        self.entry, self.tag = entry, tag                  # tag: unique model_name for BFCL instance naming
        self.turns = []                                    # per user turn: list of steps, each a list of call strings
        execute_multi_turn_func_call([], entry["initial_config"], entry["involved_classes"], tag, entry["id"])
        self.tools = {}
        for spec in convert_to_tool(entry["function"], GORILLA_TO_OPENAPI, ModelStyle.OPENAI_COMPLETIONS):
            fn = spec["function"]
            self.tools[fn["name"]] = (fn, self._executor(fn["name"]))

    def _executor(self, name):
        def call(**kwargs):
            s = convert_to_function_call([{name: kwargs}])[0]
            out, _ = execute_multi_turn_func_call([s], self.entry["initial_config"], self.entry["involved_classes"],
                                                  self.tag, self.entry["id"])
            self.turns[-1][-1].append(s)
            return out[0]
        return call

    def client(self, inner):
        conv = self

        class StepClient:                                   # every model response is one BFCL step
            def chat(self, messages, tools, max_tokens=4096):
                conv.turns[-1].append([])
                return inner.chat(messages, tools, max_tokens)
        return StepClient()

    def decoded(self):
        return [[step for step in turn if step] for turn in self.turns]


def check(entry, answer, decoded):
    tag = "chk_" + uuid.uuid4().hex[:12]
    try:
        if len(decoded) != len(answer):
            return {"valid": False, "error_type": "multi_turn:force_terminated",
                    "error_message": f"{len(decoded)} of {len(answer)} turns run"}
        return multi_turn_checker(decoded, answer, entry, CATEGORY, tag)
    finally:
        _forget(tag)


def converse(client, entry, cond, rep, trace=None, max_turns=MAX_TURNS):
    tag = f"hx_{re.sub(r'[^0-9A-Za-z]', '_', cond)}_{rep}_{uuid.uuid4().hex[:8]}"
    conv = Conversation(entry, tag)
    step_client = conv.client(client)
    history, turn_info, error = None, [], None
    try:
        for turn in entry["question"]:
            conv.turns.append([])
            res = hx.run(step_client, turn[0]["content"], conv.tools, features=ab.features_of(cond),
                         control=(cond == "C"), contract=None, verify=None, max_turns=max_turns,
                         history=history, system=SYSTEM)
            info = {k: res[k] for k in ("calls", "events", "error")}
            info["turns"] = res["turns"] - sum(1 for m in history or [] if m["role"] == "assistant")  # hx counts history too
            history = res["messages"]
            turn_info.append(info)
            if res["error"]:
                error = "force_terminated" if res["error"] == "max_turns" else res["error"]
                break
    finally:
        _forget(tag)
    return conv, history, turn_info, error


def run_one(client, entry, answer, cond, rep, out):
    start = time.monotonic()
    conv, messages, turn_info, error = converse(client, entry, cond, rep)
    decoded = conv.decoded()
    if error and error != "force_terminated":
        result = {"valid": False, "error_type": "multi_turn:inference_error", "error_message": error}
    else:
        result = check(entry, answer, decoded)
    row = {"task": entry["id"], "cond": cond, "rep": rep, "pass": bool(result["valid"]),
           "error_type": result.get("error_type"), "error": error,
           "turns": sum(t["turns"] for t in turn_info), "calls": sum(len(s) for t in decoded for s in t),
           "events": [e for t in turn_info for e in t["events"]], "user_turns": len(turn_info),
           "seconds": round(time.monotonic() - start, 1)}
    tr = {"row": row, "decoded": decoded, "ground_truth": answer, "turn_info": turn_info,
          "checker": result, "messages": messages}
    (out / "traces" / f"{entry['id']}__{cond}__{rep}.json").write_text(
        json.dumps(tr, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return row


# ---------------------------------------------------------------- self test (no model server)

class ScriptClient:
    """Replays given tool-call steps, then answers with text. Used to test the grading path."""

    def __init__(self, steps):
        self.steps, self.i = steps, 0

    def chat(self, messages, tools, max_tokens=4096):
        if messages[-1]["role"] == "user" and not messages[-1]["content"].startswith(("[harness]", "Please double-check")):
            self.queue = list(self.steps.pop(0)) if self.steps else []
        if self.queue:
            calls = self.queue.pop(0)
            tcs = [{"id": f"c{self.i}_{j}", "type": "function",
                    "function": {"name": n, "arguments": json.dumps(a)}} for j, (n, a) in enumerate(calls)]
            self.i += 1
            return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": tcs}}]}
        return {"choices": [{"message": {"role": "assistant", "content": "Done."}}]}


def _parse_call(s, entry):
    """Ground-truth call string -> (name, kwargs); positional arguments are named from the backend signature."""
    node = ast.parse(s, mode="eval").body
    name, args = node.func.id, {k.arg: ast.literal_eval(k.value) for k in node.keywords}
    if node.args:
        import importlib
        import inspect
        for c in entry["involved_classes"]:
            cls = getattr(importlib.import_module(CLASS_FILE_PATH_MAPPING[c]), c)
            if hasattr(cls, name):
                params = [p for p in inspect.signature(getattr(cls, name)).parameters if p != "self"]
                args.update({params[i]: ast.literal_eval(v) for i, v in enumerate(node.args)})
                break
    return name, args


def cmd_selftest(a):
    entries, answers = load()
    ids = sorted(entries, key=lambda i: int(i.rsplit("_", 1)[1]))
    bad, schema_blocked = 0, []
    for i in ids[: a.n]:
        e, gt = entries[i], answers[i]
        # perfect: every ground-truth call, one call per step, through hx.run and the executors
        steps = [[[_parse_call(c, e)] for c in turn] for turn in gt]
        for cond in ("B", "H"):
            conv, _, info, err = converse(ScriptClient([list(s) for s in steps]), e, cond, 0)
            r = check(e, gt, conv.decoded())
            if r["valid"] and not err:
                continue
            if cond == "H" and any("invalid_args" in t["events"] for t in info):
                schema_blocked.append(i)          # ground truth itself breaks the declared schema
                continue
            bad += 1
            print(f"{i} perfect {cond}: FAIL {r.get('error_type')} {err or ''}")
        conv, _, _, _ = converse(ScriptClient([]), e, "B", 0)
        if check(e, gt, conv.decoded())["valid"]:
            bad += 1
            print(f"{i} empty run passed")
        # one turn dropped: replay ground truth except the last turn
        conv, _, _, _ = converse(ScriptClient([list(s) for s in steps[:-1]]), e, "B", 0)
        if gt[-1] and check(e, gt, conv.decoded())["valid"]:
            bad += 1
            print(f"{i} last turn dropped but passed")
    print(f"perfect run blocked by H schema validation (ground truth violates the tool schema): {schema_blocked}")
    print(f"selftest on {min(a.n, len(ids))} entries: {'OK' if not bad else f'{bad} problems'}")


# ---------------------------------------------------------------- run / report

def cmd_run(a):
    out = Path(a.out)
    (out / "traces").mkdir(parents=True, exist_ok=True)
    extra = json.loads(os.getenv("LLM_EXTRA", "{}"))
    client = hx.client_from_env(extra)
    entries, answers = load()
    ids = a.ids.split(",") if a.ids else random.Random(a.seed).sample(sorted(entries), a.n)
    done_path = out / "results.jsonl"
    done = set()
    if done_path.exists():
        for line in done_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done.add((r["task"], r["cond"], r["rep"]))
    jobs = [(i, c, r) for i in ids for c in a.conds.split(",") for r in range(a.rep) if (i, c, r) not in done]
    random.Random(a.seed).shuffle(jobs)
    import importlib.metadata as md
    meta = {"model": os.environ["LLM_MODEL"], "extra": extra, "conds": a.conds, "rep": a.rep, "seed": a.seed,
            "ids": ids, "bfcl_eval": md.version("bfcl-eval"), "data_file": DATA_FILE.name,
            "data_sha256": sha256(DATA_FILE), "answer_sha256": sha256(ANSWER_FILE), "system": SYSTEM,
            "max_turns_per_user_turn": MAX_TURNS, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(jobs)} runs to do ({len(done)} already done)")
    with cf.ThreadPoolExecutor(a.workers) as pool, done_path.open("a", encoding="utf-8") as f:
        futs = {pool.submit(run_one, client, entries[i], answers[i], c, r, out): (i, c, r) for i, c, r in jobs}
        for n, fut in enumerate(cf.as_completed(futs), 1):
            try:
                r = fut.result()
            except Exception as e:  # noqa: BLE001 - one broken run must not stop the batch; it is retried on resume
                print(f"[{n}/{len(jobs)}] {futs[fut]} crashed: {type(e).__name__}: {e}")
                continue
            with _lock:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
            print(f"[{n}/{len(jobs)}] {r['task']:20} {r['cond']:4} {'PASS' if r['pass'] else 'fail'} "
                  f"turns={r['turns']} calls={r['calls']} {r['seconds']}s {r['error_type'] or ''}", flush=True)
    cmd_report(a)


def cmd_report(a):
    out = Path(a.out)
    rows = [json.loads(l) for l in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8")) if (out / "meta.json").exists() else {}
    conds = sorted({r["cond"] for r in rows}, key=lambda c: (c != "B", c != "C", c != "H", c))
    lines = [f"BFCL {CATEGORY}  bfcl-eval {meta.get('bfcl_eval')}  {meta.get('data_file')} "
             f"sha256 {str(meta.get('data_sha256'))[:16]}  model {meta.get('model')}",
             f"{'cond':6} {'n':>4} {'pass':>7} {'turns':>6} {'calls':>6} {'sec':>6}"]
    for c in conds:
        rs = [r for r in rows if r["cond"] == c]
        lines.append(f"{c:6} {len(rs):4} {statistics.mean(r['pass'] for r in rs):7.1%} "
                     f"{statistics.mean(r['turns'] for r in rs):6.1f} {statistics.mean(r['calls'] for r in rs):6.1f} "
                     f"{statistics.mean(r['seconds'] for r in rs):6.1f}")
    lines.append("")
    for b in conds:
        for base in ("B", "C"):
            if b == base or base not in conds or (base == "C" and b == "B"):
                continue
            p = ab.paired(rows, base, b)
            if p:
                lines.append(f"{b} vs {base}: {p['diff']:+.1%} (95% CI {p['ci95'][0]:+.1%} .. {p['ci95'][1]:+.1%}), "
                             f"tasks better/worse {p['task_wins']}/{p['task_losses']} sign p={p['sign_p']:.3f} "
                             f"(n={p['tasks']})")
    lines.append("")
    for c in conds:
        cnt = {}
        for r in rows:
            if r["cond"] == c and not r["pass"]:
                cnt[r["error_type"]] = cnt.get(r["error_type"], 0) + 1
        lines.append(f"checker errors {c}: " + (", ".join(f"{k}={v}" for k, v in sorted(cnt.items())) or "-"))
    for c in conds:
        ev = {}
        for r in rows:
            if r["cond"] == c:
                for e in r["events"]:
                    ev[e] = ev.get(e, 0) + 1
        lines.append(f"events {c}: " + (", ".join(f"{k}={v}" for k, v in sorted(ev.items())) or "-"))
    text = "\n".join(lines)
    (out / "report.txt").write_text(text + "\n", encoding="utf-8")
    print(text)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--conds", default="B,C,H")
    r.add_argument("--n", type=int, default=50)
    r.add_argument("--ids", default="", help="comma-separated test ids instead of a sample")
    r.add_argument("--rep", type=int, default=1)
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--workers", type=int, default=2)
    q = sub.add_parser("report")
    q.add_argument("--out", required=True)
    s = sub.add_parser("selftest")
    s.add_argument("--n", type=int, default=200)
    a = p.parse_args()
    {"run": cmd_run, "report": cmd_report, "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    main()
