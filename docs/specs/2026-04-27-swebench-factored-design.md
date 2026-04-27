# SWE-bench-Lite + factored search — design doc

Status: **draft, awaiting user review**
Date: 2026-04-27

## 1. Goal

Pivot the pilot's empirical center of gravity from MCQ / Q&A benchmarks
(MEDIQ / FinanceBench / AgentClinic) to **SWE-bench-Lite**, and introduce
a **factored controller**: reflection generates agents (personas), an
ADAS-style search wires edges between existing agents.

Both moves are driven by the framing pivot recorded in
`memory/project_framing.md`:

- Multi-role *justification* must come from the task. SWE-bench-Lite has
  natural reader / locator / patch-writer / test-checker roles.
- Reward must be programmatic (no human labels at evolve time). pytest
  pass/fail is the canonical example.
- Search is no longer dirty word; it's a tool that fits one of the two
  factored sub-problems (combinatorial edge wiring), while reflection
  remains the right tool for the other (knowledge-bound persona
  authoring).

## 2. SWE-bench-Lite — scope and evaluation

### 2.1 Dataset
- Source: HF `princeton-nlp/SWE-bench_Lite` (300 instances).
- First-pass subset: **30 instances** (seed=0, deterministic shuffle) for
  tractable evolve cycles. Held-out test set: **30 different instances**.
- Each instance: `instance_id`, `repo`, `base_commit`, `problem_statement`,
  `hints_text`, `FAIL_TO_PASS`, `PASS_TO_PASS`, `gold` patch.

### 2.2 Task input — **mode choice has framing implications**
- **Mode 1 — oracle-file (cheaper)**: hand the agent graph the file(s)
  named in the gold patch + relevant test snippet. Pros: trivial to
  implement, fast eval. **Cons: collapses reader / locator roles** — the
  multi-role story SWE-bench was supposed to provide weakens to
  "read snippet, write patch" (1–2 agents max).
- **Mode 2 — full-codebase + grep/read tools**: agents have a `read_file`
  / `search_codebase` tool. Pros: preserves multi-role justification
  (reader + locator + writer + tester). Cons: 1–2 weeks of tool-use
  infra (the project currently has no tool-use abstraction); patches
  may explode in token cost as agents read many files.
- **The two cannot be combined cleanly.** Oracle-mode kills the framing;
  tool-use mode adds significant scope. **User decision required.**
- Default in this doc: assume the user picks Mode 1 for first pass + a
  later upgrade to Mode 2; flag this as a critical decision in §6.

### 2.3 Evaluation harness (no Docker, K8s pod compatible)
- Per task:
  1. `git clone <repo> ; git checkout <base_commit>` into a scratch dir (cache by `(repo, base_commit)`)
  2. `uv venv .venv-task && uv pip install -e <repo>` (cache **per `(repo, base_commit)`** — same install reused across all candidate patches; pip install dominates wall time, so this cache is load-bearing, not optional)
  3. Apply the agent's patch via `git apply` (catch errors)
  4. Run `pytest -x <FAIL_TO_PASS + PASS_TO_PASS>` with timeout 60 s
  5. Score: 1 if all FAIL_TO_PASS pass AND all PASS_TO_PASS still pass; 0 otherwise
  6. `git stash` patch + venv left intact for next eval
- Implementation: separate module `src/swebench_eval.py`. Cache repo
  checkouts and venvs under `data/swebench_envs/<repo>/<base_commit>/`. Parallelize
  across CPU only (vLLM is GPU-bound, eval is CPU-bound, so they don't fight).
- **No reliance on the official SWE-bench Docker harness** — we re-implement
  the minimal pass/fail check.

### 2.3.1 Subset selection — install-complexity filter (REQUIRED, not optional)
SWE-bench-Lite repos vary wildly in install complexity. Without Docker,
some break outright. Hard-allowlist for first pass:

| Repo | Status | Install |
|---|---|---|
| `sympy/sympy` | OK | pure Python |
| `pallets/flask` | OK | pure Python |
| `psf/requests` | OK | pure Python |
| `pytest-dev/pytest` | OK | pure Python |
| `marshmallow-code/marshmallow` | OK | pure Python |
| `Pylons/pyramid` | OK | pure Python |
| `django/django` | **avoid** — needs PostgreSQL/SQLite-config |
| `sphinx-doc/sphinx` | **avoid** — C deps |
| `pylint-dev/pylint` | risky — heavy AST machinery |
| `astropy/astropy` | **avoid** — Fortran/C |
| `scikit-learn/scikit-learn` | risky — Cython, large build |

Filter SWE-bench-Lite to the OK rows, *then* sample 30 train + 30 test.
Estimated remaining instance count after filter: ~140–180 of 300.

### 2.4 Sandbox safety
- Patches run arbitrary code via pytest, including the candidate's mistakes.
- Mitigation: per-task scratch dir under `/tmp/swebench-scratch/<task_id>/`,
  hard wall-clock timeout, RLIMIT_AS, no network access in eval venv (`pip
  install --no-deps` after initial setup).

## 3. Factored controller architecture

### 3.1 Single-iter, two-stage flow (alternation rejected by user 2026-04-27)

The first draft alternated reflection and edge search across iters with a
cadence parameter `K`. The user pointed out that splitting iters this way
is awkward — each iter only changes one aspect but evaluation cost is paid
twice. **Both stages now run inside every iter**, sharing the train pass.

**Stage 1 — reflection (persona authoring)**
- Uses the v3 sample-level reflection / aggregator pipeline already in
  `src/controller.py` and `src/evolve.py::evolve_v3`.
- Output is *constrained* to `add_agent` / `remove_agent` /
  `rewrite_persona`. Edge edits emitted at this stage are **dropped**.
- Prompt focus: "given these failure traces, what specialist is missing?"

**Stage 2 — edge controller (per Q4 (b))**
- LLM controller given the post-Stage-1 agent set + the same train tapes
  emits **B candidate edge configurations** in natural language
  (typically B = 3–5).
- No explicit `random` / `greedy` enumeration — the LLM acts as the
  proposal distribution. Cheap (one LLM call) and aligned with ADAS-style
  meta-prompting.
- Prompt focus: "given these specialists, how should information flow
  between them to handle the failure traces above?"
- All B candidates evaluated on the train set, best by `train_acc`
  selected.

### 3.2 Outer loop
```python
graph = seed (planner-executor)
for iter in 1..max_iters:
    # 1. Current-graph train pass → tapes + train_acc
    tapes, acc_current = train_pass(graph, train)

    # 2. Stage 1 (reflection) — persona edits only
    persona_edits = controller.propose_persona_edits(tapes, brief)
    graph_with_personas = apply_persona_edits(graph, persona_edits)

    # 3. Stage 2 (edge controller, Q4 (b)) — B candidate edge configs
    edge_candidates = controller.propose_edge_candidates(
        graph_with_personas, tapes, B=5,
    )
    candidates = [apply_edges(graph_with_personas, e) for e in edge_candidates]

    # 4. Evaluate every candidate on the train set
    accs = [train_pass(c, train)[1] for c in candidates]
    best_c, best_acc = argmax(accs)

    # 5. Accept rule (strict, programmatic — pytest pass/fail for SWE-bench)
    if best_acc > acc_current:
        graph = best_c
```

Cost per iter: `1 + B` train passes. With `B=5` and `n_train=10`: 60
task evals/iter. SWE-bench at ~30 s/task (warm venv) → ~30 min/iter.
5 iters → ~2.5 h per evolve run. Tractable.

### 3.3 Cost reality check
- Train pass on SWE-bench-Lite: 10 tasks × ~30 s (warm venv cache; pip install dominates cold runs at 5–10×).
- Per iter: `1 + B` = 6 train passes × 10 tasks × 30 s = **30 min**.
- 5 iters = **2.5 h / evolve run**.
- Tractable. The earlier ~300 h estimate assumed naive full greedy; user-confirmed Q4 (b) replaces that with controller-emitted B=5 candidates, which is the load-bearing change.
- If a single SWE-bench task pytest stalls (slow tests, hung process), per-task timeout 90 s; fail = score 0.

### 3.4 Resolved: "그때그때" semantics
**(A) Offline per-iter search** — confirmed by user 2026-04-27. ADAS-family
standard (ADAS / AFlow / GPTSwarm / MaAS all use offline-fixed topology
applied identically at inference). (B) per-task dynamic routing is
characteristic of Mixture-of-Agents, not the ADAS lineage we want to
compare against.

### 3.2 Outer loop
```
graph = seed (planner-executor)
for iter in 1..max_iters:
    if iter % K == 0:
        # Reflection arm: maybe add/remove an agent
        sample_evals = run_train_pass_with_eval(graph)
        edits = aggregate_to_persona_edits(sample_evals)
        graph_with_new_agents = apply_persona_edits(graph, edits)
    else:
        graph_with_new_agents = graph

    # Edge search arm: rewire
    candidates = edge_search(graph_with_new_agents, train, algo='greedy')
    best_candidate = max(candidates, key=lambda g: train_acc(g, train))

    # Accept rule (programmatic, label-free for SWE-bench)
    if train_acc(best_candidate, train) > train_acc(graph, train):
        graph = best_candidate
```

### 3.3 ADAS-comparable joint baseline
- Same wall-clock budget as factored.
- Single LLM meta-prompter searches over both agents AND edges in one shot
  (mirrors ADAS Eq. 1).
- Implementation: a v4 mode in `controller.py` that emits unrestricted
  `EditBatch` (current v3 behavior, but driven by ADAS-style meta-search
  loop with N candidates per generation).
- Used **only for comparison** in §3 of the paper.

## 4. Code changes outline

| Module | Change |
|---|---|
| `src/datasets.py` | add `load_swebench_lite()` |
| `src/swebench_eval.py` (new) | per-task pytest sandbox |
| `src/score.py` | dispatcher gains `swebench_lite` → `score_swebench()` |
| `src/baselines.py` | CoT / P-E personas adapted (`patch-writer` flavored) |
| `src/controller.py` | factored mode flags: `propose_persona_edits()` (reflection arm), `propose_edge_search()` (search arm), `propose_joint()` (ADAS baseline) |
| `src/evolve.py` | `evolve_factored()` outer loop (§3.2) |
| `scripts/run_pilot.py` | `--mode factored` and `--edge-search-algo {random,greedy}`, `--reflection-every K` |
| `scripts/run_pilot.py` | `--benchmark swebench_lite` |
| `data/briefs/swebench_lite.md` | hand-authored brief (reader / locator / patch-writer specialty hints) |

## 5. Phasing

| Phase | What | ETA |
|---|---|---|
| **P0 (gating, 2–3 h)** | **CoT-alone on 30-instance subset.** If CoT ≥ 65–70 %, multi-agent headroom is too thin — abort the SWE-bench pivot before sinking 3 weeks. **Mandatory checkpoint before P1.** | tiny |
| **P1** (2–3 days) | SWE-bench dataset loader + venv eval harness with `(repo, base_commit)` cache; smoke-test on 3 instances with pe_g. Subset filter (§2.3.1). | small |
| **P2** (1–2 days) | CoT / P-E baselines on filtered SWE-bench-Lite n=30 + held-out 30 | small |
| **P3** (3–5 days) | Implement factored evolve loop; smoke on MEDIQ first (cheaper iter) | medium |
| **P4** (2–3 days) | Run factored on SWE-bench-Lite, compare to CoT / P-E | small |
| **P5** (3–5 days) | ADAS joint-search baseline; matched-budget Pareto curve | medium |
| **P6** (4–5 days) | Multi-seed (s ∈ {0, 1, 2}) on SWE-bench-Lite; write up | medium |

**Total: ~3 weeks** (revised up from initial 2-week estimate after
realistic eval-cost accounting in §3.4). Single-track most-realistic path
to a defensible EMNLP Findings / workshop paper. P2 and P3 are partially
parallelizable.

P0 is **load-bearing** — skipping it risks 2–3 weeks of work on a
saturated benchmark.

## 6. Decisions resolved (2026-04-27)

| # | Question | Answer |
|---|---|---|
| Q1 | oracle-file vs tool-use | **Mode 2 (tool-use)** — read_file / search_codebase abstraction required |
| Q2 | ADAS-family standard | (A) offline per-iter search — confirmed |
| Q3 | P0 gating before P1 | **Yes**, run CoT-alone gating first |
| Q4 | edge search algorithm | **(b)** controller LLM emits B natural-language edge candidates per iter; B=5 |
| Q5 | reflection cadence | K dropped — single-iter two-stage flow (reflection + edge controller in same iter) |
| Q6 | ADAS joint baseline | After CoT gating result is in (i.e. immediately after P0/P2, before P3-factored) |
| Q7 | keep MEDIQ/FB/AC | **Drop** — clean codebase, single-domain commit |
| Q8 | first-pass scope | n_train=10, n_test=30, max_iters=5 |

**Open**: P0 abort threshold. Default proposal: abort if CoT ≥ 70 % on
n=30. Fall back to HumanEval+ / MBPP+ subset if SWE-bench saturates.
User confirmation on this one is still pending.

## 7. Open risks

- **SWE-bench eval is slow per task** (clone + venv + pip install + pytest).
  Estimated 30–90 s per evaluation, dominated by pip install. Mitigation:
  cache `.venv-task` per repo, reuse across patches on same repo.
- **Patches that don't apply cleanly** — common failure mode. Score 0 for
  these (no partial credit). Frequency: in SWE-bench reports ~20–30 % of
  agent outputs fail to apply.
- **Factored may underperform joint at our small scale**. If yes, that's
  still a publishable negative result (workshop tier) — but should be
  framed correctly in the paper.
- **Multi-agent justification still needs to *demonstrably* beat
  single-agent on SWE-bench**. CoT might already saturate easy instances.
  Subset selection should preferentially include harder instances.
