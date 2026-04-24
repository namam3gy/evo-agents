# ROADMAP

`agent_orchestration` 파일럿의 진행상황을 담는 living dashboard.
실험 스펙은 `project_ko.md`에, 파일럿을 실제로 돌리면서 발견한 사항은
`../docs/insights/pilot_ko.md`에 있다. 이 파일은 실험 사이클이 한
바퀴 끝날 때마다 갱신된다.

*Last updated: 2026-04-24*

---

## 1. 연구 목적

**한 줄.** 반복 태스크 family 위에서 multi-agent DAG (topology + persona
+ edges)를 **순수 in-context reflection**으로 — 컨트롤러 훈련도 없고
명시적 탐색 절차도 없이 — 점진적으로 진화시킬 수 있는지 테스트하는
파일럿 연구.

**선행 연구 대비 differentiator** (`project_ko.md` §1, §7 참조):
- ADAS / AFlow / GPTSwarm / MaAS / Puppeteer (NeurIPS 2025)은 모두
  **search** (archive / MCTS / supernet) 또는 **RL**에 의존.
- 이 파일럿은 frozen backbone 위에서 **trajectory tape에 대한
  reflection**으로 topology + persona + edges를 co-evolve. 이것이
  유일한 실질적 differentiator.
- Caveat: `project_ko.md`는 이것만으로는 NeurIPS 2026 main track에
  불충분하다고 평가 (acceptance 3–6% 추정). ARR 경유 EMNLP 2026
  (~5–10%)이 현실적인 primary 타겟.

## 2. 타겟 결과

### 2.1 방법론적 (피봇 후 H1)

**H1 (2026-04-24)**: Reflection-only multi-agent evolution이 CoT / Planner-Executor baseline보다 **persona가 이질적 전문성 혹은 정보를 담는 domain-specific 과제**에서 측정 가능한 val/test 개선을 낸다 (FinanceBench, AgentClinic; MEDIQ는 `../docs/insights/pilot_ko.md` §6.4에 따라 sanity 전용).

**경험적 trigger**: GSM8K의 `calib_01`에서 evolved가 두 baseline 모두보다 test에서 낮음 (`pilot_ko.md` §4.1); GSM8K는 multi-agent가 exploit하는 정보 비대칭 레버가 구조적으로 없음. 이 피봇은 "GSM8K가 *the wrong domain* 이었지 *단지 어려운 것*이 아님"을 같이 입증할 것을 commit.

**Falsifier**: 세 도메인 *모두*에서 n ≥ 30 (§5.2)에 evolved ≈ baseline이면, 연구를 Framing C (persona-necessity negative result) 방향으로 재프레이밍.

**보조 방법론적 질문**:
1. Evolved가 test로 전이되는가 (val↔test gap < 3pp)?
2. Controller가 실제로 어떤 종류의 edit을 내는가? Rationale이 specific tape 사례를 인용하는가, 아니면 generic "add an agent"로 default되는가? (Sanity에서 이미 *일부* 도메인 적응 관찰 — AgentClinic의 "summarizer for concise diagnosis" vs GSM8K의 "arithmetic verifier" 반사.)

### 2.2 논문 (per `project_ko.md` §7)
- **Primary:** ARR 경유 EMNLP 2026 main — **deadline 2026-05-25
  (D-31)**.
- **Secondary:** NeurIPS 2026 Datasets & Benchmarks Track —
  2026-05-06 (D-12). *Pivot 결정 미결정.*
- **Tertiary:** NeurIPS 2026 workshop (Lifelong Agents 등) —
  deadline 여름.

### 2.3 리뷰어 bar 실험 커버리지 (반드시 clear)
- [ ] Matched compute에서 Best-of-N single-agent
- [ ] ≥2 백본 family (예: Qwen3-72B + Claude/GPT 중 하나)
- [ ] ≥3 이질적 벤치마크, non-saturated 1개 포함
- [ ] ADAS + (Puppeteer 또는 MaAS 또는 EvoMAC)과의 직접 비교
- [ ] Harness ablation (컨트롤러 on/off, random-persona, fixed-topo)
- [ ] Failure-mode taxonomy (MAST-style)
- [ ] Cost Pareto (tokens × wall-clock × $)
- [ ] LLM-judge calibration (≥100 샘플, human agreement κ)

---

## 3. 완료 (Done)

### ✅ 파일럿 인프라
- `src/` 라이브러리: `llm.py`, `graph.py`, `orchestrator.py`,
  `controller.py`, `evolve.py`, `baselines.py`, `datasets.py`,
  `score.py`, `types.py`.
- `scripts/run_pilot.py` — baseline + evolution 드라이버.
- `scripts/serve_vllm.sh` — vLLM 0.19.1 호환으로 패치됨
  (`--no-enable-log-requests`).
- `uv`-관리 환경, pinned `.python-version`.

### ✅ End-to-end smoke 검증
- `results/smoke_baselines/` — baseline 정상 실행.
- `results/smoke_evolve/` — 1-iter evolution이 컨트롤러가 실제로
  edit을 내고 graph가 mutate됨을 확인.
- `results/run_20260423_140620/` — 첫 full run 아티팩트 존재.

### ✅ 3대 운영 blocker 식별 & 수정 (`../docs/insights/pilot_ko.md` §1)
1. vLLM 0.19.1 CLI 플래그 drift → `serve_vllm.sh` 패치.
2. Triton JIT에 시스템 `gcc` 필요 → 설치.
3. 공유 H200 → `EVO_GPU_UTIL=0.55` 수동 override 필요.

### ✅ 초기 관찰 (`../docs/insights/pilot_ko.md` §2)
- 5 샘플에선 CoT / P-E / Evolved 모두 100% — discriminative power
  없음. **→ n_val / n_test를 수백 단위로 올려야 함.**
- val이 포화된 상태에서도 컨트롤러는 sensible한 edit (verifier
  에이전트 + edge 추가)을 제안 — **hypothetical intervention**의
  증거이며 no-op이 아님. 이것이 파일럿이 끌어내려는 동작.
- iter당 worker 토큰이 controller 토큰의 ~3–4배 → 전체 비용은
  `worker × iter`에 지배됨; controller 토큰보다 `--n-train` 최적화가
  먼저.

### ✅ evolve log에 `is_noop` 필드 추가
- `evolve_log.json.iterations[*].is_noop: bool` 추가
  (`src/evolve.py:31`). seed iter에는 False, 빈 edit batch에는 True.
  포화된 val에서의 no-op rate 측정을 unblock.

### ✅ Calibration run `calib_01` (2026-04-24)
- `results/calib_01/` — n_val=n_test=50, seed=0, max_iters=3,
  wall=~66분. 분석은 `../docs/insights/pilot_ko.md` §4에,
  재현 가능한 read-out은 `notebooks/calib_01_analysis.ipynb`에.
- 표면 발견: **evolved graph가 test에서 두 baseline 모두보다
  낮음** (86% vs CoT 92% / P-E 90%) — 토큰 비용은 2–3.7배. n=50에선
  val 상에서도 discrimination이 없음 (CoT=P-E=94%). n≥300 seed≥3
  필요성을 강화.
- 파이프라인 수준 발견 (아래에서 수정됨): 이전 Opt-1 accept 정책
  하에서 `best_graph`와 `best_val_acc`가 서로 다른 graph를 가리킬 수
  있었음.

### ✅ `evolve.py` accept semantics — Opt-2 strict (2026-04-24)
- Opt-2 선택: `best_graph` / `best_val_acc`는 **val이 엄격히 개선될
  때만** 갱신 (`val_acc > best_val_acc`). tie / near-best 후보는
  REJECTED. default `accept_slack = 0.0`; 기존 Opt-1 동작은 ablation
  용으로 `accept_slack > 0` 분기로 유지.
- `results/smoke_opt2/` (n=3, max_iters=2)에서 검증: 두 evolve iter
  모두 val=100%로 tie → REJECTED. 최종 `best_graph == seed`,
  `best_val_acc == 1.0` — 두 값이 같은 graph를 가리킴 (Opt-1에서는
  그렇지 않았음).

### ✅ 도메인 피봇 — GSM8K 은퇴, 3 새 벤치 활성화 (2026-04-24)
- **경험적 trigger**: `calib_01`에서 GSM8K test에 evolved < 두 baseline (86% vs 92% / 90%), 그리고 GSM8K는 multi-agent가 exploit하는 정보 비대칭 레버가 구조적으로 없음 (자립적 텍스트, 선형 산술, 단일 모델이 94%). 전체 근거는 `../docs/insights/pilot_ko.md` §6.
- `src/datasets.py` 재작성: `load_benchmark(name, ...)`가 FinanceBench (HF `PatronusAI/financebench`), MEDIQ (non-interactive initial, GitHub raw JSONL), AgentClinic (single-pass wrapper, GitHub raw JSONL)로 dispatch.
- `src/score.py` 재작성 — dispatcher: MCQ exact-match (MEDIQ) 또는 LLM-judge (FinanceBench, AgentClinic). 같은 Qwen이 Qwen 판정 — self-bias flag.
- Baseline seed persona의 수학 전제 제거; controller 프롬프트 일반화. `run_pilot.py --benchmark {name}` required.
- 벤치당 n=3 sanity로 파이프라인 E2E 검증, 그리고 controller가 **도메인 적응 rationale**을 낸다는 첫 긍정 신호. 아티팩트: `results/sanity_{mediq,agentclinic,financebench}/`.
- 알려진 이슈: FinanceBench의 long-context가 controller의 DAG 규율을 밀어냄 — §5.1 에서 scale 전에 수정.

---

## 4. 진행 중 (In Progress)

*(현재 활성 항목 없음 — 다음 실험 선택 대기.)*

---

## 5. 다음 할 일 (우선순위)

### 5.1 🔜 FinanceBench long-context에서 controller DAG 규율 패치
- **왜:** FinanceBench sanity에서 controller가 DAG-invalid edit을 두 번 연속으로 내놓음 (planner가 END 도달 불가). Evidence text가 prompt를 지배하면서 topology reasoning이 밀림 (`../docs/insights/pilot_ko.md` §6.3). 미수정 시 FinanceBench evolve는 사실상 zero-iter.
- **무엇:** `src/controller.py::CONTROLLER_SYSTEM`에 짧은 타겟 수정 — DAG 규칙 강조 또는 `describe(graph)`를 prompt 내 고현저 위치(예: user prompt 뒤)로 이동. n=3 sanity 재실행.
- **Size:** smoke 포함 ~30분.

### 5.2 🔜 도메인 피봇 첫 측정: 벤치당 n_val = n_test ≈ 30
- **왜:** n=3 sanity는 파이프라인 돌음 + controller rationale이 도메인 적응적임을 확인했지만, n=3에서는 의미있는 accuracy 신호가 나올 수 없음 (표본 오차 ±25+ pp).
- **무엇:** 벤치당 `--n-train 10 --n-val 30 --n-test 30 --max-iters 3 --seed 0`. CoT / P-E / Evolved 비교. 예상 wall: 벤치당 20–40분 × 3 = 총 1.5시간.
- **Output:** 첫 도메인 피봇 증거. 세 가능한 패턴: (a) 어느 한 도메인이라도 evolved > baseline → framing B / A+B가 viable; (b) 세 도메인 모두 evolved ≈ baseline → framing C (persona-necessity negative result) 확정; (c) 혼합 — 도메인별 후속.
- **Blocker:** FinanceBench에 대해서만 §5.1 선행.

### 5.3 Harness ablation (controller on/off, random persona, fixed topo)
- **왜:** `project_ko.md` §7 essential ablation — 가장 저렴하고 가장
  중요. 특히 **random-persona control**은 post-MAST에서 사실상
  필수 (reviewer 질문 #1).
- **무엇:** `run_pilot.py`에
  `--controller-mode {none, random, fixed-topo, full}` 플래그 추가;
  §5.2에서 승리한 도메인에서 matched seed와 n_val 하에 네 개 모두 실행.

### 5.4 두 번째 백본 추가
- **왜:** "≥2 모델 family에서 이득이 유지됨"은 리뷰어 bar 항목.
- **후보:** Qwen3-72B (오픈) + Claude 4.x / GPT-4.1 중 하나 (API).
  예산 결정 필요.

### 5.5 LLM-judge 교체 (다른 family)
- **왜:** 현재 sanity는 FinanceBench + AgentClinic 판정에 Qwen-as-judge 사용. `../docs/insights/pilot_ko.md` §6.1에 self-bias flag. 리뷰어가 반드시 짚을 포인트.
- **후보:** Claude Haiku 4.5 (저렴) 또는 GPT-4.1-mini (API). Judge 전용 소규모 예산.

### 5.6 직접 baseline: ADAS + (Puppeteer 또는 EvoMAC 또는 MaAS)
- **왜:** "이게 ADAS와 어떻게 다른가?"가 reviewer 질문 #0.
- **Size:** 각 3–5일. **ADAS는 non-negotiable.**

---

## 6. 미결 결정

| 항목 | 옵션 | Deadline |
|---|---|---|
| **논문 framing** | (A) causal/diagnostic 컨트롤러 · (B) GeoMacroBench + cross-asset · (C) persona-필요성 negative result · (A+B) 결합 | 1주 내 |
| **타겟 venue** | EMNLP 2026 main ARR (5/25) · NeurIPS D&B (5/6) · workshop (여름) | 첫 실제 결과 후 |
| **도메인 피봇** | general 유지 (GSM8K 등) · medical · cross-asset finance | framing과 함께 결정 |
| **백본 조합** | Qwen만 · 오픈 + API 혼합 | 예산 체크 후 |

---

## 7. 미시작

- Failure-mode taxonomy (MAST-style).
- Cost Pareto 파이프라인.
- LLM-judge calibration 실험.
- GeoMacroBench 구축 (도메인 피봇 결정 후에만).
- 작성 / related-work 비교표.

---

## 8. Deadline 달력

| 날짜 | 이벤트 | 상태 |
|---|---|---|
| 2026-05-04 | NeurIPS 2026 abstract | D-10 — fallback only |
| 2026-05-06 | NeurIPS 2026 full paper / D&B | D-12 — 매우 공격적 |
| **2026-05-25** | **EMNLP 2026 ARR submission** | **D-31 — primary target** |
| 2026-08-02 | EMNLP direct commitment | D-100 — fallback |
| 2026-08–09 | NeurIPS workshop (예상) | — fallback |

---

## 9. 갱신 규칙 (미래-나 / Claude 용)

- 각 실험 사이클 후, 항목을 §3 완료 · §4 진행 중 · §5 다음 할 일
  사이에서 이동.
- 미결 결정 (§6)이 확정되면 제거하고 §1–§2에 반영.
- 날짜는 항상 YYYY-MM-DD. 상대 날짜 금지.
- 상세 숫자 / 플롯은 `results/<run_id>/` 또는
  `../docs/insights/pilot_ko.md`로; ROADMAP은 **링크와 한 줄 요약**만
  담는다. 이것은 dashboard이지 diary가 아니다.
