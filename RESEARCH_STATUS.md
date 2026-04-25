# RESEARCH STATUS — `agent_orchestration` pilot

**Snapshot date**: 2026-04-25

A high-level synthesis of where the pilot is, what the latest data says,
and the immediate decision points. For day-to-day tracking see
[`references/roadmap.md`](references/roadmap.md); for tactical lessons see
[`docs/insights/pilot.md`](docs/insights/pilot.md). Korean mirror:
[`RESEARCH_STATUS_ko.md`](RESEARCH_STATUS_ko.md).

---

## TL;DR

1. Pipeline is end-to-end stable on three domain benchmarks
   (FinanceBench, MEDIQ, AgentClinic) after the 2026-04-24 pivot away
   from GSM8K.
2. First calibration run (`calib_01`, GSM8K, n=50) showed evolved <
   both baselines on test (-4 to -6 pp at 2.1-3.7× token cost) — the
   empirical trigger for the pivot.
3. Next decision point: **n=30 first measurement on each new domain**
   (after the FinanceBench controller-prompt patch). Three branches
   off that — Framing B (one domain wins), Framing C (negative
   result), Framing A+B (mixed → causal-controller story).

---

## Document map

| File | Purpose |
|---|---|
| `RESEARCH_STATUS.md` (this file) | Snapshot — where we are, what's next |
| `references/project.md` | Research spec + brutal novelty / venue assessment |
| `references/roadmap.md` | Living dashboard — Done / In Progress / Next / Decisions |
| `docs/insights/pilot.md` | Run-by-run tactical insights (operational, methodological, codebase) |
| `notebooks/calib_01_analysis.ipynb` | Cell-by-cell read-out of the calibration run |
| `README.md` / `CLAUDE.md` | Quick-start + agent guidance |

EN is canonical; `*_ko.md` mirrors live alongside.

---

## Current state

Phase: **post-pivot, pre-first-domain-measurement**.

- Latest commit: `e5725e7` (controller DAG-discipline clarification) on
  top of `a531a3f` (domain pivot + restructure).
- Active branch: `feat-domain-pivot` → ready to merge to `main`.
- Active hypothesis: **H1** (post-pivot) — see [§Hypothesis](#hypothesis).
- Active blocker: FinanceBench long-context input was displacing
  controller DAG discipline (`pilot.md` §6.3). Patch landed as
  `e5725e7`; n=3 sanity re-run still owed.

---

## Empirical findings to date

### Pilot infrastructure (validated)

- vLLM 0.19.1 + Qwen2.5-32B-Instruct on shared H200 stable with
  `EVO_GPU_UTIL=0.55`.
- `is_noop` field lands in `evolve_log.json`; all 3 iters of `calib_01`
  show `is_noop == False` — the controller does not collapse to no-op
  even under saturated val.
- Opt-2 strict accept semantics in `src/evolve.py`: the
  `best_graph` ↔ `best_val_acc` decoupling that surfaced in `calib_01`
  is resolved (verified on `results/smoke_opt2/`).

### `calib_01` (GSM8K, n=50, max_iters=3, ~66 min wall)

|  | val | test | tokens / test task |
|---|---:|---:|---:|
| CoT | 94% | 92% | 350 |
| Planner-Executor | 94% | 90% | 621 |
| Evolved (4 agents, 8 edges) | — | **86%** | **1,303** |

**Headline**: evolved underperforms both baselines on test by 4-6 pp at
2.1-3.7× the tokens. With n=50 the gap is at the sample-error floor
(~±7 pp 95% CI for a 3-sample comparison), so not proof — but it is
consistently on the wrong side of zero.

**Diagnosis** (`pilot.md` §4.3): controller rationales were thin —
generic "add a verifier" / "add a reformulator" reflexes rather than
tape-grounded causal reads. Exactly the failure mode that Framing A
(causal/diagnostic controller) is designed to attack.

### Domain-pivot sanity (n=3 per benchmark, 2026-04-24)

| Benchmark | Pipeline runs E2E | Controller domain-adaptive |
|---|---|---|
| MEDIQ | ✅ | tie → REJECTED (Opt-2) |
| AgentClinic | ✅ | ✅ proposed `add_agent(summarizer)` for "concise diagnosis" |
| FinanceBench | ✅ | ❌ emitted DAG-invalid edits twice — patched in `e5725e7` |

Sanity accuracies at n=3 are too noisy to compare across methods
(vLLM temp=0 non-determinism at batch boundaries + LLM-judge variance).
But two qualitative signals matter:
- **Positive**: controller rationales **change with domain**. The
  GSM8K "arithmetic verifier" reflex is replaced by AgentClinic's
  "summarizer for concise diagnosis." First reason to believe the
  domain pivot has a chance.
- **Negative**: FinanceBench's long evidence context displaced the
  controller's DAG reasoning. The `e5725e7` patch addresses the
  obvious failure mode; whether the controller now produces useful
  edits on FinanceBench is open.

---

## Hypothesis

**H1 (2026-04-24)**: Reflection-only multi-agent evolution produces a
measurable val/test improvement over CoT and Planner-Executor baselines
**on domain-specific tasks where personas carry heterogeneous expertise
or information** (FinanceBench, AgentClinic). MEDIQ in non-interactive
initial mode is sanity-only — Li et al. 2024 already documented that
the non-interactive setting underperforms the interactive one on
GPT-3.5, so a near-baseline result there does *not* falsify H1.

**Falsifier**: if evolved ≈ baseline across *all three* domains at
n ≥ 30, reframe toward Framing C (persona-necessity negative result).

**Empirical trigger for H1's domain restriction**: GSM8K (self-contained
text, linear arithmetic, ~94% single-model saturation) structurally
lacks the information-asymmetric lever that multi-agent exploits. The
`calib_01` regression is read as *"the wrong domain"*, not *"a hard
domain"*.

---

## Next decisions (immediate, in order)

| # | Action | Output | Decision triggered |
|---|---|---|---|
| 1 | Re-run FinanceBench n=3 sanity post-`e5725e7` | Whether DAG validity is restored on long-context input | Unblocks #2 for FinanceBench |
| 2 | Domain-pivot first measurement: n_val = n_test ≈ 30 per benchmark | First real accuracy signal across three domains (~1.5 h wall) | **Framing B vs C vs A+B** |
| 3 | Tag rationales (cites specific tape vs generic) | Quantified rationale-quality signal | Input to Framing A scope |

After #2, branch:
- **Branch B**: ≥1 domain shows evolved > baseline → commit to
  Framing B (or A+B), aim EMNLP ARR (D-31, 2026-05-25).
- **Branch C**: evolved ≈ baseline everywhere → pivot to Framing C
  (negative result), reframe as MAST-style "persona-necessity
  investigation" — fast, cheap, credible in the 2026 climate per
  `project.md` §7.
- **Branch A+B**: mixed across domains → tighten to "diagnostic
  controller, evaluated on the domain where it works."

---

## Open decisions (`roadmap.md` §6)

| Item | Open since | Notes |
|---|---|---|
| Paper framing | 2026-04-24 | Resolves after §5.2 measurement (≤1 week) |
| Target venue | 2026-04-24 | EMNLP ARR (5/25) primary; D&B (5/6) aggressive |
| Backbone mix | 2026-04-24 | Second backbone needs budget decision |

---

## Risk register

1. **Time-to-deadline**: D-31 to EMNLP ARR. Reviewer-bar checklist
   below has 9 items; ~2/9 cleared. Realistic full-clearance is
   6-8 weeks per `project.md` §5. **Mitigation**: scope to A+B (or C)
   framing rather than the full reviewer ask; ARR is the cycle that
   *frames* the contribution, not the one that *proves* it.
2. **Single-H200 bottleneck**: §5.2 scaling extrapolated to
   ~5-6 h / seed × 3 seeds = 15-18 h wall (`pilot.md` §4.4). Sequential
   per backbone. Multi-backbone work requires additional GPU allocation
   or API budget.
3. **LLM-judge self-bias** (FinanceBench, AgentClinic): the same
   Qwen2.5-32B judges itself. Reviewer will ask. **Mitigation**:
   `roadmap.md` §5.5 — separate-family judge (Claude Haiku 4.5 or
   GPT-4.1-mini) on a judge-only budget.
4. **The pivot itself is a story we owe the reader**: not just "domain
   helps" but "GSM8K was the wrong testbed for the right reasons."
   `pilot.md` §6 has the argument but it needs scaled-n confirmation.

---

## Paper-readiness self-assessment

`project.md` §3's reviewer-bar checklist:

| Item | Status |
|---|---|
| Best-of-N single-agent @ matched compute | ❌ |
| ≥2 backbone families | ❌ — Qwen only |
| ≥3 heterogeneous benchmarks (incl. non-saturated) | ⚠️ 3 scaffolded, 0 measured at scale |
| Direct comparison vs ADAS + 1 of (Puppeteer / MaAS / EvoMAC) | ❌ — ADAS non-negotiable |
| Harness ablation (controller on/off, random persona, fixed topo) | ❌ |
| Failure-mode taxonomy (MAST-style) | ❌ |
| Cost Pareto (tokens × wall × $) | ⚠️ tokens partially logged |
| LLM-judge calibration (≥100 samples, human κ) | ❌ |
| Code + prompts + tool defs + model versions released | ⚠️ internal |

**Net**: 0 cleared, 3 partial, 6 not started. Full clearance requires
6-8 weeks. EMNLP ARR (D-31) is realistic only if we tighten scope to a
defensible subset (A+B or C) — not the full reviewer ask.

---

## One-line summary

> Pivoted off GSM8K after `calib_01` showed evolved < baseline; three
> new domain benchmarks scaffolded with the first positive signal of
> domain-adaptive controller rationales; FinanceBench DAG-discipline
> patched (`e5725e7`); the next move is the n=30 first measurement that
> decides Framing B vs C vs A+B.
