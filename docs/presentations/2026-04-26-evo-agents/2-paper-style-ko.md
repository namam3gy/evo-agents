# 논문화 PPT — 슬라이드별 해설 (한글)

이 문서는 `2-paper-style-ko.pptx` 의 각 슬라이드를 도메인을 처음 접하는 분도
따라올 수 있도록 풀어 쓴 한글 해설입니다. 각 슬라이드 한 장 = 본문 한 단락
(필요 시 짧은 용어 풀이) 형식입니다.

> **갱신 노트 (2026-04-27)**: v2 streaming run #2 (MEDIQ seed=1) 결과,
> Controller v3 (full-pass + sample-level reflection + side-channel Q&A)
> 설계와 첫 실험 결과를 반영하여 §4·§7·§9·§10 슬라이드를 갱신/추가했다.

---

## 용어 빠른 정리 (먼저 읽으면 좋음)

- **LLM (Large Language Model)** — GPT, Claude, Qwen 처럼 거대한 텍스트 생성
  모델. 본 연구는 Qwen2.5-32B 라는 오픈 모델을 backbone으로 사용한다.
- **에이전트 (Agent)** — 특정 역할(예: "당신은 임상 감별 진단 전문가입니다…")
  의 페르소나 텍스트로 조건화된 LLM 호출 1개. 물리 로봇이 아니다.
- **DAG (Directed Acyclic Graph)** — 방향성 비순환 그래프. 본 연구에서는
  여러 에이전트를 노드로, "누가 누구의 출력을 입력으로 받느냐"를 엣지로
  가지는 워크플로우 구조.
- **컨트롤러 (Controller)** — *워커* 에이전트들의 trajectory tape을 읽고
  다음 라운드의 그래프 편집을 제안하는 별도의 LLM. 학습되지 않고, 그저
  in-context로 동작한다.
- **trajectory tape** — 한 task에 대해 워커 에이전트들이 순서대로 만든
  출력 + 정답 여부를 나란히 적은 짧은 보고서.
- **EditBatch** — 컨트롤러가 출력하는 JSON으로, "agent X 추가 / Y 제거 /
  엣지 (a→b) 추가" 같은 그래프 편집 연산 묶음.
- **paired-batch** — 같은 부트스트랩 미니배치 위에서 best와 candidate를
  *동시에* 평가해, 배치마다 다른 난이도가 cancel되도록 하는 비교 방식.
- **[SUMMARY] / [QUERY]** (v3 전용) — 각 워커 노드의 출력에 강제되는 구조화
  요약 블록과, 워커가 다른 노드에 1회 한정으로 묻는 질문 토큰. v3에서
  도입.

---

## 슬라이드 1 — 제목

이 발표는 "성찰만으로 진화하는 멀티-에이전트 DAG"라는 파일럿 연구
결과를 요약한다. 핵심 한 문장: 검색이나 강화학습 없이 LLM 컨트롤러가 본인의
워커들이 남긴 trajectory tape만 보고 그래프를 점진적으로 편집하면 — 그것만으로
워크플로우가 진화하는가? 발표자는 thyun.park, 작성일은 2026-04-27 (v3 반영본).

## 슬라이드 2 — 초록 (Abstract)

논문 1쪽짜리 요약. 백본은 Qwen2.5-32B로 고정하고, 도메인은 의료 (MEDIQ /
AgentClinic)와 금융 (FinanceBench) 세 가지를 사용한다. 1차 결과:
v1 컨트롤러는 단순한 "verifier 추가" 반사만 보였고, v2는 도메인 전문가
페르소나 (예: 감별 진단 전문가)를 출력하도록 재설계되었다. n=30 단일 시드
측정에서 발견한 ±13pp 측정 노이즈 문제를 해결하기 위해 streaming evolve
모드를 도입했고, 두 시드 모두에서 Evolved가 P-E 대비 **+4pp** 라는 *동일한*
paired Δ를 재현했다. 다음으로 streaming의 구조적 한계 (cross-batch absolute
acc, max_agents binding, orphan-edit INVALID)를 해결한 **Controller v3**를
설계·구현했다 — full-pass + 샘플 단위 reflection (n=30 evals → 3 mid → 1
final EditBatch) + 워커 DAG에 [SUMMARY] / [QUERY] side-channel Q&A를 부여.
v3 첫 run (MEDIQ seed=0)에서 **Evolved 52% > CoT 46% (+6pp)** 로,
전체 파일럿에서 처음으로 CoT 베이스라인을 이긴 결과가 나왔다 (단, 단일
시드). 다중 시드 sweep은 진행 예정.

## 슬라이드 3 — Section: 1. 서론

여기서부터 §1 서론. 동기 → 기여 두 슬라이드로 풀어낸다.

## 슬라이드 4 — 1.1 연구 동기

단일 LLM은 똑똑하지만, 도메인 특화 작업에서는 "기획자 / 전문가 / 검증자"
처럼 역할을 나누면 정확도가 더 올라간다는 보고가 많다. 하지만 *어떻게*
역할 분담 그래프를 자동으로 디자인할지는 열린 문제다. 기존 답변은 (a)
검색 (ADAS, AFlow, GPTSwarm 등 — 후보 그래프를 archive에서 탐색) 또는
(b) 강화학습 (Puppeteer 등) 두 갈래. 본 연구는 그 둘을 모두 빼고, 그저
LLM에게 "이 trajectory tape을 보고 그래프를 직접 고쳐 봐"라고 부탁하면
어떻게 되는지 묻는다.

## 슬라이드 5 — 1.2 기여 (Contributions)

네 가지로 정리된다. (1) reflection-only 멀티-에이전트 진화 자체 —
검색·RL이 없는 방식의 가능성을 측정했다. (2) Controller v2 —
"organization-designer" 프레이밍으로, 같은 백본이 도메인별로 마치 다른
전문가처럼 행동하도록 만드는 시스템 프롬프트 + 도메인 brief 조합. (3)
streaming paired-batch evolve mode — 측정 노이즈가 크던 환경에서 paired
ACCEPT 비율을 1/9 → 4/10 으로 끌어올린 알고리즘 변경. (4) **Controller
v3** — full-pass 모드 + 샘플 단위 hierarchical reflection (per-task
priority-weighted aggregation) + 워커 DAG의 side-channel Q&A; orphan
auto-drop 으로 INVALID를 0으로 만들고 첫 CoT-beat 결과를 산출.

## 슬라이드 6 — Section: 2. 관련 연구

여기서부터 §2. 검색-기반 / RL-기반 두 갈래의 기존 연구를 표로 정리한다.

## 슬라이드 7 — 2.1 검색·RL 기반 자동 설계

대표 다섯 줄 비교: ADAS (archive 검색), AFlow (MCTS), GPTSwarm
(graph search + edge importance), MaAS (multi-agent supernet), Puppeteer
(NeurIPS 2025, RL). 모두 *학습 신호 또는 검색 절차*를 가정한다는 공통점을
가진다.

## 슬라이드 8 — 2.2 본 연구의 차별점

본 연구는 frozen LLM (학습 안 함) + 자연어 trajectory tape (검색 archive
없음) + 자연어 EditBatch (액션 디자인 없음)만으로 그래프를 진화시킨다.
이 슬롯은 *좁다*. 좁다는 것은 reviewer가 "ADAS와 다른 게 뭔가요?"라고
물을 때 핵심을 명확히 답할 수 있다는 장점도 있고, 동시에 "그래서 더 잘
되나요?"라는 압박을 받기도 쉽다는 단점도 있다. EMNLP 2026 ARR 트랙이
1차 목표.

## 슬라이드 9 — Section: 3. 문제 정의

여기서부터 §3. 그래프와 편집 연산 → reflection-only 가정 두 슬라이드.

## 슬라이드 10 — 3.1 그래프와 편집 연산

그림: CoT (1 에이전트, 입력→solver→출력) / Planner-Executor (계획자가
먼저 plan을 짜고 실행자가 plan을 따라 답함) / Evolved (예: triage →
{소화기, 심장} → answer 의 4-에이전트 specialty department). 편집 연산은
agent 추가/제거 + persona 재작성 + edge 추가/제거 5종류이며, 한
라운드에 1-3개를 묶어 EditBatch로 출력한다.

## 슬라이드 11 — 3.2 Reflection-only 가정

본 연구의 핵심 가정 셋: (a) 백본 weights 동결 — fine-tune이나 RL
미세조정 안 함. (b) 컨트롤러는 검색 archive 없음 — 입력은 trajectory
tape + (선택적) domain brief뿐. (c) accept 규칙은 검증 정확도(legacy)
또는 같은 batch에서의 paired Δ(streaming) 또는 full-pass train_acc
strict (v3). 이 가정이 좁은 만큼, "in-context 성찰만으로 어디까지
가능한가?"라는 한 가지 질문에 정확히 답할 수 있다.

## 슬라이드 12 — Section: 4. 방법

여기서부터 §4 방법. v2 컨트롤러 → persona 규칙 / brief → streaming
paired-batch → controller v3 (full-pass + sample-level reflection) →
side-channel Q&A → accept 규칙 + max_agents 제약 여섯 슬라이드.

## 슬라이드 13 — 4.1 Controller v2 — organization designer 프레이밍

그림: v1과 v2의 reflection 루프를 나란히 비교. 중요한 점은 *루프 자체는
동일*하다는 것이다. 차이는 SYSTEM 프롬프트와 부수적인 domain brief뿐.
v1의 시스템 프롬프트는 "그래프를 편집하라" 정도의 일반적인 안내였는데,
v2는 "당신은 도메인 전문가들의 *조직(organization)*을 설계하는 사람입니다.
이 도메인에서 더 잘 굴러가는 조직이 되도록 그래프를 편집하세요"라는
프레이밍으로 바꾸었다.

## 슬라이드 14 — 4.2 Persona 작성 규칙 + 도메인 brief

새로 추가하는 모든 에이전트는 (a) 인용된 specialty (예: "10년 경력의
내과 감별 진단 전문가")와 (b) 구체적 procedure (예: "기본 발생률을 먼저
고려하고, 그 다음 환자 인구학을 본다")를 페르소나 텍스트에 명시하도록
강제한다. 일반적인 "verifier", "summarizer", "critic" 같은 역할은
specialty와 짝짓지 않으면 *금지*. 또한 도메인별로 80-110줄짜리 brief
(`data/briefs/*.md`)를 만들어두고 컨트롤러 user prompt에 prefix로 붙인다.
이 brief는 task style / failure modes / useful expertise / anti-patterns
를 자연어로 담은 일종의 도메인 cheat sheet.

## 슬라이드 15 — 4.3 Streaming paired-batch evolve mode

그림: 라운드마다 train+val 풀에서 with-replacement로 B 태스크 (예: 100)를
뽑아 mini-batch을 만든다. 그 *같은 batch*로 best_graph와 candidate
(apply_edits 결과)를 둘 다 평가하여 b_acc, c_acc를 얻는다. ACCEPT는
c_acc가 b_acc + ε 보다 클 때만. 핵심은 paired 비교라서, batch마다
난이도가 다른 cross-batch 노이즈가 cancel된다는 점이다. v2 streaming은
§5.1에 사용되었고, §5.2 부터는 다음 슬라이드의 v3으로 교체된다.

## 슬라이드 16 — 4.4 Controller v3 — full-pass + 샘플 단위 reflection

streaming run #1 / #2가 노출한 세 가지 구조적 문제 (cross-batch
`best_val_acc`가 max-over-independent-samples로 비신뢰, max_agents binding이
30~40 % 라운드를 INVALID화, orphan prune)를 해결하기 위해 v3은 *legacy 형식의
full-pass 루프*로 돌아간다. 각 iter에서 (a) best_graph와 candidate를
*동일한 train set 30 태스크 전부* 위에서 평가하고, (b) ACCEPT는
`train_acc(candidate) > train_acc(best)` strict, (c) `apply_edits`는
orphan agent를 INVALID 대신 *조용히 drop* 한다 — 그래서 v3에서는 INVALID
라운드가 0이다. 그러나 단순히 legacy로 회귀하면 reflection density가 낮아
질 텐데, 이를 막기 위해 다음 두 가지를 새로 도입한다 — 슬라이드 17·18.

## 슬라이드 17 — 4.5 샘플 단위 reflection + 계층적 집계

핵심 아이디어: 컨트롤러를 *각 train task 마다* 호출하여, 그 한 샘플의
tape이 "이 그래프에 대해 무엇을 시사하는가?"를 묻는다. 출력 스키마는
`{rationale, suggested_edits, priority: 0-100, target_aspect}` 네 필드.
priority는 컨트롤러가 자기 의견의 강도를 자가 보정하는 슬롯이고,
target_aspect는 structure / role / length / expertise 중 하나로 어떤
차원의 변경을 원하는지를 표시한다. 이 30개 샘플 평가가 priority 내림차순
정렬 후 10개씩 묶여 *3개의 mid_decision*으로 합쳐지고, 다시 1개의 *final
EditBatch*로 합쳐져 그래프에 적용된다 (30 → 3 → 1 의 hierarchical
aggregation). 이 구조가 "한 샘플의 노이즈가 그래프 편집을 좌우"하는
사고 사고를 막아준다.

## 슬라이드 18 — 4.6 워커 DAG의 side-channel Q&A ([SUMMARY] / [QUERY])

워커 그래프 자체에도 두 가지 채널을 추가한다. (1) **[SUMMARY] 블록 (S-2)**:
모든 워커 에이전트는 자기 응답 끝에 `claim / evidence / confidence` 3행
요약을 강제로 emit. orchestrator가 이를 파싱해 그 *다음* 에이전트의 user
prompt 앞에 `[Conversation so far]` 블록으로 넣어준다 — `agent.inputs` 와는
독립된 *추가* 정보 채널 (W-2). (2) **[QUERY] 토큰 (Q-3)**: 모든 워커
프롬프트에 "원하면 다른 에이전트 1명에게 질문 1개를 던지세요. `[QUERY <name>]
<question>` 형식으로 한 줄 출력 후 멈추세요"라는 instruction을 추가. 워커가
이를 emit하면 orchestrator가 (Call B, lite-mode, 256 tokens, 재귀 금지)
답변을 받아 (Call C) 원래 워커가 답변과 함께 자기 추론을 *재개* 하도록
한다 — 노드당 최악 3 LLM 호출. recursion 금지 / 1 query/노드/태스크 hard cap.

## 슬라이드 19 — 4.7 Accept rule + max_agents 제약

세 모드의 accept 정책. **Legacy (v2 n=30)**: Opt-2 strict — val 정확도가
*strict* 향상된 경우에만 best 갱신; tie REJECT. **Streaming (v2 §5.1)**:
paired Δ > ε; default ε=0.0. **v3 full-pass**: train_acc strict > 비교.
공통 제약: **max_agents** cap이 그래프 크기를 제한; v2는 default 8 (소프트),
v3은 **10 (HARD — apply_edits가 INVALID)**. v3에서는 추가로 `apply_edits`가
무입력 / 무출력 agent를 자동으로 drop 하므로 partial-wire 편집이
INVALID가 아니라 no-op이 된다.

## 슬라이드 20 — 5. 구현 (Implementation)

코드 트리 1쪽 요약. `src/`에 라이브러리 (llm, graph, orchestrator,
controller, evolve, score, types), `scripts/run_pilot.py`가 단일 드라이버,
`scripts/serve_vllm.sh`가 vLLM 서버 부트 스크립트. 환경 관리는 `uv`,
백본은 Qwen2.5-32B-Instruct를 H200 GPU 한 장에 bf16으로 띄움.
`max_model_len=16384`은 v2의 brief + 멀티-에이전트 tape이 8192를 넘기 때문에
필요. 결과 산출물은 매번 `results/<run_id>/{evolve_log.json, results.json,
plots/, iter_K/}` 형태로 저장된다 (v3는 iter_K/{evals.jsonl, mid_decisions,
final_edit, train_eval, evolve_state} 가 추가로 dump 되어 `tail -f` 가능).

## 슬라이드 21 — 6.1 실험 설정 — 도메인

세 도메인의 성격 비교. **FinanceBench** — 10-K 기업 보고서에서
숫자를 추출해 답하는 QA. GAAP / TTM / 회계연도처럼 financial 어휘에
약하면 헷갈리고, 긴 컨텍스트에서 retrieval이 안 되면 hedging
(애매한 답)으로 빠진다. **MEDIQ** — 임상 vignette을 읽고 객관식 정답을
고르는 task. 감별 진단 + 기본 발생률 (base rate) 사고가 핵심이고,
인구학 (예: 17세 여학생) 단서를 무시하면 틀린다. **AgentClinic** —
single-pass 임상 케이스. 어느 specialty (소화기 / 심장 등)로 routing
할지가 정확도에 직결된다.

## 슬라이드 22 — 6.2 측정 지표 + 노이즈 floor

지표는 (a) test accuracy (held-out test에서의 정답률), (b)
paired-accept rate (streaming에서 ACCEPT된 라운드 / 유효 라운드),
(c) 토큰/태스크. 중요한 caveat: 같은 그래프를 두 번 다른 vLLM 인스턴스에서
돌려도 test accuracy가 13pp 가까이 흔들릴 수 있다 (FinanceBench v2 retry,
또는 MEDIQ run #1 → run #2 사이 CoT 68 → 46 의 22pp 변동 사례).
이 노이즈 floor가 우리가 보려는 architectural 효과와 비슷한 수준이라
*paired Δ* (Evolved vs P-E in the same run)가 cross-run 변동을
타고 가장 안정적인 비교 지표가 된다.

## 슬라이드 23 — Section: 7. 실험 결과

여기서부터 §7. 시간 순으로 calib_01 → v1 n=30 → v2 n=30 → streaming
run #1 → streaming run #2 → patches sanity → v3 first run → v3 vs v2
요약 8 슬라이드.

## 슬라이드 24 — 7.1 calib_01 (GSM8K) — 출발점

가장 처음 50개 샘플로 돌린 GSM8K 실험. Evolved 86% / CoT 92% / P-E 90%.
Evolved가 두 baseline 모두에 *지고* 토큰은 2-3배 더 쓴다. 단순히
"멀티-에이전트가 좋다"는 가설이 깨지는 결과인데, 원인은 GSM8K 자체에
있다 — 단일 모델이 이미 saturate해서 헤드룸이 없고, 텍스트가 self-contained
이라 정보 비대칭이 없으며, 산술이 선형이라 planner/executor 분해가
이득을 못 만든다. 그래서 도메인 피봇 결정.

## 슬라이드 25 — 7.2 v1 controller @ n=30

세 도메인 표. FinanceBench 0pp, MEDIQ +6.7pp (±18pp 노이즈 안), AgentClinic
0pp — 어느 도메인도 baseline을 *명확히* 이기지 못함. 더 중요한 발견은
컨트롤러의 *행동*: FinanceBench에서 같은 `add_verifier` edit을 3 라운드
연속 출력했고, 도메인 어휘가 전무했다. v1 시스템 프롬프트가 너무 얇아서
도메인 헤드룸을 이용하지 못한다는 가설이 굳어진다 — v2 재설계로 이행.

## 슬라이드 26 — 7.3 Controller v2 @ n=30

v2의 행동은 분명히 달라졌다 — `gaap_analyst`, `period_validator`,
`differential_diagnostician`, `adolescent_specialist` 같은 이름의
specialist persona가 등장하고, AgentClinic iter-3은 정식
"triage → 소화기/심장 → answer"의 specialty department 구조까지 제안.
*그러나* test 승리는 일어나지 않았다. FinanceBench가 +10pp로 이긴
것처럼 보이는데, best_graph는 seed (편집 없이 채택)였고 같은 P-E 그래프의
parallel test run보다 13pp 멀어졌다 — 이건 v2의 효과가 아니라 vLLM
배치 순서 / KV 캐시 비결정성에서 오는 cross-run 노이즈. v2 *행동*은
H2 만족, 그러나 *test 승리*는 미달성.

## 슬라이드 27 — 7.4 Streaming run #1 (B=100 R=10 seed=0)

per-round Δ bar chart. 10 라운드 중 4번 ACCEPT (Δ +1, +1, +8, +4),
2번 reject, 4번 INVALID (controller가 그래프 캡 6에 도달했는데도
add_agent를 계속 시도해서 거부, 또는 prune이 다른 agent를 orphan화).
legacy 모드의 1/9 ACCEPT 와 비교하면 *방법이 fire한다*는 첫 실증.
여기서부터 streaming-mode가 본 연구의 가장 강한 차별점이 된다.

## 슬라이드 28 — 7.5 Run #1 — DAG 진화 + token cost

5개 DAG snapshot으로 그래프가 어떻게 자라는지 보여준다 — R0 seed (planner+executor)
→ R1 ACCEPT (+감별 진단 전문가) → R2 ACCEPT (+역학 컨설턴트) →
R4 ACCEPT (+청소년 의학 전문가) → R8 ACCEPT (planner 제거 +
differential_generator 추가). Token 비용 그래프: CoT 0.46k / P-E 0.79k /
Evolved 2.9k tokens per task에 정확도 68% / 58% / 62%. 토큰을 더 쓴다고
정확도가 따라오지 않는다 — 이건 약점으로 정직하게 명시할 부분.

## 슬라이드 29 — 7.6 Streaming run #2 (MEDIQ seed=1) — paired Δ 재현

같은 streaming 모드에서 시드만 바꾼 run #2. 라운드 결과: **2 ACCEPT /
6 reject / 2 INVALID** (run #1 대비 ACCEPT 절반, INVALID는 절반).
test n=50 결과: CoT 46% / P-E 42% / Evolved 46%. **Δ vs P-E = +4pp**
가 run #1과 *동일하게* 재현되었다. 절대 정확도는 시드 0 (CoT 68%) 대비
22pp 낮은 split이지만, paired Δ가 split 난이도를 cancel하면서 streaming
mode의 *안정적인* 신호로 자리잡는다. INVALID 2건은 둘 다 orphan-edit 패턴
(partial-wire add_agent / orphan prune) 으로, run #1의 INVALID 패턴이
seed에 robust하게 재현된다는 것을 보여준다 — v3에서 해결할 부분.

## 슬라이드 30 — 7.7 §5.1.5 patches + sanity

Streaming run #1·#2에서 발견된 3 blocker (max_agents cap, prune orphan,
concept-level repeat)를 패치한 commit `8405c78` 요약. 검증 sanity
(B=20 R=3 mediq seed=0): r2에서 paired ACCEPT (Δ=+5pp)이 떴고,
`_build_user_prompt` 직접 호출로 새 `# Constraints` 블록이 정상 렌더되는
것을 확인. 다만 R=3 / cap=8에서는 cap-binding과 concept-level
anti-repeat이 실제로 fire하지 않아 (배치가 작아서) 이건 streaming의 본질적
한계로 결론 내고 § 4.4 ~ §4.6 의 Controller v3 재설계로 이행.

## 슬라이드 31 — 7.8 Controller v3 첫 run — Evolved beats CoT (+6pp)

v3 첫 실험: MEDIQ seed=0, n_train=30, max_iters=10, **wall ≈ 5h**
(v2 streaming 9-10h의 절반). 이터별 결과: 4 ACCEPT (iter 1, 5, 7, 8) /
6 reject / **0 INVALID** — orphan auto-drop이 streaming의 INVALID 30-40 %
문제를 완전히 해소. 최종 그래프는 8-에이전트 specialty department
(planner → {differential_diagnostician, epidemiology_base_rate_consultant,
adolescent_medicine_specialist} → physical_exam_mapper / laboratory_consultant
/ obgyn_consultant → executor). **Test n=50: CoT 46% / P-E 50% /
Evolved 52%** — *전체 파일럿에서 처음으로* Evolved 가 CoT를 이긴 결과
(+6pp). 토큰은 P-E 1.09k 대비 3.28k (3.0×). caveat: 단일 시드 + 단일
도메인 + ±13pp 노이즈 안이라 multi-seed 재현이 필수.

## 슬라이드 32 — 7.9 v3 vs v2 streaming — 종합

같은 MEDIQ 도메인에서 세 run을 정리한 표. **v2 streaming run #1 (s=0)**:
9h45 wall / 4 ACCEPT / 4 INVALID / 6 agents / Δ vs CoT = −6pp / Δ vs P-E
= +4pp. **v2 streaming run #2 (s=1)**: 9h32 wall / 2 ACCEPT / 2 INVALID
/ 4 agents / Δ vs CoT = 0pp / Δ vs P-E = +4pp. **v3 first run (s=0)**:
**5h wall** (½) / 4 ACCEPT / **0 INVALID** / 8 agents / **Δ vs CoT = +6pp**
/ Δ vs P-E = +2pp. v3은 절반 wall 로 같은 ACCEPT 횟수를, 더 큰 그래프를,
그리고 처음으로 CoT를 이기는 결과를 산출한다. 단, v2와 v3 모두 *단일
시드*씩이라 multi-seed sweep이 venue submission 직전 필수 작업.

## 슬라이드 33 — Section: 8. 분석

여기서부터 §8. 측정 노이즈 + 토큰 비용/실패 모드 두 슬라이드.

## 슬라이드 34 — 8.1 측정 노이즈와 paired-batch / full-pass의 효과

±13pp same-graph 노이즈는 vLLM의 비결정성에서 온다. legacy 모드에서는
이 노이즈가 cross-batch 비교를 망쳐서 architectural Δ를 reject로 묻어버렸다.
streaming paired-batch는 best와 candidate를 *같은 batch*에 넣어
이 노이즈를 cancel한다 (1/9 → 4/10 ACCEPT). 그러나 streaming의 absolute
acc는 여전히 bootstrap 분포에 의존해 cross-batch best_val_acc는 비신뢰
판정. v3 full-pass는 *동일한 30개 train task* 위에서 best와 candidate를
둘 다 평가하므로 noise floor 안에서 strict 비교가 가능하고, MEDIQ s=0
에서 4 ACCEPT를 INVALID 0으로 산출했다. paired Δ (+4pp vs P-E) 가
v2 streaming 두 시드에서 *재현* 된 것이 본 연구의 가장 robust한 정량
신호이며, v3 +6pp vs CoT는 *단일 시드 한정 강신호* 로 cross-seed 검증
대상이다.

## 슬라이드 35 — 8.2 토큰 비용과 실패 모드

Worker 토큰 ≈ 55 × controller 토큰 (run #1 기준 4.03M : 73.7k).
즉 wall-time과 비용은 worker LLM 호출이 좌우한다. v3은 노드당 [QUERY]
fire 시 3 LLM 호출까지 늘어나 worker 비용이 평균 1.5-2× 증가하지만,
INVALID 로 버려지는 라운드가 0이라 wall efficiency는 streaming의 ½.
실패 모드 (run #1·#2 기준): max_agents cap binding 6건 (전부 INVALID),
prune이 다른 agent를 orphan 4건, 같은 역할에 다른 이름을 붙여 5라운드
연속 같은 변경을 제안한 concept-level repeat. v3에서 (1) max_agents cap을
prompt + apply_edits hard로 plumbing, (2) orphan auto-drop, (3) concept-level
repeat은 여전히 soft-only — open issue로 향후 작업.

## 슬라이드 36 — Section: 9. 한계 및 향후 작업

여기서부터 §9. 한계와 향후 두 슬라이드. 정직한 자기 평가가 목적.

## 슬라이드 37 — 9.1 한계 (Limitations)

7가지 약점을 정직하게 나열한다: ① v3의 +6pp vs CoT는 *단일 시드 단일
도메인 (MEDIQ s=0)* — multi-seed × multi-domain 재현 필요. ② ±13pp
노이즈 floor 가 v3에서도 여전 (run-to-run absolute acc 22pp 변동 관찰됨).
③ LLM-judge가 같은 family Qwen이라 self-bias 위험. ④ 단일 backbone,
단일 judge. ⑤ v3 wall 5h × seed × domain → 3×3 sweep 약 45h
(streaming 의 ½). ⑥ ADAS / MaAS / Puppeteer 직접 baseline 미실시 —
reviewer 첫 질문이 될 항목. ⑦ concept-level anti-repeat 이 v3에서도
prompt-only soft constraint — orchestration layer hard enforcement는 향후
작업. 이 7개를 그대로 논문 §6 "Limitations"에 옮길 예정.

## 슬라이드 38 — 9.2 향후 작업 (Future Work)

§5.2-§5.7 로드맵. (1) **v3 multi-seed sweep** (MEDIQ s={1,2}, AgentClinic
s={0,1,2}, FinanceBench s={0,1,2}) — venue submission 직전 핵심. (2)
random-persona ablation — v2/v3 페르소나를 동일 개수의 random 텍스트로
교체해 specialty 효과를 격리. (3) harness ablation — controller {none,
random, fixed-topo, full v3}. (4) 두 번째 백본 (Qwen3-72B + Claude/GPT
API). (5) LLM-judge를 다른 family로 교체 (Claude Haiku 4.5 또는
GPT-4.1-mini). (6) **ADAS + (MaAS / Puppeteer / EvoMAC) 직접 baseline** —
reviewer 필수 항목이라 이건 비협상. (7) [QUERY] fire-rate / valid-rate
측정 — v3 component-level ablation 의 input.

## 슬라이드 39 — 10. 결론

다섯 줄 결론: ① reflection-only 멀티-에이전트 진화는 *그래프를 움직이게*
만든다 — v2가 도메인 어휘를 가진 specialist persona를 출력함이 그
증거. ② v2 @ n=30 단일 시드에서는 baseline을 못 이겼고, 노이즈가 신호를
가렸다. ③ streaming paired-batch가 노이즈 floor 문제를 부분 해결한다 —
1/9 → 4/10 ACCEPT 비약, 그리고 두 시드에서 paired Δ vs P-E = +4pp로
재현. ④ **Controller v3** (full-pass + 샘플 단위 reflection + side-channel
Q&A + orphan auto-drop) 가 INVALID를 0으로 만들고 wall을 ½로 줄이며,
MEDIQ s=0 에서 처음으로 Evolved 가 CoT 를 +6pp 차이로 이기는 결과를
산출. ⑤ 단일 시드 한정 강신호 — 다중 시드 / 두 번째 백본 / ADAS 직접
비교가 venue submission 직전 잔여 작업.

## 슬라이드 40 — 감사합니다 / Q&A

발표 종료. 코드와 결과는 github.com/namam3gy의 project repo에 공개되어
있고, 살아있는 로드맵 트래커는 `references/roadmap_ko.md`에서 확인할 수
있다.

---

## 보충 — Novelty가 강한/약한 부분 (논문 §6에 들어갈 자기 평가 — v3 반영)

### 강한 (Novelty)
1. **Reflection-only 진화 자체** — 기존 ADAS / GPTSwarm / MaAS /
   Puppeteer가 모두 검색이나 학습 신호를 사용하는 것에 반해, 이 연구는
   순수 in-context reflection만 사용한다. *좁은* 슬롯이지만 명확하게
   비어있던 슬롯이다.
2. **Streaming paired-batch evolve mode** — 측정 노이즈가 dominant한
   환경에서 paired ACCEPT 비율을 1/9 → 4/10 로 끌어올린 알고리즘적
   변경. 두 시드에서 paired Δ vs P-E = +4pp 재현 — robust 신호.
3. **Org-designer 컨트롤러 + 도메인 brief** — 같은 backbone이 도메인별로
   다른 전문가처럼 행동하게 만드는 prompt-engineering 기법. v1 → v2의
   행동 변화는 정성적으로 분명하다.
4. **Controller v3 (가장 강한 novelty 후보)** — (a) 샘플 단위 reflection
   + 30 → 3 → 1 hierarchical aggregation, (b) 워커 DAG 의 [SUMMARY]
   transcript + [QUERY] side-channel Q&A 로, 워커 단위와 메타 단위 양쪽에서
   reflection density 를 높임. (c) orphan auto-drop 으로 INVALID 를 0 으로
   만들고 v2 streaming 의 30~40 % round-loss 를 제거. (d) 첫 CoT-beat 결과
   (+6pp on MEDIQ s=0).

### 약한 (Weaknesses, 정직하게)
1. **v3 +6pp vs CoT 는 단일 시드 단일 도메인** — multi-seed × multi-domain
   재현이 가장 큰 미해결 작업.
2. **단일 backbone / 단일 judge** — reviewer 표준 질문에 대답이 약하다.
3. **ADAS 직접 비교 미실시** — "어떻게 ADAS와 다른가요?"의 자연스러운
   다음 질문 "그래서 ADAS와 비교해서 더 잘 되나요?"에 답이 없다.
4. **soft constraint의 한계** — concept-level anti-repeat이 v3 에서도
   prompt-only. orchestration layer 에서 하드 enforce 하는 것이 다음 단계.
5. **Wall budget** — v3 3×3 sweep 이 ~45h (streaming 의 ½). 더 큰
   backbone 비교나 ablation 을 추가할 때마다 시간이 비례해서 늘어난다.
6. **GSM8K negative result는 narrative entry 일 뿐** — 핵심 결과가 아니라,
   왜 이 도메인 piv가 필요했는지를 설명하는 *이유*로 사용된다.
7. **[QUERY] fire-rate / parse-rate 미측정** — v3 component-level ablation
   의 input 이 아직 없다.
