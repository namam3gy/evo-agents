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

## 4. 남은 과제 / 다음에 해볼 것

1. **n_val 300+ 로 재실행** — 방법 간 차이가 실제로 나타나는지 확인.
2. **seed 최소 3개로 변동성 측정** — 현재 seed 하나짜리 run은 "verifier를 추가했다"가 체리피킹일 가능성을 배제 못함.
3. **Controller의 no-op 비율 로그** — §2.2 참고. `evolve_log.json`에 `is_noop: bool` 필드 추가를 제안.
4. **`scripts/serve_vllm.sh` pre-flight** — gcc 존재 / GPU free memory 체크 / vllm CLI flag sniff를 기동 전에 수행.
5. **pyproject에 jupyter 관련 dev-extra** — `nbformat`, `nbclient`, `ipykernel`을 선택적 extra로 넣어두면 노트북 재실행이 편해진다. 현재는 매번 `uv pip install` 해야 함.

---

## 5. 요약 한 줄

>  파일럿은 **정상 동작**하고, controller는 **포화된 val에서도 의미 있는 개입**을 한다. 헤드라인 숫자를 뽑으려면 (a) n_val/n_test를 키우고 (b) seed를 여럿 돌려 variance를 봐야 한다. 운영상으론 `gcc` / `vllm CLI 플래그` / `gpu_util`이 기동 실패의 3대 원인이었다.
