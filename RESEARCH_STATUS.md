# RESEARCH STATUS — `agent_orchestration` pilot

**Snapshot date**: 2026-04-25 (post controller v2 + v2 n=30 sweep)

A high-level synthesis of where the pilot is, what the latest data says,
and the immediate decision points. For day-to-day tracking see
[`references/roadmap.md`](references/roadmap.md); for tactical lessons see
[`docs/insights/pilot.md`](docs/insights/pilot.md). Korean mirror:
[`RESEARCH_STATUS_ko.md`](RESEARCH_STATUS_ko.md).

---

## TL;DR

1. **v1 controller at n=30** across three domain benchmarks
   (FinanceBench, MEDIQ, AgentClinic) shows evolved at-or-below
   baselines on test (Δ ∈ {0, +6.7, 0} pp, all within noise). v1
   rationales were generic "add a verifier" reflexes.
2. **Controller v2 redesigned as an *organization designer*** — fed
   per-domain briefs, mandated to author specialist personas with cited
   expertise, anti-repeat rule, active prune. Behavior change at
   sanity is dramatic: domain-vocabulary personas
   (`gaap_analyst`, `differential_diagnostician`, `cardiologist`,
   `gastroenterologist`), use of `remove_agent`, tape-citing
   rationales, hand-off chains.
3. **v2 at n=30** still does not produce a defensible test win
   over baselines (Δ ∈ {+10, -3.4, -6.6} pp; the +10pp on FinanceBench
   is same-graph noise, not a real evolution effect). Strict accept
   policy at n=30 + per-iter wall ~10 min means most architectural
   changes are rejected before they get a fair noise-averaged read.
4. **Next**: streaming mini-batch evolve mode (100-200 sample sliding
   window, 5-10 rounds) per the original user redirect — to unblock
   more rounds within a reasonable wall, and to give v2's larger
   architectural moves room to be evaluated more than once.

---

## Document map

| File | Purpose |
|---|---|
| `RESEARCH_STATUS.md` (this file) | Snapshot — where we are, what's next |
| `references/project.md` | Research spec + brutal novelty / venue assessment |
| `references/roadmap.md` | Living dashboard — Done / In Progress / Next / Decisions |
| `docs/insights/pilot.md` | Run-by-run tactical insights (operational, methodological, codebase) |
| `notebooks/calib_01_analysis.ipynb` | Cell-by-cell read-out of the calibration run |
| `data/briefs/{name}.md` | Per-domain brief consumed by controller v2 |
| `README.md` / `CLAUDE.md` | Quick-start + agent guidance |

EN canonical; `*_ko.md` mirrors live alongside.

---

## Current state

Phase: **post v2 n=30 sweep, pre streaming-mode work**.

- Latest commit (head of `feat-domain-pivot`): `d7b926f` — controller v2,
  domain briefs, plumbing, serve_vllm hardening, roadmap update.
- Previous: `1a56154` (RESEARCH_STATUS), `e5725e7` (DAG-discipline
  patch), `a531a3f` (domain pivot + restructure). Branch is on top of
  `main` at `844b81c`.
- Active hypothesis: **H1** partially falsified at v1; **H2** behavior
  satisfied, test win not yet — see [§Hypothesis](#hypothesis).
- Active blocker: per-iter wall (~10 min on FinanceBench) makes >3 rounds
  expensive in current train→controller→val mode; n=30 + Opt-2 strict
  rejects most v2 candidates. Streaming mode (next §) addresses both.

---

## Empirical findings to date

### Pilot infrastructure (validated)

- vLLM 0.19.1 + Qwen2.5-32B-Instruct on shared H200 stable.
  `scripts/serve_vllm.sh` defaults to `CUDA_VISIBLE_DEVICES=0`,
  `EVO_GPU_UTIL=0.55`, `--max-model-len 16384`, and auto-installs gcc
  on missing CC.
- `is_noop` field lands in `evolve_log.json`.
- Opt-2 strict accept semantics (`best_graph` ↔ `best_val_acc` always
  agree).

### `calib_01` (GSM8K, n=50, max_iters=3, ~66 min wall)

|  | val | test | tokens / test task |
|---|---:|---:|---:|
| CoT | 94% | 92% | 350 |
| Planner-Executor | 94% | 90% | 621 |
| Evolved (4 agents, 8 edges) | — | **86%** | **1,303** |

Evolved underperforms both baselines on test by 4-6 pp at 2.1-3.7× the
tokens. v1 rationales generic. → empirical trigger for the domain pivot.

### v1 controller at n=30 (2026-04-25)

3 benchmarks × `--n-train 10 --n-val 30 --n-test 30 --max-iters 3 --seed 0`.

| Domain | CoT test | P-E test | Evolved test | Δ vs best baseline |
|---|---:|---:|---:|---:|
| FinanceBench | 70.0% | 66.7% | 70.0% | 0pp |
| MEDIQ | 43.3% | 43.3% | 50.0% | +6.7pp |
| AgentClinic | 66.7% | 70.0% | 70.0% | 0pp |

v1 controller behavior: FinanceBench emits the same `add_verifier` edit
3 times in a row (no domain vocab, no use of prior_edits feedback);
MEDIQ varies after iter 2 ACCEPT; AgentClinic alternates summarizer ↔
verifier with some domain vocab.

→ H1 weakly falsified at this controller version. Headroom exists but
the v1 controller is too thin to exploit it. Drives the v2 redesign.

### Controller v2 redesign (2026-04-25, commit `d7b926f`)

`src/controller.py::CONTROLLER_SYSTEM` reframed as architect of an *org
chart of domain experts*. Mandatory specialist persona authoring rules
(cited expertise + concrete procedure); generic `verifier / summarizer
/ critic` forbidden unless paired with a specialty. Anti-repeat rule.
Active prune incentive. Domain brief consumed via `_build_user_prompt`
and threaded through `propose_edits → evolve → run_pilot`.

Three domain briefs in `data/briefs/{financebench,mediq,agentclinic}.md`
(~80–110 lines each: task style, common failure modes, useful expertise,
useful patterns, anti-patterns).

### v2 sanity (n=10 per benchmark, controller behavior verification)

| | persona names emitted | domain vocab | `remove_agent` | tape citation |
|---|---|---|---|---|
| FinanceBench | unit_checker, period_verifier, period_specialist, unit_specialist | GAAP, fiscal year, TTM, SEC filings, millions/thousands | 0 | partial |
| MEDIQ | differential_diagnostician, adolescent_specialist, physical_exam_mapper, internal_medicine_differential_diagnostician | base rate × clinical fit, behavioral and eating disorders, MCQ options | 2 | ✅ ("17-year-old girl case", "elevated blood pressure → bulimia") |
| AgentClinic | decisive_diagnosis_writer, triage_specialist | no hedging, canonical clinical term, red flags, triage | 1 | ✅ ("task ac-23, ac-50") |

**Behavior change is dramatic**, especially MEDIQ (specialist + remove)
and AgentClinic (decisive_diagnosis_writer + triage_specialist + remove).

### v2 controller at n=30 (2026-04-25)

3 benchmarks × same params as v1; FinanceBench retried at `max_model_len=16384`
because the v2 controller prompt now exceeds the original 8192 with brief +
multi-agent tapes.

| Domain | CoT test | P-E test | Evolved test | Δ vs best baseline | best_graph |
|---|---:|---:|---:|---:|---|
| FinanceBench (16k retry) | 73.3% | 70.0% | **83.3%** | +10pp* | seed (all iters REJECT) |
| MEDIQ | 43.3% | 46.7% | 43.3% | -3.4pp | 3-agent (iter 2 ACCEPT: remove planner + add differential_diagnostician + physical_exam_mapper) |
| AgentClinic | 60.0% | 73.3% | 66.7% | -6.6pp | seed (all iters REJECT) |

*FinanceBench's +10pp is **measurement noise**, not a v2 win:
`evolved/test=83.3%` was produced by the same seed graph as
`planner_executor/test=70%` in the same run (best_graph == seed because
all iters rejected). vLLM batch ordering / KV-cache state differs
between the two consecutive evaluations, producing same-graph variance
of >10pp at n=30. Cannot be cited as a real effect.

**Notable v2 architectural proposals (even when REJECTED)**:
- AgentClinic iter 3: `add(triage_specialist) + add(gastroenterologist)
  + add(cardiologist) + remove(planner) + remove(executor)` with
  `START → triage → {gastro | cardio} → END` — a literal triage-routed
  specialty department. Exactly the user's organizational vision; got
  rejected because val tied with seed (Opt-2 strict).
- MEDIQ iter 2 ACCEPT: planner removed; `START → differential_diagnostician
  → physical_exam_mapper → END` plus existing executor — the only
  architectural ACCEPT in the v2 sweep.

### v1 vs v2 comparison summary

| Axis | v1 | v2 |
|---|---|---|
| Persona name space | `verifier`, `summarizer`, `reformulator`, `critic` | `gaap_analyst`, `period_validator`, `differential_diagnostician`, `adolescent_specialist`, `physical_exam_mapper`, `triage_specialist`, `gastroenterologist`, `cardiologist`, `decisive_diagnosis_writer` |
| Domain vocab in personas | 0 | dense (GAAP, TTM, fiscal year, base rate × clinical fit, no hedging, red flags, …) |
| Tape-citing rationales | none | yes (specific task IDs, demographic-specific cases) |
| `remove_agent` use | 0 | multi-agent prune, including `remove(planner)` and `remove(executor)` |
| Edit variety across rounds | "verifier" 3 times | per-round different organizational moves |
| **n=30 test Δ vs baseline** | {0, +6.7, 0} pp (all within noise) | {+10*, -3.4, -6.6} pp (the +10 is noise) |

Net read: **v2 is qualitatively a better controller for the user's
intent (real organization design); n=30 measurement does not yet
distinguish it from baseline on test accuracy.** This is the
measurement-design problem, not (necessarily) a controller-quality
problem.

---

## Hypothesis

**H1 (2026-04-24)** — Reflection-only multi-agent evolution improves
val/test on domain-specific tasks. **Status 2026-04-25**: weakly
falsified at the v1 controller version (n=30 evolved at-or-below
baselines on all three domains). Could still hold with v2 + better
measurement.

**H2 (2026-04-25, post-controller-redesign)** — An *organization-
designer* controller fed a domain brief produces specialist personas,
varied edits, active prunes, and yields a measurable val/test
improvement over both baselines AND the v1 controller. **Status
2026-04-25**: **behavior half satisfied** (specialist personas, varied
edits, prunes — all confirmed); **test win not satisfied** (n=30
results within noise of v1).

**H2 falsifier**: even with streaming-mode evolution (5-10 rounds at
100–200-sample mini-batches) and multi-seed runs, evolved still ≈
baselines on test → fall back to Framing C (persona-necessity negative
result) and reframe paper accordingly.

---

## Next decisions (immediate, in order)

| # | Action | Output | Decision triggered |
|---|---|---|---|
| 1 | **Streaming evolve mode** in `src/evolve.py` (mini-batch + max_rounds 5–10 + moving-average accept) | Allow 5–10 rounds within ≲1 h wall; multiple noise-averaged validations per architectural change | Will the evolved graph stabilize and beat baselines once v2 has more rounds and less noisy validation? |
| 2 | Re-run 3 domains × streaming mode × multi-seed (≥3) | Noise-averaged v2 numbers; final H2 verdict | Final framing decision (B / C / A+B) |
| 3 | Random-persona ablation (per `roadmap.md` §5.4) | Whether v2's specialty wins are real or could be replicated by random-named personas | Reviewer-bar question #1 (post-MAST) |

After #1+#2, branch:
- **Branch B**: streaming v2 shows ≥1 domain with evolved > baseline at
  multi-seed → commit to Framing B / A+B for EMNLP ARR
  (D-31, 2026-05-25).
- **Branch C**: still ≈ baseline → pivot to Framing C
  (persona-necessity negative result), use the rich v2 behavior
  evidence as **support** for the negative-result claim
  ("we redesigned the controller to do exactly what real org-design
  would suggest, and it still didn't beat baselines — therefore the
  bottleneck is not controller laziness").

---

## Open decisions (`roadmap.md` §6)

| Item | Open since | Notes |
|---|---|---|
| Paper framing | 2026-04-24 | Resolves after streaming + multi-seed (≤1 week) |
| Target venue | 2026-04-24 | EMNLP ARR (5/25) primary; D&B (5/6) aggressive |
| Backbone mix | 2026-04-24 | Second backbone needs budget decision |

---

## Risk register

1. **Measurement noise dominates the signal at n=30**. Same graph,
   same data, evaluated twice in the same run produces test-accuracy
   deltas of 10+pp due to vLLM batch ordering / KV-cache state. Until
   we average over multiple seeds (or use deterministic batching), we
   cannot trust ≤10pp differences.
2. **Time-to-deadline**: D-31 to EMNLP ARR. Reviewer-bar checklist
   below: 0/9 cleared. Realistic full-clearance is 6-8 weeks per
   `project.md` §5. Mitigation: scope to A+B (or C) framing.
3. **Single-H200 bottleneck for evo_agents** (GPU 0). Sibling projects
   on GPU 1. Multi-backbone work requires API budget.
4. **LLM-judge self-bias** (FinanceBench, AgentClinic): the same
   Qwen2.5-32B judges itself. Mitigation: separate-family judge
   (`roadmap.md` §5.7).
5. **The pivot itself is a story we owe the reader**: not just "domain
   helps" but "GSM8K was the wrong testbed for the right reasons."

---

## Paper-readiness self-assessment

`project.md` §3's reviewer-bar checklist:

| Item | Status |
|---|---|
| Best-of-N single-agent @ matched compute | ❌ |
| ≥2 backbone families | ❌ — Qwen only |
| ≥3 heterogeneous benchmarks (incl. non-saturated) | ⚠️ 3 measured at n=30 (v1 + v2), need n≥100 with multi-seed for defensible numbers |
| Direct comparison vs ADAS + 1 of (Puppeteer / MaAS / EvoMAC) | ❌ — ADAS non-negotiable |
| Harness ablation (controller on/off, random persona, fixed topo) | ❌ |
| Failure-mode taxonomy (MAST-style) | ❌ |
| Cost Pareto (tokens × wall × $) | ⚠️ tokens partially logged |
| LLM-judge calibration (≥100 samples, human κ) | ❌ |
| Code + prompts + tool defs + model versions released | ⚠️ internal |

**Net**: 0 cleared, 3 partial, 6 not started.

---

## One-line summary

> v1 controller at n=30 → at-or-below baselines (consistent with
> calib_01); v2 controller redesigned as organization designer →
> dramatically better behavior (specialist personas, prune, hand-off
> chains) but still no test win at n=30 because measurement noise
> dominates and only 3 rounds fit in the wall budget. Next: streaming
> mini-batch mode for 5–10 rounds with noise-averaged accept, then
> multi-seed runs, then framing decision.
