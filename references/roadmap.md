# ROADMAP

Living progress dashboard for the `agent_orchestration` pilot. The
experiment spec lives in `project.md`; real-world findings from
running the pilot are captured in `../docs/insights/pilot.md`. This file is updated
every time an experiment cycle completes.

*Last updated: 2026-04-26*

---

## 1. Research Purpose

**One-liner.** A pilot study to test whether a multi-agent DAG
(topology + personas + edges) can be progressively evolved over a
repetitive task family using **pure in-context reflection** — no
controller training, no explicit search procedure.

**Differentiator vs. prior art** (see `project.md` §1, §7):
- ADAS / AFlow / GPTSwarm / MaAS / Puppeteer (NeurIPS 2025) all rely on
  **search** (archive / MCTS / supernet) or **RL**.
- This pilot co-evolves topology + personas + edges from
  **reflection over trajectory tapes** on a frozen backbone, which is
  the only real differentiator.
- Caveat: `project.md` judges this alone insufficient for
  NeurIPS 2026 main track (3–6% acceptance estimate). EMNLP 2026 via
  ARR (~5–10%) is the realistic primary target.

## 2. Target Outcomes

### 2.1 Methodological (H1 + H2)

**H1 (2026-04-24, post-pivot — partially falsified 2026-04-25)**:
Reflection-only multi-agent evolution produces a measurable val/test
improvement over CoT and Planner-Executor baselines on domain-specific
tasks. **Status 2026-04-25**: at n=30 across three domains the evolved
graph is at-or-below baselines (FinanceBench Δ=0pp, MEDIQ Δ=+6.7pp
within ±18pp noise, AgentClinic Δ=0pp). Combined with `calib_01`'s
observation that controller rationales were generic "add a verifier"
reflexes (`pilot.md` §4.3), the simplest explanation is **the v1
controller is too thin to exploit the domain headroom that exists** —
not that the headroom is missing. This drives H2.

**H2 (2026-04-25, post-controller-redesign)**: An *organization-
designer* controller fed a domain brief produces specialist personas
(cited domain expertise) and varied edits (not the verifier-add
reflex), and yields a measurable val/test improvement over both
baselines AND the v1 controller in at least one domain at n ≥ 30.

**H2 dependencies (delivered before measurement)**:
- v1 baseline already measured: `results/n30_{financebench,mediq,agentclinic}/`.
- Domain briefs: `data/briefs/{financebench,mediq,agentclinic}.md`.
- Controller v2: organization-designer framing in
  `src/controller.py::CONTROLLER_SYSTEM`; specialist persona
  authoring rules; anti-repeat rule; brief slot plumbed through
  `propose_edits → evolve → run_pilot`.

**H2 falsifier**: if controller v2 still emits generic personas (no
domain vocabulary) AND/OR test ≈ baseline across all three domains at
n ≥ 30, fall back toward Framing C (persona-necessity negative
result) and adjust paper framing accordingly.

**Empirical trigger for H1's domain restriction**: `calib_01` on GSM8K
showed evolved < both baselines on test (§4.1 of `pilot.md`); GSM8K
structurally lacks the information-asymmetric lever multi-agent
exploits. The GSM8K result is the *narrative entry point* for the
pivot, not the discriminating evidence.

**Secondary methodological questions**:
1. Does evolved transfer to test (val↔test gap < 3pp)?
2. What kinds of personas does v2 actually author? Are they
   domain-specific (cited specialty + concrete procedure) or do they
   collapse back to generic verifiers? — to be answered in §5.1 v2 sanity.
3. Do v2 edits use `remove_agent`? Does v2 vary across rounds (per
   anti-repeat rule)?

### 2.2 Paper (per `project.md` §7)
- **Primary:** EMNLP 2026 main via ARR — **deadline 2026-05-25 (D-31)**.
- **Secondary:** NeurIPS 2026 Datasets & Benchmarks Track — 2026-05-06
  (D-12). *Pivot decision still open.*
- **Tertiary:** NeurIPS 2026 workshop (Lifelong Agents, etc.) —
  deadlines in summer.

### 2.3 Reviewer-bar experiment coverage (must clear)
- [ ] Best-of-N single-agent, matched compute
- [ ] ≥2 backbone families (e.g. Qwen3-72B + one of Claude/GPT)
- [ ] ≥3 heterogeneous benchmarks, including a non-saturated one
- [ ] Direct comparison vs. ADAS + (Puppeteer or MaAS or EvoMAC)
- [ ] Harness ablation (controller on/off, random-persona, fixed-topo)
- [ ] Failure-mode taxonomy (MAST-style)
- [ ] Cost Pareto (tokens × wall-clock × $)
- [ ] LLM-judge calibration (≥100 samples, human agreement κ)

---

## 3. Done

### ✅ Pilot infrastructure
- `src/` library: `llm.py`, `graph.py`, `orchestrator.py`,
  `controller.py`, `evolve.py`, `baselines.py`, `datasets.py`,
  `score.py`, `types.py`.
- `scripts/run_pilot.py` — baselines + evolution driver.
- `scripts/serve_vllm.sh` — patched for vLLM 0.19.1
  (`--no-enable-log-requests`).
- `uv`-managed environment, pinned `.python-version`.

### ✅ End-to-end smoke validation
- `results/smoke_baselines/` — baselines run successfully.
- `results/smoke_evolve/` — 1-iter evolution confirmed the controller
  actually emits edits and the graph mutates.
- `results/run_20260423_140620/` — first full run artifacts exist.

### ✅ Three operational blockers identified & fixed (`../docs/insights/pilot.md` §1)
1. vLLM 0.19.1 CLI flag drift → `serve_vllm.sh` patched.
2. Triton JIT needs system `gcc` → installed.
3. Shared H200 → `EVO_GPU_UTIL=0.55` manual override needed.

### ✅ Early observations (`../docs/insights/pilot.md` §2)
- With 5 samples, CoT / P-E / Evolved all score 100% — no
  discriminative power. **→ n_val / n_test must be scaled to hundreds.**
- Even on a saturated val set the controller proposed a sensible edit
  (add verifier agent + edges) — evidence of **hypothetical
  intervention** rather than no-op, which is the behavior the pilot is
  trying to elicit.
- Worker tokens are ~3–4× controller tokens per iter → total cost is
  dominated by `worker × iter`; optimize `--n-train` before controller
  tokens.

### ✅ `is_noop` field in evolve log
- `evolve_log.json.iterations[*].is_noop: bool` added
  (`src/evolve.py:31`). Set False on the seed iter, True on empty edit
  batches. Unblocks no-op-rate measurement under saturated val.

### ✅ Calibration run `calib_01` (2026-04-24)
- `results/calib_01/` — n_val=n_test=50, seed=0, max_iters=3,
  wall=~66 min. See `../docs/insights/pilot.md` §4 for analysis and
  `notebooks/calib_01_analysis.ipynb` for the reproducible read-out.
- Surface finding: **evolved graph underperforms both baselines on
  test** (86% vs CoT 92% / P-E 90%) while costing 2–3.7× more tokens.
  Val discrimination is also null at n=50 (CoT=P-E=94%). Strengthens
  the case for n≥300 seed≥3.
- Pipeline-level finding (now fixed, see below): under the old Opt-1
  accept policy `best_graph` and `best_val_acc` could point at
  different graphs.

### ✅ `evolve.py` accept semantics — Opt-2 strict (2026-04-24)
- Picked Opt-2: `best_graph` / `best_val_acc` advance **only on a
  strict val improvement** (`val_acc > best_val_acc`). Tie / near-best
  candidates are REJECTED. Default `accept_slack = 0.0`; the old
  Opt-1 behavior stays available behind `accept_slack > 0` for
  ablations.
- Verified on `results/smoke_opt2/` (n=3, max_iters=2, both evolved
  iters tied at 100% val and were REJECTED; final `best_graph == seed`
  with `best_val_acc == 1.0` — the two agree, which they did not
  under Opt-1).

### ✅ Domain pivot — GSM8K retired, 3 new benchmarks activated (2026-04-24)
- **Empirical trigger**: `calib_01` showed evolved < both baselines
  on GSM8K test (86% vs 92% / 90%), and GSM8K structurally lacks the
  information-asymmetric lever that multi-agent exploits (self-contained
  text, linear arithmetic, single-model saturation at 94%). See
  `../docs/insights/pilot.md` §6 for full rationale.
- `src/datasets.py` rewritten: `load_benchmark(name, ...)` dispatches
  to FinanceBench (HF `PatronusAI/financebench`), MEDIQ
  (non-interactive initial mode, GitHub raw JSONL), AgentClinic
  (single-pass wrapper, GitHub raw JSONL).
- `src/score.py` rewritten as dispatcher: MCQ exact-match (MEDIQ) or
  LLM-judge (FinanceBench, AgentClinic). Same Qwen judges Qwen —
  self-bias flagged.
- Baseline seed personas de-mathified; controller prompt
  de-mathified. `run_pilot.py --benchmark {name}` required.
- Sanity at n=3 per benchmark confirms pipeline runs end-to-end.
  Artifacts in `results/sanity_{mediq,agentclinic,financebench}/`.

### ✅ Controller DAG-discipline patch (`e5725e7`, 2026-04-25)
- FinanceBench sanity revealed a recurring antipattern:
  `add_agent(verifier) | add_edge(verifier→END) | remove_edge(executor→END)`
  without compensating `executor→verifier`, orphaning executor.
- Fix: clarified DAG reachability in `CONTROLLER_SYSTEM` and added a
  reminder in user prompt. Verified on `results/sanity_financebench_v2/`
  — controller now emits valid edits, `executor→END` preserved.

### ✅ First domain-pivot measurement at n=30 (2026-04-25)
- 3 benchmarks × `--n-train 10 --n-val 30 --n-test 30 --max-iters 3 --seed 0`.
  Artifacts: `results/n30_{financebench,mediq,agentclinic}/`.

| Domain | CoT test | P-E test | Evolved test | Δ vs best baseline |
|---|---:|---:|---:|---:|
| FinanceBench | 70.0% | 66.7% | 70.0% | 0pp |
| MEDIQ        | 43.3% | 43.3% | 50.0% | +6.7pp (within ±18pp noise) |
| AgentClinic  | 66.7% | 70.0% | 70.0% | 0pp |

- v1 controller behavior at n=30: FinanceBench emitted the same
  `add_verifier` edit 3 times in a row (no domain vocabulary, no
  use of prior_edits feedback). MEDIQ varied edits after iter 2 was
  ACCEPTED. AgentClinic alternated `summarizer ↔ verifier` (some
  domain vocabulary).
- **Read**: H1 weakly falsified at this controller version. Headroom
  exists but the v1 controller is too thin to exploit it. Drives the
  controller v2 redesign below.

### ✅ Controller v2 — organization-designer framing (2026-04-25, commit `d7b926f`)
- New `CONTROLLER_SYSTEM` reframes the agent graph as an *org chart of
  domain experts*. Mandatory specialist persona authoring rules
  (cited expertise + concrete procedure); generic "verifier /
  summarizer" forbidden unless paired with specialty. Anti-repeat
  rule. Active prune incentive.
- Three domain briefs authored: `data/briefs/{financebench,mediq,agentclinic}.md`
  (~80–110 lines each — task style, failure modes, useful expertise,
  useful patterns, anti-patterns).
- Brief plumbed through `propose_edits → evolve → run_pilot`.
- `scripts/serve_vllm.sh`: gcc auto-install on missing CC, default
  `CUDA_VISIBLE_DEVICES=0` (GPU 0 reserved for evo_agents per
  workspace `../CLAUDE.md`), default `--max-model-len 16384` (the v2
  controller prompt with brief + multi-agent tapes can exceed 8192).

### ✅ v2 sanity at n=10 across 3 domains (2026-04-25)
- Artifacts: `results/sanity_v2_{financebench,mediq,agentclinic}/`.
- Verified controller v2 behavior:
  - Specialist persona names: `gaap_analyst`, `period_validator`,
    `differential_diagnostician`, `adolescent_specialist`,
    `physical_exam_mapper`, `triage_specialist`,
    `decisive_diagnosis_writer`, …
  - Domain vocabulary in personas (GAAP, TTM, fiscal year, base rate
    × clinical fit, no hedging, red flags, …).
  - `remove_agent` used (MEDIQ ×2, AgentClinic ×1).
  - Tape-citing rationales ("17-year-old girl case", "task ac-23").
- All v2 sanity pass criteria met.

### ✅ v2 n=30 measurement on 3 domains (2026-04-25)
- 3 benchmarks × `--n-train 10 --n-val 30 --n-test 30 --max-iters 3 --seed 0`.
  Artifacts: `results/n30_v2_{financebench_retry,mediq,agentclinic}/`.
  (FinanceBench retried at 16k context after the original v2 run hit
  the 8192 limit at iter 2 — see `pilot.md` §7.)

| Domain | CoT test | P-E test | Evolved test | Δ vs best baseline | best_graph |
|---|---:|---:|---:|---:|---|
| FinanceBench (16k) | 73.3% | 70.0% | 83.3%* | +10pp* | seed (all REJECT) |
| MEDIQ              | 43.3% | 46.7% | 43.3%  | -3.4pp | 3-agent (iter 2 ACCEPT) |
| AgentClinic        | 60.0% | 73.3% | 66.7%  | -6.6pp | seed (all REJECT) |

- *FinanceBench's +10pp is **same-graph noise**: best_graph == seed,
  yet test acc differs from `planner_executor/test=70%` by 13pp due
  to vLLM batch-ordering / KV-cache state non-determinism. Cannot be
  cited as a v2 win.
- AgentClinic iter 3 (REJECTED but notable): proposed
  `add(triage_specialist) + add(gastroenterologist) + add(cardiologist)
  + remove(planner) + remove(executor)` with
  `START → triage → {gastro|cardio} → END` — a literal triage-routed
  specialty department; rejected because val tied with seed under
  Opt-2 strict.
- **Read**: H2 behavior satisfied (specialist personas, varied edits,
  prune); H2 test win NOT satisfied at n=30. Drives the streaming-
  mode work below.

### ✅ Streaming evolve mode (commit `51a9aa9`, 2026-04-25)
- `src/evolve.py::evolve_streaming()`: per-round bootstrap-sampled
  mini-batch (`batch_size`) from a stream pool (`train + val`); both
  `best_graph` and `candidate` evaluated on the **same batch** for a
  paired comparison; accept iff `c_acc > b_acc + accept_epsilon`.
- `EvolveLog` grew `mode` and `config` fields so analyzers can tell
  legacy vs streaming runs and read the streaming params.
- `scripts/run_pilot.py`: `--mode {legacy,streaming}` selector plus
  `--batch-size`, `--max-rounds`, `--accept-epsilon`. Stream pool =
  `train + val` combined.
- Sanity verified on `results/sanity_streaming_mediq/` (B=20 R=3): 4
  rounds recorded with paired same-batch comparison, mode/config
  landed, controller emits the same v2 specialist personas.

### ✅ First real streaming run on MEDIQ (B=100 R=10 seed=0, 2026-04-26)
- `results/streaming_v2_mediq_b100r10_s0/` + analyzer
  `scripts/analyze_streaming.py` (commit `57fdcd9`). Wall ≈ 9h45m
  on shared H200 (per-round 52 min — 5–6× the roadmap's optimistic
  10 min/round estimate). See `../docs/insights/pilot.md` §8 for
  the full read-out.
- **Pass criteria split**: (1) any round c_acc > b_acc → **True**
  (4 / 10 paired ACCEPTS); (2) best_val_acc > seed_batch_acc →
  **False** (62% vs 62%, structurally broken under bootstrap
  resampling — see pilot.md §8.4).
- **Test**: CoT 68% / P-E 58% / Evolved 62%. Δ vs best baseline =
  -6pp (vs CoT). Evolved beats P-E by +4pp at 6.3× tokens; loses
  to CoT.
- **Headline wins**: streaming-mode design *does* fire (4 paired
  ACCEPTS vs 1 / 9 in v2 legacy across 3 domains). Pre-`§5.2`
  blockers identified: pass criterion redefinition, max_agents
  cap binds, anti-repeat is string-level not concept-level.

### ✅ Pre-§5.2 controller patches (2026-04-26, commit `8405c78`)
- `src/controller.py`: `propose_edits` gains a `max_agents`
  kwarg; `_build_user_prompt` now opens with a `# Constraints`
  block (`max_agents = N, current n_agents = n. K agent slots
  remaining before the cap.`) and renders an explicit `AT CAP —
  only remove_agent / rewrite_persona / topology edits are
  allowed.` line when `n_agents == max_agents`. SYSTEM prompt
  adds (a) a prune-DAG reminder ("removing X must not orphan any
  agent that depended on X for input") and (b) a concept-level
  anti-repeat callout (rename ≠ different idea — `differential_generator`
  → `clinical_filter` → `pediatrician` count as the same edit).
- `src/evolve.py`: both legacy and streaming evolve loops thread
  `max_agents` through to `propose_edits`.
- `scripts/run_pilot.py`: `--max-agents` default 6 → 8 (fits
  triage + 2-3 specialists + answer chains; the AgentClinic v2
  iter-3 example in §7.4 was 8 agents).
- **Patch 4 (doc)**: `best_val_acc > seed_batch_acc` was already
  declared structurally broken in pilot.md §8.4 and §5.2 already
  scores on **test acc + paired-accept rate** — no further doc
  edits needed.
- Validation:
  - `results/smoke_patches_v3/` (B=5 R=1 mediq, 3 min): exit=0,
    streaming round fires, no regressions.
  - `results/sanity_streaming_v3_mediq_s0/` (B=20 R=3 mediq
    seed=0, ~50 min wall, 2026-04-26): 3 rounds completed; round
    1 rejected (Δ=0), round 2 paired ACCEPT (Δ=+5pp on
    `add_agent(differential_diagnostician)`), round 3 rejected
    (Δ=0); final 3-agent graph (planner / executor /
    differential_diagnostician); per-round wall ≈ 10 min, scaling
    linearly from §8's 52 min/round at B=100. Direct
    `_build_user_prompt(max_agents=8, n_agents=2)` invocation
    confirms the `# Constraints` block renders. Cap-binding and
    concept-level-anti-repeat firing are not exercised at R=3
    (best-effort observations deferred to the §5.2 B=100 R=10
    sweep). Detail in `../docs/insights/pilot.md` §8.9.
- Closes §5.1.5; §5.2 multi-seed sweep can run cleanly.

---

## 4. In Progress

*(None — §5.2 sweep is the next-session starting point.)*

---

## 5. Next Up (priority order)

### 5.2 🔜 Multi-seed v2 streaming sweep on 3 domains
- **Why**: noise-averaged final v2 numbers; H2 verdict.
- **What**: streaming mode × 3 domains × seed ∈ {0, 1, 2}
  (~9 sequential runs). Compare streaming-v2 vs n30-v1 baselines.
- **Wall budget**: at MEDIQ ~10 h / run, the full 3 × 3 grid is
  ~90 hours — multi-session. Start with MEDIQ seeds {1, 2}
  (seed-0 already done), then AgentClinic, then FinanceBench.
- **Score**: **test acc + paired-accept rate** (per pilot.md §8.4
  option (C)), not the broken `best_val_acc > seed_batch` criterion.
- **Optional warm-up**: `B=50 R=10` on MEDIQ seed=1 (~5 h) to check
  whether smaller batches still surface paired ACCEPTs at
  acceptable noise — if so, drop B for the rest of the sweep to
  fit more runs in budget.

### 5.3 Random-persona ablation
- **Why**: `project.md` §7 essential ablation; reviewer question #1
  post-MAST. Replace v2 controller's emitted persona text with same
  count of *random* personas; measure delta.

### 5.4 Harness ablation (controller on/off, random topo, fixed topo)
- **Why:** `project.md` §7 essential ablations — cheapest and most
  important alongside §5.3.
- **What:** Add `--controller-mode {none, random, fixed-topo, full}`
  flag to `run_pilot.py`; run all four under matched seed and n_val on
  whichever domain wins §5.2.

### 5.5 Add a second backbone
- **Why:** "Gains hold on ≥2 model families" is on the reviewer bar.
- **Candidates:** Qwen3-72B (open) + one of Claude 4.x / GPT-4.1
  (API). Needs budget decision.

### 5.6 LLM-judge replacement (separate family)
- **Why:** Current sanity uses Qwen-as-judge for FinanceBench +
  AgentClinic. Self-bias flagged in `../docs/insights/pilot.md` §6.1.
  Reviewer will ask.
- **Candidates:** Claude Haiku 4.5 (cheap) or GPT-4.1-mini via API.
  Small judge-only budget.

### 5.7 Direct baselines: ADAS + (Puppeteer or EvoMAC or MaAS)
- **Why:** "How is this not ADAS?" is reviewer question #0.
- **Size:** 3–5 days each. **ADAS is non-negotiable.**

---

## 6. Open Decisions

| Item | Options | Deadline |
|---|---|---|
| **Paper framing** | (A) causal/diagnostic controller · (B) GeoMacroBench + cross-asset · (C) persona-necessity negative result · (A+B) combined | within 1 week |
| **Target venue** | EMNLP 2026 main ARR (5/25) · NeurIPS D&B (5/6) · workshop (summer) | after first real results |
| **Domain pivot** | keep general (GSM8K, etc.) · medical · cross-asset finance | decide with framing |
| **Backbone mix** | Qwen only · open + API mix | after budget check |

---

## 7. Not Started

- Failure-mode taxonomy (MAST-style).
- Cost Pareto pipeline.
- LLM-judge calibration experiment.
- GeoMacroBench construction (only after domain pivot is decided).
- Writing / related-work comparison table.

---

## 8. Deadline Calendar

| Date | Event | Status |
|---|---|---|
| 2026-05-04 | NeurIPS 2026 abstract | D-10 — fallback only |
| 2026-05-06 | NeurIPS 2026 full paper / D&B | D-12 — very aggressive |
| **2026-05-25** | **EMNLP 2026 ARR submission** | **D-31 — primary target** |
| 2026-08-02 | EMNLP direct commitment | D-100 — fallback |
| 2026-08–09 | NeurIPS workshops (expected) | — fallback |

---

## 9. Update Rules (for future-me / Claude)

- After each experiment cycle, shift items between §3 Done · §4 In
  Progress · §5 Next Up.
- Once an Open Decision (§6) is made, remove it and reflect it in
  §1–§2.
- Dates are always YYYY-MM-DD. No relative dates.
- Detailed numbers / plots go into `results/<run_id>/` or
  `../docs/insights/pilot.md`; ROADMAP carries only **a link and a one-line
  summary**. This is a dashboard, not a diary.
