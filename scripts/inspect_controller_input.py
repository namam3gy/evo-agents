"""Reconstruct exactly what the controller sees in one round.

Runs the P-E seed graph on a tiny mediq batch (4 tasks), collects the
trajectory tapes, and prints:

  1. SYSTEM prompt (controller_v2, full)
  2. one full _summarize_tape output (so you can see the per-tape format)
  3. the full _build_user_prompt output that propose_edits() ships to the
     controller LLM (domain brief + Constraints + current graph + train acc
     + sampled trajectories + reminder).

Run via:
    uv run python scripts/inspect_controller_input.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.baselines import planner_executor_graph
from src.controller import (
    CONTROLLER_SYSTEM,
    Outcome,
    _build_user_prompt,
    _summarize_tape,
)
from src.datasets import load_benchmark
from src.llm import LLMClient
from src.orchestrator import run_graph
from src.score import score


SEP = "=" * 78


def main() -> int:
    print(f"{SEP}\nLoading 4 MEDIQ train tasks (seed=0)\n{SEP}")
    train, _val, _test = load_benchmark("mediq", n_train=4, n_val=0, n_test=0, seed=0)
    print(f"loaded {len(train)} tasks")

    print(f"\n{SEP}\nBuilding P-E seed graph + running 4 worker passes\n{SEP}")
    g = planner_executor_graph()
    llm = LLMClient()
    print(f"model={llm.model} base_url={llm.base_url}")

    outcomes: list[Outcome] = []
    for i, t in enumerate(train, 1):
        tape = run_graph(g, t, llm)
        correct = score(tape.final, t, llm)
        outcomes.append(Outcome(task=t, tape=tape, correct=correct))
        print(f"  task {i}: id={t.task_id} correct={bool(correct)}")
    n_correct = sum(o.correct for o in outcomes)
    print(f"acc={n_correct}/{len(outcomes)}")

    print(f"\n\n{SEP}\nPART 1 — SYSTEM PROMPT (controller_v2, full)\n{SEP}\n")
    print(CONTROLLER_SYSTEM)

    print(f"\n\n{SEP}\nPART 2 — ONE _summarize_tape OUTPUT (per-tape format)\n{SEP}\n")
    print(_summarize_tape(outcomes[0].tape, outcomes[0].correct))

    print(f"\n\n{SEP}\nPART 3 — FULL CONTROLLER USER PROMPT (one round)\n{SEP}\n")
    brief = (REPO_ROOT / "data" / "briefs" / "mediq.md").read_text()
    user = _build_user_prompt(
        g, outcomes,
        prior_edits=[],
        domain_brief=brief,
        max_agents=8,
    )
    print(user)
    return 0


if __name__ == "__main__":
    sys.exit(main())
