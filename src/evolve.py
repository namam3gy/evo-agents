from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from tqdm import tqdm

from .controller import Outcome, propose_edits
from .datasets import Task
from .graph import GraphEditError, apply_edits, describe
from .llm import LLMClient
from .orchestrator import run_graph
from .score import score
from .types import EditBatch, Graph, Tape


@dataclass
class IterationLog:
    iteration: int
    train_acc: float
    val_acc: float
    accepted: bool
    n_agents: int
    n_edges: int
    edit_batch: dict
    worker_tokens: int
    controller_tokens: int
    elapsed_s: float
    graph_snapshot: dict


@dataclass
class EvolveLog:
    iterations: list[IterationLog] = field(default_factory=list)
    best_graph: dict | None = None
    best_val_acc: float = -1.0


def _evaluate(graph: Graph, tasks: list[Task], llm: LLMClient) -> tuple[float, list[Outcome]]:
    outcomes: list[Outcome] = []
    for t in tasks:
        tape = run_graph(graph, t, llm)
        c = score(tape.final, t.answer)
        outcomes.append(Outcome(task=t, tape=tape, correct=c))
    acc = sum(o.correct for o in outcomes) / max(1, len(outcomes))
    return acc, outcomes


def _brief_edits(eb: EditBatch) -> str:
    ops = []
    for e in eb.edits:
        if e.op in ("add_agent", "remove_agent", "rewrite_persona"):
            ops.append(f"{e.op}({e.name})")
        else:
            ops.append(f"{e.op}({e.from_}->{e.to})")
    return f"[{' | '.join(ops)}] rationale={eb.rationale[:180]}"


def evolve(
    seed_graph: Graph,
    train: list[Task],
    val: list[Task],
    llm: LLMClient,
    max_iters: int = 6,
    max_agents: int = 6,
    accept_slack: float = 0.02,
    prior_window: int = 3,
    progress: bool = True,
) -> tuple[Graph, EvolveLog]:
    log = EvolveLog()
    best_graph = seed_graph
    best_val_acc = -1.0
    prior_edit_summaries: list[str] = []

    init_worker_tokens = llm.usage.total()
    val_acc0, _ = _evaluate(best_graph, val, llm)
    best_val_acc = val_acc0
    log.iterations.append(
        IterationLog(
            iteration=0,
            train_acc=float("nan"),
            val_acc=val_acc0,
            accepted=True,
            n_agents=len(best_graph.agents),
            n_edges=len(best_graph.edges),
            edit_batch={"rationale": "seed", "edits": []},
            worker_tokens=llm.usage.total() - init_worker_tokens,
            controller_tokens=0,
            elapsed_s=0.0,
            graph_snapshot=best_graph.model_dump(),
        )
    )

    pbar = tqdm(range(1, max_iters + 1), desc="evolve", disable=not progress)
    for it in pbar:
        t0 = time.time()
        pre_worker = llm.usage.total()

        train_acc, train_outcomes = _evaluate(best_graph, train, llm)
        pre_controller = llm.usage.total()

        try:
            edit_batch = propose_edits(llm, best_graph, train_outcomes, prior_edit_summaries[-prior_window:])
        except Exception as e:
            pbar.write(f"[iter {it}] controller error: {e}")
            continue
        controller_tokens = llm.usage.total() - pre_controller

        try:
            candidate = apply_edits(best_graph, edit_batch, max_agents=max_agents)
        except GraphEditError as e:
            pbar.write(f"[iter {it}] invalid edit rejected: {e}")
            log.iterations.append(
                IterationLog(
                    iteration=it,
                    train_acc=train_acc,
                    val_acc=best_val_acc,
                    accepted=False,
                    n_agents=len(best_graph.agents),
                    n_edges=len(best_graph.edges),
                    edit_batch=edit_batch.model_dump(),
                    worker_tokens=pre_controller - pre_worker,
                    controller_tokens=controller_tokens,
                    elapsed_s=time.time() - t0,
                    graph_snapshot=best_graph.model_dump(),
                )
            )
            prior_edit_summaries.append(f"iter{it} REJECTED: {_brief_edits(edit_batch)}")
            continue

        pre_eval = llm.usage.total()
        val_acc, _ = _evaluate(candidate, val, llm)
        worker_tokens = (pre_controller - pre_worker) + (llm.usage.total() - pre_eval)

        accepted = val_acc >= best_val_acc - accept_slack
        verdict = "ACCEPTED" if accepted else "rejected"
        pbar.write(
            f"[iter {it}] train={train_acc:.2%} val={val_acc:.2%} (prev_best={best_val_acc:.2%}) {verdict} | {_brief_edits(edit_batch)}"
        )
        if accepted:
            best_graph = candidate
            if val_acc > best_val_acc:
                best_val_acc = val_acc
            prior_edit_summaries.append(f"iter{it} ACCEPTED val={val_acc:.2%}: {_brief_edits(edit_batch)}")
        else:
            prior_edit_summaries.append(f"iter{it} REJECTED val={val_acc:.2%}: {_brief_edits(edit_batch)}")

        log.iterations.append(
            IterationLog(
                iteration=it,
                train_acc=train_acc,
                val_acc=val_acc,
                accepted=accepted,
                n_agents=len(candidate.agents),
                n_edges=len(candidate.edges),
                edit_batch=edit_batch.model_dump(),
                worker_tokens=worker_tokens,
                controller_tokens=controller_tokens,
                elapsed_s=time.time() - t0,
                graph_snapshot=best_graph.model_dump(),
            )
        )

    log.best_graph = best_graph.model_dump()
    log.best_val_acc = best_val_acc
    return best_graph, log


def dump_log(log: EvolveLog, path: str) -> None:
    with open(path, "w") as f:
        json.dump(
            {
                "iterations": [i.__dict__ for i in log.iterations],
                "best_graph": log.best_graph,
                "best_val_acc": log.best_val_acc,
            },
            f,
            indent=2,
        )


def dump_graph(graph: Graph, path: str) -> None:
    with open(path, "w") as f:
        json.dump({"graph": graph.model_dump(), "describe": describe(graph)}, f, indent=2)
