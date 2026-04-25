# A brutally honest assessment of your self-evolving multi-agent paper proposal

**Bottom line up front:** The core idea — "a controller agent that iteratively observes execution and modifies the number of agents, personas, prompts, and call graph" — is **not novel in 2026**. At least six strong prior works already cover this space (ADAS, Puppeteer/Evolving Orchestration at NeurIPS 2025, MaAS at ICML 2025 Oral, Agent Symbolic Learning, EvoMAC at ICLR 2025, AutoAgents at IJCAI 2024), and a 2026 successor line (HyperAgents, Darwin Gödel Machine, MAS²) has already moved the frontier to recursive self-modification. Submitting the idea as described will almost certainly be desk-flagged or rejected as incremental unless you identify a sharper, more specific novelty axis. NeurIPS 2026 main-track acceptance probability is **\~3–6%** as currently scoped; EMNLP 2026 main-track is **\~5–10%**. The realistic, achievable targets are either (a) EMNLP 2026 main with a strongly reframed contribution, (b) a NeurIPS workshop (Lifelong Agents, MemAgents, Agents in the Wild — though most 2026 deadlines have passed), or (c) COLM 2027 with a much stronger story. Timeline is the secondary bottleneck: NeurIPS 2026's paper deadline is **May 6, 2026 (12 days from today)**, not 3 weeks; EMNLP 2026 via ARR is **May 25, 2026 (31 days)**, which is the more realistic target.

The rest of this report details the prior-art landscape, a concrete novelty triage, reviewer-preempting analysis, a domain/benchmark recommendation, and three concrete differentiation strategies that could move the acceptance probability materially.

---

## 1. Related work: the space is crowded and the closest priors already cover all four of your axes

The literature breaks into seven clusters. I'll highlight the critical papers in each with their exact coverage of your four controller dimensions: **(a)** modify # agents, **(b)** modify personas, **(c)** modify prompts, **(d)** modify topology.

### Cluster A — Direct controller-rewrites-team prior art (your main competition)

**ADAS — Automated Design of Agentic Systems** (Hu, Lu, Clune, **ICLR 2025**, arXiv:2408.08435). A meta-agent iteratively programs new agentic systems in **Python code** over an archive of discoveries. Because code is Turing-complete, its search space already subsumes your four dimensions. Evaluated on ARC, DROP, MGSM, MMLU, GPQA. Coverage: **✅a, ✅b, ✅c, ✅d**. This is the single most dangerous citation for your proposal — if your controller uses code edits, reviewers will immediately ask "how is this not ADAS?"

**Multi-Agent Collaboration via Evolving Orchestration — "Puppeteer"** (Dang et al., Tsinghua, **NeurIPS 2025**, arXiv:2505.19591). An orchestrator agent evolves mid-execution and "adaptively promotes more effective agents while removing those that are less useful," observing compact cyclic structures emerge. This matches **your exact framing** of an in-task controller rewriting the team. Coverage: **✅a, ⚠️b, ⚠️c, ✅d**. The fact that this is NeurIPS 2025 (not 2024) means the program committee has *already accepted* your basic story once.

**MaAS — Multi-Agent Architecture Search via Agentic Supernet** (Zhang et al., **ICML 2025 Oral**, arXiv:2502.04180). A learned controller samples a query-dependent sub-architecture from an "agentic supernet" over operators (CoT, Debate, ReAct, etc.); execution feedback jointly updates the supernet distribution and operators via Monte-Carlo gradients. The word **"controller" is explicit** in the paper. Coverage: **✅a, ⚠️b, ⚠️c, ✅d**.

**AutoAgents** (Chen et al., **IJCAI 2024**, arXiv:2309.17288). Planner + Agent-Observer + Action-Observer drafts and refines a specialized agent team with roles/personas from a task description. The "observer reflects on designated plans and agents' responses and iteratively improves them" is linguistically almost identical to your proposal. Coverage: **✅a, ✅b, ✅c (at draft), ⚠️d**.

**Agent Symbolic Learning** (Zhou et al., AIWaves, arXiv:2406.18532). Treats pipeline as a computational graph; defines "language loss" and "language gradients" to back-propagate feedback through **prompts, tools, and pipeline structure itself**. Their symbolic optimizers explicitly edit the call graph from execution traces. Coverage: **✅a, ⚠️b, ✅c, ✅d**.

**EvoMAC — Self-Evolving Multi-Agent Collaboration Networks** (Hu et al., **ICLR 2025**, arXiv:2410.16946). Test-time textual back-propagation iteratively edits agents and edges during execution, evaluated on software-development benchmarks. **Covers all four axes iteratively at test time** — the only real gap versus your proposal is that it's SE-domain-specific and uses test cases as the feedback proxy. Coverage: **✅a, ✅b, ✅c, ✅d, iterative at test-time**.

### Cluster B — Query-level meta-agent generation

**FlowReasoner** (Gao et al., arXiv:2504.15257, Apr 2025). RL-trained meta-agent (DeepSeek-R1-distilled) generates a personalized MAS per user query. +10.52% over o1-mini. One-shot per query, not iterative. **✅a, ✅b, ✅c, ✅d** but single-pass.

**MAS-GPT** (Ye et al., **ICML 2025**, arXiv:2503.03686). SFT-trained 32B LLM that emits complete executable MAS code per query. One-shot. **✅a, ✅b, ✅c, ✅d** but single-pass.

**MAS²** (arXiv:2509.24323, Sept 2025). "MAS recursively generates another MAS" via collaborative tree optimization. Directly in your space.

### Cluster C — Self-modifying single agents

**Gödel Agent** (Yin et al., arXiv:2410.04444). Self-referential: inspects and modifies its own code including its self-improvement logic. **Darwin Gödel Machine** (Zhang, Hu, Lu, Lange, Clune, arXiv:2505.22954, May 2025) extends this with archive-based open-ended evolution; 20%→50% on SWE-bench. **HyperAgents / DGM-H** (Meta FAIR, ICLR 2026, arXiv:2603.19461) integrates task-agent + meta-agent in a single editable program where the meta-agent rewrites both. These are your cleanest 2026 benchmarks to beat conceptually.

### Cluster D — Graph/workflow optimization (the "old guard")

**GPTSwarm** (Zhuge et al., **ICML 2024 Oral**) — graph-based node (prompt) + edge (topology) optimization via REINFORCE. **AFlow** (Zhang et al., **ICLR 2025 Oral**) — MCTS over code-level workflows with an operator library. **AgentSquare** (Shang et al., ICLR 2025) — modular search over Planning/Reasoning/Tool-Use/Memory. **MASS** (arXiv:2502.02533) — interleaved prompt + topology search. **EvoFlow** (arXiv:2502.07373) — niching evolutionary population of workflows. **G-Designer** (arXiv:2410.11782) — GNN-based task-adaptive topology. **DyLAN** (arXiv:2310.02170, ICLR 2024 rejected but highly cited) — dynamic LLM-agent network with importance-score pruning. **ScoreFlow** (arXiv:2502.04306) — Score-DPO for workflow preference optimization.

### Cluster E — Prompt/program optimization foundations

DSPy (Khattab et al., ICLR 2024), MIPROv2 (EMNLP 2024), **GEPA** (Agrawal et al., ICLR 2026 Oral — reflective prompt evolution outperforming RL with 35× fewer rollouts), **TextGrad** (Yuksekgonul et al., Nature 2025), **Trace/OptoPrime** (Cheng et al., NeurIPS 2024), OPRO (Yang et al., ICLR 2024), Promptbreeder (ICML 2024), FunSearch (Nature 2024), EvoPrompt (ICLR 2024), Archon (Saad-Falcon et al., ICLR SSI-FM 2025 Oral — inference-time architecture search). These are textual-gradient and LLM-as-optimizer primitives; you'll need to cite and compare to at least TextGrad, GEPA, and Trace.

### Cluster F — Medical multi-agent systems

**MedAgents** (Tang et al., ACL 2024 Findings), **MDAgents** (Kim et al., **NeurIPS 2024 Oral** — adaptive Solo/MDT/ICT triage), **AgentClinic** (Schmidgall et al., **ICLR 2025** — sequential dialogue benchmark, multimodal, bias variants), **ColaCare** (WWW 2025 — EHR+LLM fusion), **Agent Hospital / MedAgent-Zero** (Li et al., Tsinghua, arXiv:2405.02957 — 32-department simulacrum with self-evolving doctor), **AI Hospital** (COLING 2025), **ClinicalAgent/CT-Agent** (ACM-BCB 2024), **MedAide** (arXiv:2410.12532), **MEDCO** (arXiv:2408.12496), **KG4Diagnosis** (AAAI Bridge 2025), **MAI-DxO + SDBench** (Microsoft, arXiv:2506.22405 — 5 functional roles Dr. Hypothesis/Test-Chooser/Challenger/Stewardship/Checklist reach 80–85.5% on NEJM-CPC vs. 20% for physicians), **AMIE** (Google, *Nature* 2025), Polaris (2403.13313), KAMAC (2509.14998), MedAgentSim (2025).

### Cluster G — Financial multi-agent systems

**FinCon** (Yu et al., **NeurIPS 2024** — Manager–Analyst hierarchy with conceptual verbal reinforcement), **TradingAgents** (Xiao et al., **AAAI 2025** — 7-role firm hierarchy with Bull/Bear debate), **FinAgent** (KDD 2024), **FinMem** (AAAI-SS 2024), **FinRobot** (ICAIF 2024), **TradExpert** (AAAI 2025), **AlphaAgents** (arXiv:2508.11152), **StockAgent** (arXiv:2407.18957), **QuantAgent**, **ATLAS**, **MASCA**. Benchmarks: **FinBen** (NeurIPS 2024 D&B — 42 datasets), **FinanceBench** (Patronus AI), **FinQA/ConvFinQA** (EMNLP 2021/2022), BizBench (ACL 2024), MultiFinBen, **FINSABER** (Li et al. 2025 — bias-controlled backtest that **deflates prior LLM trading gains**), **Agent Market Arena**, **StockBench**. Key caution: **FINSABER empirically shows previously reported LLM trading advantages collapse under survivorship/look-ahead/data-snooping controls.**

---

## 2. Brutal novelty assessment

**The honest verdict:** Your proposal, as stated, is a **repackaging** of already-published work. Every single element has been published:

- "Controller observes execution, then rewrites team" → **Puppeteer (NeurIPS 2025)**, Agent Symbolic Learning, EvoMAC.
- "Modifies agents/personas/prompts/topology jointly" → **ADAS (ICLR 2025)**, EvoMAC, FlowReasoner, MAS-GPT.
- "Controller as natural-language meta-reasoner" → AutoAgents, Agent Symbolic Learning (language gradients).
- "Controller as code/DAG modifier" → ADAS, AFlow, Gödel Agent, Darwin Gödel Machine, Meta-Harness.
- "Starts simple (planner/executor) and grows" → Agent Hospital (self-evolving doctor), EvoAgent (EA from a single agent), AutoAgents (drafts team from scratch).
- "Medical specialist personas" → MedAgents, MDAgents, MAI-DxO, Agent Hospital.
- "Financial bond/equity/geopolitical/quant personas" → TradingAgents (bull/bear/news/technical), FinCon (7-analyst hierarchy).

**What could still be genuinely new, if you sharpen the contribution:**

1. **Cross-asset financial decomposition (bond + equity + geopolitics + quant)** is a real whitespace. No existing MAS treats fixed income as a first-class agent, and no system explicitly reasons across asset classes with a geopolitics specialist driving cross-asset causal chains (e.g., Fed move → DXY → EM bonds → commodity equities). **This is the single most defensible novelty claim available to you.** But it is a domain contribution, not a method contribution, and reviewers will say "TradingAgents already does Bull/Bear/News/Technical."
2. **Iterative in-task controller editing of personas (not just prompts or topology), grounded in diagnosed communication-bottleneck signals from the trace.** EvoMAC does personas iteratively but only in SE; Puppeteer does team composition but not persona rewriting; ADAS does everything but offline. A controller that specifically diagnoses *which persona is miscommunicating with which* and surgically rewrites the offender is a narrower but defensible niche.
3. **Observability-first formulation.** If you frame the contribution as a **diagnostic/causal controller** — where the controller runs a causal analysis of the trace (e.g., counterfactual replay "what if this edge were removed?") before editing — that is genuinely underexplored.

**What reviewers will say (anticipate these critiques literally word-for-word):**

- *"The proposed framework reads as a natural-language-level re-implementation of ADAS/Puppeteer/Agent Symbolic Learning. The authors must compare directly and quantitatively."*
- *"The controller's four action primitives (add/remove/modify persona/rewire) are an enumeration of operations already implicit in ADAS's code-search space. No formal argument is given for why this decomposition is preferable."*
- *"The gains reported on MedQA/MedMCQA are marginal on frontier backbones and likely reflect prompt-diversity rather than structural evolution. Please ablate against best-of-N single-agent at matched token budget."* (This critique is now standard post-MAST.)
- *"The paper does not compare to Puppeteer (NeurIPS 2025), MaAS (ICML 2025), EvoMAC (ICLR 2025), FlowReasoner, or Agent Symbolic Learning."*
- *"No theoretical characterization of when the controller converges, when it oscillates, or when it causes performance regressions."*
- *"No cost/latency analysis. Does the controller LLM overhead dominate the multi-agent team's throughput?"*
- *"The persona decomposition feels post-hoc. Have the authors tested whether a random decomposition into equally-many agents performs comparably?"* (This is the killer question for any persona paper in 2026.)

---

## 3. Acceptance probability — realistic, not aspirational

**NeurIPS 2026 main track:** With the proposal as currently described, **3–6%**. For context, NeurIPS 2025 received ~23,000 papers, had capacity overflow that rejected some accepted papers, and ACs were empowered to reject positively-reviewed papers. The 2026 cycle introduces early AC meta-reviews before rebuttal — meaning weak framing gets flagged earlier. Agent papers are in explicit reviewer-fatigue phase; the MAST paper (NeurIPS 2025) quantified that most MAS claims don't hold up under controlled baselines, and that taxonomy is now a reviewer weapon.

**EMNLP 2026 main track:** **5–10%.** Slightly friendlier to NLP-angled agent work, but EMNLP 2026's CFP explicitly warns about "thinly sliced contributions" and will penalize incremental work. Going through ACL Rolling Review adds a filtering step (reviews arrive before commitment deadline, so you can redirect to Findings if reviews are weak).

**What would raise these probabilities meaningfully:**

- To ~15–20% at NeurIPS: a genuine methodological twist not already in ADAS/Puppeteer/EvoMAC, a controlled experiment that includes best-of-N + ADAS + Puppeteer as baselines at matched compute, ≥2 base model families, ≥3 heterogeneous benchmarks, a failure-mode taxonomy (MAST-style), and a full harness ablation. This is ~8–10 weeks of work, not 3.
- To ~20–30% at EMNLP: an NLP-framed contribution (e.g., controller as a language-gradient reasoner, with linguistic analysis of the controller's edits) combined with the above. Easier to clear because EMNLP weights NLP insights more.
- To ~40–60% at NeurIPS **Datasets & Benchmarks Track**: a new benchmark (geopolitics × multi-asset, or sequential cross-specialty medical reasoning with bias perturbations) plus the system as an evaluation vehicle. D&B is where I'd actually push this if you want a top-venue paper in 2026.

**The bar you must clear (explicit checklist from 2024–2026 reviewer patterns):**

1. Beat best-of-N single-agent at matched token/wall-clock/$-budget.
2. Show gains on ≥2 base model families (e.g., Qwen3-72B + Claude 4.x + Llama-4).
3. Evaluate on ≥3 heterogeneous benchmarks, with at least one non-saturated one (GPQA-Diamond, MedXpertQA, MedAgentsBench hard, SWE-bench Verified, TheAgentCompany, CORE-Bench).
4. Direct comparison to ADAS, AFlow, and either Puppeteer or MaAS or EvoMAC.
5. Harness ablation: remove loop/memory/controller components individually and report.
6. Failure-mode taxonomy with human-judged calibration (BadScientist showed LLM-judges accept 67–82% of fabricated papers — reviewers are now deeply cynical).
7. Full cost Pareto curve (tokens, wall-clock, $-cost).
8. Code + prompts + tool definitions + model versions released.
9. ≥2 ablation: (i) remove controller, use fixed planner/executor; (ii) replace controller with random persona perturbation to test that *structure*, not diversity, is what matters.

---

## 4. Domain and benchmark recommendation — pick finance with a cross-asset angle, not medical

### Medical vs. financial comparison

| Dimension | Medical | Financial |
|---|---|---|
| Persona intuitiveness | Very high — MDT metaphor is instantly legible | High — firm/asset-class roles are instantly legible |
| Saturation at top venues | **High** — NeurIPS 2024 Oral (MDAgents), ICLR 2025 (AgentClinic), ~12 systems in 24 months | Moderate — FinCon at NeurIPS 2024, few main-track papers |
| Benchmark availability | Excellent (MedQA, MedMCQA, PubMedQA, MedXpertQA, AgentClinic, MedCalc, SDBench) | Good but reproducibility-suspect (FinBen, FinQA, FinanceBench, FINSABER) |
| Reviewer skepticism | Rising — "your specialists don't actually help on hard sets" | Rising — "your backtest is data-snooped" (FINSABER deflated prior claims) |
| Headroom | Only on hard/new sets (MedXpertQA, SDBench, MedAgentBench) | Substantial on cross-asset and geopolitics |
| Novelty for your personas | Low — specialty-MDT has been done ~12 times | **High — bond + geopolitics agents are genuinely new** |
| Feasibility in 3 weeks | Good (MCQA + AgentClinic) | Tight (need bias-controlled backtest) |

**Recommendation: go financial with the cross-asset framing, but mitigate reproducibility risk.** The bond + equity + geopolitics + quant decomposition is the **single most defensible novelty element** in your proposal. Nobody treats fixed income as a first-class agent. A geopolitical agent that reasons causally across asset classes (Fed rate → DXY → EM bonds → commodity equities) has no direct prior art. This is the differentiable hook.

If you go medical instead, you must avoid the MDT-specialty template entirely (it's exhausted) and adopt **MAI-DxO-style functional roles** (hypothesis/test-picker/skeptic/cost/safety) evaluated on **non-saturated hard sets** (MedXpertQA Text, MedAgentsBench hard subset, AgentClinic, MedCalc-Bench, MedAgentBench-FHIR). Skip MedQA/MedMCQA/PubMedQA as primary metrics — they are saturated on frontier models.

**Recommended feasible eval suite (3 weeks, 8×H200):**

- **If financial:** FinBen (breadth, few hours), FinanceBench 150-open (depth), FinQA + ConvFinQA (reasoning), **FINSABER's 20-year bias-controlled backtest** (must-include for reviewer defense), a **curated geopolitical-event → cross-asset reasoning set** you build yourself (20–50 events: Ukraine invasion, SVB collapse, OPEC+ cut, Fed pivots, TSMC earthquake) — **this curated set is itself a publishable contribution**.
- **If medical:** MedXpertQA Text, MedAgentsBench hard, AgentClinic-MedQA (sequential), MedCalc-Bench, BiasMedQA. Explicitly skip MedQA/MedMCQA as primary metrics.

Software engineering (SWE-bench Verified, TerminalBench-2) is actually the strongest domain for reviewer trust and has the most headroom, but your persona-visibility requirement fits poorly — SWE doesn't decompose naturally into distinct expert personas.

---

## 5. Timeline feasibility — the user said "3 weeks" but NeurIPS is 12 days away

**Current date: April 24, 2026.** Key deadlines:

| Venue | Deadline | Days from today | Feasible? |
|---|---|---|---|
| NeurIPS 2026 abstract | **May 4, 2026 AoE** | **10 days** | Only if abstract is broadly scoped |
| NeurIPS 2026 full paper | **May 6, 2026 AoE** | **12 days** | **Very aggressive.** Not 3 weeks. |
| ICML 2026 | Jan 28, 2026 — *passed* | — | No |
| COLM 2026 | Mar 31, 2026 — *passed* | — | No |
| ACL 2026 ARR commitment | Mar 14, 2026 — *passed* | — | No |
| **EMNLP 2026 via ARR** | **May 25, 2026 AoE** | **31 days** | **Realistic.** Your 3-week budget fits with a buffer. |
| EMNLP 2026 direct commitment | Aug 2, 2026 | 100 days | Too late for your timeline, but a fallback |
| ICLR 2026 workshops (Lifelong Agents, MemAgents) | Most passed Feb 15, 2026 | — | No |
| NeurIPS 2026 workshops | Typically Aug–Sept 2026 | 120–150 days | Possible later fallback |
| ML4H 2026 | Expected ~early Sept 2026 | ~140 days | Possible later fallback |

**Highest-risk timeline elements (in order):**

1. **Running the controller optimization loop itself.** A single full trajectory is 5–50 LLM calls per task × 50–500 tasks × 3–10 iterations of controller edits × 3 seeds × 2+ backbones × 3+ benchmarks = potentially hundreds of thousands of LLM calls. At open-weights-70B on 8×H200, this is doable but consumes most of Weeks 1–2. Using frontier APIs risks $5–20K spend.
2. **Building the bias-controlled financial eval** (FINSABER-style with delisted, multi-window, multi-seed). This is 5–7 days by itself.
3. **Comparing to ADAS, Puppeteer, and MaAS.** Their codebases are nontrivial to reproduce. You must budget 3–5 days for baselines.
4. **Controller design iteration.** You will almost certainly need to redesign the controller (NL reasoning vs. code edits vs. hybrid) 2–3 times before it works. Budget a week.
5. **Writing.** Top-venue writing with strong framing against 15+ prior works is 5–7 days minimum.

**Totaling:** A properly executed version of this paper needs ~6–8 weeks, not 3. In 3 weeks you can produce a **workshop-quality paper**; in the 12 days to NeurIPS you can produce essentially nothing competitive at a main track.

### Recommended fallback plan

**Primary target: EMNLP 2026 main via ARR (May 25, 2026, 31 days).** Compress as follows:

- **Days 1–7:** Freeze the controller design (NL meta-reasoning with a small set of structured edit operations is my recommendation; see §7). Implement on top of an existing framework (DSPy or AutoGen) to save engineering time. Build the cross-asset financial benchmark as your novelty anchor — 30 geopolitical events × multi-asset reasoning questions, with human-annotated gold answers for a subset.
- **Days 8–17:** Run experiments on 2 backbones (Qwen3-72B + GPT-4.1 or Claude 4.5), 3 benchmarks (FinBen subset + FinanceBench + your curated set), baselines (single-agent CoT, best-of-N, TradingAgents, FinCon, Puppeteer, ADAS). Ablations (remove controller, random permutation, fix topology).
- **Days 18–24:** Failure-mode analysis on 100+ traces, MAST-style taxonomy, cost Pareto, harness ablation.
- **Days 25–31:** Write, revise, prepare ARR submission.

**Secondary target: NeurIPS 2026 Datasets & Benchmarks Track (May 6, 12 days).** Only if you can narrow the contribution to "**GeoMacroBench**: a bias-controlled benchmark for cross-asset geopolitical reasoning in multi-agent LLM systems," with your system as one of several evaluated. This is more realistic in 12 days than a method paper, and D&B reviewers are friendlier to dataset + demonstration submissions.

**Tertiary target: NeurIPS 2026 workshop (deadline ~Aug–Sept).** If the above don't work, land the paper at a workshop (Lifelong Agents, Multi-Turn Interactions, LLM Agents) and expand to COLM 2027 or ICLR 2027.

---

## 6. Confirmed 2026 deadlines

- **NeurIPS 2026:** abstract May 4, 2026 AoE; full paper **May 6, 2026 AoE**; notification **Sept 24, 2026**; conference Dec 6–12, 2026 (multi-city: Sydney, Atlanta, Paris). Pilot early AC meta-reviews before rebuttal — prepare your limitations and comparison-to-prior-art sections with extra care because reviewers will see them flagged before the rebuttal window.
- **EMNLP 2026:** ARR submission deadline **May 25, 2026 AoE**; author-reviewer discussion Jul 7–13; meta-review Jul 30; EMNLP commitment Aug 2; acceptance Aug 20; camera-ready Sept 20; conference Oct 24–29, 2026 in Hungary.
- **ICML 2026:** Deadlines *passed* (Jan 28, 2026); notification Apr 30, 2026; conference Jul 6–11, 2026, Seoul.
- **COLM 2026:** Deadlines *passed* (Mar 31, 2026); notification Jul 8; conference Oct 6–9, 2026, San Francisco.
- **ACL 2026:** ARR Feb cycle *passed*; conference Jul 2–7, 2026, San Diego.
- **ICLR 2026:** Conference Apr 23–27, 2026, Rio de Janeiro — happening right now; all deadlines passed.
- **ML4H 2026:** Expected ~early Sept 2026 deadline; Dec 2026 symposium co-located with NeurIPS.
- **NeurIPS workshops:** Typically announced Jun–Jul, deadlines late Aug–mid Sept. 2025 editions to watch: Multi-Turn Interactions in LLMs, Open-World Agents, Bridging Language/Agent/World Models (LAW), Foundation Models Meet Embodied Agents.

---

## 7. Concrete differentiation strategies that could actually work

Given the density of prior art, three paths can still produce a publishable contribution. Ranked by feasibility in your 31-day window:

### Strategy A — Reframe as "causal/diagnostic controller" (most feasible, medium novelty)

Instead of positioning as "a controller that evolves structure," position as **"a controller that performs causal trace analysis to diagnose multi-agent failures, then applies minimal surgical edits."** Mechanics: after each execution, the controller runs counterfactual replays ("what if agent X's output were Y instead?") to identify the causal bottleneck, then issues **a single scoped edit** (rewrite persona Z, add agent of type W, prune edge X→Y). This is distinct from ADAS (code synthesis, not diagnosis), Puppeteer (selection/pruning from pool, not diagnosis), Agent Symbolic Learning (gradient-based, not counterfactual), and EvoMAC (backprop, not causal). The MAST taxonomy (NeurIPS 2025) can ground the failure modes. Reviewers appreciate causal framing. **Acceptance lift estimate: +5–8 percentage points.**

### Strategy B — Cross-asset financial benchmark + system (highest novelty, medium feasibility)

Build **GeoMacroBench**: 30–50 geopolitical events from 2023–2025 (post-LLM-cutoff for at least one backbone), each paired with 5–10 cross-asset reasoning questions (e.g., "Given the Oct 2023 Israel–Hamas conflict, what is the expected 30-day direction of Brent, DXY, 10Y UST, EM equities, and defense stocks, and why?"), with gold answers from Bloomberg consensus + realized outcomes. Evaluate your bond/equity/geopolitics/quant decomposition against TradingAgents, FinCon, and a single-agent baseline. **This has dataset-contribution value and domain-novelty value simultaneously.** Pair with FinBen + FinanceBench for comparability. Use FINSABER's methodology to preempt the backtest-bias critique. **Acceptance lift estimate: +10–15 pp; possibly strongest at NeurIPS D&B Track.**

### Strategy C — Persona-necessity ablation as the scientific claim (highest risk, highest credibility)

Re-pitch as a *scientific investigation* rather than a system contribution: **"Are specialized personas actually necessary, or do they act as prompt diversity in disguise?"** Run a controlled experiment with four conditions: (i) your full specialist decomposition; (ii) *random* personas of the same count; (iii) *identical clones* with different temperatures; (iv) a single agent with best-of-N at matched compute. Do this across 3–5 benchmarks and 2–3 backbones. If specialists genuinely help, you have mechanistic evidence. If they don't (which MAST suggests is likely on many benchmarks), you have a **negative result** that is highly publishable in the current climate — negative results in the MAST tradition are winning at NeurIPS 2025. **Acceptance lift estimate: +8–12 pp. Risk: you might discover your system doesn't actually work.**

### Recommended combined strategy

Combine A + B: frame as **"a diagnostic controller for cross-asset financial reasoning agents, evaluated on a new geopolitical-event benchmark."** This gives you a method contribution (diagnostic controller) + a benchmark contribution (GeoMacroBench) + a domain contribution (bond + geopolitics as first-class agents). Submit to NeurIPS D&B Track (May 6 if feasible) or EMNLP 2026 main via ARR (May 25).

### Essential ablations regardless of strategy

- **Controller on/off** (fixed planner+executor baseline).
- **Random-persona control** (same # agents, random roles) — tests whether structure matters.
- **Fixed-topology control** — tests whether topology search matters.
- **Number-of-iterations sweep** — does the controller converge, oscillate, regress?
- **Backbone sweep** (≥2 families) — does gain hold on stronger models?
- **Best-of-N at matched compute** — THE critical baseline post-MAST.
- **Direct comparison to ADAS, Puppeteer, and one of MaAS/EvoMAC/FlowReasoner.**
- **LLM-judge calibration** on ≥100 samples with human agreement κ.
- **Cost Pareto curve** (tokens + $-cost + wall-clock vs. performance).

---

## Closing verdict

The proposal as described will not get into NeurIPS 2026 main track in its current form and timeline. The honest paths forward are (1) narrow and reframe around the cross-asset financial benchmark + diagnostic controller, target EMNLP 2026 via ARR (May 25, 31 days, feasible), or (2) accept that the current scope needs 8–10 weeks and aim for NeurIPS 2026 workshops or COLM 2027 with a genuinely stronger experimental package. The third honest option is to execute the persona-necessity negative-result experiment — which is fast, cheap, credible in the 2026 climate, and publishable — but requires abandoning the system-paper framing. Do not submit a me-too evolving-orchestrator paper against Puppeteer, MaAS, ADAS, and EvoMAC without a sharp differentiator; it will be rejected, and the rejection will be correct.

---

## Update log

### 2026-04-24 — GSM8K retired; H1 restated around domain-specific benchmarks

**Empirical trigger.** `calib_01` (n_val = n_test = 50, max_iters = 3, seed = 0) on GSM8K showed *evolved graph underperforms both baselines on test* (86% vs CoT 92% / P-E 90%) while costing 2–3.7× more tokens. Controller rationales read as generic "add-an-agent" reflexes rather than tape-grounded diagnoses. Full analysis: `docs/insights/pilot.md` §4; reproducible notebook: `notebooks/calib_01_analysis.ipynb`.

**Diagnosis.** GSM8K structurally under-rewards multi-agent systems. The task context is self-contained (no external knowledge lever), the solution trajectory is linear arithmetic (no real division of labor), and a single strong LLM (Qwen2.5-32B) already saturates to 94%. Persona specialization has **no information-asymmetric lever** to pull — the only thing an added agent can do is corrupt the information chain. This also aligns with the literature signal that Li et al. 2024 (MEDIQ) report non-interactive-initial beats basic interactive (45.6% vs 42.2% on GPT-3.5) — "more agents" is not automatically a win.

**Revised H1 (2026-04-24).** Reflection-only multi-agent evolution produces a measurable val/test improvement over single-LLM (CoT) and minimal-multi-agent (Planner-Executor) baselines **on domain-specific tasks where personas carry heterogeneous expertise or information** — specifically FinanceBench and AgentClinic. MEDIQ non-interactive is reserved as a sanity/pipeline platform (it does not probe multi-agent affordance on its own; see §6.4 of `pilot.md`).

**Falsifier.** If `evolved ≈ baseline` across *all three* domains at n ≥ 30 (the §5.2 measurement in `roadmap.md`), the research reframes toward Strategy C (persona-necessity negative result) in §7 above, which becomes the primary contribution rather than a side axis.

**Commit this triggers.** The pivot also commits us to showing GSM8K was *the wrong domain, not just a hard one*. That claim is defensible from the observations above but must be written explicitly in the related-work section when paper time comes.

**Benchmarks activated.**
- **FinanceBench** (Patronus, CC-BY-NC-4.0, 150 samples) — single-turn Q→A over SEC filings. LLM-judge scoring.
- **MEDIQ non-interactive initial** (Li et al. 2024, CC-BY-4.0, 13k cases, dev subset) — MCQ over a frozen first-turn snippet. MCQ exact-match scoring. Sanity platform, not the hypothesis test.
- **AgentClinic single-pass wrapper** (Schmidgall et al. 2024, MIT, 107 cases MedQA variant) — full OSCE case → one-shot diagnosis. LLM-judge scoring. Multi-turn original mode deferred to a later phase.

**Pipeline-level observations so far** (sanity batch, n=3): controller rationales are **domain-adaptive** (AgentClinic's "summarizer for concise diagnosis" replaces GSM8K's "arithmetic verifier" reflex). First *positive* empirical signal that the pivot can recover H1. FinanceBench separately surfaced a DAG-discipline failure in the controller under long evidence context — patch is §5.1 in `roadmap.md`.