# Evo-agents Presentations — Design (2026-04-26)

User-approved scope for two slide decks built from the work captured in
`docs/insights/pilot.md`, `references/roadmap.md`, and `notebooks/`.

## Decisions captured

| Knob | Choice |
|---|---|
| Slide count per deck | ~30-35 (Standard, "B"). PPT 2 lean variant ~25. |
| Figure depth | Existing `results/<run>/plots/*.png` reused + 6 new figures (`assets/`) |
| Ongoing §5.2 MEDIQ seed=1 run | Mark as **ongoing**, partial R0–R3 results, "to be updated" |
| Audience PPT 1 | ML/DL academic generalist (multi-agent working knowledge) |
| Color palette | **Forest & Moss** (forest `#2C5F2D`, moss `#97BC62`, cream `#F5F5F5`) — evolution motif |
| Typography | Calibri / Calibri Light (English); Korean falls back to system Korean font |

## Deliverables

```
docs/presentations/2026-04-26-evo-agents/
├── DESIGN.md                        # this file
├── 1-advisor-talk.pptx              # English, ~32 slides
├── 2-paper-style-ko.pptx            # Korean, ~25 slides
├── 2-paper-style-ko.md              # Korean per-slide commentary (newcomer-friendly)
└── assets/
    ├── dag_baselines.png
    ├── controller_v1_v2_loop.png
    ├── paired_batch_flow.png
    ├── dag_evolution_seq.png
    ├── per_round_delta.png
    └── token_cost_pareto.png
```

## PPT 1 outline (advisor talk, 32 slides, English)

Time-ordered: each stage = (setup → result → insight) bundle.

| # | Bundle | Content |
|---|---|---|
| 1-2 | Title + hook | One-liner ("Can a multi-agent DAG evolve from reflection alone?") + roadmap dashboard |
| 3-5 | Setup | DAG formalism, CoT vs P-E baselines, pilot infra |
| 6-9 | calib_01 (GSM8K) | results + figs + insights (GSM8K mismatch, opt-2 strict) |
| 10-13 | Domain pivot | why GSM8K wrong, 3 new benchmarks, sanity n=3 |
| 14-16 | v1 controller @ n=30 | 3-domain table + insight: H1 partially falsified, "verifier reflex" |
| 17-21 | Controller v2 (org-designer) | system-prompt redesign + domain briefs + sanity n=10 + n=30 results |
| 22-25 | Streaming mode | rationale + paired-batch flow + run #1 (4/10 ACCEPT) + 3 blockers |
| 26-28 | §5.1.5 patches + sanity | three patches + sanity_v3 + soft-constraint limits |
| 29 | §5.2 ongoing | seed=1 partial + ETA + next steps |
| 30-31 | Novelty & weaknesses | honest self-assessment |
| 32 | Q&A / backup | reviewer-bar coverage, ADAS / MaAS comparison plan |

## PPT 2 outline (paper-style, 25 slides, Korean, lean)

Maps paper chapters to slides; each slide gets one paragraph in the md companion.

| # | Chapter | # of slides |
|---|---|---:|
| 1 | Title + Abstract | 1 |
| 2 | Introduction | 2 |
| 3 | Related Work | 2 |
| 4 | Problem & Definitions | 2 |
| 5 | Method | 4 |
| 6 | Implementation | 1 |
| 7 | Experimental Setup | 2 |
| 8 | Experiments & Results | 6 |
| 9 | Analysis & Discussion | 2 |
| 10 | Limitations & Future Work | 2 |
| 11 | Conclusion | 1 |

## Novelty / weaknesses (explicit in both decks)

**Novelty (strong)**
- Reflection-only multi-agent evolution (no search / no RL) — real differentiator vs ADAS / MaAS / Puppeteer.
- Controller v2: organization-designer framing (domain brief + specialist personas).
- Streaming paired-batch evolve mode (legacy 1/9 → 4/10 ACCEPT in run #1).

**Weaknesses (honest)**
- v2 @ n=30 does not beat baselines on test; ±13pp measurement noise dominates architectural effect (§7.5).
- LLM-judge is same-family Qwen → self-bias risk.
- Single backbone (Qwen2.5-32B), single judge.
- B=100 R=10 streaming wall ≈ 9-10h × seed × domain → 3×3 sweep = ~90h.
- ADAS / MaAS / Puppeteer direct comparison not yet done (reviewer question #0).
- Concept-level anti-repeat patch is soft-constraint only — may not fire (sanity_v3 round 2 was an exact repeat).

## Working order

1. Generate the 6 new figures into `assets/` (matplotlib + networkx, ~30 min).
2. Build PPT 1 with python-pptx (~1h).
3. Build PPT 2 with python-pptx (~40 min).
4. Write Korean md companion (~30 min, paragraph per slide).
5. QA: pptx → pdf → jpg → subagent visual inspection → fix → re-verify.
6. Commit `docs/presentations/2026-04-26-evo-agents/`.
