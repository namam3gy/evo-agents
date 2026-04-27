"""Quick eval: load v3 FinanceBench sanity's final graph + run CoT / P-E / Evolved on held-out test."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tqdm import tqdm

from src.baselines import cot_graph, planner_executor_graph
from src.datasets import load_benchmark
from src.llm import LLMClient
from src.orchestrator import run_graph
from src.score import score
from src.types import Graph


def bench(graph, tasks, llm, desc):
    pre = llm.usage.total()
    correct = 0
    for t in tqdm(tasks, desc=desc, leave=False):
        tape = run_graph(graph, t, llm)
        correct += score(tape.final, t, llm)
    return {
        "name": desc,
        "accuracy": correct / max(1, len(tasks)),
        "tokens": llm.usage.total() - pre,
        "n": len(tasks),
    }


def main():
    evolved_path = REPO / "results" / "sanity_v3_financebench_s0" / "evolved_graph_final.json"
    evolved = Graph.model_validate(json.load(open(evolved_path)))

    _, _, test = load_benchmark("financebench", n_train=5, n_val=0, n_test=30, seed=0)
    print(f"loaded {len(test)} held-out test tasks (FinanceBench, seed=0, indices [5..35))")

    llm = LLMClient()
    cot_g = cot_graph()
    pe_g = planner_executor_graph()

    out = {}
    out["cot"] = bench(cot_g, test, llm, "cot/test")
    out["planner_executor"] = bench(pe_g, test, llm, "pe/test")
    out["evolved_v3"] = bench(evolved, test, llm, "evolved_v3/test")

    print("\n=== FinanceBench v3 sanity — held-out test (n=30) ===")
    for k, v in out.items():
        print(f"  {k:20s} acc={v['accuracy']*100:5.1f}%  tokens={v['tokens']}")

    out_path = REPO / "results" / "sanity_v3_financebench_s0" / "test_compare.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
