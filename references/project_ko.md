# self-evolving multi-agent 논문 제안에 대한 브루탈한 평가

**한 줄 결론:** "실행을 관찰하고 에이전트 수·페르소나·프롬프트·호출 그래프를 수정하는 컨트롤러 에이전트"라는 핵심 아이디어는 **2026년 기준으로 새롭지 않다**. 이미 최소 6편의 강력한 선행 연구가 이 공간을 덮고 있고 (ADAS, NeurIPS 2025의 Puppeteer/Evolving Orchestration, ICML 2025 Oral의 MaAS, Agent Symbolic Learning, ICLR 2025의 EvoMAC, IJCAI 2024의 AutoAgents), 2026년 후속 라인 (HyperAgents, Darwin Gödel Machine, MAS²)은 이미 **재귀적 자기 수정** 프론티어까지 옮겨 왔다. 현재 서술된 대로 제출하면 desk-flag 되거나 incremental로 rejected 될 가능성이 매우 높다. 더 날카롭고 구체적인 novelty 축을 찾지 않는 한 그렇다. 현재 스코프 기준 NeurIPS 2026 main track acceptance 확률은 **약 3–6%**, EMNLP 2026 main은 **약 5–10%**이다. 현실적으로 도달 가능한 타겟은 (a) contribution을 강하게 reframe한 EMNLP 2026 main, (b) NeurIPS workshop (Lifelong Agents, MemAgents, Agents in the Wild — 단 2026년 대부분의 deadline은 이미 지남), 혹은 (c) 훨씬 더 탄탄한 스토리로 COLM 2027이다. Timeline이 두 번째 병목이다: NeurIPS 2026 논문 deadline은 **2026년 5월 6일 (오늘로부터 D-12)**로 3주가 아니다. ARR을 경유하는 EMNLP 2026은 **2026년 5월 25일 (D-31)**이 더 현실적인 타겟이다.

이하 보고서는 선행 연구 지형, 구체적인 novelty triage, reviewer 선제 분석, 도메인/벤치마크 추천, 그리고 acceptance 확률을 실질적으로 끌어올릴 수 있는 세 가지 차별화 전략을 다룬다.

---

## 1. 선행 연구: 공간이 혼잡하고, 가장 가까운 선행 연구들이 이미 네 축 모두를 덮고 있다

문헌은 7개의 클러스터로 나뉜다. 각 클러스터에서 중요한 논문을 당신의 컨트롤러 4차원 — **(a)** 에이전트 수 변경, **(b)** 페르소나 변경, **(c)** 프롬프트 변경, **(d)** 토폴로지 변경 — 에 대한 커버리지와 함께 제시한다.

### 클러스터 A — "컨트롤러가 팀을 다시 쓴다" 직접 계열 (당신의 주 경쟁자)

**ADAS — Automated Design of Agentic Systems** (Hu, Lu, Clune, **ICLR 2025**, arXiv:2408.08435). 메타-에이전트가 아카이브 기반으로 **Python 코드**로 새로운 agentic 시스템을 반복적으로 프로그래밍한다. 코드는 튜링 완전하므로 탐색 공간이 이미 당신의 네 차원을 포괄한다. ARC, DROP, MGSM, MMLU, GPQA로 평가. 커버리지: **✅a, ✅b, ✅c, ✅d**. 당신의 제안에 가장 치명적인 단 하나의 인용. 컨트롤러가 코드 편집을 한다면 리뷰어는 즉시 "이게 ADAS와 어떻게 다른가?"를 물을 것이다.

**Multi-Agent Collaboration via Evolving Orchestration — "Puppeteer"** (Dang et al., Tsinghua, **NeurIPS 2025**, arXiv:2505.19591). 오케스트레이터 에이전트가 실행 중 진화하며 "더 효과적인 에이전트를 적응적으로 승격시키고 덜 유용한 것은 제거"한다. compact cyclic structure가 발현됨을 관찰. 이것은 **당신의 정확한 프레이밍**과 일치한다 — in-task 컨트롤러가 팀을 rewrite. 커버리지: **✅a, ⚠️b, ⚠️c, ✅d**. 이것이 NeurIPS 2025라는 사실은 — 2024가 아니라 — 프로그램 위원회가 당신의 기본 스토리를 *이미 한 번 받아들였다*는 뜻이다.

**MaAS — Multi-Agent Architecture Search via Agentic Supernet** (Zhang et al., **ICML 2025 Oral**, arXiv:2502.04180). 학습된 컨트롤러가 연산자 (CoT, Debate, ReAct 등) 위의 "agentic supernet"에서 쿼리별 서브아키텍처를 샘플링하고, 실행 피드백이 Monte-Carlo 그라디언트로 supernet 분포와 연산자를 동시에 업데이트한다. 논문에 **"controller"라는 단어가 명시적**으로 등장. 커버리지: **✅a, ⚠️b, ⚠️c, ✅d**.

**AutoAgents** (Chen et al., **IJCAI 2024**, arXiv:2309.17288). Planner + Agent-Observer + Action-Observer가 태스크 설명으로부터 특화된 에이전트 팀을 역할/페르소나와 함께 초안/정제. "observer가 지정된 계획과 에이전트 반응을 성찰하고 반복적으로 개선한다"는 표현은 당신의 제안과 거의 동일. 커버리지: **✅a, ✅b, ✅c (초안 단계), ⚠️d**.

**Agent Symbolic Learning** (Zhou et al., AIWaves, arXiv:2406.18532). 파이프라인을 계산 그래프로 취급하고 "language loss"와 "language gradient"를 정의해 피드백을 **프롬프트, 도구, 파이프라인 구조 자체로 역전파**. 그들의 symbolic optimizer는 실행 trace로부터 call graph를 명시적으로 편집한다. 커버리지: **✅a, ⚠️b, ✅c, ✅d**.

**EvoMAC — Self-Evolving Multi-Agent Collaboration Networks** (Hu et al., **ICLR 2025**, arXiv:2410.16946). 테스트 타임 textual back-propagation이 실행 중 에이전트와 엣지를 반복 편집. 소프트웨어 개발 벤치마크에서 평가. **네 축을 모두 테스트 타임에 반복적으로 커버**하며, 당신의 제안과의 유일한 실제 gap은 SE 도메인 특화 + 피드백 proxy로 테스트 케이스를 쓴다는 점뿐. 커버리지: **✅a, ✅b, ✅c, ✅d, iterative at test-time**.

### 클러스터 B — 쿼리 수준 메타-에이전트 생성

**FlowReasoner** (Gao et al., arXiv:2504.15257, 2025년 4월). RL-훈련된 메타-에이전트 (DeepSeek-R1 증류)가 유저 쿼리별 맞춤형 MAS를 생성. o1-mini 대비 +10.52%. 쿼리당 one-shot, iterative 아님. **✅a, ✅b, ✅c, ✅d** 그러나 single-pass.

**MAS-GPT** (Ye et al., **ICML 2025**, arXiv:2503.03686). SFT-훈련된 32B LLM이 쿼리별로 완전한 실행 가능한 MAS 코드를 출력. One-shot. **✅a, ✅b, ✅c, ✅d** 그러나 single-pass.

**MAS²** (arXiv:2509.24323, 2025년 9월). "MAS가 재귀적으로 다른 MAS를 생성" — collaborative tree optimization 경유. 당신의 공간에 직접.

### 클러스터 C — 자기 수정 단일 에이전트

**Gödel Agent** (Yin et al., arXiv:2410.04444). 자기 참조적: 자기 개선 로직을 포함한 자기 코드를 검사·수정. **Darwin Gödel Machine** (Zhang, Hu, Lu, Lange, Clune, arXiv:2505.22954, 2025년 5월)은 이를 아카이브 기반 open-ended evolution으로 확장; SWE-bench에서 20%→50%. **HyperAgents / DGM-H** (Meta FAIR, ICLR 2026, arXiv:2603.19461)은 단일 편집 가능한 프로그램에 task-agent + meta-agent를 통합하고 메타-에이전트가 둘 다 rewrite. 이것들이 2026년 개념적으로 넘어서야 할 가장 깨끗한 벤치마크.

### 클러스터 D — Graph/workflow optimization (old guard)

**GPTSwarm** (Zhuge et al., **ICML 2024 Oral**) — REINFORCE 기반 graph의 노드(프롬프트) + 엣지(토폴로지) 최적화. **AFlow** (Zhang et al., **ICLR 2025 Oral**) — 연산자 라이브러리를 갖춘 코드 수준 workflow에 대한 MCTS. **AgentSquare** (Shang et al., ICLR 2025) — Planning/Reasoning/Tool-Use/Memory에 대한 모듈형 탐색. **MASS** (arXiv:2502.02533) — 프롬프트와 토폴로지의 교차 탐색. **EvoFlow** (arXiv:2502.07373) — workflow의 niching 진화 population. **G-Designer** (arXiv:2410.11782) — GNN 기반 task-adaptive 토폴로지. **DyLAN** (arXiv:2310.02170, ICLR 2024 rejected이지만 인용 많음) — importance-score pruning의 동적 LLM-agent network. **ScoreFlow** (arXiv:2502.04306) — workflow preference optimization을 위한 Score-DPO.

### 클러스터 E — 프롬프트/프로그램 최적화 기반

DSPy (Khattab et al., ICLR 2024), MIPROv2 (EMNLP 2024), **GEPA** (Agrawal et al., ICLR 2026 Oral — 35배 적은 rollout으로 RL을 능가하는 reflective prompt evolution), **TextGrad** (Yuksekgonul et al., Nature 2025), **Trace/OptoPrime** (Cheng et al., NeurIPS 2024), OPRO (Yang et al., ICLR 2024), Promptbreeder (ICML 2024), FunSearch (Nature 2024), EvoPrompt (ICLR 2024), Archon (Saad-Falcon et al., ICLR SSI-FM 2025 Oral — inference-time architecture search). 이것들은 textual-gradient와 LLM-as-optimizer 기반체다. 적어도 TextGrad, GEPA, Trace는 인용·비교가 필수.

### 클러스터 F — 의료 multi-agent 시스템

**MedAgents** (Tang et al., ACL 2024 Findings), **MDAgents** (Kim et al., **NeurIPS 2024 Oral** — adaptive Solo/MDT/ICT triage), **AgentClinic** (Schmidgall et al., **ICLR 2025** — sequential dialogue benchmark, multimodal, bias variants), **ColaCare** (WWW 2025 — EHR+LLM fusion), **Agent Hospital / MedAgent-Zero** (Li et al., Tsinghua, arXiv:2405.02957 — 32개 부서 simulacrum with 자기 진화 의사), **AI Hospital** (COLING 2025), **ClinicalAgent/CT-Agent** (ACM-BCB 2024), **MedAide** (arXiv:2410.12532), **MEDCO** (arXiv:2408.12496), **KG4Diagnosis** (AAAI Bridge 2025), **MAI-DxO + SDBench** (Microsoft, arXiv:2506.22405 — 5개 기능 역할 Dr. Hypothesis/Test-Chooser/Challenger/Stewardship/Checklist이 NEJM-CPC에서 80–85.5% 달성, 의사 20% 대비), **AMIE** (Google, *Nature* 2025), Polaris (2403.13313), KAMAC (2509.14998), MedAgentSim (2025).

### 클러스터 G — 금융 multi-agent 시스템

**FinCon** (Yu et al., **NeurIPS 2024** — conceptual verbal reinforcement의 Manager–Analyst 위계), **TradingAgents** (Xiao et al., **AAAI 2025** — Bull/Bear debate가 있는 7개 역할 기업 위계), **FinAgent** (KDD 2024), **FinMem** (AAAI-SS 2024), **FinRobot** (ICAIF 2024), **TradExpert** (AAAI 2025), **AlphaAgents** (arXiv:2508.11152), **StockAgent** (arXiv:2407.18957), **QuantAgent**, **ATLAS**, **MASCA**. 벤치마크: **FinBen** (NeurIPS 2024 D&B — 42개 데이터셋), **FinanceBench** (Patronus AI), **FinQA/ConvFinQA** (EMNLP 2021/2022), BizBench (ACL 2024), MultiFinBen, **FINSABER** (Li et al. 2025 — **이전 LLM 트레이딩 이득을 deflate하는** bias-controlled backtest), **Agent Market Arena**, **StockBench**. 중요 주의사항: **FINSABER는 survivorship/look-ahead/data-snooping 통제 하에서 이전에 보고된 LLM 트레이딩 우위가 무너짐을 경험적으로 보여준다.**

---

## 2. 브루탈한 novelty 평가

**솔직한 평결:** 현재 서술된 당신의 제안은 이미 출판된 연구의 **재포장**이다. 모든 단일 요소가 이미 출판되어 있다:

- "컨트롤러가 실행을 관찰하고 팀을 다시 쓴다" → **Puppeteer (NeurIPS 2025)**, Agent Symbolic Learning, EvoMAC.
- "에이전트/페르소나/프롬프트/토폴로지를 함께 수정" → **ADAS (ICLR 2025)**, EvoMAC, FlowReasoner, MAS-GPT.
- "자연어 meta-reasoner 형태의 컨트롤러" → AutoAgents, Agent Symbolic Learning (language gradients).
- "코드/DAG 수정자 형태의 컨트롤러" → ADAS, AFlow, Gödel Agent, Darwin Gödel Machine, Meta-Harness.
- "간단한 planner/executor에서 시작해 성장" → Agent Hospital (자기 진화 의사), EvoAgent (단일 에이전트에서의 EA), AutoAgents (처음부터 팀 초안).
- "의료 전문 페르소나" → MedAgents, MDAgents, MAI-DxO, Agent Hospital.
- "금융 채권/주식/지정학/퀀트 페르소나" → TradingAgents (bull/bear/news/technical), FinCon (7-analyst 위계).

**contribution을 날카롭게 하면 여전히 진정으로 새로울 수 있는 것:**

1. **Cross-asset financial decomposition (bond + equity + geopolitics + quant)**은 실제 whitespace다. 기존 MAS 중 fixed income을 first-class agent로 취급하는 것은 없고, asset class를 가로지르며 지정학 전문가가 cross-asset causal chain (예: Fed move → DXY → EM bonds → commodity equities)을 이끄는 시스템도 없다. **이것이 당신이 주장 가능한 단일 최강의 novelty claim이다.** 다만 이것은 method contribution이 아닌 domain contribution이며, 리뷰어는 "TradingAgents가 이미 Bull/Bear/News/Technical을 한다"고 말할 것이다.
2. **Iterative in-task controller editing of personas** (단지 프롬프트나 토폴로지가 아니라), **trace에서 진단된 communication-bottleneck signal에 근거.** EvoMAC은 페르소나를 iterative하게 편집하지만 SE에 국한; Puppeteer는 팀 구성을 하지만 페르소나 rewriting은 아님; ADAS는 모든 것을 하지만 offline. *어느 페르소나가 어느 페르소나와 miscommunicate*하는지 구체적으로 진단하고 그 범인을 surgically 재작성하는 컨트롤러는 좁지만 방어 가능한 niche다.
3. **Observability-first 공식화.** Contribution을 **diagnostic/causal controller**로 프레임하고 — 컨트롤러가 편집 *전에* trace에 대한 causal 분석 (예: "이 엣지가 제거된다면?" counterfactual replay)을 수행하는 형태로 — 하면 이것은 실제로 underexplored다.

**리뷰어가 할 말 (문자 그대로 예상하라):**

- *"제안된 프레임워크는 ADAS/Puppeteer/Agent Symbolic Learning의 자연어 수준 재구현으로 읽힌다. 저자들은 직접적이고 정량적으로 비교해야 한다."*
- *"컨트롤러의 네 가지 action primitive (add/remove/modify persona/rewire)는 ADAS의 코드 탐색 공간에 이미 함축되어 있는 연산의 열거이다. 이 분해가 왜 선호되어야 하는지에 대한 formal argument가 없다."*
- *"MedQA/MedMCQA에서 보고된 이득은 frontier backbone에서 marginal이며 구조적 진화가 아닌 prompt-diversity를 반영할 가능성이 높다. Matched token budget에서 best-of-N single-agent와 ablate해 달라."* (이 비판은 post-MAST 표준이다.)
- *"본 논문은 Puppeteer (NeurIPS 2025), MaAS (ICML 2025), EvoMAC (ICLR 2025), FlowReasoner, Agent Symbolic Learning과 비교하지 않는다."*
- *"컨트롤러가 언제 수렴하고, 언제 oscillate하고, 언제 성능 회귀를 유발하는지에 대한 이론적 특성화가 없다."*
- *"비용/지연 분석이 없다. 컨트롤러 LLM 오버헤드가 multi-agent 팀의 throughput을 지배하는가?"*
- *"페르소나 분해가 post-hoc처럼 느껴진다. 저자들은 같은 수의 에이전트를 random으로 분해한 것과의 비교를 테스트했는가?"* (2026년 모든 페르소나 논문에 대한 killer 질문.)

---

## 3. Acceptance 확률 — 현실적으로, 아스피레이셔널하지 않게

**NeurIPS 2026 main track:** 현재 서술 기준 **3–6%**. 맥락: NeurIPS 2025는 ~23,000편 submission, capacity overflow로 positively-reviewed 논문 일부도 rejected, AC가 긍정적 리뷰 논문도 reject할 권한을 부여받았다. 2026 사이클에는 rebuttal 전 early AC meta-review가 도입되어 약한 framing이 더 일찍 flag 된다. Agent 논문은 명시적인 reviewer-fatigue 국면이다; MAST 논문 (NeurIPS 2025)은 대부분의 MAS claim이 통제된 baseline에서 유지되지 않음을 정량화했고, 그 taxonomy는 이제 reviewer의 무기다.

**EMNLP 2026 main track:** **5–10%.** NLP 각도의 agent 연구에 약간 더 friendly하지만, EMNLP 2026의 CFP는 명시적으로 "thinly sliced contributions"를 경고하고 incremental 연구를 penalize할 것이다. ACL Rolling Review를 거치면 필터링 단계가 추가된다 (commitment deadline 전에 review가 도착하므로 리뷰가 약하면 Findings로 redirect 가능).

**이 확률을 유의미하게 올리려면:**

- NeurIPS에서 ~15–20%: ADAS/Puppeteer/EvoMAC에 아직 없는 진짜 방법론적 twist, matched compute에서 best-of-N + ADAS + Puppeteer를 baseline으로 포함한 통제 실험, ≥2 base model family, ≥3 이질적 벤치마크, failure-mode taxonomy (MAST-style), 전체 harness ablation. 이것은 3주가 아니라 ~8–10주의 작업.
- EMNLP에서 ~20–30%: NLP-framed contribution (예: language-gradient reasoner 형태의 컨트롤러 + 컨트롤러의 편집에 대한 언어학적 분석) + 위 전부. EMNLP는 NLP insight에 더 비중을 둬 clear가 쉬움.
- NeurIPS **Datasets & Benchmarks Track** ~40–60%: 새 벤치마크 (geopolitics × multi-asset, 혹은 bias perturbation이 있는 sequential cross-specialty medical reasoning) + 평가 vehicle로서의 당신 시스템. 2026년 top-venue 논문을 원한다면 나라면 여기로 push.

**반드시 넘어야 할 bar (2024–2026 리뷰어 패턴에서 명시적 체크리스트):**

1. Matched token/wall-clock/$ budget에서 best-of-N single-agent를 이긴다.
2. ≥2 base model family에서 이득을 보인다 (예: Qwen3-72B + Claude 4.x + Llama-4).
3. ≥3 이질적 벤치마크에서 평가, 최소 1개는 non-saturated (GPQA-Diamond, MedXpertQA, MedAgentsBench hard, SWE-bench Verified, TheAgentCompany, CORE-Bench).
4. ADAS, AFlow, 그리고 Puppeteer 또는 MaAS 또는 EvoMAC 중 하나와의 직접 비교.
5. Harness ablation: loop/memory/controller 컴포넌트를 개별적으로 제거해 보고.
6. Human-judged calibration이 있는 failure-mode taxonomy (BadScientist는 LLM-judge가 67–82%의 fabricated 논문을 accept함을 보여줌 — 리뷰어는 이제 깊이 냉소적).
7. 전체 cost Pareto curve (tokens, wall-clock, $-cost).
8. 코드 + 프롬프트 + 도구 정의 + 모델 버전 릴리즈.
9. ≥2개 ablation: (i) 컨트롤러 제거, fixed planner/executor 사용; (ii) 컨트롤러를 random persona perturbation으로 교체해 *구조*가 diversity가 아닌 실제 요인임을 테스트.

---

## 4. 도메인과 벤치마크 추천 — medical 대신 cross-asset 각도의 finance

### Medical vs. financial 비교

| 차원 | Medical | Financial |
|---|---|---|
| 페르소나 직관성 | 매우 높음 — MDT 은유 즉시 legible | 높음 — 회사/asset-class 역할 즉시 legible |
| Top venue 포화도 | **높음** — NeurIPS 2024 Oral (MDAgents), ICLR 2025 (AgentClinic), 24개월 내 ~12개 시스템 | 중간 — FinCon at NeurIPS 2024, main-track 논문 드묾 |
| 벤치마크 가용성 | 우수 (MedQA, MedMCQA, PubMedQA, MedXpertQA, AgentClinic, MedCalc, SDBench) | 양호하지만 재현성 의심 (FinBen, FinQA, FinanceBench, FINSABER) |
| Reviewer 회의 | 상승 — "당신의 전문가들이 hard set에서 실제로 도움이 되지 않는다" | 상승 — "당신의 backtest는 data-snooped" (FINSABER가 이전 주장을 deflate) |
| Headroom | hard/new set에서만 (MedXpertQA, SDBench, MedAgentBench) | cross-asset과 지정학에서 상당함 |
| 당신 페르소나의 novelty | 낮음 — specialty-MDT는 ~12회 수행됨 | **높음 — bond + geopolitics agent는 진정으로 새로움** |
| 3주 내 실행 가능성 | 양호 (MCQA + AgentClinic) | 빡빡함 (bias-controlled backtest 필요) |

**추천: cross-asset 프레이밍과 함께 financial로 가되, reproducibility 리스크를 완화하라.** bond + equity + geopolitics + quant 분해는 당신 제안에서 **단일 최강의 novelty 요소**다. 아무도 fixed income을 first-class agent로 취급하지 않는다. asset class를 가로지르며 causal 추론을 하는 지정학 agent (Fed rate → DXY → EM bonds → commodity equities)는 직접적인 선행 연구가 없다. 이것이 차별화 훅이다.

대신 medical로 간다면, MDT-specialty 템플릿을 완전히 피하고 (소진됨) **MAI-DxO-style functional role** (hypothesis/test-picker/skeptic/cost/safety)을 **non-saturated hard set** (MedXpertQA Text, MedAgentsBench hard subset, AgentClinic, MedCalc-Bench, MedAgentBench-FHIR)에서 평가해야 한다. MedQA/MedMCQA/PubMedQA는 primary metric으로 건너뛰어라 — frontier 모델에서 이미 포화.

**추천 실행 가능 평가 suite (3주, 8×H200):**

- **Financial이면:** FinBen (breadth, 몇 시간), FinanceBench 150-open (depth), FinQA + ConvFinQA (reasoning), **FINSABER의 20년 bias-controlled backtest** (리뷰어 방어용 필수), **직접 구축한 지정학-event → cross-asset reasoning set** (20–50 event: 우크라이나 침공, SVB 붕괴, OPEC+ 감산, Fed pivot, TSMC 지진) — **이 curated set 자체가 출판 가능한 contribution**.
- **Medical이면:** MedXpertQA Text, MedAgentsBench hard, AgentClinic-MedQA (sequential), MedCalc-Bench, BiasMedQA. 명시적으로 MedQA/MedMCQA는 primary metric에서 제외.

소프트웨어 엔지니어링 (SWE-bench Verified, TerminalBench-2)은 실제로 reviewer trust에 가장 강하고 headroom이 가장 크지만, 당신의 페르소나 visibility 요구사항과 잘 안 맞는다 — SWE는 자연스럽게 구별되는 전문가 페르소나로 분해되지 않는다.

---

## 5. Timeline 실행 가능성 — 유저는 "3주"라 했지만 NeurIPS는 12일 뒤

**오늘 날짜: 2026년 4월 24일.** 주요 deadline:

| Venue | Deadline | 오늘로부터 | 실행 가능? |
|---|---|---|---|
| NeurIPS 2026 abstract | **2026년 5월 4일 AoE** | **10일** | 폭넓게 스코프된 abstract일 때만 |
| NeurIPS 2026 full paper | **2026년 5월 6일 AoE** | **12일** | **매우 공격적.** 3주가 아님. |
| ICML 2026 | 2026년 1월 28일 — *지남* | — | 불가 |
| COLM 2026 | 2026년 3월 31일 — *지남* | — | 불가 |
| ACL 2026 ARR commitment | 2026년 3월 14일 — *지남* | — | 불가 |
| **ARR 경유 EMNLP 2026** | **2026년 5월 25일 AoE** | **31일** | **현실적.** 3주 예산에 버퍼를 두고 맞음. |
| EMNLP 2026 direct commitment | 2026년 8월 2일 | 100일 | 타임라인에 너무 늦지만 fallback |
| ICLR 2026 workshop (Lifelong Agents, MemAgents) | 대부분 2026년 2월 15일에 지남 | — | 불가 |
| NeurIPS 2026 workshop | 보통 2026년 8–9월 | 120–150일 | 이후 fallback 가능 |
| ML4H 2026 | 예상 ~2026년 9월 초 | ~140일 | 이후 fallback 가능 |

**가장 높은 리스크의 타임라인 요소 (순서대로):**

1. **컨트롤러 최적화 루프 자체의 실행.** 단일 full trajectory는 태스크당 5–50 LLM 콜 × 50–500 태스크 × 3–10 iter 컨트롤러 편집 × 3 seed × 2+ 백본 × 3+ 벤치마크 = 잠재적으로 수십만 LLM 콜. 8×H200에서 open-weights-70B이면 가능하지만 Week 1–2 대부분을 소비. Frontier API를 쓰면 $5–20K 지출 리스크.
2. **Bias-controlled financial eval 구축** (delisted, multi-window, multi-seed의 FINSABER-style). 이것만 5–7일.
3. **ADAS, Puppeteer, MaAS와의 비교.** 이들의 코드베이스는 재현이 쉽지 않음. Baseline에 3–5일 예산.
4. **컨트롤러 설계 iteration.** 작동하기 전에 컨트롤러를 거의 확실히 2–3회 재설계해야 함 (NL reasoning vs. 코드 편집 vs. hybrid). 1주 예산.
5. **Writing.** 15편+ 선행 연구에 대해 강한 framing의 top-venue writing은 최소 5–7일.

**총합:** 이 논문의 올바른 실행 버전에는 3주가 아닌 **~6–8주**가 필요. 3주 내로는 **workshop 품질 논문**을, NeurIPS까지 12일 내로는 본질적으로 main track 경쟁력 있는 것을 아무것도 생산 불가.

### 추천 fallback plan

**Primary target: ARR 경유 EMNLP 2026 main (2026년 5월 25일, 31일).** 다음과 같이 압축하라:

- **1–7일:** 컨트롤러 설계 동결 (소수의 구조화된 edit 연산으로 NL meta-reasoning이 내 추천; §7 참조). 기존 프레임워크 (DSPy 또는 AutoGen) 위에 구현해 엔지니어링 시간 절약. novelty 앵커로 cross-asset financial 벤치마크 구축 — 30개 지정학 event × multi-asset reasoning 질문, 서브셋에 대해서는 human-annotated gold answer.
- **8–17일:** 2 백본 (Qwen3-72B + GPT-4.1 또는 Claude 4.5), 3 벤치마크 (FinBen subset + FinanceBench + curated set), baseline (single-agent CoT, best-of-N, TradingAgents, FinCon, Puppeteer, ADAS)에서 실험 실행. Ablation (컨트롤러 제거, random permutation, fix topology).
- **18–24일:** 100+ trace에 대한 failure-mode 분석, MAST-style taxonomy, cost Pareto, harness ablation.
- **25–31일:** 작성, 수정, ARR submission 준비.

**Secondary target: NeurIPS 2026 Datasets & Benchmarks Track (5월 6일, 12일).** contribution을 "**GeoMacroBench**: multi-agent LLM system에서의 cross-asset 지정학 reasoning을 위한 bias-controlled 벤치마크"로 좁히고 당신 시스템을 평가된 여러 시스템 중 하나로 둘 때만. 12일 내 method 논문보다 현실적이고, D&B 리뷰어는 dataset + demonstration submission에 friendly.

**Tertiary target: NeurIPS 2026 workshop (deadline ~8–9월).** 위 방법이 안 되면 workshop (Lifelong Agents, Multi-Turn Interactions, LLM Agents)에 논문을 착지시키고 COLM 2027 또는 ICLR 2027로 확장.

---

## 6. 확정된 2026 deadline

- **NeurIPS 2026:** abstract 2026년 5월 4일 AoE; full paper **2026년 5월 6일 AoE**; notification **2026년 9월 24일**; conference 2026년 12월 6–12일 (multi-city: Sydney, Atlanta, Paris). rebuttal 전 early AC meta-review pilot — 리뷰어가 rebuttal 창 전에 flag된 것을 볼 것이므로 limitation과 prior-art 비교 섹션을 특별히 주의해서 준비하라.
- **EMNLP 2026:** ARR submission deadline **2026년 5월 25일 AoE**; author-reviewer discussion 7월 7–13일; meta-review 7월 30일; EMNLP commitment 8월 2일; acceptance 8월 20일; camera-ready 9월 20일; conference 2026년 10월 24–29일 Hungary.
- **ICML 2026:** Deadline *지남* (2026년 1월 28일); notification 2026년 4월 30일; conference 2026년 7월 6–11일, Seoul.
- **COLM 2026:** Deadline *지남* (2026년 3월 31일); notification 7월 8일; conference 2026년 10월 6–9일, San Francisco.
- **ACL 2026:** ARR 2월 cycle *지남*; conference 2026년 7월 2–7일, San Diego.
- **ICLR 2026:** Conference 2026년 4월 23–27일, Rio de Janeiro — 지금 진행 중; 모든 deadline 지남.
- **ML4H 2026:** 2026년 9월 초 deadline 예상; 2026년 12월 심포지엄, NeurIPS와 co-located.
- **NeurIPS workshop:** 보통 6–7월 공지, deadline 8월 말–9월 중순. 주목할 2025 edition: Multi-Turn Interactions in LLMs, Open-World Agents, Bridging Language/Agent/World Models (LAW), Foundation Models Meet Embodied Agents.

---

## 7. 실제로 작동할 수 있는 구체적 차별화 전략

선행 연구 밀도를 감안할 때 여전히 출판 가능한 contribution을 생성할 수 있는 세 경로. 31일 창에서의 feasibility 순위:

### 전략 A — "Causal/Diagnostic 컨트롤러"로 reframe (가장 feasibility, medium novelty)

"구조를 진화시키는 컨트롤러" 대신 **"multi-agent 실패를 진단하기 위해 trace의 causal 분석을 수행하고 최소한의 surgical edit을 적용하는 컨트롤러"**로 포지셔닝. 메커니즘: 각 실행 후 컨트롤러가 counterfactual replay ("에이전트 X의 output이 Y였다면?")를 실행해 causal 병목을 식별, 그 다음 **단일 scoped edit** (페르소나 Z rewrite, 타입 W의 에이전트 추가, 엣지 X→Y 프루닝) 발행. 이것은 ADAS (코드 합성, 진단 없음), Puppeteer (pool에서의 선택/프루닝, 진단 없음), Agent Symbolic Learning (그라디언트 기반, counterfactual 없음), EvoMAC (backprop, causal 없음)과 구별. MAST taxonomy (NeurIPS 2025)는 failure mode를 ground할 수 있음. 리뷰어는 causal framing을 선호한다. **Acceptance 리프트 추정: +5–8 percentage point.**

### 전략 B — Cross-asset financial 벤치마크 + 시스템 (가장 novelty, medium feasibility)

**GeoMacroBench** 구축: 2023–2025년의 30–50개 지정학 event (적어도 하나의 백본의 post-LLM-cutoff), 각각 5–10개 cross-asset reasoning 질문 (예: "2023년 10월 이스라엘-하마스 분쟁이 주어졌을 때 Brent, DXY, 10Y UST, EM equity, 방위산업 주식의 30일 기대 방향은 무엇이고, 이유는?"), Bloomberg consensus + realized outcome에서의 gold answer. 당신의 bond/equity/geopolitics/quant 분해를 TradingAgents, FinCon, single-agent baseline과 평가. **이것은 데이터셋 기여 가치와 도메인 novelty 가치를 동시에 가진다.** 비교 가능성을 위해 FinBen + FinanceBench와 pair. backtest-bias 비판을 선제 대응하기 위해 FINSABER 방법론 사용. **Acceptance 리프트 추정: +10–15 pp; NeurIPS D&B Track에서 가장 강할 수 있음.**

### 전략 C — 과학적 주장으로서의 페르소나-필요성 ablation (가장 리스크, 가장 credibility)

시스템 기여가 아닌 *과학적 조사*로 재포지셔닝: **"특화된 페르소나가 실제로 필요한가, 아니면 prompt diversity의 변장인가?"** 네 조건의 통제 실험: (i) 당신의 full specialist 분해; (ii) 같은 수의 *random* 페르소나; (iii) 다른 temperature의 *동일 clone*; (iv) matched compute에서 best-of-N single agent. 3–5개 벤치마크, 2–3 백본에서 실행. 전문가가 진짜로 도움이 되면 메커니즘적 증거; 안 되면 (MAST가 암시하듯) 현재 환경에서 매우 출판 가능한 **negative result**. MAST 전통의 negative result는 NeurIPS 2025에서 승리. **Acceptance 리프트 추정: +8–12 pp. 리스크: 시스템이 실제로 작동하지 않음을 발견할 수 있음.**

### 추천 결합 전략

A + B 결합: **"cross-asset financial reasoning agent를 위한 diagnostic 컨트롤러, 새로운 지정학-event 벤치마크에서 평가"**로 프레임. 이것은 method contribution (diagnostic 컨트롤러) + benchmark contribution (GeoMacroBench) + domain contribution (first-class agent로서의 bond + geopolitics)을 제공. NeurIPS D&B Track (5월 6일 feasible하면) 또는 ARR 경유 EMNLP 2026 main (5월 25일)에 제출.

### 전략에 관계없이 필수 ablation

- **컨트롤러 on/off** (고정된 planner+executor baseline).
- **Random-persona control** (같은 수의 에이전트, random role) — 구조가 중요한지 테스트.
- **고정 토폴로지 control** — 토폴로지 탐색이 중요한지 테스트.
- **iteration 수 sweep** — 컨트롤러가 수렴하는지, oscillate하는지, 회귀하는지.
- **백본 sweep** (≥2 family) — 더 강한 모델에서도 이득이 유지되는지.
- **Matched compute에서의 best-of-N** — post-MAST 결정적 baseline.
- **ADAS, Puppeteer, 그리고 MaAS/EvoMAC/FlowReasoner 중 하나와의 직접 비교.**
- **LLM-judge calibration** on ≥100 sample, human agreement κ.
- **Cost Pareto curve** (tokens + $-cost + wall-clock vs. performance).

---

## 맺음 평결

현재 서술된 대로의 제안은 현재 형식과 타임라인으로는 NeurIPS 2026 main track에 들어가지 못한다. 솔직한 전진 경로는 (1) cross-asset financial 벤치마크 + diagnostic 컨트롤러 주위로 좁히고 reframe하여 ARR 경유 EMNLP 2026 (5월 25일, 31일, feasible) 타겟, 또는 (2) 현재 스코프에 8–10주가 필요함을 받아들이고 진정으로 더 강한 실험 패키지로 NeurIPS 2026 workshop 또는 COLM 2027을 목표로 한다. 세 번째 솔직한 옵션은 페르소나-필요성 negative-result 실험 실행 — 빠르고 저렴하고 2026 환경에서 credible하고 출판 가능 — 이지만 system-paper framing을 포기해야 한다. Puppeteer, MaAS, ADAS, EvoMAC에 대한 날카로운 차별자 없이 me-too evolving-orchestrator 논문을 제출하지 말라; reject될 것이며 reject는 옳을 것이다.

---

## 업데이트 로그

### 2026-04-24 — GSM8K 은퇴; 도메인 특화 벤치 주위로 H1 재정의

**경험적 trigger.** `calib_01` (n_val = n_test = 50, max_iters = 3, seed = 0)에서 GSM8K의 *evolved graph가 두 baseline 모두보다 test에서 낮음* (86% vs CoT 92% / P-E 90%) — 토큰은 2–3.7배 더. Controller rationale이 tape-grounded 진단이 아니라 generic "agent 하나 더 붙이자" 반사처럼 읽힘. 전체 분석: `docs/insights/pilot_ko.md` §4; 재현 노트북: `notebooks/calib_01_analysis.ipynb`.

**진단.** GSM8K는 multi-agent 시스템에 구조적으로 under-rewarding. Task 맥락이 self-contained (외부 지식 레버 X), 해결 궤적이 선형 산술 (실제 분업 X), 단일 강한 LLM (Qwen2.5-32B)이 이미 94%로 포화. Persona 전문화에 **정보 비대칭 레버가 없음** — 추가 agent가 할 수 있는 건 정보 체인을 오염시키는 것뿐. 문헌 신호와도 일치 — Li et al. 2024 (MEDIQ)는 non-interactive-initial이 basic interactive보다 우위 (GPT-3.5에서 45.6% vs 42.2%)를 보고. "agent가 많다 = 자동으로 좋다"가 아님.

**갱신된 H1 (2026-04-24).** Reflection-only multi-agent evolution이 single-LLM (CoT)과 minimal-multi-agent (Planner-Executor) baseline보다 **persona가 이질적 전문성 혹은 정보를 담는 domain-specific 과제**에서 — 구체적으로 FinanceBench와 AgentClinic에서 — 측정 가능한 val/test 개선을 낸다. MEDIQ non-interactive는 sanity / 파이프라인 플랫폼으로만 사용 (단독으로 multi-agent affordance를 probe하지 않음; `pilot_ko.md` §6.4 참조).

**Falsifier.** 세 도메인 *모두*에서 n ≥ 30 (`roadmap_ko.md`의 §5.2 측정)에 `evolved ≈ baseline`이면, 위 §7의 Strategy C (persona-necessity negative result)로 재프레이밍 — 이것이 side axis가 아니라 primary contribution이 됨.

**이 피봇이 commit하는 것.** 피봇은 동시에 "GSM8K가 *the wrong domain*이었지 *단지 어려운 것*이 아님"을 입증할 것을 commit. 이 주장은 위 관찰들로부터 defensible하지만, 논문 작성 시 related-work 섹션에서 명시적으로 써야 한다.

**활성화된 벤치마크.**
- **FinanceBench** (Patronus, CC-BY-NC-4.0, 150 샘플) — SEC filing 기반 single-turn Q→A. LLM-judge 채점.
- **MEDIQ non-interactive initial** (Li et al. 2024, CC-BY-4.0, 13k cases, dev subset) — frozen first-turn snippet 기반 MCQ. MCQ exact-match 채점. 가설 테스트가 아닌 sanity 플랫폼.
- **AgentClinic single-pass wrapper** (Schmidgall et al. 2024, MIT, MedQA variant 107 cases) — full OSCE case → one-shot 진단. LLM-judge 채점. 원래의 multi-turn 모드는 후단계로 연기.

**지금까지 파이프라인 수준 관찰** (sanity batch, n=3): controller rationale이 **도메인 적응적** (AgentClinic의 "summarizer for concise diagnosis"가 GSM8K의 "arithmetic verifier" 반사를 대체). 피봇이 H1을 회복시킬 수 있다는 첫 *긍정* 경험적 신호. FinanceBench는 별도로 long evidence context 하에서 controller의 DAG 규율 실패를 드러냄 — 패치는 `roadmap_ko.md`의 §5.1.
