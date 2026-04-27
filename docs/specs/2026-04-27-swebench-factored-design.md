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

### 3.1 Two arms

**Reflection arm** (this project's contribution)
- Uses the v3 sample-level reflection / aggregator pipeline already in
  `src/controller.py` and `src/evolve.py::evolve_v3`.
- Output is restricted to `add_agent` / `remove_agent` / `rewrite_persona`.
  Edge edits emitted by reflection are **dropped**.
- Triggered every K iters (K=2 initially) — reflection is expensive,
  search is cheap.

**Edge search arm** (ADAS-style, narrowed)
- Input: current agent set `{a_1, …, a_n}`.
- Search space: subsets of `{(a_i, a_j) | i, j ∈ [START, a_1, …, a_n, END], i ≠ j}`
  with edge count ≤ `max_edges` (default 50).
- Acyclicity enforced; orphan auto-drop already exists in `apply_edits`.
- Algorithms — **each costs N train_acc evaluations × n_train tasks × per-task wall**:
  - `random`: sample B = 5–10 edge configs, evaluate train_acc on each, pick best.
  - `greedy`: start from current best edges, propose K candidate single-edge changes per step (K = 5–10), evaluate, accept best. Repeat ≤ 3 steps. **Not full greedy over all 64+ pairs** — that costs ~600 evals/iter (see §3.4).
- Both run every iter.

### 3.4 Cost reality check — non-negotiable

- **Train pass on SWE-bench-Lite is expensive**: 30 tasks × ~30–60 s/task (pytest dominated by warm pip install on cached venv; cold installs are 5–10× slower). Call it 25 min per train pass with venv cache, 4 h without.
- Naive full greedy edge search at n=8 agents would issue ~600 train-pass evals per iter → infeasible.
- Therefore the search algorithms above are **strictly bounded**: B ≤ 10 candidates per iter, K ≤ 10 per greedy step, ≤ 3 greedy steps. Hard cap = 30 train passes per iter ≈ 12.5 h per iter at warm cache, n_train=30.
- For first runs, drop `n_train` to **10**. That cuts iter wall to ~4 h. With 5 iters → ~20 h per evolve run, plus baselines.
- If even this is too slow, fall back to **LLM-as-edge-judge proxy** ("does this wiring make sense?" Y/N) for inner loop, with periodic spot-check eval on full train_acc every K iters. Trades exactness for tractability.

### 3.5 "그때그때" — interpretation
The user phrased the edge-wiring step as **"그때그때 연결"** (connect on the
fly). This is ambiguous between two designs:

- **(A) Offline per-iter search** *(this doc's current §3.1–3.3 reading)*: edge
  search picks one fixed wiring per iter, evaluates train_acc, accepts strict
  improvements. Same accept-rule structure as v3.
- **(B) Per-task dynamic routing**: at inference time on each task,
  a routing module picks edges based on the task content. No fixed graph;
  the graph *is* the router. This is closer to GPTSwarm + dynamic agent
  selection (e.g. Mixture-of-Agents).

The two are very different code paths. **Need user confirmation before
locking in §3.1.** Default assumption in this doc is (A) until told
otherwise.

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

## 6. Decisions for the user — **answer before P1 starts**

1. **Oracle-file vs tool-use (§2.2, framing-critical)** — Mode 1
   (oracle, fast, multi-role weak) or Mode 2 (tool-use, slow, multi-role
   strong)? The whole framing pivot rides on this.
2. **"그때그때" semantics (§3.5)** — offline per-iter edge search (A) or
   per-task dynamic routing (B)? Different code paths, different paper.
3. **Edge-search algorithm** — `random` only, `greedy` only, or both as
   an ablation? (Both adds ~2 days but supports a clean methodology
   table.)
4. **Reflection cadence K** — K=1 (every iter; current v3 default), K=2
   (every 2 iters; reflection cheaper this way), or K=∞ (reflection only
   at iter 0; pure edge search after — cleanest factored-only ablation)?
5. **ADAS joint baseline timing** — implement P5 in this sprint, or
   defer until factored numbers exist? Defer is cheaper but means the
   first paper draft can't include the comparison.
6. **Keep MEDIQ/FB/AC support** — recommended yes (multi-domain story).
   Drop only if you want to commit hard to a single-domain paper.
7. **First-pass scope** — n_train=10 / n_test=30 / max_iters=5 (cost-
   adapted; see §3.4 cost calc) is the realistic floor. n_train=30 only
   if P0 reveals very fast eval (< 10 s/task — unlikely).
8. **P0 gating threshold** — at what CoT accuracy do we abandon the
   pivot? Suggestion: **abort if CoT ≥ 70 % AND P-E ≥ 70 %** (no headroom),
   continue if at least one is ≤ 60 %. User to confirm.

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
