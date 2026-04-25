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

### 6.5 Immediate next steps (status as of 2026-04-25)

1. ~~Patch the controller prompt so FinanceBench-style long-context
   inputs don't displace the DAG rule.~~ **Done** in commit `e5725e7`;
   verified on `results/sanity_financebench_v2/`.
2. ~~Scale each benchmark to **n_val = n_test ≈ 30, max_iters = 3**.~~
   **Done** as `results/n30_{financebench,mediq,agentclinic}/`. See §7
   below for the post-v1 + v2 read-out.
3. Decided after §7: **continue** with the controller v2 redesign
   instead of pivoting straight to Framing C — H1 was weakly
   falsified at the v1 controller, but v1 emitted essentially no
   domain-aware behavior, so the falsification is contaminated by
   controller laziness rather than purely by domain headroom.

---

## 7. Controller v2: organization-designer redesign (2026-04-25)

### 7.1 Why redesign

The v1 first n=30 sweep (`results/n30_{financebench,mediq,
agentclinic}/`) produced disappointing test numbers and, more
informatively, **uniform v1 controller behavior across domains**:

- FinanceBench v1: emitted `add_agent(verifier)` three rounds in a row
  with rationales like *"lacks a verification step to ensure the
  executor's output is accurate"* — zero finance vocabulary, no
  reaction to the prior_edits hint.
- MEDIQ v1: started identically but happened to be ACCEPTED on iter 2
  by noise; iter 3 then varied (anti-repeat-on-accept observed
  empirically).
- AgentClinic v1: alternated `summarizer ↔ verifier` with some domain
  vocab ("concise diagnosis").

So at n=30 the v1 controller emitted essentially the same generic
verifier-add reflex everywhere, regardless of domain. Diagnosis: the
controller should design *real organizations* of domain specialists,
not paste a verifier in front of END.

### 7.2 What changed in v2 (commit `d7b926f`)

`src/controller.py::CONTROLLER_SYSTEM` reframed as **architect of an
org chart of domain experts**:

- Mandatory **specialist persona authoring rules** with BAD/GOOD
  examples. Generic role names (`verifier`, `summarizer`, `critic`,
  `reviewer`, `validator`) are **forbidden** unless paired with a
  specialty (e.g. `cardiology_consultant`,
  `financial_disclosure_auditor`, `differential_diagnostician`).
- Personas must **cite domain expertise** and describe a
  domain-specific procedure in 2–3 sentences.
- **Anti-repeat rule**: do not propose the same operation type in
  consecutive rounds; vary edits across rounds.
- **Active prune incentive**: encouraged use of `remove_agent` for
  agents whose output doesn't influence END.
- **Domain brief slot** in the user prompt: per-benchmark briefs
  (~80–110 lines each) live in `data/briefs/{name}.md` and are
  injected at the top of every controller call.

`_build_user_prompt` reorders sections — DOMAIN BRIEF first, current
graph second, sampled trajectories third, prior edits fourth, with a
reminder block telling the controller to ground rationales in the
brief and cite specific tape examples. `propose_edits → evolve →
run_pilot` thread the brief through.

`scripts/serve_vllm.sh` was hardened during this work: gcc auto-install
on missing CC (container reservations are ephemeral), default
`CUDA_VISIBLE_DEVICES=0` (the project's reserved device per the
workspace `../CLAUDE.md`), default `--max-model-len 16384` (the v2
prompt with brief + multi-agent tape summaries can exceed 8192,
especially on FinanceBench).

### 7.3 v2 sanity at n=10 — behavior verified

`results/sanity_v2_{financebench,mediq,agentclinic}/`. All three
domains met the pass criteria: specialist persona names, domain vocab
in personas, varied edits across rounds. `remove_agent` used in 2 of 3.

Highlights:

- **FinanceBench sanity v2**: emitted `unit_checker` and
  `period_verifier`; persona text quotes "GAAP-trained financial
  analyst", "fiscal year vs. calendar year", "TTM vs annual",
  "millions, thousands". Iter 3 was ACCEPTED (val 50→90; n=10 noise
  helped here).
- **MEDIQ sanity v2**: iter 1 added `differential_diagnostician` and
  `physical_exam_mapper`. Iter 2 ACCEPTED with a literal
  `remove_agent(planner)` plus an `adolescent_specialist` for an
  observed eating-disorder case. Iter 3 retried with a different
  specialty mix.
- **AgentClinic sanity v2**: iter 1 `decisive_diagnosis_writer`
  ("convert the prior reasoning into a single, decisive diagnosis
  name with no hedging or qualifiers" — verbatim from the brief).
  Iter 2 added `triage_specialist` ("emergency medicine physician...
  identify red flags") plus `remove_agent(planner)`. Iter 3 combined
  triage + decisive.

The qualitative jump from v1 is large. v1 controller had ~zero domain
words in its emitted personas; v2 personas read like job-description
copy.

### 7.4 v2 at n=30 — test win not yet

`results/n30_v2_{financebench_retry,mediq,agentclinic}/`. Per-iter
wall ranged 4–11 min; FinanceBench retried at `--max-model-len 16384`
because the original v2 run hit the 8192 limit at iter 2:
*"This model's maximum context length is 8192 tokens. However, you
requested 1500 output tokens and your prompt contains at least 6693
input tokens, for a total of at least 8193 tokens."*

| Domain | CoT test | P-E test | Evolved test | Δ vs best baseline | best_graph |
|---|---:|---:|---:|---:|---|
| FinanceBench (16k) | 73.3% | 70.0% | 83.3%* | +10pp* | seed (all REJECT) |
| MEDIQ              | 43.3% | 46.7% | 43.3%  | -3.4pp | 3-agent (iter 2 ACCEPT) |
| AgentClinic        | 60.0% | 73.3% | 66.7%  | -6.6pp | seed (all REJECT) |

*FinanceBench's apparent +10pp is **same-graph noise**: best_graph
== seed (all evolve iters rejected), yet `evolved/test` differs from
`planner_executor/test` by 13pp in the same run. vLLM batch ordering
/ KV-cache state is not deterministic enough to make two consecutive
evaluations of the same graph land within 5pp at n=30. Same-graph
variance ≥ between-graph variance at this n. **Cannot be cited as a
v2 effect.**

The most striking REJECTED proposal of the sweep is **AgentClinic
iter 3**:

```text
add_agent(triage_specialist)     # ED triage with red-flag screen
add_agent(gastroenterologist)
add_agent(cardiologist)
remove_agent(planner)
remove_agent(executor)
add_edge(START, triage_specialist)
add_edge(triage_specialist, gastroenterologist)
add_edge(triage_specialist, cardiologist)
add_edge(gastroenterologist, END)
add_edge(cardiologist, END)
```

A literal triage-routed specialty department: a triage agent screens
the case and routes to either gastroenterology or cardiology, both
report directly to END. The original planner+executor pair is pruned
entirely. Got rejected because val tied with seed (Opt-2 strict
requires *strict* improvement).

### 7.5 The measurement-noise problem

Two separate observations point at the same problem:

1. **Same-graph cross-run variance**: FinanceBench v2 retry shows
   `planner_executor/test = 70%` and `evolved/test = 83%` for the
   same underlying seed graph in the same run. 13 percentage points
   on n=30 just from re-running the inference loop.
2. **v1 vs v2 cross-run variance on baselines**: v1 n=30 FinanceBench
   reported P-E val=83% / test=67%; v2 retry reported P-E val=83% /
   test=70%. The seed graph is identical; only the run differs.

vLLM at temperature=0 is *not* fully deterministic when batches and
KV-cache states differ. At n=30, this variance dominates any signal
≤±10pp. Two implications:

- **Headline numbers below ±10pp at n=30 should not be reported as
  results.** This rules out cleanly comparing v1 to v2 at the current
  sample size.
- **n must scale, OR seed must be averaged.** A 3-seed multi-seed
  average over n=30 effectively gives n=90 worth of comparison power
  per method. This is cheaper than scaling each individual run to
  n=300.

### 7.6 Wall budget and Opt-2 strict

A FinanceBench v2 iter takes ~10–12 min at n_train=10, n_val=30 with
3–4 agents. Three rounds is ~40 min for evolve alone, plus
baselines + test bench = ~75 min wall per benchmark per seed.

Opt-2 strict requires `val_acc > best_val_acc` (no slack). With
±18pp noise at n=30, an architectural change has to clear roughly
that bar to be ACCEPTED — which means most v2 candidates (which are
genuinely large changes — adding 2–3 specialists, pruning planner)
get rejected on noise alone. The single ACCEPT in the v2 sweep
(MEDIQ iter 2) was a same-effective-direction move that happened to
beat the noise floor.

The streaming-mode work (`../../references/roadmap.md` §5.1)
addresses both constraints simultaneously: a 100–200-sample sliding
window per round amortizes noise; the controller fires once per
window rather than once per full train sweep, allowing 5–10 rounds
in roughly the same wall.

### 7.7 What this section does *not* claim

- That v2 is *better* on test than v1 at n=30 — measurement noise
  prevents that comparison.
- That the strict accept policy is wrong — it is conservative, but
  conservatism is appropriate when noise is large.
- That `gastroenterologist`-style specialty agents *would* improve
  test if accepted — we don't know, because they were never given a
  fair multi-batch evaluation.

It does claim:
- v2 controller behavior is qualitatively the kind of organization
  design the user requested in the redirect.
- The bottleneck to seeing whether that behavior helps test
  accuracy is the **measurement design**, not (necessarily) the
  controller.

---

## 8. One-line summary

> v1 controller at n=30 → at-or-below baselines on test on all three
> domains, with rationales that read as a generic "add a verifier"
> reflex regardless of domain (§7.1). Controller v2 redesign as
> organization designer (§7.2) produces qualitatively different
> behavior — specialist personas with cited domain expertise,
> tape-citing rationales, active prune (§7.3). v2 at n=30 is *not*
> demonstrably better on test (§7.4) — measurement noise (§7.5)
> dominates and Opt-2 strict + per-iter wall budget (§7.6) means most
> architectural changes get rejected before they can be evaluated
> over multiple noise-averaged batches. Streaming-mode work is the
> next bottleneck-buster.
>
> Historical (pre-v2) summary, kept for context: GSM8K result from
> `calib_01`: evolved underperforms both
> baselines on test while costing 2–3.7× more tokens, and the
> previous accept policy decoupled `best_graph` from `best_val_acc`
> (§4) — both addressed before this pivot.
