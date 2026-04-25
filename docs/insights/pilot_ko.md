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

### 6.5 즉시 다음 단계

1. FinanceBench long-context 때문에 controller의 DAG 규칙이 밀리는 문제 패치 — `src/controller.py::CONTROLLER_SYSTEM` 짧은 타겟 수정.
2. 각 벤치를 **n_val = n_test ≈ 30, max_iters = 3**로 확장 (공유 H200에서 벤치당 ~20–40분). 이것이 실제 첫 domain-pivot 측정.
3. 그 *후에야* 도메인 피봇이 가설을 회복시키는지, 아니면 Framing C (persona-necessity negative result)로 피봇할지 결정.

---

## 7. 요약 한 줄

> GSM8K 은퇴 후 세 새 도메인 벤치(FinanceBench, MEDIQ, AgentClinic)에서 파이프라인이 **정상 동작** (§6). 피봇의 첫 긍정 신호: **controller rationale이 도메인에 따라 달라짐** — 예전처럼 "arithmetic verifier 추가"로 default되지 않음 (§6.3). 첫 부정 신호: FinanceBench의 long evidence context가 controller의 DAG 규율을 깨뜨림 (§6.3). 역사적 `calib_01` 결과: GSM8K에서 evolved가 두 baseline보다 test에서 낮고 2–3.7배 토큰 비용, 이전 accept 정책이 `best_graph`와 `best_val_acc`을 decoupled (§4) — 둘 다 이 피봇 전에 해결됨.
