# 자기 진화형 다중 에이전트 오케스트레이션 (Self-Evolving Multi-Agent Orchestration) 연구 리뷰

> **작성일**: 2026-04-25  
> **대상 브랜치**: `claude/review-2026-04-25`  
> **검토 범위**: 프로젝트 루트의 `README.md`, `INSIGHTS.md`, `CLAUDE.md`, `src/`, `scripts/`, `demo.ipynb` 일체  
> **검토 목적**: ① 가설 ↔ 실험 정합성 ② 연구 방향 적절성 ③ NeurIPS / EMNLP 채택 가능성 분석 ④ 채택 가능성 향상을 위한 수정안

---

## 0. 사전 안내 (Disclaimer)

- 작업 시작 시점 기준으로 프로젝트 내 `references/`, `docs/` 디렉터리는 **존재하지 않습니다**. 따라서 본 리뷰는 다음 자료에 한정해 수행했습니다.
  - `README.md` — 연구 의도, Related Work, 헤드라인 가설 정리
  - `INSIGHTS.md` — 파일럿 실행 결과 및 운영상 발견사항
  - `src/*.py` — 컨트롤러/오케스트레이터/그래프/평가 구현
  - `scripts/run_pilot.py` — 파일럿 엔트리포인트
  - `demo.ipynb` — 실행 결과 시연 노트북
- 외부 관련 연구 검증은 2026년 4월 시점 웹 검색을 활용했습니다 (말미 출처 참고).
- 본 문서는 한국어로 작성하며, 영문 약어는 첫 등장 시 풀어 적습니다 (예: 거대 언어 모델 (Large Language Model, LLM)).

---

## 1. 한 줄 요약 (TL;DR)

> **현재 파일럿의 아이디어는 "신선한 한 가지 점"을 가지고 있지만, 그 점이 NeurIPS/EMNLP 본 학회 단일 논문으로 통과하기엔 (a) 실험 규모가 임계량 미만이고, (b) 동시기 NeurIPS 2025 등재 논문 2편과 직접 충돌합니다. 채택 가능성을 의미 있게 끌어올리려면 ① 다중 도메인 × 다중 시드 × 다중 백본 실험으로 스케일업, ② "탐색 없이 (search-free) 반성만으로 (reflection-only)" 라는 차별점을 실험적으로 분리·증명, ③ EMNLP/Workshop 트랙 동시 노림수가 합리적 전략입니다.**

---

## 2. 프로젝트 현황 정리

### 2.1 연구 가설 (Research Hypothesis)

`README.md`와 `controller.py`의 시스템 프롬프트로부터 다음과 같이 재구성할 수 있습니다.

| 구분 | 명시적 (Explicit) | 암묵적 (Implicit) |
|---|---|---|
| 핵심 주장 | "거대 언어 모델 기반 컨트롤러가 **순수 반성 (in-context reflection)** 만으로 다중 에이전트 유향 비순환 그래프 (Directed Acyclic Graph, DAG)의 **위상(topology) + 페르소나(persona) + 엣지(edge)** 를 함께 진화시킬 수 있다" | (1) 탐색 (검색 / 몬테 카를로 트리 탐색 / 슈퍼넷) 없이도 작동한다 (2) 컨트롤러를 학습시키지 않아도 작동한다 (3) 동결된 (frozen) 32B 백본에서 작동한다 |
| 기대 결과 | 진화된 그래프가 2~3 iteration 내에 베이스라인 (Chain-of-Thought, Planner-Executor) 을 상회하고 plateau에 도달 | val ↔ test 일반화 격차 < 3pp |
| 행동 신호 | verifier / critic / 재구성기 (reformulator) 에이전트 추가 + 비-선형 엣지 출현 | 컨트롤러가 saturated 상태에서도 의미 있는 개입을 한다 |

### 2.2 구현 구조 (Implementation Topology)

```
                 ┌──────────────────────────┐
                 │  Worker Layer (frozen)   │
                 │  Qwen2.5-32B-Instruct    │
                 │  (vLLM, OpenAI-compat)   │
                 └────────────┬─────────────┘
                              │ trajectory tapes
                              ▼
        ┌─────────────────────────────────────────┐
        │   Controller (LLM call, JSON output)     │
        │   propose_edits(graph, outcomes, prior)  │
        │   ops: add/remove/rewrite_persona +      │
        │        add/remove edge                   │
        └────────────┬────────────────────────────┘
                     │ EditBatch
                     ▼
        ┌─────────────────────────────────────────┐
        │   apply_edits → validate (DAG, reach)   │
        │   accept slack-based hill climbing       │
        └─────────────────────────────────────────┘
```

핵심 모듈은 다음과 같이 정리됩니다.

| 파일 | 역할 | 라인 단서 |
|---|---|---|
| `src/types.py` | `Agent`, `Graph`, `Edit`, `EditBatch` 등 핵심 데이터 모델 (Pydantic) | 60–84 |
| `src/graph.py` | DAG 검증, edit 적용, seed CoT/Planner-Executor | 73–142 |
| `src/orchestrator.py` | 위상 정렬 후 worker 호출, tape 누적 | 36–67 |
| `src/controller.py` | JSON edit 제안, 시스템 프롬프트, 재시도 1회 | 15–42, 105–127 |
| `src/evolve.py` | hill climbing 루프, accept_slack 기반 수용/거부 | 60–167 |

### 2.3 파일럿 실험 결과 (현재까지)

`INSIGHTS.md`로부터 정리:

| 항목 | 관찰값 | 해석 |
|---|---|---|
| n_val=5, n_test=5 smoke 결과 | CoT/P-E/Evolved 모두 100% | **차이가 보이지 않음**. 헤드라인 수치로 인용 불가 |
| 컨트롤러 행동 (iter 1, val=100%) | `add_agent(verifier) + add_edge(executor→verifier) + add_edge(verifier→END)` | val saturate 상태에서도 가설적 실패 모드 지목 → 긍정적 신호 |
| 토큰 비용 비율 | worker 11,977 vs controller 3,534 (≈ 3.4×) | 비용 지배 요인은 worker × iter |
| 시드 다양성 | seed=0 단일 | 분산 (variance) 측정 불가능, 체리피킹 위험 |
| 도메인 다양성 | GSM8K 단일 | 일반화 주장 곤란 |

---

## 3. 가설 ↔ 실험 결과 정합성 분석

### 3.1 정합성 매트릭스

| 가설 | 직접 검증된 부분 | 검증되지 못한 부분 | 위험도 |
|---|---|---|---|
| H1: 반성 기반 컨트롤러가 의미 있는 그래프 편집을 만든다 | iter 1에서 verifier 제안 (코드/로그 1건) | 다양한 실패 모드 → 적절한 edit 매핑이 일관되는지, no-op 비율 등 | 🟡 중 |
| H2: 동결 백본에서 베이스라인 대비 성능 향상 | (n=5 포화로 측정 불가) | accuracy_vs_iter.png 의미 있는 곡선 부재 | 🔴 높음 |
| H3: val→test 일반화 격차 < 3pp | (테스트 n=5로 측정 불가) | held-out 일반화 증거 전혀 없음 | 🔴 높음 |
| H4: 탐색 없이 (search-free) 작동 | 코드상 명백 (greedy + accept_slack) | 탐색 기반 (AFlow, MaAS) 대비 우위 입증 데이터 없음 | 🟡 중 |
| H5: 컨트롤러 학습 없이 작동 | 코드상 명백 (ICL only) | 학습된 컨트롤러 (MaAS, AgentNet) 대비 우위 데이터 없음 | 🟡 중 |

### 3.2 핵심 결론

> **현재 단계 = "정상 동작 확인 (sanity check)" 단계이며, "가설 검증" 단계가 아닙니다.**  
> 코드는 의도대로 동작하고 컨트롤러가 합리적인 edit을 산출한다는 사실 자체는 잘 보였습니다. 그러나 H2/H3 (성능 우위 + 일반화) 는 통계적으로 입증된 바가 전혀 없습니다. INSIGHTS.md §4의 "n_val 300+, seed≥3, no-op 로깅" 작업이 모두 선행되어야 본 실험 단계에 진입한다고 평가합니다.

---

## 4. 관련 연구 지형 (Related Work Landscape)

`README.md`에 명시된 6편 + 웹 검색으로 발견한 동시기 (2025–2026) 핵심 연구를 표로 정리합니다.

### 4.1 비교표

| # | 논문 / 약어 | 학회 | 그래프 표현 | 최적화 방식 | 컨트롤러 학습 | 동결 백본 | 위상 진화 | 페르소나 진화 | 본 파일럿과의 거리 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **ADAS** (Hu et al., 2024) | ICLR 2025 | 자유 코드 (Python) | 메타 에이전트 + 아카이브 검색 | ❌ | ✅ | ✅ | ✅ (코드 내 임의) | 가까움. 차이는 **구조화 JSON edit ↔ 자유 코드 생성** |
| 2 | **AFlow** (Zhang et al., 2024) | ICLR 2025 Oral | 코드 노드 + 엣지 | **MCTS** + 실행 피드백 | ❌ | ✅ | 부분 (operator) | ✅ | 가까움. 차이는 **탐색 알고리즘 의존도** |
| 3 | **GPTSwarm** (Zhuge et al., 2024) | ICML 2024 Oral | 계산 그래프 | **REINFORCE 학습** | ✅ (gradient) | ❌ | ✅ (엣지) | ❌ (노드 prompt만) | 중간. **학습 vs 무학습** 축에서 분리 |
| 4 | **MaAS** (Zhang et al., 2025) | ICML 2025 Oral | Agentic Supernet | **슈퍼넷 + 컨트롤러 학습** | ✅ | 부분 | ✅ (라우팅) | ❌ | 중간. **NAS 패러다임** 자체를 거부하는 차이 |
| 5 | **Multi-Agent via Evolving Orchestration** (Dang, Qian et al.) | NeurIPS 2025 | 센트럴 오케스트레이터 + puppets | **강화 학습 (RL)** | ✅ | ❌ | ✅ (라우팅) | ❌ | **직접 충돌** — 제목·문제 정의 가까움 |
| 6 | **AgentNet** (Yang et al.) | NeurIPS 2025 | 분산 (decentralized) DAG + RAG | 분산 진화 + 라우팅 | ✅ | ❌ | ✅ | 부분 | **직접 충돌** — DAG 진화 키워드 일치 |
| 7 | **EvoFlow** (Zhang et al., 2025) | preprint (ICLR'26 후보) | code workflow population | **유전 알고리즘 (GA)** + niching | ❌ | ✅ | ✅ | 부분 | 가까움. 차이는 **GA vs reflection** |
| 8 | **AGP / Adaptive Graph Pruning** | ECAI 2025 | 최대 완전 그래프 + pruning | **2-stage 학습 (NAS)** | ✅ | ❌ | ✅ | ❌ | 중간 |
| 9 | **TAVO (Trajectory-Aware Verbalized Optimization)** | OpenReview 2025 | prompt-level | **언어화된 (verbalized) 정책 편집** | ❌ | ✅ | ❌ | ✅ | **가장 가까운 정신적 친척** — 위상은 안 바꿈 |
| 10 | **Reflexion / Self-Refine 계열** | NeurIPS 2023 + | single agent | self-feedback | ❌ | ✅ | ❌ | (rewrite) | 멀음. 단일 에이전트 한정 |

### 4.2 차별화 포지셔닝 다이어그램

```
                  학습 기반 (Trained)
                          ▲
                          │
            GPTSwarm ●  ●  AGP
                     │
     MaAS ●          │   ● Evolving Orchestration (NeurIPS 25)
                     │   ● AgentNet (NeurIPS 25)
                     │
탐색 기반 ◀──────────┼──────────▶ 탐색 없음 (Reflection-only)
     ●  AFlow (MCTS) │   ● ADAS (Archive search)
     ●  EvoFlow (GA) │
                     │
                     │   ★ ★  ← 본 파일럿 (Reflection + Frozen + No search)
                     │   ● TAVO (prompt-only, 위상 미진화)
                     ▼
                  학습 없음 (Training-free)
```

★ 위치는 **"학습 없음 × 탐색 없음 × 위상 + 페르소나 동시 진화"** 라는 좁은 사분면입니다. 이론적 빈 공간으로서는 의미 있으나, 그 공간이 실증적으로 가치 있다는 증명이 필요합니다.

### 4.3 직접 충돌 (Concurrent Work) 알림

| 논문 | 충돌 정도 | 본 파일럿이 다른 점 |
|---|---|---|
| **Multi-Agent Collaboration via Evolving Orchestration** (NeurIPS 2025, Dang & Qian) | 🚨 매우 높음 | 그쪽은 **학습된 (RL) 오케스트레이터**, 본 파일럿은 **무학습 ICL 컨트롤러**. 그쪽은 cyclic structure emergence, 본 파일럿은 strict DAG. |
| **AgentNet** (NeurIPS 2025) | ⚠️ 높음 | 그쪽은 **분산 + RAG**, 본 파일럿은 **중앙 집중 + 무메모리** |
| **EvoFlow** (preprint) | ⚠️ 중간 | 그쪽은 **유전 알고리즘**, 본 파일럿은 **반성** |

> 즉 "다중 에이전트 오케스트레이션을 진화시킨다" 는 큰 줄기는 NeurIPS 2025에 이미 두 편이 자리 잡았기에, **본 파일럿은 정확한 차별점 (axis of difference) 을 명시적으로 1–2 문장으로 발화하지 못하면 reviewer로부터 incremental 판정을 받기 매우 쉽습니다.**

---

## 5. NeurIPS / EMNLP 채택 가능성 분석

### 5.1 학회별 특성

| 학회 | 주요 평가축 | 일반적 채택률 | 다중 에이전트 트랙 분위기 (2025–2026) |
|---|---|---|---|
| **NeurIPS 2026 (Main)** | 새로움(novelty) + 실험 엄밀성 + 이론적 통찰 | ≈ 22-26% | 매우 경쟁적. 이미 AgentNet, Evolving Orchestration 채택. **차별점이 분명해야 함** |
| **NeurIPS 2026 (Datasets & Benchmarks)** | 재현성 + 커뮤니티 가치 + 벤치마킹 표준 | ≈ 30% | "training-free baseline 표준화" 각도로 재포장 가능 |
| **EMNLP 2026 (Main)** | NLP 기여 + 실험 엄밀성 | ≈ 20-25% | 추론(reasoning) + 다중 에이전트 인기 트랙 |
| **EMNLP 2026 (Findings)** | 위와 유사하나 incremental 허용 | ≈ 30-35% | **현실적 1순위 후보** |
| **NeurIPS / EMNLP Workshop** | 새로움 < 명확성 < 재현성 | ≈ 50-65% | 타이밍 좋음 (Multi-Turn Interactions WS, Multi-Agent WS 등 활발) |

### 5.2 현재 상태 그대로의 채택 가능성 추정 (보수적)

| 트랙 | 추정 확률 | 주된 거절 사유 (예상) |
|---|---|---|
| NeurIPS 2026 Main | **3-7%** | (a) 실험 규모 부족 (1 도메인, n=5, seed=1) (b) NeurIPS 25 동시기 논문과 차별점 모호 (c) 이론적 분석 부재 |
| EMNLP 2026 Main | **8-12%** | 위 (a)(b)와 동일 + NLP 기여각 모호 |
| EMNLP 2026 Findings | **20-28%** | 차별점 약함 |
| 관련 Workshop | **45-60%** | 무난한 채택권 |

### 5.3 보강 후 채택 가능성 (가정: §6 권고안 모두 수행)

| 트랙 | 추정 확률 | 핵심 가정 |
|---|---|---|
| NeurIPS 2026 Main | **15-25%** | 3 도메인 × 3 시드 × 2 백본, ADAS/AFlow/MaAS 직접 비교에서 cost-adjusted 우위 |
| EMNLP 2026 Main | **25-35%** | 위 + NLP 추론 (reasoning) 중심 framing |
| EMNLP 2026 Findings | **45-55%** | "training-free 베이스라인" 각도 |
| Workshop | **70-85%** | 매우 안정적 |

> **수치는 절대값이 아니라 상대적 위계로 읽어주세요.** 본 학회 채택은 reviewer 분배 효과가 ±10pp로 작용합니다.

---

## 6. 채택 가능성을 높이기 위한 권고안

### 6.1 즉시 실행 (실험 규모 임계점 돌파)

| # | 권고 | 근거 | 우선순위 |
|---|---|---|---|
| R1 | **n_train=64+, n_val=300+, n_test=500+** 으로 고정 재실행 | INSIGHTS §2.1, §4.1 — n=5에선 차이 측정 불가 | 🔴 P0 |
| R2 | **시드 ≥ 3** 으로 평균 ± 표준편차 보고 | reviewer #1이 가장 먼저 보는 항목. 단일 시드는 reject 필연 | 🔴 P0 |
| R3 | **3개 이상 도메인** — GSM8K (수학) + HumanEval/MBPP (코드) + HotpotQA (다단계 QA) | NeurIPS 2025 6편 모두 ≥ 3 도메인. 단일 도메인은 NeurIPS 본 학회에선 거의 즉사 | 🔴 P0 |
| R4 | **백본 다양화** — Qwen2.5-32B + Llama-3.1-70B + GPT-4o-mini 등 ≥ 2 | 일반화 주장 + cross-LLM transfer (MaAS의 강점이기도 함) | 🟠 P1 |
| R5 | **ADAS, AFlow, MaAS와 동일 백본·동일 데이터로 직접 비교** | reviewer가 즉시 묻는 질문. 코드는 모두 공개됨 | 🔴 P0 |

### 6.2 방법론 개선 (Methodology Sharpening)

| # | 권고 | 근거 |
|---|---|---|
| R6 | **Ablation #1**: 반성 (reflection) vs 무작위 edit, 반성 vs 단순 prior-free edit | "reflection이 진짜 효과적인가" 라는 핵심 질문에 답해야 함 |
| R7 | **Ablation #2**: topology-only vs persona-only vs both | 본 파일럿의 키워드 "co-evolve" 의 가치 입증 |
| R8 | **Ablation #3**: accept_slack 민감도 (0.0 / 0.02 / 0.05) | hill climbing의 robustness 측정 |
| R9 | **No-op 비율, edit reversal, edit divergence 지표 추가** | INSIGHTS §2.2 후속 — "컨트롤러가 점점 보수적이 되는가?" 측정 |
| R10 | **비용 정규화 평가** — accuracy / dollar, accuracy / token | AFlow, MaAS의 강력한 비교축. 무학습이 비용 우위로 직결됨을 정량화 |
| R11 | **컨트롤러 백본 분리** — worker = 32B, controller = 8B / 70B 변동 | 무학습 ICL 컨트롤러의 saturation 점 측정 |

### 6.3 이론적 / 개념적 보강 (Theoretical Framing)

| # | 권고 | 근거 |
|---|---|---|
| R12 | **차별점을 1-문장 슬로건으로** — 예: *"Search-free, training-free co-evolution of topology and personas via verbalized edit policies."* | reviewer 첫 페이지 노출용 |
| R13 | **이론적 모티베이션 절** 추가 — JSON edit 공간을 이산 정책 공간으로 보고, in-context reflection을 verbalized policy improvement로 framing | TAVO와의 연결 + GPTSwarm/MaAS와의 거리 명시 |
| R14 | **Failure case study** — 반성-only가 실패하는 task family 1개 이상 솔직히 보고 | 부정적 결과는 reviewer 신뢰도를 크게 올림 |
| R15 | **Interpretability 절** — JSON edit 시퀀스의 자연어 해독 가능성을 강조 | ADAS/AFlow의 코드 생성 대비 본 파일럿의 명확한 우위 |

### 6.4 위험 관리 (Risk Mitigation)

| # | 위험 | 완화 |
|---|---|---|
| RM1 | NeurIPS 2025 동시기 논문과 incremental 판정 | §4.3에 명시한 두 논문을 본문에서 **명시적으로** 비교, 정량적 차이 표로 제시 |
| RM2 | "왜 RL/MCTS가 아닌가" 질문 | R6, R10으로 답변. **무학습이 단지 게으른 것이 아니라 의미 있는 trade-off** 임을 비용 표로 보임 |
| RM3 | "왜 GSM8K만?" 질문 | R3 다중 도메인으로 차단 |
| RM4 | "백본 의존성" 질문 | R4 백본 다양화로 차단 |
| RM5 | reviewer가 단순한 prompt 엔지니어링으로 치부 | R12 슬로건 + R13 이론적 framing으로 차단 |

### 6.5 단계적 발표 전략 (Staged Submission Strategy)

```
2026 Q2  ┌──────────────────────────────────────────────────┐
         │ 1) R1-R5 실행 (4-6주) → 1차 백서 / arXiv          │
         │ 2) NeurIPS 2026 Main 제출 (5월 중순 마감 예상)    │
         └──────────────────────────────────────────────────┘
              │
              │ Reject 시
              ▼
2026 Q3  ┌──────────────────────────────────────────────────┐
         │ 3) reviewer 피드백 반영 + R6-R11 ablation         │
         │ 4) EMNLP 2026 Main 제출 (6월 마감 예상)            │
         │    + 동시 NeurIPS Workshop 제출 (보험)             │
         └──────────────────────────────────────────────────┘
              │
              │ Findings로 떨어져도 ok / Workshop은 거의 확실
              ▼
2026 Q4  Camera-ready + 후속 연구 (lifelong, multi-task)
```

---

## 7. 연구 방향 자체에 대한 큰 그림 평가

### 7.1 방향 자체는 살아있는가?

✅ **그렇습니다.** EvoAgentX/Awesome-Self-Evolving-Agents 서베이가 2025–2026년에 만들어졌고, "self-evolving agents" 라는 표제가 NeurIPS / ACL / EMNLP에서 활발히 다루어지고 있습니다. **시기적으로 늦지 않았습니다.**

### 7.2 다만, 다음 두 가지는 재고하실 가치가 있습니다

#### (a) "오케스트레이션 진화" 라는 거대 줄기는 이미 포화 직전

NeurIPS 2025에 직접 충돌 논문 2편 + ICLR/ICML 2025에 4편이 있는 상태입니다. 이 방향에서 본 학회를 노리려면 (i) 매우 strong한 실증 + (ii) 명확한 axis of difference 두 개가 동시에 필요합니다.

#### (b) 보다 신선한 잠재 각도 (Pivot 옵션)

다음 셋 중 하나로 piv하면 차별성이 자연스럽게 생깁니다.

1. **Lifelong / cross-task evolution**  
   현재는 "GSM8K 한 도메인에서 진화" 입니다. 만약 진화한 그래프가 **다른 도메인 (코드 → 수학 → QA)** 으로 transfer 되거나, 아예 **task family를 자동 식별** 한다면 — MaAS의 "cross-dataset transferability" 와 정면으로 비교 가능합니다.

2. **Interpretability-first framing**  
   ADAS는 자유 Python을 생성하기에 사후 해석이 어렵고, AFlow도 MCTS 내부의 의사결정이 불투명합니다. 본 파일럿은 **JSON edit 시퀀스 + rationale text** 라는 자연 언어 가독 형식이 **무료로** 따라옵니다. 이것을 핵심으로 framing하면 (예: "Auditable architecture evolution") 신선한 차별성이 됩니다.

3. **Cost-Pareto 베이스라인 표준화**  
   비용 대비 정확도에서 무학습 ICL이 학습 기반 (GPTSwarm, MaAS) 대비 어디까지 경쟁력 있는지 표준화한 벤치마크 — NeurIPS Datasets & Benchmarks 트랙에 자연스럽게 들어맞음.

---

## 8. 종합 평가 표

| 평가 항목 | 현재 상태 | 권고안 적용 후 |
|---|---|---|
| 새로움 (Novelty) | 🟡 중 (concurrent works 있음) | 🟢 명확한 axis 확보 |
| 실험 엄밀성 (Rigor) | 🔴 부족 (n=5, seed=1) | 🟢 NeurIPS 표준 충족 |
| 일반화 증거 (Generalization) | 🔴 부재 | 🟢 3 domain × 2 backbone |
| 이론적 통찰 (Insight) | 🟡 약함 | 🟡 verbalized policy framing 추가 시 중 |
| 재현성 (Reproducibility) | 🟢 좋음 (코드 깔끔, uv, INSIGHTS 풍부) | 🟢 동일 |
| 임팩트 잠재력 (Impact) | 🟡 중 | 🟢 interpretability/cost angle 시 상승 |
| 직접 충돌 위험 | 🔴 높음 (NeurIPS 25 ×2) | 🟡 명시적 비교로 완화 |

---

## 9. 결론 및 실행 권고

### 9.1 결론

1. **연구 방향 자체는 유효하며 시기적으로 적절합니다.** 다만 NeurIPS 2025 동시기 채택 논문 2편이 같은 큰 줄기를 차지했기에, **차별점 발화 + 실증 임계량 돌파** 가 동시에 필요합니다.
2. **현재 실험 결과는 가설을 검증하지 못했습니다.** 정상 동작 확인 단계입니다. NeurIPS/EMNLP 수준의 실험은 §6.1 R1–R5 완료 시점부터 시작합니다.
3. **방법론 자체는 좋은 잠재력을 가집니다.** 특히 interpretability / cost 두 축은 학습 기반 경쟁자 대비 본질적으로 유리한 카드입니다.

### 9.2 단기 (4-6주) 실행 권고

```
[1주차]   R1 (스케일업) + R2 (다중 시드) — GSM8K로 우선 견고화
[2-3주차] R3 (도메인 추가) — HumanEval + HotpotQA 통합
[3-4주차] R5 (ADAS/AFlow/MaAS 직접 비교) — 동일 백본
[4-5주차] R6-R11 (ablation 본격화) + R10 (cost 정규화)
[5-6주차] R12-R15 (이론/framing) + 1차 arXiv
```

### 9.3 발표 전략 권고 (현실적)

> **1순위: EMNLP 2026 Main 제출 + NeurIPS 2026 Workshop 동시 보험**  
> **2순위 (모험): NeurIPS 2026 Main 도전 — 단, §6.1 모두 완료 후만**  
> **3순위 (안전): EMNLP Findings + NeurIPS Datasets & Benchmarks 트랙**

---

## 10. 부록: 본 리뷰가 활용한 외부 자료

### 10.1 직접 비교 대상 논문 (출처)

- ADAS — [arXiv 2408.08435](https://arxiv.org/abs/2408.08435), [OpenReview](https://openreview.net/forum?id=t9U3LW7JVX)
- AFlow — [arXiv 2410.10762](https://arxiv.org/abs/2410.10762), [GitHub](https://github.com/FoundationAgents/AFlow)
- GPTSwarm — [PMLR 235:62743](https://proceedings.mlr.press/v235/zhuge24a.html), [GitHub](https://github.com/metauto-ai/GPTSwarm)
- MaAS — [arXiv 2502.04180](https://arxiv.org/abs/2502.04180), [GitHub](https://github.com/bingreeky/MaAS)
- Multi-Agent Collaboration via Evolving Orchestration (NeurIPS 2025) — [arXiv 2505.19591](https://arxiv.org/abs/2505.19591), [OpenReview](https://openreview.net/forum?id=L0xZPXT3le)
- AgentNet (NeurIPS 2025) — [arXiv 2504.00587](https://arxiv.org/html/2504.00587v1), [GitHub](https://github.com/zoe-yyx/AgentNet)
- EvoFlow — [arXiv 2502.07373](https://arxiv.org/abs/2502.07373)
- Adaptive Graph Pruning (ECAI 2025) — [arXiv 2506.02951](https://arxiv.org/abs/2506.02951)
- TAVO (Trajectory-Aware Verbalized Optimization) — [OpenReview](https://openreview.net/forum?id=dkbQwUp9gW)

### 10.2 전반적 트렌드 자료

- [A Survey of Self-Evolving Agents (2025)](https://arxiv.org/abs/2507.21046)
- [Awesome-Self-Evolving-Agents (EvoAgentX)](https://github.com/EvoAgentX/Awesome-Self-Evolving-Agents)
- [NeurIPS 2025 Workshop on Multi-Turn Interactions in LLMs](https://workshop-multi-turn-interaction.github.io/)

### 10.3 본 리뷰의 한계

- `references/`, `docs/` 디렉터리가 부재한 상태로, 작성자가 의도한 "참고 문헌 + 설계 노트" 가 실제로 어떤 내용이었는지 본 리뷰가 알 길이 없습니다. 두 디렉터리에 누적된 문서가 있다면 §3, §4의 정합성 판정과 §6의 권고 우선순위가 변동될 수 있습니다.
- 실험 결과는 `INSIGHTS.md`에 기록된 1-iter 스모크 1건에 한정되어 있습니다. `results/<run_id>/` 로컬 산출물이 추가로 존재한다면 §3.1, §3.2 결론이 강화 또는 수정될 수 있습니다.
- 채택 확률 추정은 학회별 일반적 분포 + concurrent work 효과를 정성적으로 가중한 값이며, 단일 reviewer 효과로 ±10pp 변동합니다.

---

*문서 끝.*
