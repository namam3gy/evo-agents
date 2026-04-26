# Pilot 실행 인사이트

`agent_orchestration` 파일럿을 실제로 띄우면서 발견한, 문서/코드만 보고는 알 수 없었던 지점들 정리.

---

## 1. 운영상 걸림돌 (operational)

### 1.1 vLLM 0.19.1에서 `--disable-log-requests`가 제거됨

`scripts/serve_vllm.sh`의 원본은 `--disable-log-requests` 플래그를 사용하지만 0.19.1에선 `unrecognized arguments` 로 즉시 죽는다 (exit 2). 플래그 모델이 `--enable-log-requests | --no-enable-log-requests` 페어로 바뀌었기 때문.

- **조치**: `--disable-log-requests` → `--no-enable-log-requests`
- **교훈**: vLLM은 마이너 버전 사이에서도 CLI 플래그가 잘 깨진다. 서버 스크립트에는 `vllm --version`과 실행 전 `--help | grep log-requests` 한 줄짜리 guard를 두는 게 싸다.

### 1.2 Triton JIT는 시스템 C 컴파일러가 없으면 KV 캐시 초기화 단계에서 실패

모델 가중치는 GPU에 다 올라가고 라우트도 모두 등록된 뒤에 `determine_available_memory` 호출 중 터지는 게 당황스러웠다. 진짜 원인은 맨 아래:

```
torch._inductor.exc.InductorError: RuntimeError: Failed to find C compiler.
Please specify via CC environment variable or set triton.knobs.build.impl.
```

Triton이 런타임에 `cuda_utils.c`를 JIT 컴파일하는데, 이미지에 `gcc-12-base`(라이브러리)만 있고 `gcc`(컴파일러)가 없었다.

- **조치**: `sudo apt-get install gcc`
- **교훈**: torch/vllm/triton 휠은 self-contained처럼 보이지만 **Triton만은 시스템 cc를 요구**한다. 베어 컨테이너에서 첫 inference를 할 때 흔히 밟는 지뢰. `Dockerfile` / `setup.sh` 초기화에 `gcc`를 박아두자.

### 1.3 공유 GPU에서 `gpu-memory-utilization`은 default(0.90)가 아니라 실제 free에 맞춰야 한다

H200(143 GB) 한 장을 다른 두 프로세스가 33 GB 점유한 상태였다. 0.90을 그대로 쓰면 vLLM은 ~129 GB를 요구해서 충돌. 0.55로 낮추니 Qwen2.5-32B(bf16 weight ~65 GB) + KV 캐시에 충분.

- **조치**: `EVO_GPU_UTIL=0.55 bash scripts/serve_vllm.sh`
- **교훈**: 공유 노드에선 `scripts/serve_vllm.sh` 기동 직전 `nvidia-smi --query-gpu=memory.free`를 읽어 util을 동적으로 계산하는 게 안전. 지금 스크립트는 사용자가 직접 env var을 넣도록 되어있어서 놓치기 쉽다.

---

## 2. 실행으로 드러난 파이프라인 특성 (methodology)

### 2.1 5샘플에선 CoT/P-E/Evolved가 모두 100%

Qwen2.5-32B가 GSM8K에서 충분히 강하다. 5-val / 5-test로는 방법 간 차이가 하나도 안 잡힌다 (`results/smoke_evolve/results.json` 참조).

- **교훈**: 헤드라인 수치는 `--n-val`, `--n-test`를 최소 **수백** 단위로 올려야 의미 있다. smoke check 목적으로만 5샘플을 쓰고, 결과 보고에 이 값을 인용하면 안 된다.

### 2.2 Controller는 val이 이미 포화여도 의미 있는 edit을 낸다

val이 100%인 iter 1에서 controller는 여전히 다음을 제안했다:

- `add_agent(verifier)` + `add_edge(executor→verifier)` + `add_edge(verifier→END)`
- Rationale: *"The executor occasionally makes arithmetic mistakes, such as rounding inaccuracies. Introducing a verifier agent can help catch and correct these errors."*

즉 "정답률이 이미 100%니까 바꾸지 말자"로 귀결되지 않고, 실패 모드를 **가설적으로** 지목해 행동한다. 이것 자체가 파일럿이 검증하려는 동작이므로 긍정적 신호.

- **교훈**: 후속 실험에선 val이 포화 상태일 때 controller가 얼마나 자주 **empty edit** (= no-op)을 내는지를 별도 지표로 측정해볼 가치가 있다. 현재 `evolve_log.json.edits`는 rationale과 op 리스트만 있고 no-op 플래그가 명시적으로 없다.

### 2.3 Worker 토큰이 controller 토큰보다 3~4배 비싸다

1-iter 실행 기준:

| 주체       | 토큰     |
|------------|----------|
| worker     | 11,977   |
| controller | 3,534    |

Iter 수가 늘면 worker 쪽이 거의 선형으로 늘고 controller는 iter 당 ~3.5k로 고정. 전체 비용은 **worker × iter**가 지배. 초반 grid search엔 controller 토큰 최적화보다 `--n-train` 관리가 훨씬 레버리지가 크다.

---

## 3. 코드 단서 (codebase notes)

다른 세션에서 이 코드를 다시 붙을 때 바로 걸릴 만한 것들.

### 3.1 `src/llm.py`의 `LLMClient.chat`은 positional 두 개가 필수

시그니처:

```python
LLMClient().chat(system: str, user: str, ...)
```

OpenAI SDK 스타일(`messages=[...]`)이 아니다. 호출부에서 system / user를 쪼개 넘겨야 한다.

### 3.2 `results/<run>/evolved_graph_final.json`은 `{graph, describe}` 래퍼를 가진다

`agents`/`edges`에 바로 접근하면 `KeyError`. 항상 `data["graph"]` 밑으로 내려가야 한다. (반면 `evolve_log.json.iterations[*].graph_snapshot`은 래퍼 없이 바로 agents/edges가 있다 — 포맷이 비대칭이므로 스크립트 짤 때 주의.)

### 3.3 `vllm`은 의도적으로 `pyproject.toml` 밖

`CUDA 버전-pinning` 문제 때문에 `uv sync`가 아닌 `uv pip install vllm`으로 별도 설치한다 (`CLAUDE.md`에도 명시). 즉 `uv sync`만 깨끗한 환경에선 서버가 안 뜬다. 재현성을 위해 `requirements-vllm.txt` 같은 보조 파일 하나 두고 README에 명시하면 좋다.

### 3.4 `serve_vllm.sh`는 이제 `uv run python`을 쓴다

원본은 bare `python`을 호출해 프로젝트 venv 바깥의 시스템 파이썬을 집을 위험이 있었다. 이번에 `exec uv run python ...`으로 고정 (`scripts/serve_vllm.sh:15`).

---

## 4. Calibration run `calib_01` (2026-04-24)

중간 샘플 규모의 첫 E2E 실행 — n_val=n_test=50, seed=0, max_iters=3, total wall ~66분. 아티팩트는 `results/calib_01/`, 셀 단위 분석은 `notebooks/calib_01_analysis.ipynb`.

### 4.1 헤드라인: evolved graph가 두 baseline보다 test에서 *낮다*

| 방법 | val acc | test acc | 토큰 (test) |
|---|---|---|---|
| CoT | 94% | 92% | 17.5k |
| Planner-Executor (seed graph) | 94% | 90% | 31.1k |
| Evolved (4 agents, 8 edges) | — | **86%** | **65.2k** |

Evolution은 **P-E의 2.1배, CoT의 3.7배 토큰을 쓰면서** 두 베이스라인보다 4–6 pp 낮게 나왔다. n=50에서는 sample-error가 ~±7 pp (95% CI, 3-sample 차이)라서 이것만으로 regression을 *증명*할 수는 없다. 하지만 gap이 일관되게 부정적인 쪽이라는 것이 "에이전트를 더 많이 쌓으면 자동으로 좋아진다"가 아니라는 첫 신호.

### 4.2 Iteration trajectory와 accept_slack quirk

```
iter 0  seed (planner + executor)                 val=94%  (best_val_acc)
iter 1  +verifier + edges                         val=92%  ACCEPTED
iter 2  +reformulator + edges                     val=92%  ACCEPTED
iter 3  +critic + edges                           val=86%  REJECTED
```

두 iteration이 val에서 regression이었는데도 **ACCEPTED**된 이유는 `src/evolve.py:139`에

```python
accepted = val_acc >= best_val_acc - accept_slack
```

이 있고, 그 다음 `best_val_acc`은 `val_acc > best_val_acc`일 때만 갱신되기 때문 (`evolve.py:146–147`). 결과:

- **`best_graph`는 iter-2 graph (verifier + reformulator)로 drift**했는데,
- **`best_val_acc`은 seed 값인 94%에 그대로 남았다.**

저장된 `results/calib_01/evolved_graph_final.json`은 4 agents이지만, `results/calib_01/evolve_log.json.best_val_acc == 0.94`는 2-agent seed graph가 달성한 값. 현재 accept 정책 하에서 두 값이 **decoupled**. 스케일 런 전에 반드시 해결해야 함 — 그러지 않으면 리뷰어에게 보고하는 "best graph"가 `best_val_acc`을 달성한 graph가 아니게 된다.

두 가지 수정안:

- **Opt-1 (loose):** accept 시 `best_val_acc = val_acc`도 같이 설정. slack-허용 탐색은 유지; 보고되는 `best_val_acc`이 저장된 graph와 일치.
- **Opt-2 (strict):** `val_acc > best_val_acc`일 때만 `best_graph`를 교체. slack 기반 graph 교체 제거; `best`는 진짜 best.

둘 다 defensible — 서로 다른 철학 (exploration vs. monotonicity) 이다.

**결정 (2026-04-24): Opt-2 (strict).** accept 분기에서 `val_acc > best_val_acc`를 요구하도록 변경 (tie는 기존 best 유지). `accept_slack` default는 `0.0`; `0` 초과로 설정하면 Opt-1 동작이 ablation용으로 복원됨. `results/smoke_opt2/` (n=3, max_iters=2)에서 검증: 두 evolve iter 모두 val=100% tie → REJECTED. 최종 `best_graph == seed`, `best_val_acc == 1.0` — 두 값 일치. 결정 기록은 `references/roadmap_ko.md` §3.

### 4.3 Controller는 여전히 hypothetical edit을 내지만 rationale이 thin하다

val=94%에서 controller가 낸 것:

- iter 1 rationale: *"The observed errors seem to stem from incomplete or incorrect arithmetic calculations by the executor."* 그런데 데이터셋은 GSM8K고 Qwen2.5-32B의 94%는 산술 오류 때문에 실패한 게 아니다. verifier는 합리적인 default move일 뿐, tape에서의 진단은 아니다.
- iter 2 rationale: *"The observed errors often arise from misinterpretation of the problem statement."* 어느 tape에서 그랬는지 불명확 — iter-2 직전에 이미 val=94%였다.
- iter 3 rationale: *"The current graph has a high accuracy but still makes some mistakes."* 좀 더 정직하지만 `add critic`도 default addition이지 causal inference는 아니다.

이것은 §2.2의 smoke-run 관찰과 일관된다: controller는 포화된 val에서도 non-empty edit을 내지만 (`is_noop == False` 세 iter 모두), rationale은 trajectory-grounded causal read라기보다 일반적인 "add more agents" reflex처럼 읽힌다. `project.md` §7 Framing A (causal/diagnostic controller)가 정확히 이 failure mode를 공략하도록 설계됨 — 증거이지 verdict는 아직 아님. n=300 결과를 보고 다시 판단.

### 4.4 Wall-clock과 per-task timing

| Phase | Wall | s/task |
|---|---|---|
| CoT val (n=50) | 4:18 | 5.2 |
| P-E val (n=50) | 6:49 | 8.2 |
| Evolve (3 iters, train n=20 + val n=50 each) | 37:55 | — |
| CoT test (n=50) | 3:51 | 4.6 |
| P-E test (n=50) | 4:43 | 5.7 |
| Evolved test (n=50, 4 agents) | 8:59 | 10.8 |

§5.1 스케일 런으로 외삽 (n_train=100 또는 200 + n_val=300 + n_test=300, seed×3, max_iters=5):

- seed당 baseline만: ~26분 / 300 (CoT) + ~41분 (P-E) ≈ 1시간.
- Evolution per iter은 val n=300이 지배: ~41분 × 5 iters ≈ 3.4시간. 여기에 train rollout (n=100): ~0.5시간. 합 ~4시간 / seed.
- Evolved test (4 agents): ~55분 / 300.
- **seed당 총 ~5–6시간. × 3 seed ≈ 15–18시간 wall** (공유 H200 기준).

만약 evolved graph가 5+ agents로 커지면 evolved-test phase는 +30% 예산 추가. 단일-H200 bottleneck으로 seed parallel은 GPU 추가 할당 없이는 불가.

### 4.5 토큰 비용 비대칭이 §2.3 추정보다 더 넓다

`calib_01`의 per-iter 비용:

| iter | worker tokens | controller tokens | ratio |
|---|---|---|---|
| 1 | 70,830 | 3,665 | 19.3× |
| 2 | 92,827 | 4,958 | 18.7× |
| 3 | 130,313 | 5,916 | 22.0× |

earlier smoke run의 3–4×는 실제 regime을 과소평가한 것. `n_train=20 + n_val=50` per iter에선 worker 토큰이 **controller의 ~20배**이고, **그래프가 agent를 추가할수록 모노토닉하게 증가**한다 — 매 val 샘플이 더 많은 agents를 통과하기 때문. Per-iter wall과 per-iter worker-tokens가 *둘 다* `n_agents`에서 super-linear. §5.1에서는 이게 예산을 더 조인다: `n_agents` 상한 (예: `--max-agents` ≤ 5) 이 생각보다 중요하다.

---

## 5. 남은 과제 / 다음에 해볼 것

1. ~~**`evolve.py` accept semantics 수정** (§4.2) — §5.1 스케일업 전에 `best_graph` / `best_val_acc` decoupling 해소.~~ **완료 2026-04-24**, Opt-2 strict 적용 + smoke 검증. §4.2 참조.
2. **n_val ≥ 300, seed ≥ 3으로 재실행** — §4.1의 4–6 pp test regression이 noise를 넘어서는지 확인.
3. **~~Controller의 no-op 비율 로그~~** — 완료. `is_noop` 필드가 `calib_01` 전에 `src/evolve.py:31`로 landed; 이번 run은 3 iter 모두 `is_noop == False`.
4. **`scripts/serve_vllm.sh` pre-flight** — gcc 존재 / GPU free memory / vllm CLI flag 체크.
5. **pyproject에 jupyter 관련 dev-extra** — `nbformat`, `nbclient`, `ipykernel`을 선택적 extra로.
6. **`n_agents` 상한** (§4.5) — 스케일 런에서 wall / 토큰 비용을 예측 가능한 박스에 두기 위해 `--max-agents 5` 이하 고려.
7. **Rationale 품질 추적** (§4.3) — 각 rationale이 특정 tape 사례를 인용하는지 아니면 generic "add X agent" default로 읽히는지 태깅하는 작은 후속 — Framing A 계획 input으로.

---

## 6. Domain pivot — sanity batch (2026-04-24)

두 가지 관찰이 합쳐져 trigger된 결정:

1. `calib_01` (§4) 에서 GSM8K에 대해 **evolved가 두 baseline 모두보다 test에서 낮음** — controller rationale이 task-grounded 진단이 아니라 generic "add an agent" 반사처럼 읽힘.
2. GSM8K는 구조적으로 multi-agent에 under-rewarding — 맥락이 self-contained, task가 선형 산술, 단일 강한 LLM이 이미 94%. Persona 전문화에 **정보 비대칭 레버가 없음**.

결정: GSM8K를 primary benchmark에서 은퇴. 진짜 multi-agent affordance가 있는 세 도메인 벤치 활성화: **FinanceBench**, **MEDIQ (non-interactive initial 모드)**, **AgentClinic (single-pass wrapper)**. 근거와 갱신된 H1은 `references/project.md`에.

### 6.1 Loader / scoring

- `src/datasets.py::load_benchmark(name, ...)` — `load_financebench`, `load_mediq`, `load_agentclinic`로 dispatch. MEDIQ/AgentClinic JSONL은 `urllib.request`로 `data/`에 한 번만 fetch; FinanceBench는 HF `PatronusAI/financebench`.
- `src/score.py::score(prediction, task, llm)` — MCQ exact-match (MEDIQ) 또는 LLM-as-judge (FinanceBench, AgentClinic)로 dispatch. **Self-bias flag**: judge가 worker와 같은 Qwen2.5-32B. Sanity엔 허용, scaled run에선 다른 family judge가 reviewer-bar.
- Baseline seed-graph persona의 "arithmetic" / "Final Answer: \<number>"를 일반 도메인용으로 일반화.

### 6.2 Sanity 결과 (n_train=2, n_val=3, n_test=3, max_iters=2)

| 벤치 | CoT val / test | P-E val / test | Evolved test | Evolution 결과 |
|---|---|---|---|---|
| MEDIQ | 67% / 0% | 0% / 33% | 33% (seed) | iter 1,2 모두 val seed와 동률 → REJECTED (Opt-2) |
| AgentClinic | 67% / 100% | 100% / 67% | 67% (seed) | Controller가 `add_agent(summarizer)` 제안 — **도메인 적응적 rationale**; tie REJECTED |
| FinanceBench | 33% / 67% | 33% / 67% | 67% (seed) | Controller가 DAG-invalid edit 두 번 연속 (planner가 END에서 도달 불가) |

아티팩트: `results/sanity_mediq/`, `results/sanity_agentclinic/`, `results/sanity_financebench/`.

### 6.3 관찰

**파이프라인 수준 (확인하고 싶었던 것)**:
- 세 loader + scorer 모두 end-to-end 실행.
- Opt-2 strict accept semantics 정상 (tie → REJECT, seed가 `best_graph`로 유지).
- 일반화된 seed persona가 MCQ / 자유 텍스트 / long-context 도메인 모두에서 orchestrator/controller 코드 변경 없이 파싱됨.

**과학적 신호 (잠정적; n=3은 결론 불가)**:
- Controller rationale이 **도메인에 따라 변화**. GSM8K의 "arithmetic verifier" 반사가 AgentClinic에선 "summarizer for concise diagnosis"로 대체됨 — reflection-only 신호가 단일 default로 collapse 하지 않음. 도메인 피봇 가설이 유효할 수 있다는 첫 경험적 근거.
- FinanceBench가 DAG 불변식을 **두 번 연속** 위반 → long evidence context가 controller의 topology reasoning을 밀어낼 가능성. Controller 프롬프트 튜닝 필요 (DAG 규칙 강조, 또는 graph description 위치를 prompt 내 고현저 위치로).

**관찰된 noise 원인 (n=3 artifact)**: 같은 seed graph를 baseline phase와 evolve seed phase에서 re-evaluate 했을 때 val 점수가 다름 (FinanceBench에서 가장 명확: baseline P-E val = 33% vs evolve seed val = 0%). 원인은 vLLM temperature=0의 배치 경계 non-determinism + LLM-judge variance 추정. n ≥ 30에선 평균 상쇄되지만 n=3에선 개별 수치 오염.

### 6.4 이 run이 *답하지 않는* 것

- Evolved가 meaningful n (≥ 30)에서 baseline을 능가하는가? n=3은 너무 작음.
- 도메인 적응 controller rationale이 **실행가능**한가? Valid edit이 실제 val을 개선하는지 확인 필요.
- FinanceBench / AgentClinic의 LLM-judge self-bias — 미조사.
- MEDIQ "non-interactive initial"은 **논문에서 지는 설정** (Li et al. 2024: GPT-3.5에서 non-interactive 45.6% > interactive 42.2%). 여기서 evolved ≈ baseline이 나온 것은 "의료에서 multi-agent 안 통한다"의 증거 *아님* — pipeline이 벤치의 알려진 regime을 재현함을 확인하는 sanity.

### 6.5 즉시 다음 단계 (2026-04-25 시점 상태)

1. ~~FinanceBench long-context 때문에 controller의 DAG 규칙이 밀리는 문제 패치~~ **완료** (commit `e5725e7`); `results/sanity_financebench_v2/`에서 검증.
2. ~~각 벤치를 **n_val = n_test ≈ 30, max_iters = 3**로 확장~~ **완료** (`results/n30_{financebench,mediq,agentclinic}/`). 아래 §7에 v1+v2 read-out.
3. §7 이후 결정: Framing C로 바로 pivot하지 않고 **controller v2 redesign** 진행 — H1이 v1 controller에서 약 falsified됐지만 v1이 사실상 도메인 인식 행동을 0개 emit했으므로 falsification이 controller laziness에 오염됨.

---

## 7. Controller v2: organization-designer 재설계 (2026-04-25)

### 7.1 왜 재설계

v1의 첫 n=30 sweep (`results/n30_{financebench,mediq,agentclinic}/`)이 실망스런 test 수치를, 더 정보적으로는 **세 도메인에 걸쳐 균일한 v1 controller 행동**을 보임:

- FinanceBench v1: 3 round 모두 `add_agent(verifier)` emit, rationale은 *"lacks a verification step to ensure the executor's output is accurate"* — 금융 어휘 0, prior_edits 신호 무시.
- MEDIQ v1: 동일하게 시작했지만 iter 2에서 노이즈로 ACCEPT됨; iter 3은 그 후 다양화 (anti-repeat-on-accept를 경험적으로 관찰).
- AgentClinic v1: `summarizer ↔ verifier` 교번, 약간의 도메인 어휘 ("concise diagnosis").

즉 n=30에서 v1은 도메인과 무관하게 같은 generic verifier-add 반사. 진단: controller가 진짜 도메인 specialist 조직을 **설계**해야 함, END 앞에 verifier 한 개 끼우는 게 아니라.

### 7.2 v2에서 바뀐 것 (commit `d7b926f`)

`src/controller.py::CONTROLLER_SYSTEM`을 **도메인 전문가 조직도의 architect**로 reframe:

- Specialist persona authoring 필수 규칙 + BAD/GOOD 예시. Generic 이름 (`verifier`, `summarizer`, `critic`, `reviewer`, `validator`) **금지** (specialty와 짝지어진 경우 제외, 예: `cardiology_consultant`, `financial_disclosure_auditor`, `differential_diagnostician`).
- Persona는 **도메인 전문성 인용** + 도메인-구체적 procedure 2-3 sentence 필수.
- **반복 금지 규칙**: 연속 round에서 같은 op 종류 금지; round 간 다양화.
- **적극적 prune 인센티브**: END에 영향 안 주는 agent에 `remove_agent` 권장.
- **도메인 brief 슬롯**: `data/briefs/{name}.md` (~80–110줄) 의 brief를 controller call 맨 위에 inject.

`_build_user_prompt`이 섹션 순서 재정렬 — DOMAIN BRIEF 먼저, current graph 둘째, sampled trajectories 셋째, prior edits 넷째, reminder 블록이 brief 기반 rationale + 특정 tape 인용을 강제. `propose_edits → evolve → run_pilot`로 brief plumbing.

`scripts/serve_vllm.sh` 견고화: CC 누락 시 gcc 자동 설치, default `CUDA_VISIBLE_DEVICES=0` (workspace `../CLAUDE.md` 기준 evo_agents 전용 GPU), default `--max-model-len 16384` (v2 prompt가 brief + multi-agent tape 때문에 8192 초과 가능, 특히 FinanceBench).

### 7.3 v2 sanity at n=10 — 행동 검증

`results/sanity_v2_{financebench,mediq,agentclinic}/`. 세 도메인 모두 pass criteria 충족: specialist persona name, persona 안 도메인 어휘, round 간 edit 다양화. `remove_agent`는 3 도메인 중 2개에서 사용.

하이라이트:

- **FinanceBench sanity v2**: `unit_checker`와 `period_verifier` emit; persona 텍스트가 "GAAP-trained financial analyst", "fiscal year vs. calendar year", "TTM vs annual", "millions, thousands" 인용. Iter 3 ACCEPTED (val 50→90; n=10 노이즈가 도움).
- **MEDIQ sanity v2**: iter 1 `differential_diagnostician` + `physical_exam_mapper` 추가. Iter 2 ACCEPTED — 문자 그대로 `remove_agent(planner)` + 관찰된 eating disorder 케이스를 위한 `adolescent_specialist`. Iter 3 다른 specialty 조합으로 재시도.
- **AgentClinic sanity v2**: iter 1 `decisive_diagnosis_writer` ("convert the prior reasoning into a single, decisive diagnosis name with no hedging or qualifiers" — brief에서 그대로). Iter 2 `triage_specialist` ("emergency medicine physician...identify red flags") + `remove_agent(planner)`. Iter 3 triage + decisive 결합.

v1으로부터 정성적 도약이 큼. v1 controller emit한 persona는 도메인 단어가 거의 0; v2 persona는 job-description 카피처럼 읽힘.

### 7.4 v2 at n=30 — test win은 아직

`results/n30_v2_{financebench_retry,mediq,agentclinic}/`. iter당 wall 4–11분; FinanceBench는 `--max-model-len 16384`로 재실행 — 원래 v2 run이 iter 2에서 8192 한계 초과:
*"This model's maximum context length is 8192 tokens. However, you requested 1500 output tokens and your prompt contains at least 6693 input tokens, for a total of at least 8193 tokens."*

| Domain | CoT test | P-E test | Evolved test | Δ vs best baseline | best_graph |
|---|---:|---:|---:|---:|---|
| FinanceBench (16k) | 73.3% | 70.0% | 83.3%* | +10pp* | seed (모든 iter REJECT) |
| MEDIQ              | 43.3% | 46.7% | 43.3%  | -3.4pp | 3-agent (iter 2 ACCEPT) |
| AgentClinic        | 60.0% | 73.3% | 66.7%  | -6.6pp | seed (모든 iter REJECT) |

*FinanceBench의 명목 +10pp는 **same-graph 노이즈**: best_graph == seed (모든 evolve iter reject)인데 같은 run의 `evolved/test`가 `planner_executor/test`와 13pp 차이. vLLM batch ordering / KV-cache 상태가 같은 graph 두 평가를 n=30에서 5pp 안에 모이게 할 만큼 deterministic하지 않음. Same-graph variance ≥ between-graph variance. **v2 효과로 cite 불가.**

Sweep에서 가장 인상적인 REJECTED 제안은 **AgentClinic iter 3**:

```text
add_agent(triage_specialist)     # ED triage with red-flag screen
add_agent(gastroenterologist)
add_agent(cardiologist)
remove_agent(planner)
remove_agent(executor)
add_edge(START, triage_specialist)
add_edge(triage_specialist, gastroenterologist)
add_edge(triage_specialist, cardiologist)
add_edge(gastroenterologist, END)
add_edge(cardiologist, END)
```

문자 그대로 triage가 라우팅하는 specialty department: triage agent가 케이스를 screen해서 gastroenterology 또는 cardiology로 라우팅, 둘 다 직접 END에 보고. 원래 planner+executor 쌍은 통째로 prune. val이 seed와 tied라 Opt-2 strict (*strict* 개선 요구)로 reject.

### 7.5 측정 노이즈 문제

같은 문제를 가리키는 두 관찰:

1. **Same-graph cross-run variance**: FinanceBench v2 retry에서 같은 underlying seed graph가 같은 run에서 `planner_executor/test = 70%`와 `evolved/test = 83%`. n=30에서 inference loop 재실행만으로 13pp 차이.
2. **v1 vs v2 cross-run variance on baselines**: v1 n=30 FinanceBench는 P-E val=83% / test=67%; v2 retry는 P-E val=83% / test=70%. seed graph 동일, run만 다름.

vLLM이 temperature=0에서도 batch와 KV-cache 상태가 다르면 *완전히* deterministic하지 않음. n=30에서 이 분산이 ≤±10pp 신호를 모두 압도. 두 함의:

- **n=30에서 ±10pp 미만 헤드라인 수치는 결과로 보고하면 안 됨.** 현 sample size에서 v1 vs v2 깔끔한 비교 불가.
- **n을 키우거나 seed를 평균.** n=30에 seed 3개 평균 = 메서드당 n=90 비교력. 각 run을 n=300으로 키우는 것보다 저렴.

### 7.6 Wall budget과 Opt-2 strict

FinanceBench v2 iter는 n_train=10, n_val=30, 3-4 agent에서 ~10–12분. 3 round = ~40분 evolve, baselines + test bench까지 합치면 벤치당 seed당 ~75분 wall.

Opt-2 strict는 `val_acc > best_val_acc` 요구 (slack 0). n=30 ±18pp 노이즈와 함께면 architectural change가 그 bar를 넘어야 ACCEPT — 즉 v2 candidate 대부분 (진짜로 큰 변화 — specialist 2-3개 추가, planner prune)이 노이즈만으로 reject. v2 sweep의 유일한 ACCEPT (MEDIQ iter 2)는 같은 효과 방향의 move가 우연히 노이즈 floor를 이긴 것.

Streaming-mode 작업 (`../../references/roadmap.md` §5.1)이 두 제약을 동시에 해결: round당 100–200 sliding window가 노이즈 amortize; controller가 full train sweep마다가 아니라 window마다 fire → 비슷한 wall 안에 5–10 round.

### 7.7 이 섹션이 *주장하지 않는* 것

- v2가 n=30에서 v1보다 test에서 *낫다* — 측정 노이즈가 그 비교를 막음.
- Strict accept 정책이 틀렸다 — 보수적이지만 노이즈 클 땐 보수적이 적절.
- `gastroenterologist` 같은 specialty agent가 ACCEPT됐다면 test가 좋아졌을 것 — 알 수 없음, 다중 batch 평가 한 번도 안 받음.

주장하는 것:
- v2 controller 행동은 사용자 redirect한 그 organization design.
- 그 행동이 test 정확도에 도움이 되는지 보는 병목은 **측정 설계**, (반드시) controller가 아님.

---

## 8. MEDIQ 첫 실제 streaming 실행 (2026-04-26)

`results/streaming_v2_mediq_b100r10_s0/`. Roadmap §5.1대로 B=100, R=10, seed=0, n_train=30 / n_val=70 / n_test=50. Wall ≈ 9h45m (roadmap의 1.5h 추정과 큰 차이 — 라운드당 ~52분, 4–6 agent 그래프에 multi-step reasoning을 100×2 forward 돌리는 비용이 지배). 자세한 분석은 EN canonical `pilot.md` §8.

### 8.1 헤드라인 숫자

| Method | val (n=70) | test (n=50) | tokens (test) |
|---|---:|---:|---:|
| CoT | 58.6% | **68.0%** | 23.0k |
| Planner-Executor (seed) | 51.4% | 58.0% | 39.4k |
| Evolved (6-agent specialist DAG) | — | 62.0% | 144.8k |

Δ(evolved − best baseline) = **−6.0pp** (vs CoT). vs P-E baseline = **+4.0pp**. Evolved는 CoT 대비 **6.3배 토큰**으로 −6pp.

### 8.2 §5.1 pass 기준 — 부분 통과

- (1) c_acc > b_acc 라운드 1개 이상? **True** — 4/10 ACCEPTED (paired Δ ∈ {+1, +1, +8, +4}pp). **streaming-mode 디자인 작동 확인.** 비교: v2 legacy n=30 3 도메인 × 3 iter = 9번 중 ACCEPT 1번. streaming은 wall당 ~4배 더 많은 paired ACCEPT.
- (2) best_val_acc > seed_batch_acc? **False** — 62% vs 62%. 이 기준은 **streaming 모드에서 구조적으로 깨짐** (§8.4). 재정의 필요.

판정: streaming-mode 자체는 작동하나, 사전 설계한 pass 기준이 paired-batch 비교에서 의미를 잃음.

### 8.3 라운드별 read-out

| r | b_acc | c_acc | Δpp | verdict | edits (요약) |
|---:|---:|---:|---:|---|---|
| 0 | 62.0% | — | — | seed | (planner+executor, 2ag/4ed) |
| 1 | 50.0% | 51.0% | +1.0 | **ACCEPT** | +differential_diagnostician +physical_exam_mapper (4ag) |
| 2 | 54.0% | 55.0% | +1.0 | **ACCEPT** | +epidemiology_consultant (5ag) |
| 3 | 52.0% | 50.0% | −2.0 | reject | +pediatric_specialist (6ag 시도) |
| 4 | 49.0% | 57.0% | +8.0 | **ACCEPT** | +adolescent_medicine_specialist (6ag) |
| 5 | 51.0% | 45.0% | −6.0 | reject | −planner +differential_generator |
| 6 | 41.0% | nan | — | INVALID | "max agents reached" |
| 7 | 54.0% | nan | — | INVALID | "max agents reached" |
| 8 | 49.0% | 53.0% | +4.0 | **ACCEPT** | −planner +differential_generator |
| 9 | 50.0% | nan | — | INVALID | "differential_diagnostician has no incoming edges" |
| 10 | 51.0% | nan | — | INVALID | "max agents reached" |

토큰: worker 4.03 M, controller 73.7 k. ratio ~55× — `calib_01` §4.5의 19–22×보다 큼 (B=100 × multi-agent 그래프).

### 8.4 새 발견: streaming 모드에서 `best_val_acc`가 구조적으로 신뢰 불가

`evolve_streaming()` (`src/evolve.py:379`)에서 `best_val_acc = max(best_acc_history)`인데, 각 항목은 *서로 다른* bootstrap 배치의 정확도. 라운드 0의 seed batch가 운좋게 seed graph를 62%로 측정했고, 이후 라운드들의 task-difficulty 분포가 모든 측정치를 41–57% 구간으로 내려보냄. **이후 라운드는 architectural quality와 무관하게 seed batch의 절대 점수를 못 넘김.**

라운드별 paired comparison (`b_acc`, `c_acc`가 같은 batch) 자체는 sound — 4 ACCEPT는 그것 위에 있음. 그러나 `max(history)`는 cross-batch라서 **난이도가 다른 independent samples 위의 maximum** = quality signal 아님. n=70 P-E val baseline = 51.4%; seed batch P-E = 62%. 이 10pp gap이 bootstrap의 lucky draw. 이후 라운드가 따라잡을 수 없음.

**pass 기준 재정의 옵션**:
- **A.** `best_graph = argmax_g (#paired-win rounds)` — paired-win 비율로 선정.
- **B.** stream pool 외부에 고정 eval batch을 두고 ACCEPT 직후 그곳에서 다시 평가 → 비교 가능한 절대 trace.
- **C.** streaming `best_val_acc`는 bookkeeping field로만 두고, **test acc**를 헤드라인으로. `best_graph`는 마지막 ACCEPT의 그래프.

§5.2 multi-seed sweep에는 **(C)** 가 가장 깔끔: test 평가가 이미 canonical 비교, `best_val_acc > seed_batch_acc` 기준은 pass 리스트에서 제거하고 **test acc + paired-accept rate**로 점수.

### 8.5 새 발견: `max_agents=6` 캡이 streaming에서 30–40% 라운드를 망가뜨림

라운드 4 후 그래프 6 agents 도달 (planner, executor, differential_diagnostician, physical_exam_mapper, epidemiology_consultant, adolescent_medicine_specialist). 캡을 모르는 controller가 specialist 추가 시도 계속. `apply_edits`가 `"max agents reached"`로 reject — 라운드당 ~30분의 `b_acc` 평가 비용이 무용. 4 INVALID 라운드 중 3개가 이 패턴. 4번째 (라운드 9)는 prune이 `differential_diagnostician`의 incoming edges를 끊어버린 별개 버그.

§5.2 전 두 가지 보완:
- **`max_agents`를 controller user prompt에 plumb.** 프롬프트 상단에 `# Constraints: max_agents=6, current=6` 한 줄 → controller가 `add_agent` 대신 `remove_agent` / `rewrite_persona` 고려.
- **prune-DAG reminder.** 기존 reminder는 insertion 중심; "X를 remove하려면 X에 의존했던 모든 agent의 input/output 경로를 유지해야 한다"는 평행한 줄이 라운드 9를 잡았을 것. 인프라 변경 없는 cheap fix.

`max_agents=6` 자체도 너무 보수적 — `pilot.md` §7.4의 AgentClinic v2 iter-3 제안 (triage + 2 specialists + 답안)이 6agents에 안 들어감. §5.2 sweep에 `max_agents=8` 권장.

### 8.6 anti-repeat가 부분적: 같은 아이디어, 다른 이름

라운드 5, 6, 8, 9, 10에 `differential_generator`/`clinical_filter`/`pediatrician` 등 — 5라운드 연속으로 START와 기존 diagnostician 사이에 "case feature extractor" 역할 specialist를 끼워넣는 시도. variant는 rename + 1-edge rewire 정도:

```
r5  remove(planner) + add(differential_generator) + START→differential_generator + differential_generator→differential_diagnostician
r6  add(differential_generator) + START→differential_generator + differential_generator→differential_diagnostician
r7  add(clinical_filter) + add(scientific_expert) + ...
r8  remove(planner) + add(differential_generator) + START→differential_generator + differential_generator→differential_diagnostician  # ACCEPTED
r9  remove(differential_generator) + add(base_rate_consultant) + ...
r10 add(pediatrician) + START→pediatrician + pediatrician→differential_diagnostician + remove(START→differential_generator)
```

현재 anti-repeat ("DO NOT REPEAT a rejected edit")은 controller가 **string level**로 해석 — 이름 다르면 다른 edit. concept-level 반복은 통과. 라운드 8의 반복은 운좋게 favorable batch에 hit해서 ACCEPT됐지만, prior_edits의 steering이 규칙이 약속하는 것보다 약함.

§5.2가 재현하면 controller에게 명시적 *concept tag*를 가르치거나 (e.g. "이미 'pre-DDx case feature extractor' 역할을 3번 제안했음, 이름은 X, Y, Z; 다른 역할로"), orchestration layer에서 edit-similarity 계산 후 더 핀포인트한 reminder. 두 번째 시드 증거가 나올 때까지 보류.

### 8.7 test 결과: evolved가 P-E 이김, CoT에 짐

evolved 6-agent 62% test는 어색한 중간:
- P-E (씨앗 그래프) 대비 +4pp 이김, 6.3배 토큰 — architectural edit이 *뭔가* 유용한 일을 한다는 작은 양의 시그널이지만 단일 시드 n=50 측정에서 noise floor 안 (`pilot.md` §7.5의 same-graph cross-run variance 13pp).
- CoT 대비 −6pp 짐, 6.3배 토큰 — multi-agent overhead가 specialist benefit을 압도.
- `n30_v2_mediq` (legacy v2 evolved test = 43.3%)와 비교 시 +18.7pp 높음. 이것 대부분도 vLLM batch-ordering noise + sample (n=50 vs n=30, 다른 seed-2 split)일 가능성 — §7.5 라인.

**이 숫자를 "streaming 승리"로 인용하면 안 됨.** 발표할 시그널은 paired ACCEPT가 fire한다는 것 (n=30 legacy는 3도메인×3iter에서 총 1번뿐), 그리고 §8.4/§8.5/§8.6의 구조적 발견.

### 8.8 §5.2가 어떻게 보여야 하는지 (§8.x 정리)

- `--max-agents 8` (`run_pilot.py`).
- `max_agents`와 현재 `n_agents`를 controller user prompt에 plumb; prune-DAG reminder 추가.
- streaming pass 기준에서 `best_val_acc > seed_batch_acc` 제거; test + paired accept-rate로 점수.
- 3 시드 × 3 도메인. MEDIQ ~10h wall 기준이면 MEDIQ만 30시간 — 명백히 multi-session. seed-0이 끝났으니 MEDIQ 시드 {1, 2}부터, 그 다음 AgentClinic, FinanceBench.
- `B=50 R=10`을 MEDIQ 시드=1로 미리 (~5h) 돌려 paired ACCEPT가 작은 배치에서도 surface하는지 확인 — 가능하면 sweep의 나머지에서 B를 줄여 시간 budget 안에 더 많은 run.

---

## 9. 요약 한 줄

> v1 controller n=30 → 세 도메인 모두 baseline 이하 또는 동률, rationale은 도메인 무관하게 generic "verifier 추가" 반사 (§7.1). Controller v2를 organization designer로 재설계 (§7.2)하니 정성적으로 다른 행동 — 인용된 도메인 전문성 specialist persona, tape 인용 rationale, 적극 prune (§7.3). v2가 n=30에서 *demonstrably 더 좋지는 않음* (§7.4) — 측정 노이즈 (§7.5)가 압도하고 Opt-2 strict + iter당 wall 예산 (§7.6) 때문에 architectural change 대부분이 다중 노이즈-평균 batch 평가받기 전에 reject.
>
> MEDIQ 첫 실제 streaming run (B=100 R=10 seed=0, §8)이 streaming-mode 디자인이 fire함을 확인 (4/10 paired ACCEPT, v2 legacy의 3도메인×3iter=9 중 1번 대비). 다만 §5.2 전에 막아야 할 3가지 구조적 blocker: (a) bootstrap resampling에서 `best_val_acc > seed_batch_acc` pass 기준이 구조적으로 깨짐 (§8.4), test acc + paired-accept rate로 교체; (b) `max_agents=6` 캡이 라운드 4에서 binding되어 이후 30–40%를 "max agents reached" INVALID로 망가뜨림 (§8.5); (c) anti-repeat이 string level로 강제, concept-level 반복은 통과 (§8.6). §5.2 사전 패치 리스트는 §8.8.
>
> 역사적 (pre-v2) 요약, 컨텍스트 보존: GSM8K `calib_01`에서 evolved가 두 baseline 모두보다 test에서 낮고 2–3.7배 토큰 비용, 이전 accept 정책이 `best_graph`와 `best_val_acc` decoupled (§4) — 둘 다 이 피봇 전에 해결됨.
