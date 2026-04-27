"""Re-eval the v3 sanity's evolved final graph on the same held-out test (n=30)
that already produced valid CoT (83.3%) and P-E (73.3%) numbers. The original
evolved_v3 result was 0% because vLLM died mid-run; this regenerates that
single column and merges into test_compare.json.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tqdm import tqdm

from src.datasets import load_benchmark
from src.llm import LLMClient
from src.orchestrator import run_graph
from src.score import score
from src.types import Graph


def main():
    sanity_dir = REPO / "results" / "sanity_v3_financebench_s0"
    blob = json.load(open(sanity_dir / "evolved_graph_final.json"))
    evolved = Graph.model_validate(blob["graph"] if "graph" in blob else blob)
    print(f"loaded evolved graph: {len(evolved.agents)} agents, {len(evolved.edges)} edges")

    _, _, test = load_benchmark("financebench", n_train=5, n_val=0, n_test=30, seed=0)
    print(f"loaded {len(test)} held-out test tasks (FinanceBench, seed=0, indices [5..35))")

    llm = LLMClient()
    print(f"LLM ready: model={llm.model} base_url={llm.base_url}")

    pre = llm.usage.total()
    correct = 0
    for t in tqdm(test, desc="evolved_v3/test", leave=False):
        tape = run_graph(evolved, t, llm)
        correct += score(tape.final, t, llm)
    out = {
        "name": "evolved_v3/test",
        "accuracy": correct / max(1, len(test)),
        "tokens": llm.usage.total() - pre,
        "n": len(test),
    }
    print(f"\nevolved_v3/test: acc={out['accuracy']*100:.1f}%  tokens={out['tokens']}  n={out['n']}")

    merged_path = sanity_dir / "test_compare.json"
    if merged_path.exists():
        merged = json.load(open(merged_path))
    else:
        merged = {}
    merged["evolved_v3"] = out
    with open(merged_path, "w") as f:
        json.dump(merged, f, indent=2)
    print(f"merged into {merged_path}")
    print("\n=== final 3-way comparison (FB held-out n=30) ===")
    for k in ("cot", "planner_executor", "evolved_v3"):
        v = merged.get(k)
        if v:
            print(f"  {k:20s} acc={v['accuracy']*100:5.1f}%  tokens={v['tokens']}")


if __name__ == "__main__":
    main()
