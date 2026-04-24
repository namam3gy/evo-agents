# ROADMAP

Living progress dashboard for the `agent_orchestration` pilot. The
experiment spec lives in `project.md`; real-world findings from
running the pilot are captured in `../docs/insights/pilot.md`. This file is updated
every time an experiment cycle completes.

*Last updated: 2026-04-24*

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

### 2.1 Methodological (H1, post-pivot)

**H1 (2026-04-24)**: Reflection-only multi-agent evolution produces
a measurable val/test improvement over CoT and Planner-Executor
baselines **on domain-specific tasks where personas carry
heterogeneous expertise or information** (FinanceBench, AgentClinic;
MEDIQ is sanity-only per §6.4 of `../docs/insights/pilot.md`).

**Empirical trigger**: `calib_01` on GSM8K showed evolved < both
baselines on test (§4.1 of `pilot.md`); GSM8K also structurally
lacks the information-asymmetric lever multi-agent exploits. The
pivot commits us to also showing GSM8K was *the wrong domain*,
not just *a hard one*.

**Falsifier**: if evolved ≈ baseline across *all three* domains at
n ≥ 30 (§5.2), the research reframes toward Framing C
(persona-necessity negative result).

**Secondary methodological questions**:
1. Does evolved transfer to test (val↔test gap < 3pp)?
2. What kinds of edits does the controller actually emit? Do
   rationales cite specific tape examples, or default to generic
   "add an agent"? (Sanity already shows *some* domain adaptation —
   AgentClinic's "summarizer for concise diagnosis" vs GSM8K's
   "arithmetic verifier" reflex.)

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
- Sanity at n=3 per benchmark confirms pipeline runs end-to-end and
  the controller produces **domain-adaptive rationales** (first
  positive signal of the pivot). Artifacts in
  `results/sanity_{mediq,agentclinic,financebench}/`.
- Known issue: FinanceBench long-context displaces the controller's
  DAG discipline — §5.1 before scale.

---

## 4. In Progress

*(Nothing active — waiting on the next experiment selection.)*

---

## 5. Next Up (priority order)

### 5.1 🔜 Patch controller prompt for long-context DAG discipline
- **Why:** FinanceBench sanity showed controller emits DAG-invalid
  edits (`planner` unreachable from END) twice in a row when evidence
  text dominates the prompt (`../docs/insights/pilot.md` §6.3).
  Unfixed, FinanceBench evolve phase is effectively zero-iter.
- **What:** short, targeted tweak in
  `src/controller.py::CONTROLLER_SYSTEM` — reinforce the DAG rule
  and/or promote `describe(graph)` to a high-salience position
  (e.g. after the user prompt, not before). Re-run n=3 sanity.
- **Size:** ~30 min including smoke.

### 5.2 🔜 Domain-pivot first measurement: n_val = n_test ≈ 30 per benchmark
- **Why:** n=3 sanity shows the pipeline runs on all three domains
  and the controller rationale is domain-adaptive, but no meaningful
  accuracy signal can come from n=3 (sample error ±25+ pp).
- **What:** per benchmark, run `--n-train 10 --n-val 30 --n-test 30
  --max-iters 3 --seed 0`. Compare CoT / P-E / Evolved.
  Expected wall: 20–40 min / benchmark × 3 = 1.5 h total.
- **Output:** First domain-pivot evidence. Three possible patterns:
  (a) evolved > baseline in at least one domain → framing B / A+B
  becomes viable; (b) evolved ≈ baseline everywhere → framing C
  (persona-necessity negative result) confirmed; (c) mixed — deeper
  per-domain follow-ups.
- **Blocker:** §5.1 for FinanceBench specifically.

### 5.3 Harness ablation (controller on/off, random persona, fixed topo)
- **Why:** `project.md` §7 essential ablations — cheapest and
  most important. The **random-persona control** in particular is
  effectively mandatory post-MAST (reviewer question #1).
- **What:** Add `--controller-mode {none, random, fixed-topo, full}`
  flag to `run_pilot.py`; run all four under matched seed and n_val
  on whichever domain wins §5.2.

### 5.4 Add a second backbone
- **Why:** "Gains hold on ≥2 model families" is on the reviewer bar.
- **Candidates:** Qwen3-72B (open) + one of Claude 4.x / GPT-4.1
  (API). Needs budget decision.

### 5.5 LLM-judge replacement (separate family)
- **Why:** Current sanity uses Qwen-as-judge for FinanceBench +
  AgentClinic. Self-bias flagged in `../docs/insights/pilot.md` §6.1.
  Reviewer will ask.
- **Candidates:** Claude Haiku 4.5 (cheap) or GPT-4.1-mini via API.
  Small judge-only budget.

### 5.6 Direct baselines: ADAS + (Puppeteer or EvoMAC or MaAS)
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
