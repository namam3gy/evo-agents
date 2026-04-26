from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

from tqdm import tqdm

from .controller import (
    Outcome,
    aggregate_final,
    aggregate_mid,
    eval_sample,
    propose_edits,
)
from .datasets import Task
from .graph import GraphEditError, apply_edits, describe
from .llm import LLMClient
from .orchestrator import run_graph, run_graph_v3
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
    is_noop: bool = False


@dataclass
class EvolveLog:
    iterations: list[IterationLog] = field(default_factory=list)
    best_graph: dict | None = None
    best_val_acc: float = -1.0
    mode: str = "legacy"  # "legacy" (full train→ctrl→full val) or "streaming" (mini-batch)
    config: dict | None = None  # mode-specific run config (batch_size, max_rounds, …)


def _evaluate(graph: Graph, tasks: list[Task], llm: LLMClient) -> tuple[float, list[Outcome]]:
    outcomes: list[Outcome] = []
    for t in tasks:
        tape = run_graph(graph, t, llm)
        c = score(tape.final, t, llm)
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
    accept_slack: float = 0.0,
    prior_window: int = 3,
    progress: bool = True,
    domain_brief: str | None = None,
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
            is_noop=False,
        )
    )

    pbar = tqdm(range(1, max_iters + 1), desc="evolve", disable=not progress)
    for it in pbar:
        t0 = time.time()
        pre_worker = llm.usage.total()

        train_acc, train_outcomes = _evaluate(best_graph, train, llm)
        pre_controller = llm.usage.total()

        try:
            edit_batch = propose_edits(
                llm,
                best_graph,
                train_outcomes,
                prior_edit_summaries[-prior_window:],
                domain_brief=domain_brief,
                max_agents=max_agents,
            )
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
                    is_noop=len(edit_batch.edits) == 0,
                )
            )
            prior_edit_summaries.append(f"iter{it} REJECTED: {_brief_edits(edit_batch)}")
            continue

        pre_eval = llm.usage.total()
        val_acc, _ = _evaluate(candidate, val, llm)
        worker_tokens = (pre_controller - pre_worker) + (llm.usage.total() - pre_eval)

        # Two accept policies:
        # - Opt-2 strict (default, accept_slack == 0): best_graph replaces only on a strict val
        #   improvement; best_val_acc always matches the stored graph.
        # - Opt-1 loose (accept_slack > 0): allow near-best candidates to replace best_graph for
        #   slack-tolerant exploration; best_val_acc tracks only the true maximum, so the two can
        #   drift apart. Kept behind the parameter so it stays available for ablations.
        if accept_slack > 0.0:
            accepted = val_acc >= best_val_acc - accept_slack
            replace_graph = accepted
            update_best_val = accepted and val_acc > best_val_acc
        else:
            accepted = val_acc > best_val_acc
            replace_graph = accepted
            update_best_val = accepted

        verdict = "ACCEPTED" if accepted else "rejected"
        pbar.write(
            f"[iter {it}] train={train_acc:.2%} val={val_acc:.2%} (prev_best={best_val_acc:.2%}) {verdict} | {_brief_edits(edit_batch)}"
        )
        if replace_graph:
            best_graph = candidate
        if update_best_val:
            best_val_acc = val_acc

        prior_edit_summaries.append(
            f"iter{it} {'ACCEPTED' if accepted else 'REJECTED'} val={val_acc:.2%}: {_brief_edits(edit_batch)}"
        )

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
                is_noop=len(edit_batch.edits) == 0,
            )
        )

    log.best_graph = best_graph.model_dump()
    log.best_val_acc = best_val_acc
    return best_graph, log


def evolve_streaming(
    seed_graph: Graph,
    stream_pool: list[Task],
    llm: LLMClient,
    max_rounds: int = 10,
    batch_size: int = 100,
    max_agents: int = 6,
    accept_epsilon: float = 0.0,
    prior_window: int = 3,
    progress: bool = True,
    domain_brief: str | None = None,
    seed: int = 0,
) -> tuple[Graph, EvolveLog]:
    """Mini-batch streaming evolve.

    Per round:
      1. Bootstrap-sample `batch_size` tasks from `stream_pool` (with
         replacement) — gives a fresh batch each round.
      2. Evaluate `best_graph` on the batch → `b_acc` + outcomes for the
         controller.
      3. Controller proposes edits from those outcomes.
      4. apply_edits → candidate. If invalid → REJECT (log + continue).
      5. Evaluate candidate on the SAME batch → `c_acc`. Paired comparison
         eliminates between-batch variance.
      6. Accept iff `c_acc > b_acc + accept_epsilon`. Replace best_graph.

    Compared to the legacy `evolve()`:
      - More rounds fit in the same wall (no full train sweep per round).
      - Paired same-batch comparison reduces single-shot vLLM noise that
        was rejecting most v2 architectural changes at n=30.
      - `IterationLog.train_acc` is overloaded as `best_on_batch` and
        `val_acc` as `cand_on_batch` — log consumers must look at
        `EvolveLog.mode == "streaming"` to interpret.
    """
    rng = random.Random(seed)
    if not stream_pool:
        raise ValueError("stream_pool is empty")

    log = EvolveLog(
        mode="streaming",
        config={
            "max_rounds": max_rounds,
            "batch_size": batch_size,
            "accept_epsilon": accept_epsilon,
            "stream_pool_size": len(stream_pool),
            "prior_window": prior_window,
            "seed": seed,
        },
    )
    best_graph = seed_graph
    best_acc_history: list[float] = []
    prior_edit_summaries: list[str] = []

    # Round 0 — seed batch (no controller call yet)
    init_worker_tokens = llm.usage.total()
    seed_batch = rng.choices(stream_pool, k=batch_size)
    seed_acc, _ = _evaluate(best_graph, seed_batch, llm)
    best_acc_history.append(seed_acc)
    log.iterations.append(
        IterationLog(
            iteration=0,
            train_acc=seed_acc,
            val_acc=seed_acc,  # in streaming, both are the seed-on-batch
            accepted=True,
            n_agents=len(best_graph.agents),
            n_edges=len(best_graph.edges),
            edit_batch={"rationale": "seed", "edits": []},
            worker_tokens=llm.usage.total() - init_worker_tokens,
            controller_tokens=0,
            elapsed_s=0.0,
            graph_snapshot=best_graph.model_dump(),
            is_noop=False,
        )
    )

    pbar = tqdm(range(1, max_rounds + 1), desc="stream-evolve", disable=not progress)
    for r in pbar:
        t0 = time.time()
        pre_worker = llm.usage.total()

        batch = rng.choices(stream_pool, k=batch_size)
        b_acc, b_outcomes = _evaluate(best_graph, batch, llm)
        pre_controller = llm.usage.total()

        try:
            edit_batch = propose_edits(
                llm,
                best_graph,
                b_outcomes,
                prior_edit_summaries[-prior_window:],
                domain_brief=domain_brief,
                max_agents=max_agents,
            )
        except Exception as e:
            pbar.write(f"[round {r}] controller error: {e}")
            log.iterations.append(
                IterationLog(
                    iteration=r,
                    train_acc=b_acc,
                    val_acc=float("nan"),
                    accepted=False,
                    n_agents=len(best_graph.agents),
                    n_edges=len(best_graph.edges),
                    edit_batch={"rationale": f"controller_error: {e}", "edits": []},
                    worker_tokens=pre_controller - pre_worker,
                    controller_tokens=0,
                    elapsed_s=time.time() - t0,
                    graph_snapshot=best_graph.model_dump(),
                    is_noop=True,
                )
            )
            best_acc_history.append(b_acc)
            continue
        controller_tokens = llm.usage.total() - pre_controller

        try:
            candidate = apply_edits(best_graph, edit_batch, max_agents=max_agents)
        except GraphEditError as e:
            pbar.write(f"[round {r}] invalid edit rejected: {e}")
            log.iterations.append(
                IterationLog(
                    iteration=r,
                    train_acc=b_acc,
                    val_acc=float("nan"),
                    accepted=False,
                    n_agents=len(best_graph.agents),
                    n_edges=len(best_graph.edges),
                    edit_batch=edit_batch.model_dump(),
                    worker_tokens=pre_controller - pre_worker,
                    controller_tokens=controller_tokens,
                    elapsed_s=time.time() - t0,
                    graph_snapshot=best_graph.model_dump(),
                    is_noop=len(edit_batch.edits) == 0,
                )
            )
            prior_edit_summaries.append(f"r{r} REJECTED (DAG): {_brief_edits(edit_batch)}")
            best_acc_history.append(b_acc)
            continue

        pre_eval = llm.usage.total()
        c_acc, _ = _evaluate(candidate, batch, llm)
        worker_tokens = (pre_controller - pre_worker) + (llm.usage.total() - pre_eval)

        # Paired strict-improvement accept (Opt-2 strict applied to same-batch comparison)
        accepted = c_acc > b_acc + accept_epsilon

        verdict = "ACCEPTED" if accepted else "rejected"
        pbar.write(
            f"[round {r}] best={b_acc:.2%} cand={c_acc:.2%} "
            f"(Δ={(c_acc - b_acc) * 100:+.1f}pp) {verdict} | {_brief_edits(edit_batch)}"
        )

        if accepted:
            best_graph = candidate
            best_acc_history.append(c_acc)
        else:
            best_acc_history.append(b_acc)

        prior_edit_summaries.append(
            f"r{r} {'ACCEPTED' if accepted else 'REJECTED'} cand={c_acc:.2%} "
            f"(vs best={b_acc:.2%}): {_brief_edits(edit_batch)}"
        )

        log.iterations.append(
            IterationLog(
                iteration=r,
                train_acc=b_acc,
                val_acc=c_acc,
                accepted=accepted,
                n_agents=len(candidate.agents),
                n_edges=len(candidate.edges),
                edit_batch=edit_batch.model_dump(),
                worker_tokens=worker_tokens,
                controller_tokens=controller_tokens,
                elapsed_s=time.time() - t0,
                graph_snapshot=best_graph.model_dump(),
                is_noop=len(edit_batch.edits) == 0,
            )
        )

    log.best_graph = best_graph.model_dump()
    log.best_val_acc = max(best_acc_history) if best_acc_history else -1.0
    return best_graph, log


def dump_log(log: EvolveLog, path: str) -> None:
    with open(path, "w") as f:
        json.dump(
            {
                "iterations": [i.__dict__ for i in log.iterations],
                "best_graph": log.best_graph,
                "best_val_acc": log.best_val_acc,
                "mode": log.mode,
                "config": log.config,
            },
            f,
            indent=2,
        )


def dump_graph(graph: Graph, path: str) -> None:
    with open(path, "w") as f:
        json.dump({"graph": graph.model_dump(), "describe": describe(graph)}, f, indent=2)


# ===========================================================================
# v3 — full train pass with sample-level eval + hierarchical aggregation
# ===========================================================================


def _evaluate_v3(graph: Graph, tasks: list[Task], llm: LLMClient) -> tuple[float, list[Outcome]]:
    """Same as _evaluate, but uses run_graph_v3 (transcript channel + Q&A)."""
    outcomes: list[Outcome] = []
    for t in tasks:
        tape = run_graph_v3(graph, t, llm)
        c = score(tape.final, t, llm)
        outcomes.append(Outcome(task=t, tape=tape, correct=c))
    acc = sum(o.correct for o in outcomes) / max(1, len(outcomes))
    return acc, outcomes


def _dump_iter_artifacts(
    iter_dir: Path,
    *,
    sample_evals: list[dict],
    mid_decisions: list[dict],
    final_edit: dict | None,
    train_eval: dict,
    evolve_state: dict,
) -> None:
    iter_dir.mkdir(parents=True, exist_ok=True)
    # evals.jsonl is appended live during the train pass; this final write is
    # idempotent and a complete record (overwrite).
    with open(iter_dir / "evals.jsonl", "w") as f:
        for ev in sample_evals:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    with open(iter_dir / "mid_decisions.json", "w") as f:
        json.dump(mid_decisions, f, indent=2, ensure_ascii=False)
    with open(iter_dir / "final_edit.json", "w") as f:
        json.dump(final_edit or {"rationale": "(no edit)", "edits": []},
                  f, indent=2, ensure_ascii=False)
    with open(iter_dir / "train_eval.json", "w") as f:
        json.dump(train_eval, f, indent=2)
    with open(iter_dir / "evolve_state.json", "w") as f:
        json.dump(evolve_state, f, indent=2, ensure_ascii=False)


def evolve_v3(
    seed_graph: Graph,
    train: list[Task],
    llm: LLMClient,
    *,
    max_iters: int = 10,
    max_agents: int = 10,
    max_edges: int = 50,
    domain_brief: str | None = None,
    out_dir: Path | None = None,
    progress: bool = True,
    seed: int = 0,
    group_size: int = 10,
) -> tuple[Graph, EvolveLog]:
    """v3 evolve mode — full train pass per iter with sample-level reflection.

    Per iter:
      1. Run best_graph on the FULL train set with run_graph_v3 (transcript
         channel + side-channel Q&A).
      2. Sample-level controller eval after each task (priority 0-100,
         suggested edits, target_aspect). Streamed to evals.jsonl live.
      3. Hierarchical aggregation: groups of `group_size` (default 10) →
         mid_decisions; then mids → final EditBatch.
      4. apply_edits → candidate (max_agents=10 hard, max_edges=50 soft).
      5. Run candidate on the SAME train set → train_acc(candidate).
      6. Accept iff train_acc(candidate) > train_acc(best). Strict.

    Per-iter artifacts dumped to `out_dir/iter_K/` (if out_dir given) so the
    user can `tail -f evals.jsonl` mid-run for live visibility.
    """
    if not train:
        raise ValueError("train set is empty")

    log = EvolveLog(
        mode="v3",
        config={
            "max_iters": max_iters,
            "max_agents": max_agents,
            "max_edges": max_edges,
            "n_train": len(train),
            "group_size": group_size,
            "seed": seed,
        },
    )

    best_graph = seed_graph

    # --- Iter 0: seed baseline on the train set (no controller call) ---
    init_worker_tokens = llm.usage.total()
    t0 = time.time()
    seed_acc, _ = _evaluate_v3(best_graph, train, llm)
    log.iterations.append(
        IterationLog(
            iteration=0,
            train_acc=seed_acc,
            val_acc=seed_acc,  # no separate val in v3 — accept rule is on train
            accepted=True,
            n_agents=len(best_graph.agents),
            n_edges=len(best_graph.edges),
            edit_batch={"rationale": "seed", "edits": []},
            worker_tokens=llm.usage.total() - init_worker_tokens,
            controller_tokens=0,
            elapsed_s=time.time() - t0,
            graph_snapshot=best_graph.model_dump(),
            is_noop=False,
        )
    )
    if out_dir is not None:
        _dump_iter_artifacts(
            out_dir / "iter_0",
            sample_evals=[],
            mid_decisions=[],
            final_edit=None,
            train_eval={"best": {"acc": seed_acc, "n_correct": int(round(seed_acc * len(train))),
                                 "n_tasks": len(train)},
                        "candidate": None},
            evolve_state={"iter": 0, "best_graph": best_graph.model_dump(),
                          "accepted": True, "edits_applied": [], "verdict": "seed"},
        )
    if progress:
        print(f"[evolve_v3] iter 0 (seed) train_acc={seed_acc:.2%}")

    pbar = tqdm(range(1, max_iters + 1), desc="evolve_v3", disable=not progress)
    for k in pbar:
        iter_dir = (out_dir / f"iter_{k}") if out_dir is not None else None
        if iter_dir is not None:
            iter_dir.mkdir(parents=True, exist_ok=True)
            evals_jsonl_path = iter_dir / "evals.jsonl"
            # truncate at start of iter
            evals_jsonl_path.write_text("")

        t0 = time.time()
        pre_worker = llm.usage.total()

        # ----- Step 1+2: best train pass + per-sample eval -----
        sample_evals: list[dict] = []
        outcomes_best: list[Outcome] = []
        for t in train:
            tape = run_graph_v3(best_graph, t, llm)
            correct = score(tape.final, t, llm)
            outcomes_best.append(Outcome(task=t, tape=tape, correct=correct))
            ev = eval_sample(llm, best_graph, domain_brief, tape, correct)
            sample_evals.append(ev)
            if iter_dir is not None:
                with open(iter_dir / "evals.jsonl", "a") as f:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        train_acc_best = sum(o.correct for o in outcomes_best) / len(train)

        # ----- Step 3: hierarchical aggregation -----
        pre_controller = llm.usage.total()
        mid_decisions: list[dict] = []
        for i in range(0, len(sample_evals), group_size):
            group = sample_evals[i : i + group_size]
            if not group:
                continue
            mid = aggregate_mid(llm, best_graph, domain_brief, group)
            mid_decisions.append(mid)

        try:
            final_batch = aggregate_final(
                llm,
                best_graph,
                domain_brief,
                mid_decisions,
                max_agents=max_agents,
                max_edges=max_edges,
            )
        except Exception as e:
            pbar.write(f"[iter {k}] aggregate_final error: {e}")
            log.iterations.append(
                IterationLog(
                    iteration=k,
                    train_acc=train_acc_best,
                    val_acc=float("nan"),
                    accepted=False,
                    n_agents=len(best_graph.agents),
                    n_edges=len(best_graph.edges),
                    edit_batch={"rationale": f"aggregate_final error: {e}", "edits": []},
                    worker_tokens=pre_controller - pre_worker,
                    controller_tokens=llm.usage.total() - pre_controller,
                    elapsed_s=time.time() - t0,
                    graph_snapshot=best_graph.model_dump(),
                    is_noop=True,
                )
            )
            if iter_dir is not None:
                _dump_iter_artifacts(
                    iter_dir,
                    sample_evals=sample_evals,
                    mid_decisions=mid_decisions,
                    final_edit=None,
                    train_eval={"best": {"acc": train_acc_best,
                                         "n_correct": sum(o.correct for o in outcomes_best),
                                         "n_tasks": len(train)},
                                "candidate": None},
                    evolve_state={"iter": k, "best_graph": best_graph.model_dump(),
                                  "accepted": False, "edits_applied": [],
                                  "verdict": "AGG_ERROR"},
                )
            continue

        # ----- Step 4: apply edits → candidate -----
        try:
            candidate = apply_edits(best_graph, final_batch, max_agents=max_agents)
        except GraphEditError as e:
            pbar.write(f"[iter {k}] invalid edit rejected: {e}")
            log.iterations.append(
                IterationLog(
                    iteration=k,
                    train_acc=train_acc_best,
                    val_acc=float("nan"),
                    accepted=False,
                    n_agents=len(best_graph.agents),
                    n_edges=len(best_graph.edges),
                    edit_batch={"rationale": f"INVALID: {e}", "edits": [e.model_dump() for e in final_batch.edits]},
                    worker_tokens=pre_controller - pre_worker,
                    controller_tokens=llm.usage.total() - pre_controller,
                    elapsed_s=time.time() - t0,
                    graph_snapshot=best_graph.model_dump(),
                    is_noop=True,
                )
            )
            if iter_dir is not None:
                _dump_iter_artifacts(
                    iter_dir,
                    sample_evals=sample_evals,
                    mid_decisions=mid_decisions,
                    final_edit=final_batch.model_dump(),
                    train_eval={"best": {"acc": train_acc_best,
                                         "n_correct": sum(o.correct for o in outcomes_best),
                                         "n_tasks": len(train)},
                                "candidate": None},
                    evolve_state={"iter": k, "best_graph": best_graph.model_dump(),
                                  "accepted": False,
                                  "edits_applied": [e.model_dump() for e in final_batch.edits],
                                  "verdict": "INVALID"},
                )
            continue

        # ----- Step 5: candidate train pass -----
        outcomes_cand: list[Outcome] = []
        for t in train:
            tape = run_graph_v3(candidate, t, llm)
            correct = score(tape.final, t, llm)
            outcomes_cand.append(Outcome(task=t, tape=tape, correct=correct))
        train_acc_cand = sum(o.correct for o in outcomes_cand) / len(train)

        # ----- Step 6: accept rule (strict) -----
        accepted = train_acc_cand > train_acc_best
        if accepted:
            best_graph = candidate
        verdict = "ACCEPT" if accepted else "reject"

        elapsed = time.time() - t0
        worker_tokens = (pre_controller - pre_worker) + (llm.usage.total() - pre_controller)
        # rough: split tokens between worker & controller using pre_controller marker
        # (controller calls happen between pre_controller and end)
        controller_tokens = llm.usage.total() - pre_controller

        log.iterations.append(
            IterationLog(
                iteration=k,
                train_acc=train_acc_best,
                val_acc=train_acc_cand,
                accepted=accepted,
                n_agents=len(candidate.agents),
                n_edges=len(candidate.edges),
                edit_batch=final_batch.model_dump(),
                worker_tokens=pre_controller - pre_worker,
                controller_tokens=controller_tokens,
                elapsed_s=elapsed,
                graph_snapshot=(candidate if accepted else best_graph).model_dump(),
                is_noop=False,
            )
        )

        pbar.write(
            f"[iter {k}] best={train_acc_best:.2%} cand={train_acc_cand:.2%} "
            f"(Δ={(train_acc_cand - train_acc_best)*100:+.1f}pp) {verdict}"
        )

        if iter_dir is not None:
            _dump_iter_artifacts(
                iter_dir,
                sample_evals=sample_evals,
                mid_decisions=mid_decisions,
                final_edit=final_batch.model_dump(),
                train_eval={
                    "best": {"acc": train_acc_best,
                             "n_correct": sum(o.correct for o in outcomes_best),
                             "n_tasks": len(train)},
                    "candidate": {"acc": train_acc_cand,
                                  "n_correct": sum(o.correct for o in outcomes_cand),
                                  "n_tasks": len(train)},
                },
                evolve_state={
                    "iter": k,
                    "best_graph": best_graph.model_dump(),
                    "accepted": accepted,
                    "edits_applied": [e.model_dump() for e in final_batch.edits],
                    "verdict": verdict,
                },
            )

    log.best_graph = best_graph.model_dump()
    log.best_val_acc = max((it.train_acc for it in log.iterations), default=-1.0)
    return best_graph, log
