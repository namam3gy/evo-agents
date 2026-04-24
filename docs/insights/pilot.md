# Pilot execution insights

Notes on things the `agent_orchestration` pilot revealed that weren't
visible from reading the code or docs alone.

---

## 1. Operational gotchas

### 1.1 vLLM 0.19.1 removed `--disable-log-requests`

The original `scripts/serve_vllm.sh` used `--disable-log-requests`, but
on 0.19.1 the server dies immediately with `unrecognized arguments`
(exit 2). The flag model switched to the
`--enable-log-requests | --no-enable-log-requests` pair.

- **Fix**: `--disable-log-requests` → `--no-enable-log-requests`.
- **Lesson**: vLLM breaks CLI flags even between minor versions. A
  cheap guard in the server script is a one-liner that prints
  `vllm --version` and greps `--help | grep log-requests` before
  launching.

### 1.2 Triton JIT fails at KV-cache init if the system has no C compiler

It was disorienting: model weights finished loading on GPU, all routes
were registered, and only then did it blow up inside
`determine_available_memory`. The real cause was buried at the bottom:

```
torch._inductor.exc.InductorError: RuntimeError: Failed to find C compiler.
Please specify via CC environment variable or set triton.knobs.build.impl.
```

Triton JIT-compiles `cuda_utils.c` at runtime; the container had
`gcc-12-base` (the runtime library) but no `gcc` (the compiler).

- **Fix**: `sudo apt-get install gcc`.
- **Lesson**: torch/vllm/triton wheels look self-contained, but
  **Triton alone requires a system C compiler**. A classic landmine on
  the first inference call in a bare container. Bake `gcc` into your
  `Dockerfile` / `setup.sh`.

### 1.3 On a shared GPU, `gpu-memory-utilization` must match actual free memory, not the 0.90 default

One H200 (143 GB) was already taken by two other processes holding
33 GB. At 0.90, vLLM tried to claim ~129 GB and crashed. Dropping to
0.55 was enough for the Qwen2.5-32B bf16 weights (~65 GB) plus the KV
cache.

- **Fix**: `EVO_GPU_UTIL=0.55 bash scripts/serve_vllm.sh`.
- **Lesson**: on a shared node, compute the util dynamically from
  `nvidia-smi --query-gpu=memory.free` just before launching
  `scripts/serve_vllm.sh`. The script currently relies on the user
  setting an env var, which is easy to forget.

---

## 2. Pipeline characteristics that only showed up under real runs

### 2.1 At 5 samples, CoT / P-E / Evolved all score 100%

Qwen2.5-32B is strong enough on GSM8K that 5-val / 5-test leaves zero
discriminative power across methods (see
`results/smoke_evolve/results.json`).

- **Lesson**: headline numbers require `--n-val` and `--n-test` in the
  **hundreds** at minimum. 5 samples is a smoke-check only — never
  cite those numbers as results.

### 2.2 The controller proposes meaningful edits even when val is already saturated

On iter 1 with val=100%, the controller still emitted:

- `add_agent(verifier)` + `add_edge(executor→verifier)` +
  `add_edge(verifier→END)`
- Rationale: *"The executor occasionally makes arithmetic mistakes,
  such as rounding inaccuracies. Introducing a verifier agent can help
  catch and correct these errors."*

So the controller does not collapse to "accuracy is 100%, change
nothing." It picks a failure mode **hypothetically** and acts. This is
exactly the behavior the pilot is trying to elicit — a positive signal.

- **Lesson**: future runs should track how often the controller emits
  an **empty edit** (= no-op) under a saturated val, as a separate
  health metric for the "hypothetical intervention" behavior. The
  current `evolve_log.json.edits` stores rationale + op list but no
  explicit no-op flag.

### 2.3 Worker tokens cost 3–4× controller tokens

Per 1-iter run:

| Role       | Tokens   |
|------------|----------|
| worker     | 11,977   |
| controller | 3,534    |

Worker token usage scales ~linearly with iterations; the controller is
~3.5k per iter and roughly fixed. Total cost is dominated by
**worker × iter**. For early grid search, managing `--n-train` is far
higher leverage than controller-token optimization.

---

## 3. Codebase gotchas

Things that will bite the next session reading this code.

### 3.1 `LLMClient.chat` in `src/llm.py` takes two positional args

Signature:

```python
LLMClient().chat(system: str, user: str, ...)
```

It is **not** the OpenAI SDK `messages=[...]` style. Call sites must
split system / user themselves.

### 3.2 `results/<run>/evolved_graph_final.json` wraps the graph in `{graph, describe}`

Accessing `agents`/`edges` directly raises `KeyError`. Always descend
into `data["graph"]`. (In contrast,
`evolve_log.json.iterations[*].graph_snapshot` has `agents`/`edges` at
the top level with no wrapper — the two formats are asymmetric, watch
out when writing scripts.)

### 3.3 `vllm` is intentionally outside `pyproject.toml`

Because of CUDA version pinning, `vllm` is installed via
`uv pip install vllm` rather than `uv sync` (also noted in
`CLAUDE.md`). Which means a clean `uv sync`-only environment can't
boot the server. For reproducibility, a companion file like
`requirements-vllm.txt` with a README pointer would help.

### 3.4 `serve_vllm.sh` now uses `uv run python`

The original called bare `python`, which risked picking up a system
Python outside the project's venv. This has been pinned to
`exec uv run python ...` (`scripts/serve_vllm.sh:15`).

---

## 4. Calibration run `calib_01` (2026-04-24)

First E2E run at a middle sample size — n_val=n_test=50, seed=0,
max_iters=3, total wall ~66 min. Artifacts in `results/calib_01/`;
cell-by-cell read-out in `notebooks/calib_01_analysis.ipynb`.

### 4.1 Headline: evolved graph *underperforms* both baselines on test

| Method | val acc | test acc | tokens (test) |
|---|---|---|---|
| CoT | 94% | 92% | 17.5k |
| Planner-Executor (seed graph) | 94% | 90% | 31.1k |
| Evolved (4 agents, 8 edges) | — | **86%** | **65.2k** |

Evolution spends **2.1× more tokens than P-E and 3.7× more than CoT**
while landing 4–6 pp below both. With n=50 this is close to the
sample-error floor (~±7 pp 95% CI from a 3-sample difference), so we
cannot *prove* regression from this run alone. But the gap is
consistently on the wrong side of zero, which is the first signal
that "more agents" does not automatically help here.

### 4.2 Iteration trajectory and the accept_slack quirk

```
iter 0  seed (planner + executor)                 val=94%  (best_val_acc)
iter 1  +verifier + edges                         val=92%  ACCEPTED
iter 2  +reformulator + edges                     val=92%  ACCEPTED
iter 3  +critic + edges                           val=86%  REJECTED
```

Two iterations regressed on val but were still **ACCEPTED**, because
`src/evolve.py:139` uses

```python
accepted = val_acc >= best_val_acc - accept_slack
```

and then only updates `best_val_acc` when `val_acc > best_val_acc`
(`evolve.py:146–147`). Consequence:

- **`best_graph` drifts to the iter-2 graph** (verifier + reformulator),
- but **`best_val_acc` stays at 94%**, the seed value.

The saved `results/calib_01/evolved_graph_final.json` has 4 agents,
while `results/calib_01/evolve_log.json.best_val_acc == 0.94` was
achieved by the 2-agent seed graph. The two are **decoupled** under
the current accept policy. This needs to be resolved before any
scaled run; otherwise "best graph" reported to the reader is not the
graph that actually achieved `best_val_acc`.

Two plausible fixes:

- **Opt-1 (loose):** on accept, set `best_val_acc = val_acc` as well.
  Keeps slack-tolerant exploration; the reported `best_val_acc`
  matches the stored graph.
- **Opt-2 (strict):** replace `best_graph` only when
  `val_acc > best_val_acc`. Kills slack-driven graph replacement;
  `best` becomes the true best.

Either is defensible; they embody different philosophies (exploration
vs. monotonicity).

**Decision (2026-04-24): Opt-2 (strict).** The accept branch now
requires `val_acc > best_val_acc` (tie-breaks preserve the previous
best). `accept_slack` default is set to `0.0`; setting it above `0`
re-enables Opt-1 behavior for future ablations. Verified on
`results/smoke_opt2/` (n=3, max_iters=2): both evolved iters tied at
100% val and were REJECTED; final `best_graph == seed` with
`best_val_acc == 1.0` — the two now agree. See `references/roadmap.md`
§3 for the decision record.

### 4.3 Controller still emits hypothetical edits, but rationales are thin

At val=94% the controller produced:

- iter 1 rationale: *"The observed errors seem to stem from
  incomplete or incorrect arithmetic calculations by the executor."*
  But the dataset is GSM8K; Qwen2.5-32B at 94% is not failing due to
  arithmetic. The verifier is a reasonable default move, not a
  diagnosis from tape.
- iter 2 rationale: *"The observed errors often arise from
  misinterpretation of the problem statement."* Unclear from which
  tape — val was already 94% pre-iter-2.
- iter 3 rationale: *"The current graph has a high accuracy but
  still makes some mistakes."* More honest, but `add critic` is again
  a default addition, not a causal inference.

This is consistent with the smoke-run observation in §2.2: the
controller *does* produce non-empty edits under saturated val
(`is_noop == False` for all 3 iters), but the rationales read like
generic "add more agents" reflexes rather than trajectory-grounded
causal reads. This is exactly the failure mode `project.md` §7 Framing
A (causal/diagnostic controller) is designed to attack. Evidence, not
a verdict yet — worth revisiting once we have n=300 results.

### 4.4 Wall-clock and per-task timing

| Phase | Wall | s/task |
|---|---|---|
| CoT val (n=50) | 4:18 | 5.2 |
| P-E val (n=50) | 6:49 | 8.2 |
| Evolve (3 iters, train n=20 + val n=50 each) | 37:55 | — |
| CoT test (n=50) | 3:51 | 4.6 |
| P-E test (n=50) | 4:43 | 5.7 |
| Evolved test (n=50, 4 agents) | 8:59 | 10.8 |

Extrapolating to §5.1 scaled run (n_train=100 or 200 + n_val=300 +
n_test=300, seed×3, max_iters=5):

- Baselines-only per seed: ~26 min / 300 (CoT) + ~41 min (P-E) ≈ 1 h.
- Evolution per iter is dominated by val at n=300: ~41 min × 5 iters ≈
  3.4 h. Plus train rollouts (n=100): ~0.5 h. Total ~4 h / seed.
- Evolved test at 4 agents is ~55 min / 300.
- **Per-seed total: ~5–6 h. × 3 seeds ≈ 15–18 h wall** on shared H200.

If the evolved graph grows to 5+ agents, budget +30% per evolved-test
phase. The single-H200 bottleneck makes parallel seeds infeasible
without another GPU allocation.

### 4.5 Token cost asymmetry is wider than §2.3 estimated

Per-iter cost from `calib_01`:

| iter | worker tokens | controller tokens | ratio |
|---|---|---|---|
| 1 | 70,830 | 3,665 | 19.3× |
| 2 | 92,827 | 4,958 | 18.7× |
| 3 | 130,313 | 5,916 | 22.0× |

The 3–4× from the earlier smoke run understates the real regime —
at `n_train=20 + n_val=50` per iter, worker tokens are **~20× the
controller's**, and they grow **monotonically as the graph adds agents**
because every val sample now traverses more agents. Per-iter wall and
per-iter worker-tokens are *both* super-linear in `n_agents`. For
§5.1, this tightens the budget further: capping `n_agents` (e.g., via
`--max-agents` ≤ 5) matters more than we thought.

---

## 5. Open items / things worth trying next

1. ~~**Fix `evolve.py` accept semantics** (§4.2) — before §5.1 scale-up,
   resolve the `best_graph` / `best_val_acc` decoupling.~~ **Done
   2026-04-24**, Opt-2 strict landed and smoke-verified. See §4.2.
2. **Re-run at n_val ≥ 300, seed ≥ 3** — see whether the 4–6 pp test
   regression in §4.1 survives noise, or collapses.
3. **~~Log the controller's no-op rate~~** — done. `is_noop` field
   landed in `src/evolve.py:31` before `calib_01`; all 3 iters had
   `is_noop == False` in this run.
4. **Pre-flight `scripts/serve_vllm.sh`** — `gcc` existence check,
   free-GPU-memory measurement, vLLM CLI flag sniff.
5. **Jupyter dev-extra in `pyproject`** — expose `nbformat`,
   `nbclient`, `ipykernel` as optional extras so notebook re-execution
   doesn't require `uv pip install` every time.
6. **Cap `n_agents`** (§4.5) — consider `--max-agents 5` or lower for
   the scaled run to keep wall / token cost in a predictable box.
7. **Track rationale quality** (§4.3) — a small follow-up: tag each
   rationale with whether it cites a specific tape example or reads as
   a generic "add X agent" default, as input into Framing A planning.

---

## 6. Domain pivot — sanity batch (2026-04-24)

Triggered by two converging observations:

1. `calib_01` (§4) showed **evolved < both baselines on test** for
   GSM8K, with controller rationales that read as generic "add an
   agent" reflexes rather than task-grounded diagnoses.
2. GSM8K structurally under-rewards multi-agent: the context is
   self-contained, the task is linear arithmetic, and a single strong
   LLM already scores 94%. Persona specialization has **no
   information-asymmetric lever** to pull.

Decision: retire GSM8K as the primary benchmark. Activate three
domain benchmarks that *do* have multi-agent affordances:
**FinanceBench**, **MEDIQ (non-interactive initial mode)**,
**AgentClinic (single-pass wrapper)**. Rationale and updated H1 live
in `references/project.md`.

### 6.1 Loaders and scoring

- `src/datasets.py::load_benchmark(name, ...)` dispatches to
  `load_financebench`, `load_mediq`, `load_agentclinic`. Raw JSONL for
  MEDIQ / AgentClinic is fetched once into `data/` via
  `urllib.request`; FinanceBench uses HF `PatronusAI/financebench`.
- `src/score.py::score(prediction, task, llm)` dispatches:
  MCQ exact-match (MEDIQ) or LLM-as-judge (FinanceBench,
  AgentClinic). **Self-bias flag**: the judge is the same
  Qwen2.5-32B as the worker. Acceptable for sanity; a
  separate-family judge is a reviewer-bar item for scaled runs.
- Baseline seed-graph personas were generalized away from arithmetic
  ("Final Answer: <number>" → "Final Answer: <answer>").

### 6.2 Sanity results (n_train=2, n_val=3, n_test=3, max_iters=2)

| Benchmark | CoT val / test | P-E val / test | Evolved test | Evolution outcome |
|---|---|---|---|---|
| MEDIQ | 67% / 0% | 0% / 33% | 33% (seed) | iter 1 & 2 val tied at seed → REJECTED (Opt-2) |
| AgentClinic | 67% / 100% | 100% / 67% | 67% (seed) | Controller proposed `add_agent(summarizer)` — domain-adaptive rationale; tied → REJECTED |
| FinanceBench | 33% / 67% | 33% / 67% | 67% (seed) | Controller emitted DAG-invalid edit (`planner` unreachable from END) **twice** |

Artifacts: `results/sanity_mediq/`, `results/sanity_agentclinic/`,
`results/sanity_financebench/`.

### 6.3 Observations

**Pipeline-level (what we wanted to verify)**:
- All three loaders + scorers execute end-to-end.
- Opt-2 strict accept semantics behaves correctly (ties → REJECT,
  seed preserved as `best_graph`).
- Generalized seed personas parse on MCQ, free-text, and long-context
  domains without code changes to orchestrator or controller.

**Scientific-signal (tentative; n=3 is too small for conclusions)**:
- Controller rationales **change with domain**. GSM8K's "arithmetic
  verifier" reflex is replaced by AgentClinic's "summarizer for
  concise diagnosis" — the reflection-only signal does not collapse
  to a single default move. First empirical reason to believe the
  domain-pivot hypothesis has a chance.
- FinanceBench tripped the DAG invariant **twice**, suggesting the
  long evidence context is displacing topology reasoning in the
  controller. Prompt engineering is probably needed on the controller
  side (reinforce the DAG rule, or move the graph description to a
  more salient position in the prompt).

**Noise source observed (n=3 artifact)**: the same seed graph, when
evaluated in the baseline phase and then re-evaluated as the evolve
seed, returned different val accuracies (clearest on FinanceBench:
baseline P-E val = 33% vs evolve seed val = 0%). Cause is likely
vLLM temperature=0 non-determinism at batch boundaries plus
LLM-judge variance. For n ≥ 30 this averages out; at n=3 it
contaminates individual numbers.

### 6.4 What this run does *not* answer

- Does evolved outperform baselines at meaningful n (≥ 30)? Sanity
  n=3 is too small.
- Is the domain-adaptive controller rationale actionable? We would
  need to see a valid edit that measurably improves val at scale.
- LLM-judge self-bias on FinanceBench / AgentClinic — unexamined.
- MEDIQ "non-interactive initial" is the **paper-documented losing
  setting** (Li et al. 2024: 45.6% non-interactive > 42.2%
  interactive on GPT-3.5). Finding ≈baseline on this slot is *not*
  evidence that multi-agent fails on medical — it's sanity that our
  pipeline reproduces the benchmark's known regime.

### 6.5 Immediate next steps

1. Patch the controller prompt so FinanceBench-style long-context
   inputs don't displace the DAG rule (short targeted edit in
   `src/controller.py::CONTROLLER_SYSTEM`).
2. Scale each benchmark to **n_val = n_test ≈ 30, max_iters = 3**
   (~20–40 min per benchmark on shared H200). This is the real first
   domain-pivot measurement.
3. Only *then* decide whether the domain pivot recovers the
   hypothesis or whether we pivot into Framing C (persona-necessity
   negative result).

---

## 7. One-line summary

> The pilot **runs end-to-end** on three new domain benchmarks
> (FinanceBench, MEDIQ, AgentClinic) after the GSM8K retirement
> (§6). First positive signal of the pivot: **controller rationales
> vary with domain** rather than defaulting to "add an arithmetic
> verifier" (§6.3). First negative signal: FinanceBench's long
> evidence context breaks the controller's DAG discipline (§6.3).
> Historical GSM8K result from `calib_01`: evolved underperforms both
> baselines on test while costing 2–3.7× more tokens, and the
> previous accept policy decoupled `best_graph` from `best_val_acc`
> (§4) — both addressed before this pivot.
