from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from tqdm import tqdm

from src.baselines import cot_graph, planner_executor_graph
from src.datasets import Task, load_benchmark
from src.evolve import dump_graph, dump_log, evolve
from src.graph import describe
from src.llm import LLMClient
from src.orchestrator import run_graph
from src.score import score
from src.types import Graph


@dataclass
class BenchResult:
    name: str
    accuracy: float
    tokens: int
    n: int


def bench(graph: Graph, tasks: list[Task], llm: LLMClient, desc: str) -> BenchResult:
    pre = llm.usage.total()
    correct = 0
    for t in tqdm(tasks, desc=desc, leave=False):
        tape = run_graph(graph, t, llm)
        correct += score(tape.final, t, llm)
    return BenchResult(name=desc, accuracy=correct / max(1, len(tasks)), tokens=llm.usage.total() - pre, n=len(tasks))


def plot_accuracy_vs_iter(log_path: Path, baselines: dict[str, float], out_path: Path) -> None:
    with open(log_path) as f:
        log = json.load(f)
    iters = [i["iteration"] for i in log["iterations"]]
    val = [i["val_acc"] for i in log["iterations"]]

    best_so_far = []
    b = -1.0
    for v in val:
        b = max(b, v)
        best_so_far.append(b)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(iters, val, "o-", label="Evolved (per-iter val)", color="#2b7bb9")
    ax.plot(iters, best_so_far, "--", label="Evolved (best-so-far)", color="#2b7bb9", alpha=0.5)
    for name, acc in baselines.items():
        ax.axhline(acc, linestyle=":", label=f"{name} = {acc:.2%}")
    ax.set_xlabel("Evolution iteration")
    ax.set_ylabel("Validation accuracy")
    ax.set_ylim(0, 1)
    ax.set_title("Reflection-driven evolution vs. baselines")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_arch_size(log_path: Path, out_path: Path) -> None:
    with open(log_path) as f:
        log = json.load(f)
    iters = [i["iteration"] for i in log["iterations"]]
    n_ag = [i["n_agents"] for i in log["iterations"]]
    n_ed = [i["n_edges"] for i in log["iterations"]]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(iters, n_ag, "o-", label="# agents", color="#d94e4e")
    ax.plot(iters, n_ed, "s--", label="# edges", color="#4ea34e")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Count")
    ax.set_title("Architecture complexity over iterations")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_edit_mix(log_path: Path, out_path: Path) -> None:
    with open(log_path) as f:
        log = json.load(f)
    counts: dict[str, int] = {}
    for it in log["iterations"]:
        for e in it["edit_batch"].get("edits", []):
            counts[e["op"]] = counts.get(e["op"], 0) + 1
    if not counts:
        return
    fig, ax = plt.subplots(figsize=(6, 4))
    keys = list(counts.keys())
    vals = [counts[k] for k in keys]
    ax.bar(keys, vals, color="#5a8fdb")
    ax.set_ylabel("Count across run")
    ax.set_title("Edit operation mix (controller behavior)")
    for i, v in enumerate(vals):
        ax.text(i, v, str(v), ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--benchmark",
        type=str,
        required=True,
        choices=["financebench", "mediq", "agentclinic"],
        help="Which benchmark dataset to load.",
    )
    parser.add_argument("--n-train", type=int, default=20)
    parser.add_argument("--n-val", type=int, default=10)
    parser.add_argument("--n-test", type=int, default=50)
    parser.add_argument("--max-iters", type=int, default=6)
    parser.add_argument("--max-agents", type=int, default=6)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--only-baselines", action="store_true")
    parser.add_argument("--run-name", type=str, default=None)
    args = parser.parse_args()

    run_id = args.run_name or time.strftime("run_%Y%m%d_%H%M%S")
    out_dir = REPO_ROOT / "results" / run_id
    (out_dir / "plots").mkdir(parents=True, exist_ok=True)

    print(
        f"[pilot] loading {args.benchmark} "
        f"({args.n_train}/{args.n_val}/{args.n_test}, seed={args.seed})"
    )
    train, val, test = load_benchmark(
        args.benchmark, args.n_train, args.n_val, args.n_test, seed=args.seed
    )

    llm = LLMClient()
    print(f"[pilot] model={llm.model} base_url={llm.base_url}")

    # Baselines
    results: dict[str, dict] = {}
    cot_g = cot_graph()
    pe_g = planner_executor_graph()

    print("[pilot] running baselines on val ...")
    b_cot_val = bench(cot_g, val, llm, "cot/val")
    b_pe_val = bench(pe_g, val, llm, "planner_executor/val")
    print(f"  CoT val      = {b_cot_val.accuracy:.2%} (tokens={b_cot_val.tokens})")
    print(f"  P-E val      = {b_pe_val.accuracy:.2%} (tokens={b_pe_val.tokens})")

    results["baselines_val"] = {
        "cot": b_cot_val.__dict__,
        "planner_executor": b_pe_val.__dict__,
    }

    if args.only_baselines:
        with open(out_dir / "results.json", "w") as f:
            json.dump(results, f, indent=2)
        print(f"[pilot] wrote {out_dir/'results.json'}")
        return 0

    # Evolution
    brief_path = REPO_ROOT / "data" / "briefs" / f"{args.benchmark}.md"
    domain_brief = brief_path.read_text() if brief_path.exists() else None
    if domain_brief:
        print(f"[pilot] loaded domain brief from {brief_path} ({len(domain_brief)} chars)")
    else:
        print(f"[pilot] no domain brief at {brief_path} — controller runs without brief")

    print(f"[pilot] evolving for up to {args.max_iters} iterations ...")
    best, evo_log = evolve(
        seed_graph=pe_g,
        train=train,
        val=val,
        llm=llm,
        max_iters=args.max_iters,
        max_agents=args.max_agents,
        domain_brief=domain_brief,
    )
    dump_log(evo_log, str(out_dir / "evolve_log.json"))
    dump_graph(best, str(out_dir / "evolved_graph_final.json"))
    print(f"[pilot] best val acc = {evo_log.best_val_acc:.2%}")
    print(f"[pilot] final graph:\n{describe(best)}")

    # Test-set evaluation of baselines + evolved
    print("[pilot] evaluating on held-out test ...")
    b_cot_test = bench(cot_g, test, llm, "cot/test")
    b_pe_test = bench(pe_g, test, llm, "planner_executor/test")
    b_evo_test = bench(best, test, llm, "evolved/test")
    print(f"  CoT test      = {b_cot_test.accuracy:.2%}")
    print(f"  P-E test      = {b_pe_test.accuracy:.2%}")
    print(f"  Evolved test  = {b_evo_test.accuracy:.2%}")

    results["test"] = {
        "cot": b_cot_test.__dict__,
        "planner_executor": b_pe_test.__dict__,
        "evolved": b_evo_test.__dict__,
    }
    results["best_val_acc"] = evo_log.best_val_acc

    with open(out_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)

    plot_accuracy_vs_iter(
        out_dir / "evolve_log.json",
        {"CoT (val)": b_cot_val.accuracy, "Planner-Executor (val)": b_pe_val.accuracy},
        out_dir / "plots" / "accuracy_vs_iter.png",
    )
    plot_arch_size(out_dir / "evolve_log.json", out_dir / "plots" / "arch_size.png")
    plot_edit_mix(out_dir / "evolve_log.json", out_dir / "plots" / "edit_mix.png")

    print(f"[pilot] artifacts at {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
