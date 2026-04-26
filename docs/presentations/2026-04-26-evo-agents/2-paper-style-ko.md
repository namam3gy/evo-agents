# 논문화 PPT — 슬라이드별 해설 (한글)

이 문서는 `2-paper-style-ko.pptx` 의 각 슬라이드를 도메인을 처음 접하는 분도
따라올 수 있도록 풀어 쓴 한글 해설입니다. 각 슬라이드 한 장 = 본문 한 단락
(필요 시 짧은 용어 풀이) 형식입니다.

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

---

## 슬라이드 1 — 제목

이 발표는 "성찰만으로 진화하는 멀티-에이전트 DAG"라는 파일럿 연구
결과를 요약한다. 핵심 한 문장: 검색이나 강화학습 없이 LLM 컨트롤러가 본인의
워커들이 남긴 trajectory tape만 보고 그래프를 점진적으로 편집하면 — 그것만으로
워크플로우가 진화하는가? 발표자는 thyun.park, 작성일은 2026-04-26.

## 슬라이드 2 — 초록 (Abstract)

논문 1쪽짜리 요약. 백본은 Qwen2.5-32B로 고정하고, 도메인은 의료 (MEDIQ /
AgentClinic)와 금융 (FinanceBench) 세 가지를 사용한다. 1차 결과:
v1 컨트롤러는 단순한 "verifier 추가" 반사만 보였고, v2는 도메인 전문가
페르소나 (예: 감별 진단 전문가)를 출력하도록 재설계되었다. n=30 단일 시드
측정에서 발견한 ±13pp 측정 노이즈 문제를 해결하기 위해 streaming evolve
모드를 도입했고, 이는 첫 실제 run에서 10라운드 중 4 ACCEPT 라는 의미 있는
신호를 만들어냈다 (이전 legacy 모드는 9 iter 중 1 ACCEPT). 다중 시드
sweep은 현재 진행 중이다.

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

세 가지로 정리된다. (1) reflection-only 멀티-에이전트 진화 자체 —
검색·RL이 없는 방식의 가능성을 측정했다. (2) Controller v2 —
"organization-designer" 프레이밍으로, 같은 백본이 도메인별로 마치 다른
전문가처럼 행동하도록 만드는 시스템 프롬프트 + 도메인 brief 조합. (3)
streaming paired-batch evolve mode — 측정 노이즈가 크던 환경에서 ACCEPT
비율을 의미 있게 끌어올린 알고리즘 변경.

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
또는 같은 batch에서의 paired Δ(streaming). 이 가정이 좁은 만큼,
"in-context 성찰만으로 어디까지 가능한가?"라는 한 가지 질문에 정확히
답할 수 있다.

## 슬라이드 12 — Section: 4. 방법

여기서부터 §4 방법. v2 컨트롤러 → persona 규칙 / brief → streaming
paired-batch → accept 규칙 + max_agents 제약 네 슬라이드.

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
난이도가 다른 cross-batch 노이즈가 cancel된다는 점이다.

## 슬라이드 16 — 4.4 Accept rule + max_agents 제약

Legacy 모드 (Opt-2 strict): val 정확도가 *strict하게* 향상된 경우에만
best를 갱신; tie REJECT. Streaming 모드: paired Δ가 ε보다 큰 경우만
ACCEPT (default ε=0.0). max_agents는 그래프가 무한히 커지지 않도록
하는 cap (default 8). 이 cap 정보는 컨트롤러 user prompt에 `# Constraints`
블록으로 노출되어, 컨트롤러가 cap에 도달하면 add_agent 대신
remove_agent / rewrite_persona / 엣지 편집을 선택하도록 유도한다.
prune-DAG reminder는 "X를 제거하면 X에 의존하는 agent를 orphan
시키지 말 것"을 명시한다.

## 슬라이드 17 — 5. 구현 (Implementation)

코드 트리 1쪽 요약. `src/`에 라이브러리 (llm, graph, orchestrator,
controller, evolve, score, types), `scripts/run_pilot.py`가 단일 드라이버,
`scripts/serve_vllm.sh`가 vLLM 서버 부트 스크립트. 환경 관리는 `uv`,
백본은 Qwen2.5-32B-Instruct를 H200 GPU 한 장에 bf16으로 띄움.
`max_model_len=16384`은 v2의 brief + 멀티-에이전트 tape이 8192를 넘기 때문에
필요. 결과 산출물은 매번 `results/<run_id>/{evolve_log.json, results.json,
plots/}` 형태로 저장된다.

## 슬라이드 18 — 6.1 실험 설정 — 도메인

세 도메인의 성격 비교. **FinanceBench** — 10-K 기업 보고서에서
숫자를 추출해 답하는 QA. GAAP / TTM / 회계연도처럼 financial 어휘에
약하면 헷갈리고, 긴 컨텍스트에서 retrieval이 안 되면 hedging
(애매한 답)으로 빠진다. **MEDIQ** — 임상 vignette을 읽고 객관식 정답을
고르는 task. 감별 진단 + 기본 발생률 (base rate) 사고가 핵심이고,
인구학 (예: 17세 여학생) 단서를 무시하면 틀린다. **AgentClinic** —
single-pass 임상 케이스. 어느 specialty (소화기 / 심장 등)로 routing
할지가 정확도에 직결된다.

## 슬라이드 19 — 6.2 측정 지표 + 노이즈 floor

지표는 (a) test accuracy (held-out test에서의 정답률), (b)
paired-accept rate (streaming에서 ACCEPT된 라운드 / 유효 라운드).
중요한 caveat: 같은 그래프를 두 번 다른 vLLM 인스턴스에서 돌려도
test accuracy가 13pp 가까이 흔들릴 수 있다 (FinanceBench v2 retry 사례).
이 노이즈 floor가 우리가 보려는 architectural 효과와 비슷한 수준이라
n=30 단일 시드 결과로는 유의미한 비교가 어렵다 — 이게 §5.2 다중 시드
sweep이 필요한 이유.

## 슬라이드 20 — Section: 7. 실험 결과

여기서부터 §7. 시간 순으로 calib_01 → v1 n=30 → v2 n=30 → streaming
run #1 → patches sanity → §5.2 ongoing 6 슬라이드.

## 슬라이드 21 — 7.1 calib_01 (GSM8K) — 출발점

가장 처음 50개 샘플로 돌린 GSM8K 실험. Evolved 86% / CoT 92% / P-E 90%.
Evolved가 두 baseline 모두에 *지고* 토큰은 2-3배 더 쓴다. 단순히
"멀티-에이전트가 좋다"는 가설이 깨지는 결과인데, 원인은 GSM8K 자체에
있다 — 단일 모델이 이미 saturate해서 헤드룸이 없고, 텍스트가 self-contained
이라 정보 비대칭이 없으며, 산술이 선형이라 planner/executor 분해가
이득을 못 만든다. 그래서 도메인 피봇 결정.

## 슬라이드 22 — 7.2 v1 controller @ n=30

세 도메인 표. FinanceBench 0pp, MEDIQ +6.7pp (±18pp 노이즈 안), AgentClinic
0pp — 어느 도메인도 baseline을 *명확히* 이기지 못함. 더 중요한 발견은
컨트롤러의 *행동*: FinanceBench에서 같은 `add_verifier` edit을 3 라운드
연속 출력했고, 도메인 어휘가 전무했다. v1 시스템 프롬프트가 너무 얇아서
도메인 헤드룸을 이용하지 못한다는 가설이 굳어진다 — v2 재설계로 이행.

## 슬라이드 23 — 7.3 Controller v2 @ n=30

v2의 행동은 분명히 달라졌다 — `gaap_analyst`, `period_validator`,
`differential_diagnostician`, `adolescent_specialist` 같은 이름의
specialist persona가 등장하고, AgentClinic iter-3은 정식
"triage → 소화기/심장 → answer"의 specialty department 구조까지 제안.
*그러나* test 승리는 일어나지 않았다. FinanceBench가 +10pp로 이긴
것처럼 보이는데, best_graph는 seed (편집 없이 채택)였고 같은 P-E 그래프의
parallel test run보다 13pp 멀어졌다 — 이건 v2의 효과가 아니라 vLLM
배치 순서 / KV 캐시 비결정성에서 오는 cross-run 노이즈. v2 *행동*은
H2 만족, 그러나 *test 승리*는 미달성.

## 슬라이드 24 — 7.4 Streaming run #1 (B=100 R=10 seed=0)

per-round Δ bar chart. 10 라운드 중 4번 ACCEPT (Δ +1, +1, +8, +4),
2번 reject, 4번 INVALID (controller가 그래프 캡 6에 도달했는데도
add_agent를 계속 시도해서 거부, 또는 prune이 다른 agent를 orphan화).
legacy 모드의 1/9 ACCEPT 와 비교하면 *방법이 fire한다*는 첫 실증.
여기서부터 streaming-mode가 본 연구의 가장 강한 차별점이 된다.

## 슬라이드 25 — 7.5 Run #1 — DAG 진화 + token cost

5개 DAG snapshot으로 그래프가 어떻게 자라는지 보여준다 — R0 seed (planner+executor)
→ R1 ACCEPT (+감별 진단 전문가) → R2 ACCEPT (+역학 컨설턴트) →
R4 ACCEPT (+청소년 의학 전문가) → R8 ACCEPT (planner 제거 +
differential_generator 추가). Token 비용 그래프: CoT 0.46k / P-E 0.79k /
Evolved 2.9k tokens per task에 정확도 68% / 58% / 62%. 토큰을 더 쓴다고
정확도가 따라오지 않는다 — 이건 약점으로 정직하게 명시할 부분.

## 슬라이드 26 — 7.6 §5.1.5 patches + sanity, §5.2 ongoing

Streaming run #1에서 발견된 3 blocker (max_agents cap, prune orphan,
concept-level repeat)를 패치한 commit `8405c78` 요약. 검증 sanity
(B=20 R=3 mediq seed=0): r2에서 paired ACCEPT (Δ=+5pp)이 떴고,
`_build_user_prompt` 직접 호출로 새 `# Constraints` 블록이 정상 렌더되는
것을 확인. 다만 R=3에서는 cap-binding과 concept-level anti-repeat이
실제로 fire하지 않아 (배치가 작아서) 이건 §5.2 B=100 R=10 sweep으로
넘어가서 다시 검증한다. 발표 시각 기준 §5.2 MEDIQ seed=1이 진행 중이며
ETA ≈ 16:00 UTC.

## 슬라이드 27 — Section: 8. 분석

여기서부터 §8. 측정 노이즈 + 토큰 비용/실패 모드 두 슬라이드.

## 슬라이드 28 — 8.1 측정 노이즈와 paired-batch의 효과

±13pp same-graph 노이즈는 vLLM의 비결정성에서 온다. legacy 모드에서는
이 노이즈가 cross-batch 비교를 망쳐서 architectural Δ를 reject로 묻어버렸다.
streaming paired-batch는 best와 candidate를 *같은 batch*에 넣어
이 노이즈를 cancel한다. 1/9 → 4/10 ACCEPT 비약은 이 효과의 직접 증거.
다만 절대 정확도는 여전히 bootstrap 분포에 의존하기 때문에,
"best_val_acc > seed_batch_acc" 같은 cross-batch criterion은 streaming에서
*구조적으로* 깨졌다 — 그래서 채점 metric을 test acc + paired-accept
rate로 바꿨다.

## 슬라이드 29 — 8.2 토큰 비용과 실패 모드

Worker 토큰 ≈ 55 × controller 토큰 (run #1 기준 4.03M : 73.7k).
즉 wall-time과 비용은 worker LLM 호출이 좌우한다. B를 키우거나
n_agents를 키우면 wall이 폭발한다. 실패 모드 (run #1 기준):
max_agents=6 cap binding 3건 (다 INVALID), prune이 다른 agent를 orphan
1건, 같은 역할에 다른 이름을 붙여 5라운드 연속 같은 변경을 제안한
concept-level repeat. MAST-style의 정식 실패 taxonomy는 향후 작업.

## 슬라이드 30 — Section: 9. 한계 및 향후 작업

여기서부터 §9. 한계와 향후 두 슬라이드. 정직한 자기 평가가 목적.

## 슬라이드 31 — 9.1 한계 (Limitations)

7가지 약점을 정직하게 나열한다: ① v2 @ n=30이 baseline test를 못
이김. ② ±13pp 노이즈 floor가 architectural 효과를 가림. ③ LLM-judge가
같은 family Qwen이라 self-bias 위험. ④ 단일 backbone, 단일 judge.
⑤ Streaming wall이 9-10시간 × seed × domain → 3×3 sweep이 ~90시간.
⑥ ADAS / MaAS / Puppeteer 직접 baseline 미실시 — reviewer 첫 질문이
될 항목. ⑦ concept-level anti-repeat은 soft constraint 라서 sanity_v3
에서도 fire하지 않았음 (라운드 2가 라운드 1과 동일 edit인데 ACCEPT).
이 7개를 그대로 논문 §6 "Limitations"에 옮길 예정.

## 슬라이드 32 — 9.2 향후 작업 (Future Work)

§5.2-§5.7 로드맵. (1) 다중 시드 streaming sweep (현재 MEDIQ seed=1
진행 중). (2) random-persona ablation — v2 페르소나를 동일 개수의
random 텍스트로 교체해 효과를 격리. (3) harness ablation —
controller {none, random, fixed-topo, full}. (4) 두 번째 백본 (Qwen3-72B
+ Claude/GPT API). (5) LLM-judge를 다른 family로 교체. (6)
**ADAS + (MaAS / Puppeteer / EvoMAC) 직접 baseline** — reviewer 필수
항목이라 이건 비협상.

## 슬라이드 33 — 10. 결론

네 줄 결론: ① reflection-only 멀티-에이전트 진화는 *그래프를 움직이게*
만든다 — v2가 도메인 어휘를 가진 specialist persona를 출력함이 그
증거. ② 그러나 n=30 단일 시드에서는 baseline을 못 이긴다 — 노이즈가
신호를 가린다. ③ streaming paired-batch가 노이즈 floor 문제를 부분
해결한다 — 1/9 → 4/10 ACCEPT 비약. ④ publish 가능한 신호는 paired
ACCEPT activity, 약점은 정직하게 명시; 다음은 다중 시드 / 두 번째 백본
/ ADAS 직접 비교.

## 슬라이드 34 — 감사합니다 / Q&A

발표 종료. 코드와 결과는 github.com/namam3gy의 project repo에 공개되어
있고, 살아있는 로드맵 트래커는 `references/roadmap_ko.md`에서 확인할 수
있다.

---

## 보충 — Novelty가 강한/약한 부분 (논문 §6에 들어갈 자기 평가)

### 강한 (Novelty)
1. **Reflection-only 진화 그 자체** — 기존 ADAS / GPTSwarm / MaAS /
   Puppeteer가 모두 검색이나 학습 신호를 사용하는 것에 반해, 이 연구는
   순수 in-context reflection만 사용한다. *좁은* 슬롯이지만 명확하게
   비어있던 슬롯이다.
2. **Streaming paired-batch evolve mode** — 측정 노이즈가 dominant한
   환경에서 ACCEPT 비율을 의미 있게 올린 알고리즘적 변경. 1/9 → 4/10은
   재현되면 publishable.
3. **Org-designer 컨트롤러 + 도메인 brief** — 같은 backbone이 도메인별로
   다른 전문가처럼 행동하게 만드는 prompt-engineering 기법. v1 → v2의
   행동 변화는 정성적으로 분명하다.

### 약한 (Weaknesses, 정직하게)
1. **n=30에서 test 승리가 없다** — 가장 큰 약점. 다중 시드 sweep으로
   noise-averaged 수치가 나오기 전까지는 "더 잘 된다"는 주장 불가.
2. **단일 backbone / 단일 judge** — reviewer 표준 질문에 대답이 약하다.
3. **ADAS 직접 비교 미실시** — "어떻게 ADAS와 다른가요?"의 자연스러운
   다음 질문 "그래서 ADAS와 비교해서 더 잘 되나요?"에 답이 없다.
4. **soft constraint의 한계** — concept-level anti-repeat이 sanity에서
   fire하지 않았다는 사실은, prompt-engineering으로 강제한 규칙들이
   상황에 따라 무력해질 수 있음을 시사한다. orchestration layer에서
   하드 enforce 하는 것이 다음 단계.
5. **Wall budget** — 3×3 streaming sweep이 ~90시간. 더 큰 backbone 비교나
   ablation을 추가할 때마다 시간이 비례해서 늘어난다.
6. **GSM8K negative result는 narrative entry 일 뿐** — 핵심 결과가 아니라,
   왜 이 도메인 piv가 필요했는지를 설명하는 *이유*로 사용된다.
