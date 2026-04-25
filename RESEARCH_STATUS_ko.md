# RESEARCH STATUS — `agent_orchestration` 파일럿

**Snapshot 일자**: 2026-04-25 (controller v2 + v2 n=30 sweep 직후)

파일럿이 지금 어디에 있는지, 최근 데이터가 무엇을 말하는지, 다음 결정
지점이 무엇인지에 대한 상위 수준 종합. 일상 추적은
[`references/roadmap_ko.md`](references/roadmap_ko.md) 참고; 실행 시
얻은 전술적 교훈은 [`docs/insights/pilot_ko.md`](docs/insights/pilot_ko.md)
참고. 영어 원본:
[`RESEARCH_STATUS.md`](RESEARCH_STATUS.md).

---

## TL;DR

1. **v1 controller, n=30**, 세 도메인 (FinanceBench, MEDIQ, AgentClinic)에서
   evolved가 baseline 이하 또는 동률 (Δ ∈ {0, +6.7, 0} pp, 모두 노이즈 내).
   v1 rationale은 generic "verifier 추가" 반사.
2. **Controller v2를 *organization designer*로 재설계** — 도메인 brief
   주입, specialist persona authoring 강제, 반복 금지, 적극적 prune.
   sanity 단계에서 행동 격변: 도메인 어휘 풍부한 persona
   (`gaap_analyst`, `differential_diagnostician`, `cardiologist`,
   `gastroenterologist`), `remove_agent` 사용, tape 인용 rationale,
   hand-off chain.
3. **v2 n=30**도 test에서 baseline 대비 결정적 win은 못 만듦
   (Δ ∈ {+10, -3.4, -6.6} pp; FinanceBench의 +10pp는 same-graph 노이즈).
   n=30에서 strict accept + iter당 ~10분이라 큰 architectural change
   대부분이 노이즈에 가려 reject됨.
4. **다음**: streaming mini-batch evolve mode (100-200 sample sliding
   window, 5-10 round) — 사용자 원래 redirect 따라. round 수 늘리고,
   v2의 큰 architectural move를 한 번 이상 평가받게.

---

## 문서 지도

| 파일 | 용도 |
|---|---|
| `RESEARCH_STATUS_ko.md` (본 문서) | Snapshot — 지금 위치, 다음 행동 |
| `references/project_ko.md` | 연구 스펙 + brutal한 novelty / venue 평가 |
| `references/roadmap_ko.md` | Living dashboard — Done / In Progress / Next / Decisions |
| `docs/insights/pilot_ko.md` | 실행 단위 전술 인사이트 (운영, 방법론, 코드) |
| `notebooks/calib_01_analysis.ipynb` | calibration의 셀 단위 read-out |
| `data/briefs/{name}.md` | controller v2가 소비하는 도메인 brief |
| `README.md` / `CLAUDE.md` | 빠른 시작 + 에이전트 가이드 |

영어가 canonical; `*_ko.md` mirror가 함께 존재.

---

## 현재 상태

단계: **v2 n=30 sweep 직후, streaming-mode 작업 직전**.

- 가장 최근 commit (`feat-domain-pivot` HEAD): `d7b926f` — controller v2,
  도메인 brief, 배관, serve_vllm 견고화, roadmap 갱신.
- 이전: `1a56154` (RESEARCH_STATUS), `e5725e7` (DAG 규율 패치),
  `a531a3f` (도메인 pivot + restructure). Branch는 `main`(`844b81c`)
  위에.
- 활성 가설: **H1**은 v1에서 부분 falsified; **H2**는 행동만 충족, test
  win 미충족 — [§가설](#가설) 참고.
- 활성 블로커: iter당 wall (FinanceBench ~10분)이라 현재 train→
  controller→val 모드에서 3 round 이상은 비쌈; n=30 + Opt-2 strict가
  v2 candidate 대부분을 reject. Streaming 모드(다음 §)가 둘 다 해결.

---

## 지금까지 실증 발견

### 파일럿 인프라 (검증됨)

- vLLM 0.19.1 + Qwen2.5-32B-Instruct, 공유 H200에서 안정.
  `scripts/serve_vllm.sh`는 default `CUDA_VISIBLE_DEVICES=0`,
  `EVO_GPU_UTIL=0.55`, `--max-model-len 16384`, CC 누락 시 gcc 자동 설치.
- `evolve_log.json`에 `is_noop` 필드 존재.
- Opt-2 strict accept 의미론 (`best_graph` ↔ `best_val_acc` 항상 일치).

### `calib_01` (GSM8K, n=50, max_iters=3, ~66분)

|  | val | test | tokens / test task |
|---|---:|---:|---:|
| CoT | 94% | 92% | 350 |
| Planner-Executor | 94% | 90% | 621 |
| Evolved (4 agents, 8 edges) | — | **86%** | **1,303** |

evolved < baseline 4-6 pp, tokens 2.1-3.7×. v1 rationale generic. →
도메인 pivot 트리거.

### v1 controller, n=30 (2026-04-25)

3 도메인 × `--n-train 10 --n-val 30 --n-test 30 --max-iters 3 --seed 0`.

| Domain | CoT test | P-E test | Evolved test | Δ vs best baseline |
|---|---:|---:|---:|---:|
| FinanceBench | 70.0% | 66.7% | 70.0% | 0pp |
| MEDIQ | 43.3% | 43.3% | 50.0% | +6.7pp |
| AgentClinic | 66.7% | 70.0% | 70.0% | 0pp |

v1 행동: FinanceBench는 `add_verifier` 3번 반복 (도메인 어휘 0,
prior_edits 무시); MEDIQ는 iter 2 ACCEPT 후 다양화; AgentClinic은
summarizer ↔ verifier 교번 (일부 도메인 어휘).

→ H1 약 falsify. 헤드룸은 있으나 v1 controller가 너무 얕음. v2 redesign
동기.

### Controller v2 redesign (2026-04-25, commit `d7b926f`)

`src/controller.py::CONTROLLER_SYSTEM`을 *도메인 전문가 조직도*의
architect로 reframe. specialist persona authoring 필수 규칙 (인용된
전문성 + 구체 procedure); generic `verifier / summarizer / critic` 금지
(specialty와 짝지어지면 허용). 반복 금지 규칙. 적극 prune 인센티브.
도메인 brief 입력을 `_build_user_prompt`에 inject, `propose_edits →
evolve → run_pilot`로 plumbing.

도메인 brief 3개 `data/briefs/{financebench,mediq,agentclinic}.md`
(~80–110줄 — task style, 실패 모드, 유용 전문성, 패턴, 안티패턴).

### v2 sanity (벤치당 n=10, controller 행동 검증)

| | emit한 persona 이름 | 도메인 어휘 | `remove_agent` | tape 인용 |
|---|---|---|---|---|
| FinanceBench | unit_checker, period_verifier, period_specialist, unit_specialist | GAAP, fiscal year, TTM, SEC filings, millions/thousands | 0 | 부분 |
| MEDIQ | differential_diagnostician, adolescent_specialist, physical_exam_mapper, internal_medicine_differential_diagnostician | base rate × clinical fit, behavioral and eating disorders, MCQ options | 2 | ✅ ("17세 환자", "elevated blood pressure → bulimia") |
| AgentClinic | decisive_diagnosis_writer, triage_specialist | no hedging, canonical clinical term, red flags, triage | 1 | ✅ ("task ac-23, ac-50") |

**행동 격변**, 특히 MEDIQ (specialist + remove)와 AgentClinic
(decisive_diagnosis_writer + triage_specialist + remove).

### v2 controller, n=30 (2026-04-25)

3 도메인 × v1과 동일 params; FinanceBench는 `max_model_len=16384`로
재실행 (v2 prompt가 brief + multi-agent tape 때문에 8192 초과).

| Domain | CoT test | P-E test | Evolved test | Δ vs best baseline | best_graph |
|---|---:|---:|---:|---:|---|
| FinanceBench (16k retry) | 73.3% | 70.0% | **83.3%** | +10pp* | seed (모든 iter REJECT) |
| MEDIQ | 43.3% | 46.7% | 43.3% | -3.4pp | 3-agent (iter 2 ACCEPT: planner 제거 + differential_diagnostician + physical_exam_mapper 추가) |
| AgentClinic | 60.0% | 73.3% | 66.7% | -6.6pp | seed (모든 iter REJECT) |

*FinanceBench의 +10pp는 **측정 노이즈**, v2 win이 아님:
`evolved/test=83.3%`는 같은 run의 `planner_executor/test=70%`와
**동일 seed graph**가 만든 결과 (best_graph == seed, 모든 iter reject).
vLLM batch ordering / KV-cache 상태가 두 평가 사이에 다르게 형성되어
n=30에서 같은 graph가 >10pp 차이를 보임. 실제 효과로 cite 불가.

**주목할 v2 architectural 제안 (REJECTED여도)**:
- AgentClinic iter 3: `add(triage_specialist) + add(gastroenterologist)
  + add(cardiologist) + remove(planner) + remove(executor)`,
  `START → triage → {gastro | cardio} → END` — 문자 그대로 triage가
  라우팅하는 specialty department. 사용자의 organizational vision
  정확히. val이 seed와 tied라서 Opt-2 strict로 reject됨.
- MEDIQ iter 2 ACCEPT: planner 제거; `START → differential_diagnostician
  → physical_exam_mapper → END` + executor — v2 sweep에서 유일한
  architectural ACCEPT.

### v1 vs v2 비교 요약

| 축 | v1 | v2 |
|---|---|---|
| Persona 이름 공간 | `verifier`, `summarizer`, `reformulator`, `critic` | `gaap_analyst`, `period_validator`, `differential_diagnostician`, `adolescent_specialist`, `physical_exam_mapper`, `triage_specialist`, `gastroenterologist`, `cardiologist`, `decisive_diagnosis_writer` |
| Persona 도메인 어휘 | 0 | 풍부 (GAAP, TTM, fiscal year, base rate × clinical fit, no hedging, red flags, …) |
| Tape 인용 rationale | 없음 | 있음 (특정 task ID, demographic 케이스) |
| `remove_agent` 사용 | 0 | 다수 (`remove(planner)`, `remove(executor)` 포함) |
| Round간 edit 다양성 | "verifier" 3번 | round별 다른 organizational move |
| **n=30 test Δ vs baseline** | {0, +6.7, 0} pp (모두 노이즈 내) | {+10*, -3.4, -6.6} pp (+10은 노이즈) |

종합: **v2는 사용자 의도 (실제 organization 설계)에 부합하는 정성적
개선; n=30 측정으로는 baseline과 test 정확도 차이가 안 벌어짐**.
이건 측정 설계 문제이지 (반드시) controller 품질 문제는 아님.

---

## 가설

**H1 (2026-04-24)** — Reflection-only multi-agent evolution이
domain-specific task에서 val/test 향상. **2026-04-25 상태**: v1
controller 버전에서 약 falsified (n=30에서 세 도메인 모두 evolved ≤
baseline). v2 + 더 나은 측정으로 여전히 가능.

**H2 (2026-04-25, controller 재설계 후)** — *Organization-designer*
controller가 도메인 brief를 받고 specialist persona, 다양한 edit, 적극
prune을 emit하며 baseline AND v1 controller를 모두 능가. **2026-04-25
상태**: **행동은 절반 충족** (specialist persona, 다양한 edit, prune
모두 확인); **test win 미충족** (n=30 결과가 v1과 노이즈 내).

**H2 falsifier**: streaming-mode evolution (5-10 round, 100–200 mini-
batch)와 multi-seed run 후에도 evolved ≈ baseline → Framing C
(persona-necessity negative result)로 fallback, paper 재프레임.

---

## 다음 결정 (즉시, 순서대로)

| # | Action | 산출 | 트리거되는 결정 |
|---|---|---|---|
| 1 | **Streaming evolve mode** in `src/evolve.py` (mini-batch + max_rounds 5–10 + moving-average accept) | wall ≲1h 안에 5–10 round 가능; architectural change당 다중 노이즈 평균 평가 | v2가 round 더 많이 + 노이즈 적은 검증으로 baseline 이길 수 있는가? |
| 2 | streaming × 3 도메인 × multi-seed (≥3) 재실행 | 노이즈-평균된 v2 수치; 최종 H2 판정 | 최종 framing 결정 (B / C / A+B) |
| 3 | Random-persona ablation (`roadmap.md` §5.4) | v2의 specialty win이 진짜인지, random-name persona로 재현 가능한지 | Reviewer 질문 #1 (post-MAST) |

#1+#2 후 분기:
- **Branch B**: streaming v2가 multi-seed에서 ≥1 도메인 evolved >
  baseline → Framing B / A+B 확정, EMNLP ARR (D-31, 2026-05-25).
- **Branch C**: 여전히 ≈ baseline → Framing C (negative result)로
  pivot, v2의 풍부한 행동 증거를 negative result claim **지원**으로 사용
  ("real org-design이 제안하는 그대로 controller를 재설계했는데도
  baseline을 못 이김 — 따라서 병목은 controller 게으름이 아님").

---

## 미결 결정 (`roadmap_ko.md` §6)

| 항목 | 미결 시점 | 메모 |
|---|---|---|
| Paper framing | 2026-04-24 | streaming + multi-seed 후 (≤1주) 해소 |
| Target venue | 2026-04-24 | EMNLP ARR (5/25) primary; D&B (5/6) 공격적 |
| Backbone mix | 2026-04-24 | 두 번째 backbone 예산 결정 필요 |

---

## 리스크 레지스터

1. **n=30에서 측정 노이즈가 신호를 압도**. 같은 graph, 같은 데이터,
   같은 run에서 두 번 평가하면 vLLM batch ordering / KV-cache 상태로
   인해 test 정확도가 10+pp 차이. multi-seed (또는 deterministic
   batching) 평균 없이는 ≤10pp 차이 신뢰 불가.
2. **Time-to-deadline**: EMNLP ARR까지 D-31. Reviewer-bar 9개 중 0/9
   clear. `project_ko.md` §5 기준 전부 clear에 6-8주. 완화: A+B (또는
   C)로 범위 좁힘.
3. **단일 H200 병목** (evo_agents는 GPU 0). 다른 sibling 프로젝트는
   GPU 1. Multi-backbone은 API 예산 필요.
4. **LLM-judge self-bias** (FinanceBench, AgentClinic): 같은
   Qwen2.5-32B가 자신을 judge. 완화: 별도 family judge
   (`roadmap_ko.md` §5.7).
5. **피봇 자체가 독자에게 빚진 스토리**: "도메인이 도와준다"가 아니라
   "GSM8K가 옳은 이유로 틀린 testbed였다".

---

## Paper-readiness 자기평가

`project_ko.md` §3의 reviewer-bar 체크리스트:

| 항목 | 상태 |
|---|---|
| Best-of-N single-agent @ matched compute | ❌ |
| ≥2 backbone families | ❌ — Qwen only |
| ≥3 heterogeneous benchmarks (non-saturated 1개 포함) | ⚠️ 3 measured at n=30 (v1 + v2), 방어 가능한 수치는 multi-seed n≥100 필요 |
| ADAS + (Puppeteer / MaAS / EvoMAC 중 1) 직접 비교 | ❌ — ADAS 필수 |
| Harness ablation (controller on/off, random persona, fixed topo) | ❌ |
| Failure-mode taxonomy (MAST-style) | ❌ |
| Cost Pareto (tokens × wall × $) | ⚠️ 토큰만 부분 기록 |
| LLM-judge calibration (≥100 samples, human κ) | ❌ |
| Code + prompts + tool defs + model versions 공개 | ⚠️ 내부에만 |

**합산**: 0 cleared, 3 partial, 6 not started.

---

## 한 줄 요약

> v1 controller n=30 → baseline 이하 또는 동률 (calib_01과 일관);
> v2 controller를 organization designer로 재설계 → 행동은 압도적
> 개선 (specialist persona, prune, hand-off chain) 그러나 n=30 test
> win은 여전히 못 함 — 측정 노이즈가 압도하고 wall budget 안에 3
> round만 들어가기 때문. 다음: 노이즈-평균 accept을 가진 streaming
> mini-batch mode (5-10 round), 그 후 multi-seed, 그 후 framing 결정.
