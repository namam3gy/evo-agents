# RESEARCH STATUS — `agent_orchestration` 파일럿

**Snapshot 일자**: 2026-04-25

파일럿이 지금 어디에 있는지, 최근 데이터가 무엇을 말하는지, 다음 결정
지점이 무엇인지에 대한 상위 수준 종합. 일상 추적은
[`references/roadmap_ko.md`](references/roadmap_ko.md) 참고; 실행 시
얻은 전술적 교훈은 [`docs/insights/pilot_ko.md`](docs/insights/pilot_ko.md)
참고. 영어 원본:
[`RESEARCH_STATUS.md`](RESEARCH_STATUS.md).

---

## TL;DR

1. 2026-04-24 GSM8K → 도메인 벤치마크 피봇 이후, FinanceBench / MEDIQ /
   AgentClinic 세 도메인에서 파이프라인이 end-to-end로 안정 동작.
2. 첫 calibration (`calib_01`, GSM8K, n=50)에서 evolved가 두 baseline
   모두에 대해 test에서 -4 ~ -6 pp 열세, 토큰은 2.1-3.7배 → 도메인
   피봇의 실증적 트리거.
3. 다음 결정 지점: **각 새 도메인에서 n=30 첫 측정** (FinanceBench
   controller-prompt 패치 후). 그 결과로 분기 — Framing B (한 도메인이
   이긴다), Framing C (negative result), Framing A+B (혼합 → causal
   controller 스토리).

---

## 문서 지도

| 파일 | 용도 |
|---|---|
| `RESEARCH_STATUS_ko.md` (본 문서) | Snapshot — 지금 위치, 다음 행동 |
| `references/project_ko.md` | 연구 스펙 + brutal한 novelty / venue 평가 |
| `references/roadmap_ko.md` | Living dashboard — Done / In Progress / Next / Decisions |
| `docs/insights/pilot_ko.md` | 실행 단위 전술 인사이트 (운영, 방법론, 코드) |
| `notebooks/calib_01_analysis.ipynb` | calibration의 셀 단위 read-out |
| `README.md` / `CLAUDE.md` | 빠른 시작 + 에이전트 가이드 |

영어가 canonical; `*_ko.md` mirror가 함께 존재.

---

## 현재 상태

단계: **피봇 직후, 첫 도메인 측정 직전**.

- 가장 최근 commit: `e5725e7` (controller DAG 규칙 재명시), 그 위에
  `a531a3f` (도메인 피봇 + restructure).
- 활성 브랜치: `feat-domain-pivot` → `main`에 병합 준비 완료.
- 활성 가설: **H1** (피봇 후) — [§가설](#가설) 참고.
- 활성 블로커: FinanceBench의 긴 컨텍스트가 controller의 DAG 규칙을
  밀어내는 현상 (`pilot_ko.md` §6.3). 패치는 `e5725e7`로 반영됨;
  n=3 sanity 재실행은 아직.

---

## 지금까지 실증 발견

### 파일럿 인프라 (검증됨)

- vLLM 0.19.1 + Qwen2.5-32B-Instruct, 공유 H200에서 `EVO_GPU_UTIL=0.55`로
  안정.
- `evolve_log.json`에 `is_noop` 필드 안착; `calib_01`의 3 iter 모두
  `is_noop == False` — controller가 saturated val 하에서도 no-op로
  무너지지 않음.
- `src/evolve.py`의 Opt-2 strict accept 의미론으로 `calib_01`에서
  드러난 `best_graph` ↔ `best_val_acc` 디커플링 해결
  (`results/smoke_opt2/`에서 검증).

### `calib_01` (GSM8K, n=50, max_iters=3, 약 66분)

|  | val | test | tokens / test task |
|---|---:|---:|---:|
| CoT | 94% | 92% | 350 |
| Planner-Executor | 94% | 90% | 621 |
| Evolved (4 agents, 8 edges) | — | **86%** | **1,303** |

**헤드라인**: evolved는 두 baseline 모두에 대해 test에서 4-6 pp 열세,
토큰은 2.1-3.7배. n=50에서는 표본 오차 한계 내 (3-sample 비교 95% CI
약 ±7 pp)이므로 *증명*은 아니지만, 격차가 일관되게 잘못된 쪽.

**진단** (`pilot_ko.md` §4.3): controller rationale이 빈약 — tape에
근거한 인과 진단이 아니라 "verifier 추가" / "reformulator 추가" 같은
일반적 반사. 이게 정확히 Framing A (causal/diagnostic controller)가
공격하려는 실패 모드.

### 도메인-피봇 sanity (벤치당 n=3, 2026-04-24)

| Benchmark | E2E 동작 | Controller가 도메인 적응적인가 |
|---|---|---|
| MEDIQ | ✅ | tie → Opt-2 REJECT |
| AgentClinic | ✅ | ✅ "concise diagnosis"용 `add_agent(summarizer)` 제안 |
| FinanceBench | ✅ | ❌ DAG-invalid edit 두 번 — `e5725e7`에서 패치 |

n=3 sanity 정확도는 방법 간 비교에는 너무 노이즈가 큼 (vLLM batch
경계의 temp=0 비결정성 + LLM-judge 분산). 단, 두 가지 정성 신호가
중요:
- **긍정**: controller rationale이 **도메인에 따라 변함**. GSM8K의
  "arithmetic verifier" 반사가 AgentClinic에서는 "concise diagnosis용
  summarizer"로 바뀜. 도메인 피봇이 가능성을 가진다는 첫 근거.
- **부정**: FinanceBench의 긴 evidence 컨텍스트가 controller의 DAG
  추론을 밀어냄. `e5725e7` 패치가 그 자리의 명백한 실패 모드를 다루지만,
  controller가 FinanceBench에서 정말 유용한 edit을 내는지는 미지수.

---

## 가설

**H1 (2026-04-24)**: Reflection-only multi-agent evolution은 CoT 및
Planner-Executor baseline 대비 측정 가능한 val/test 향상을 만든다 —
**persona가 이질적 전문성/정보를 운반하는 도메인 task에서**
(FinanceBench, AgentClinic). MEDIQ non-interactive initial mode는
sanity 전용 — Li et al. 2024이 GPT-3.5에서 non-interactive setting이
interactive보다 열세임을 이미 문서화했으므로, 거기서 baseline 수준
결과가 나와도 H1을 *반증*하지 않음.

**Falsifier**: n ≥ 30에서 *세 도메인 모두* evolved ≈ baseline이면
Framing C (persona-necessity negative result)로 재프레임.

**H1의 도메인 제한에 대한 실증 트리거**: GSM8K (자기충족 텍스트, 선형
산술, 단일 모델 ~94% 포화)는 multi-agent가 활용할 정보 비대칭 레버가
구조적으로 없음. `calib_01`의 회귀를 *"틀린 도메인"*으로 읽음 —
*"어려운 도메인"*이 아님.

---

## 다음 결정 (즉시, 순서대로)

| # | Action | 산출 | 트리거되는 결정 |
|---|---|---|---|
| 1 | `e5725e7` 후 FinanceBench n=3 sanity 재실행 | 긴 컨텍스트에서 DAG 유효성 회복 여부 | FinanceBench의 #2 unblock |
| 2 | 도메인-피봇 첫 측정: 벤치당 n_val = n_test ≈ 30 | 세 도메인의 첫 실측 정확도 신호 (~1.5h) | **Framing B vs C vs A+B** |
| 3 | rationale 태깅 (특정 tape 인용 vs 일반론) | rationale 품질 정량 신호 | Framing A 범위 결정 입력 |

#2 이후 분기:
- **Branch B**: ≥1 도메인에서 evolved > baseline → Framing B (또는
  A+B) 확정, EMNLP ARR (D-31, 2026-05-25) 목표.
- **Branch C**: 어디서도 evolved ≈ baseline → Framing C (negative
  result)로 피봇, MAST 계열 "persona-necessity 검증"으로 재프레임 —
  2026 분위기에서 빠르고 저렴하고 신뢰성 있음 (`project_ko.md` §7).
- **Branch A+B**: 도메인 간 혼합 결과 → "diagnostic controller, 잘
  되는 도메인에서 평가"로 좁힘.

---

## 미결 결정 (`roadmap_ko.md` §6)

| 항목 | 미결 시점 | 메모 |
|---|---|---|
| Paper framing | 2026-04-24 | §5.2 측정 후 (≤1주) 해소 |
| Target venue | 2026-04-24 | EMNLP ARR (5/25) primary; D&B (5/6) 공격적 |
| Backbone mix | 2026-04-24 | 두번째 backbone은 예산 결정 필요 |

---

## 리스크 레지스터

1. **Time-to-deadline**: EMNLP ARR까지 D-31. 아래 reviewer-bar
   체크리스트 9개 중 ~2/9 clear. 전부 clear는 `project_ko.md` §5
   기준 6-8주 필요. **완화**: 풀 reviewer 요구 대신 A+B (또는 C)로
   범위를 좁힘; ARR은 기여를 *프레이밍*하는 사이클이지 *증명*하는
   사이클이 아님.
2. **단일 H200 병목**: §5.2 scaling은 seed당 ~5-6h × 3 seed = 15-18h
   wall로 추정 (`pilot_ko.md` §4.4). Backbone당 sequential.
   Multi-backbone은 추가 GPU 할당이나 API 예산 필요.
3. **LLM-judge self-bias** (FinanceBench, AgentClinic): 같은
   Qwen2.5-32B가 자신을 judge함. Reviewer가 반드시 물음. **완화**:
   `roadmap_ko.md` §5.5 — 별도 family judge (Claude Haiku 4.5 또는
   GPT-4.1-mini), judge-only 예산.
4. **피봇 자체가 독자에게 빚진 스토리**: "도메인이 도와준다"가 아니라
   "GSM8K가 옳은 이유로 틀린 testbed였다"를 증명해야 함.
   `pilot_ko.md` §6에 논거는 있으나 scaled-n 확인이 필요.

---

## Paper-readiness 자기평가

`project_ko.md` §3의 reviewer-bar 체크리스트:

| 항목 | 상태 |
|---|---|
| Best-of-N single-agent @ matched compute | ❌ |
| ≥2 backbone families | ❌ — Qwen only |
| ≥3 heterogeneous benchmarks (non-saturated 1개 포함) | ⚠️ 3개 scaffolded, scale에서 0개 측정됨 |
| ADAS + (Puppeteer / MaAS / EvoMAC 중 1) 직접 비교 | ❌ — ADAS는 필수 |
| Harness ablation (controller on/off, random persona, fixed topo) | ❌ |
| Failure-mode taxonomy (MAST-style) | ❌ |
| Cost Pareto (tokens × wall × $) | ⚠️ 토큰만 부분 기록 |
| LLM-judge calibration (≥100 samples, human κ) | ❌ |
| Code + prompts + tool defs + model versions 공개 | ⚠️ 내부에만 |

**합산**: 0 cleared, 3 partial, 6 not started. 전부 clear에 6-8주.
EMNLP ARR (D-31)은 풀 reviewer 요구가 아니라 방어 가능한 부분집합
(A+B 또는 C)으로 범위를 좁힐 때만 현실적.

---

## 한 줄 요약

> `calib_01`에서 evolved < baseline이 나와 GSM8K를 떠났고, 세 새
> 도메인 벤치를 깔아 도메인-적응 controller rationale의 첫 긍정 신호를
> 얻었다. FinanceBench DAG 규칙 패치 (`e5725e7`) 후, 다음 행동은 n=30
> 첫 측정으로 Framing B vs C vs A+B를 결정하는 것.
