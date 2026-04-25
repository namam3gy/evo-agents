# ROADMAP

Living progress dashboard for the `agent_orchestration` pilot. The
experiment spec lives in `project.md`; real-world findings from
running the pilot are captured in `../docs/insights/pilot.md`. This file is updated
every time an experiment cycle completes.

*Last updated: 2026-04-25*

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

### ✅ Controller v2 — organization-designer framing (2026-04-25)
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
  `CUDA_VISIBLE_DEVICES=1` (GPU 0 contended on shared box).

---

## 4. In Progress

**v2 sanity** (n=10 per benchmark) — checking that controller v2
emits specialist personas and varied edits before re-running n=30.

---

## 5. Next Up (priority order)

### 5.1 🔜 v2 sanity: n=10 on 3 domains
- **Why**: confirm controller v2 actually produces specialist personas
  with domain vocabulary, uses `remove_agent` at least once, and
  varies edits across rounds (per anti-repeat rule). Cheap pre-flight
  before spending hours on n=30.
- **What**: `--n-train 5 --n-val 10 --n-test 10 --max-iters 3 --seed 0`
  on each benchmark with `run-name=sanity_v2_<name>`.
- **Pass criteria**: each new persona contains ≥3 domain-specific
  terms (cardiology / GAAP / etc.) and edits are not all
  `add_agent(verifier)` repeats.

### 5.2 🔜 v2 n=30 measurement on 3 domains
- **Why**: direct comparison to v1's n=30 baseline above.
- **What**: same params as v1 run; `run-name=n30_v2_<name>`.
- **Output**: side-by-side v1 vs v2 table; H2 verdict.

### 5.3 Streaming evolve mode (mini-batch + max_rounds 5–10)
- **Why**: current `evolve.py` does full train→controller→full val per
  iteration (~17 min/iter on FinanceBench at n=30+10). Streaming mode
  with 100–200-sample sliding window unblocks 5–10 rounds in
  reasonable wall.
- **What**: new `--mode streaming --batch-size 100 --max-rounds 10`
  in `run_pilot.py`; moving-average accept criterion.
- **Size**: 1.5 day code + sanity.

### 5.4 Random-persona ablation
- **Why**: `project.md` §7 essential ablation; reviewer question #1
  post-MAST. Replace v2 controller's emitted persona text with same
  count of *random* personas; measure delta.

### 5.5 Harness ablation (controller on/off, random topo, fixed topo)
- **Why:** `project.md` §7 essential ablations — cheapest and
  most important.
- **What:** Add `--controller-mode {none, random, fixed-topo, full}`
  flag to `run_pilot.py`; run all four under matched seed and n_val
  on whichever domain wins §5.2.

### 5.6 Add a second backbone
- **Why:** "Gains hold on ≥2 model families" is on the reviewer bar.
- **Candidates:** Qwen3-72B (open) + one of Claude 4.x / GPT-4.1
  (API). Needs budget decision.

### 5.7 LLM-judge replacement (separate family)
- **Why:** Current sanity uses Qwen-as-judge for FinanceBench +
  AgentClinic. Self-bias flagged in `../docs/insights/pilot.md` §6.1.
  Reviewer will ask.
- **Candidates:** Claude Haiku 4.5 (cheap) or GPT-4.1-mini via API.
  Small judge-only budget.

### 5.8 Direct baselines: ADAS + (Puppeteer or EvoMAC or MaAS)
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
