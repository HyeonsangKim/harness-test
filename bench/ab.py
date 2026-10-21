"""A/B runner: same model, same tasks, harness conditions compared. Standard library only.

run:    python ab.py run --out runs/qwen9b --split eval --conds B,C,H --rep 3 --workers 4
report: python ab.py report --out runs/qwen9b
Conditions: B (plain loop), C (B + generic recheck turn), H (all harness features),
            H-<feature> (H without one feature), B+<feature> (B with one feature).
env: LLM_URL, LLM_MODEL, optional LLM_API_KEY, LLM_CA_FILE, LLM_EXTRA (JSON merged into every request)
"""
import argparse
import copy
import concurrent.futures as cf
import json
import os
import random
import statistics
import threading
import time
from pathlib import Path

import env
import grade
import hx
import importlib


def features_of(cond):
    if cond in ("B", "C", "P", "PT", "V", "R"):
        return ()
    if cond in ("RH", "HS", "RS", "RF"):    # RH: run_python + harness; HS/RS: + skill; RF: + data as a file
        return hx.FEATURES
    if cond in ("H1", "RH1"):               # harness v1 (stall note instead of repeat block)
        return hx.FEATURES_V1
    if cond == "H":
        return hx.FEATURES
    if cond.startswith("H-"):
        return tuple(f for f in hx.FEATURES if f != cond[2:])
    if cond.startswith("B+"):
        return (cond[2:],)
    raise ValueError(cond)


def run_one(client, task, cond, rep, out):
    tag = f"{task['id']}__{cond}__{rep}"
    ws, verify = None, None
    if task["tools"] == "none":
        if cond == "RF":
            tools = env.python_tool(out / "ws" / tag, input_text=task["prompt"])
        else:
            tools = env.python_tool(out / "ws" / tag) if cond in ("R", "RH", "RS") else {}
    elif task["tools"] == "erp":
        tools = env.ERP_TOOLS
    elif task["tools"] == "doc":
        tools = env.doc_tools(task["docs"])
    else:
        ws = env.Workspace(out / "ws" / tag, task["files"], task["test_cmd"])
        tools = ws.tools()

        def verify():
            r = ws.run_tests()
            return r["exit_code"] == 0, r["output"][-1200:]
    if cond == "PT":                        # plain answer with the model's own long thinking turned on
        client = copy.copy(client)
        client.extra = {**client.extra, **json.loads(os.getenv("LLM_THINK_EXTRA", "{}"))}
        client.max_tokens = 16000
    start = time.monotonic()
    try:
        if cond == "V":
            res = vote(client, task, out / "traces" / tag)
        else:
            res = hx.run(client, task["prompt"], tools, features=features_of(cond), control=(cond == "C"),
                         contract=task.get("contract"), verify=verify, trace=out / "traces" / f"{tag}.json",
                         system=system_for(task, cond), resume=ws is None)
    except Exception as e:  # noqa: BLE001 - anything that escapes the loop is an infrastructure failure
        return {"task": task["id"], "domain": task["domain"], "cond": cond, "rep": rep, "pass": False,
                "turns": 0, "calls": 0, "events": [], "error": f"connection: {type(e).__name__}: {e}"[:200],
                "edit_failures": 0, "seconds": round(time.monotonic() - start, 1)}
    try:
        ok = bool(task["check"](res["answer"] or "", grade.parse_json(res["answer"] or ""), ws))
    except Exception as e:  # noqa: BLE001 - a crashing check is a failed answer
        ok, res["error"] = False, res["error"] or f"check: {type(e).__name__}"
    return {"task": task["id"], "domain": task["domain"], "cond": cond, "rep": rep, "pass": ok,
            "tokens": res.get("tokens"),
            "turns": res["turns"], "calls": res["calls"], "events": res["events"], "error": res["error"],
            "edit_failures": ws.edit_failures if ws else 0, "seconds": round(time.monotonic() - start, 1)}


SKILLS = Path(__file__).resolve().parent / "skills"
SKILL_FILE = {"erp": "erp.md", "code": "code.md", "doc": "doc.md", "none": "python.md"}


def system_for(task, cond):
    """HS and RS add the skill file of the task's tool family to the system prompt; others use the plain one."""
    if cond not in ("HS", "RS"):
        return hx.SYSTEM
    text = (SKILLS / SKILL_FILE[task["tools"]]).read_text(encoding="utf-8").strip()
    return hx.SYSTEM + "\n\n# How to work with these tools\n" + text


def _answer_key(answer, contract):
    """Normalized answer used to compare samples: JSON values with numbers normalized, else stripped text."""
    if contract and contract.get("type") == "json":
        parsed = grade.parse_json(answer or "")
        if parsed is None:
            return None
        norm = {k: (grade.num(v) if grade.num(v) is not None else
                    sorted(map(str, v)) if isinstance(v, list) else " ".join(str(v).split()))
                for k, v in parsed.items()}
        return json.dumps(norm, ensure_ascii=False, sort_keys=True)
    return " ".join((answer or "").split()) or None


def vote(client, task, trace_prefix, n=3):
    """Majority vote over up to n independent answers; stops early when the first two agree."""
    answers, keys, turns, error = [], [], 0, None
    tokens = {"prompt": 0, "completion": 0}
    for i in range(n):
        r = hx.run(client, task["prompt"], {}, trace=trace_prefix.with_name(f"{trace_prefix.name}_s{i}.json"))
        turns += r["turns"]
        for k in tokens:
            tokens[k] += (r.get("tokens") or {}).get(k, 0)
        error = error or r["error"]
        answers.append(r["answer"])
        keys.append(_answer_key(r["answer"], task.get("contract")))
        if i == 1 and keys[0] is not None and keys[0] == keys[1]:
            break
    counts = {}
    for k in keys:
        if k is not None:
            counts[k] = counts.get(k, 0) + 1
    best = max(counts, key=lambda k: (counts[k], -keys.index(k))) if counts else None
    pick = answers[keys.index(best)] if best is not None else answers[0]
    return {"answer": pick, "turns": turns, "calls": 0, "events": [f"vote_samples={len(answers)}"], "tokens": tokens,
            "error": error if pick is None else None}


def infra(r):
    """Run lost to the gateway or network, not to the model. Excluded from scores, run again on resume."""
    return bool(r["error"]) and r["error"].startswith(("http_", "connection"))


def cmd_run(a):
    out = Path(a.out)
    (out / "traces").mkdir(parents=True, exist_ok=True)
    extra = json.loads(os.getenv("LLM_EXTRA", "{}"))
    client = hx.client_from_env(extra)
    all_tasks = importlib.import_module(a.taskfile).TASKS
    chosen = [t for t in all_tasks if t["split"] == a.split and (not a.tasks or t["id"] in a.tasks.split(","))]
    done_path = out / "results.jsonl"
    done, keep = set(), []
    if done_path.exists():
        for line in done_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if not infra(r):            # runs lost to gateway/connection errors are run again
                done.add((r["task"], r["cond"], r["rep"]))
                keep.append(line)
        done_path.write_text("".join(l + "\n" for l in keep), encoding="utf-8")
    jobs = [(t, c, r) for t in chosen for c in a.conds.split(",") for r in range(a.rep) if (t["id"], c, r) not in done]
    random.Random(a.seed).shuffle(jobs)          # interleave conditions so server drift hits all equally
    jobs.sort(key=lambda j: j[2])                # finish every task x condition of one repeat before the next
    meta = {"taskfile": a.taskfile, "model": os.environ["LLM_MODEL"], "extra": extra, "gap": os.getenv("LLM_GAP", "0"), "split": a.split, "conds": a.conds, "rep": a.rep,
            "tasks": [t["id"] for t in chosen], "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(jobs)} runs to do ({len(done)} already done)")
    lock = threading.Lock()
    with cf.ThreadPoolExecutor(a.workers) as pool, done_path.open("a", encoding="utf-8") as f:
        futs = {pool.submit(run_one, client, t, c, r, out): (t["id"], c, r) for t, c, r in jobs}
        for i, fut in enumerate(cf.as_completed(futs), 1):
            r = fut.result()
            with lock:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
            print(f"[{i}/{len(jobs)}] {r['task']:10} {r['cond']:10} rep{r['rep']} "
                  f"{'PASS' if r['pass'] else 'fail'} turns={r['turns']} {r['seconds']}s {r['error'] or ''}")
    cmd_report(a)


# ---------------------------------------------------------------- statistics

def binom_two_sided(k, n):
    """Exact sign test p-value for k successes out of n at p=0.5."""
    if n == 0:
        return 1.0
    from math import comb
    tail = sum(comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired(rows, a, b, seed=0, iters=10000):
    """Task-level paired comparison of condition b against a."""
    by = {}
    for r in rows:
        by.setdefault(r["task"], {}).setdefault(r["cond"], []).append(r["pass"])
    tasks = [t for t, c in by.items() if a in c and b in c]
    diffs = [statistics.mean(by[t][b]) - statistics.mean(by[t][a]) for t in tasks]
    if not diffs:
        return None
    rnd = random.Random(seed)
    boots = sorted(statistics.mean(rnd.choice(diffs) for _ in diffs) for _ in range(iters))
    wins, losses = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    # run-level McNemar on (task, rep) pairs, as a second view
    ra = {(r["task"], r["rep"]): r["pass"] for r in rows if r["cond"] == a}
    rb = {(r["task"], r["rep"]): r["pass"] for r in rows if r["cond"] == b}
    keys = ra.keys() & rb.keys()
    only_b = sum(rb[k] and not ra[k] for k in keys)
    only_a = sum(ra[k] and not rb[k] for k in keys)
    return {"tasks": len(tasks), "diff": statistics.mean(diffs), "ci95": (boots[int(.025 * iters)], boots[int(.975 * iters)]),
            "task_wins": wins, "task_losses": losses, "sign_p": binom_two_sided(wins, wins + losses),
            "run_only_b": only_b, "run_only_a": only_a, "mcnemar_p": binom_two_sided(only_b, only_b + only_a)}


def cmd_report(a):
    out = Path(a.out)
    allrows = [json.loads(l) for l in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    reps = getattr(a, "reps", 0)
    if reps:                                  # balanced view: only repeats 0..reps-1, only tasks done in every condition
        allrows = [r for r in allrows if r["rep"] < reps]
        conds_all = {r["cond"] for r in allrows}
        have = {}
        for r in allrows:
            if not infra(r):
                have.setdefault((r["task"], r["rep"]), set()).add(r["cond"])
        allrows = [r for r in allrows if have.get((r["task"], r["rep"])) == conds_all]
    rows = [r for r in allrows if not infra(r)]
    lost = len(allrows) - len(rows)
    conds = sorted({r["cond"] for r in rows}, key=lambda c: (c != "B", c != "C", c != "H", c))
    domains = sorted({r["domain"] for r in rows})
    lines = []
    hdr = f"{'cond':10} {'pass':>7} {'pass^k':>7} " + " ".join(f"{d:>6}" for d in domains) + f" {'turns':>6} {'ktok':>6} {'sec':>6} {'errors':>7}"
    lines.append(hdr)
    for c in conds:
        rs = [r for r in rows if r["cond"] == c]
        by_task = {}
        for r in rs:
            by_task.setdefault(r["task"], []).append(r["pass"])
        pk = statistics.mean(all(v) for v in by_task.values())
        dom = " ".join(f"{statistics.mean(r['pass'] for r in rs if r['domain'] == d):6.0%}" if any(r['domain'] == d for r in rs) else "     -" for d in domains)
        lines.append(f"{c:10} {statistics.mean(r['pass'] for r in rs):7.1%} {pk:7.1%} {dom} "
                     f"{statistics.mean(r['turns'] for r in rs):6.1f} "
                     f"{statistics.mean(sum((r.get('tokens') or {}).values()) for r in rs) / 1000:6.1f} "
                     f"{statistics.mean(r['seconds'] for r in rs):6.1f} "
                     f"{sum(1 for r in rs if r['error']):7}")
    lines.append("")
    order = ("B", "P", "C", "H", "R", "RH")    # each condition is compared with every earlier base present
    for b in conds:
        for base in order:
            if b == base or base not in conds or (b in order and order.index(b) <= order.index(base)):
                continue
            p = paired(rows, base, b)
            if p:
                lines.append(f"{b} vs {base}: {p['diff']:+.1%} (95% CI {p['ci95'][0]:+.1%} .. {p['ci95'][1]:+.1%}), "
                             f"tasks better/worse {p['task_wins']}/{p['task_losses']} sign p={p['sign_p']:.3f}; "
                             f"runs only-{b}/only-{base} {p['run_only_b']}/{p['run_only_a']} McNemar p={p['mcnemar_p']:.3f}")
    ev = {}
    for r in rows:
        for e in r["events"]:
            ev.setdefault(r["cond"], {}).setdefault(e, 0)
            ev[r["cond"]][e] += 1
    lines.append("")
    for c in conds:
        if c in ev:
            lines.append(f"events {c}: " + ", ".join(f"{k}={v}" for k, v in sorted(ev[c].items())))
    if lost:
        lines.append(f"infra: {lost} runs lost to gateway/network errors, excluded; rerun the same command to retry them")
    errs = {}
    for r in allrows:
        if r["error"]:
            errs[(r["cond"], r["error"][:90])] = errs.get((r["cond"], r["error"][:90]), 0) + 1
    for (c, e), n in sorted(errs.items()):
        lines.append(f"error {c}: {e} x{n}")
    text = "\n".join(lines)
    (out / "report.txt").write_text(text + "\n", encoding="utf-8")
    print(text)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--split", default="eval")
    r.add_argument("--conds", default="B,C,H")
    r.add_argument("--rep", type=int, default=3)
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--tasks", default="")
    r.add_argument("--seed", type=int, default=7)
    r.add_argument("--taskfile", default="tasks", help="task module: tasks or tasks_gen")
    q = sub.add_parser("report")
    q.add_argument("--out", required=True)
    q.add_argument("--reps", type=int, default=0, help="only the first N repeats, paired across conditions")
    a = p.parse_args()
    cmd_run(a) if a.cmd == "run" else cmd_report(a)


if __name__ == "__main__":
    main()
