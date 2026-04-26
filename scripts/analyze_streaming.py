"""Read-out for a streaming-mode evolve run.

Usage:
    uv run python scripts/analyze_streaming.py results/<run_id>

Prints config, per-round summary, pass-criteria verdict, and headline
test numbers. Writes nothing — pure stdout. Mirrors what we'd want in
notebooks/streaming_<run>_analysis.ipynb later.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def fmt_pct(x: float) -> str:
    return f"{x * 100:5.1f}%" if isinstance(x, (int, float)) and x == x else "  nan"


def brief_edits(edit_batch: dict) -> str:
    ops = []
    for e in edit_batch.get("edits", []):
        op = e.get("op")
        name = e.get("name") or f"{e.get('from_')}->{e.get('to')}"
        ops.append(f"{op}({name})")
    return " | ".join(ops) if ops else "(no edits)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    args = ap.parse_args()

    run_dir = args.run_dir
    log_path = run_dir / "evolve_log.json"
    res_path = run_dir / "results.json"
    if not log_path.exists():
        print(f"FATAL: {log_path} not found", file=sys.stderr)
        return 1

    log = json.loads(log_path.read_text())
    res = json.loads(res_path.read_text()) if res_path.exists() else {}

    mode = log.get("mode", "legacy")
    cfg = log.get("config") or {}
    iters = log.get("iterations", [])
    best_val_acc = log.get("best_val_acc", -1.0)

    print(f"=== {run_dir.name} ===")
    print(f"mode={mode}")
    if mode != "streaming":
        print("WARNING: this analyzer expects mode=streaming.")
    print(f"config: {cfg}")
    print()

    # Per-round
    seed_acc = iters[0]["train_acc"] if iters else float("nan")
    print(f"{'round':>5} {'b_acc':>6} {'c_acc':>6} {'  Δpp':>6} {'verdict':>10} {'agents':>6} {'edges':>5} {'sec':>6}  edits")
    print(f"{'seed':>5} {fmt_pct(seed_acc):>6} {'-':>6} {'-':>6} {'-':>10} {iters[0]['n_agents']:>6} {iters[0]['n_edges']:>5} {'-':>6}  -")
    n_accepted = 0
    n_invalid = 0
    n_noop = 0
    for it in iters[1:]:
        b = it["train_acc"]; c = it["val_acc"]
        delta = (c - b) * 100 if c == c else float("nan")
        verdict = "ACCEPTED" if it["accepted"] else "rejected"
        if it["accepted"]:
            n_accepted += 1
        if it.get("is_noop"):
            n_noop += 1
        if c != c:  # nan = invalid edits or controller error
            n_invalid += 1
            verdict = "INVALID"
        print(f"{it['iteration']:>5} {fmt_pct(b):>6} {fmt_pct(c):>6} {delta:>6.1f} {verdict:>10} "
              f"{it['n_agents']:>6} {it['n_edges']:>5} {it['elapsed_s']:>6.0f}  {brief_edits(it['edit_batch'])}")
    print()

    # Pass criteria (roadmap §5.1):
    #   1. at least one round has c_acc > b_acc (any accept fires)
    #   2. best_val_acc strictly improves over seed batch acc
    crit1 = n_accepted > 0
    crit2 = best_val_acc > seed_acc
    print(f"pass criteria:")
    print(f"  (1) any round c_acc > b_acc?            {crit1}  (n_accepted={n_accepted})")
    print(f"  (2) best_val_acc > seed_batch_acc?      {crit2}  ({fmt_pct(best_val_acc)} vs seed {fmt_pct(seed_acc)})")
    print(f"  → overall PASS={crit1 and crit2}")
    print()

    # Operational stats
    total_worker = sum(it.get("worker_tokens", 0) for it in iters)
    total_controller = sum(it.get("controller_tokens", 0) for it in iters)
    total_wall_min = sum(it.get("elapsed_s", 0) for it in iters) / 60
    print(f"operational:  rounds={len(iters)-1}  invalid={n_invalid}  noop={n_noop}  "
          f"worker_tokens={total_worker:,}  controller_tokens={total_controller:,}  evolve_wall={total_wall_min:.1f} min")
    print()

    # Best graph composition
    bg = log.get("best_graph") or {}
    if bg:
        agents = list(bg.get("agents", {}).keys())
        edges = bg.get("edges", [])
        print(f"best_graph: {len(agents)} agents = {agents}")
        print(f"            {len(edges)} edges")

    # Headline test
    if "test" in res:
        print()
        print("=== held-out test ===")
        for k in ("cot", "planner_executor", "evolved"):
            t = res["test"].get(k, {})
            if t:
                print(f"  {k:>17} = {fmt_pct(t['accuracy'])}  tokens={t.get('tokens', 0):,}")
        # Simple Δ
        ev = res["test"].get("evolved", {}).get("accuracy")
        cot = res["test"].get("cot", {}).get("accuracy")
        pe = res["test"].get("planner_executor", {}).get("accuracy")
        if ev is not None and cot is not None and pe is not None:
            best_baseline = max(cot, pe)
            print(f"  Δ(evolved - best_baseline) = {(ev - best_baseline) * 100:+.1f}pp")

    return 0


if __name__ == "__main__":
    sys.exit(main())
