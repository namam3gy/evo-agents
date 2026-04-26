# Controller v3 — design spec

**Date**: 2026-04-26
**Status**: design approved (in conversation), implementation pending
**Motivation**: v2 controller at n=30 + streaming run #1 / #2 do not show a clean
test-set win over baselines (paired Δ = +4pp Evolved − P-E in both seeds is the
strongest signal so far, but absolute numbers tie or trail CoT at the noise floor).
This spec defines a denser reflection mechanism + a side-channel Q&A capability
on the worker DAG, replacing the streaming evolve mode for §5.2.

This document is an **English-canonical spec**. A Korean mirror should be added
at `docs/specs/2026-04-26-controller-v3-design_ko.md` once the implementation
plan is committed.

---

## 1. Top-level decisions

| # | Knob | Choice |
|---|---|---|
| 1 | Mode | **Replace streaming** with a new `evolve_v3()` (legacy-style full-pass per iter) |
| 2 | Accept rule | `train_acc(candidate) > train_acc(best)` — strict |
| 3 | Conversation channel | **W-2** — keep `agent.inputs` wiring, add a separate "Conversation so far" prefix |
| 4 | Conversation schema | **S-2** — each agent emits `[SUMMARY] claim / evidence / confidence [/SUMMARY]` |
| 5 | Side-channel Q&A | **Q-3 prompt-driven** — instruction in the node's prompt, 1–3 LLM calls/node |
| 6 | Sample-level eval input | **I-2** — current graph + domain brief + this sample's tape (no prior evals) |
| 7 | Sample-level eval output | **O-2** — `{rationale, suggested_edits, priority: 0-100, target_aspect}` |
| 8 | Aggregation | **M-A** — same schema across mid + final, sample evals sorted by priority high→low |
| 9 | `max_iters` | **10** |
| 10 | `max_agents` | **10 (hard)** — `apply_edits` enforces, INVALID on violation |
| 11 | `max_edges` | **50 (soft)** — surfaced in prompt only |
| 12 | Mid-iter visibility | **per-iter dump** — `results/<run_id>/iter_K/` containing `evals.jsonl`, `mid_decisions.json`, `final_edit.json`, `train_eval.json`, `evolve_state.json` |

---

## 2. Per-iter data flow (one iter inside `evolve_v3()`)

```
────────────────────────────────────────────────────────────────────────────────
[Iter k]
1. (Optional) refresh train set order — same n_train tasks every iter (deterministic).

2. Run `best_graph` on the full train set:
   for each task in train:
       tape = run_graph_v3(best_graph, task, llm)            ← uses Q&A + transcript
       sample_eval = controller.eval_sample(
           graph=best_graph,
           brief=domain_brief,
           tape=tape,
       )                                                     ← I-2 input, O-2 output
       evals_jsonl.append(sample_eval)
       train_correct += score(tape.final, task)
   train_acc(best) = train_correct / n_train

3. Hierarchical aggregation:
   sort sample_evals by priority desc
   group_size = 10
   mid_decisions = []
   for i in range(0, len(evals), group_size):
       group = sample_evals[i : i + group_size]
       mid = controller.aggregate_mid(graph=best_graph, brief, group)
       mid_decisions.append(mid)
   final_edit_batch = controller.aggregate_final(
       graph=best_graph, brief, mid_decisions, max_agents=10, max_edges=50
   )

4. Apply final_edit_batch to best_graph:
   try:
       candidate_graph = apply_edits(best_graph, final_edit_batch, max_agents=10)
   except GraphEditError as e:
       record INVALID, skip step 5–6, advance iter

5. Run candidate_graph on the SAME train set (same task order) → train_acc(candidate).

6. Accept rule (strict):
       if train_acc(candidate) > train_acc(best): best_graph = candidate
       else:                                       reject

7. Dump per-iter artifacts to results/<run_id>/iter_K/
────────────────────────────────────────────────────────────────────────────────
```

`max_iters = 10`, so the loop runs 10 times (or stops early if no edits fire).

After the loop ends, the final test eval (CoT / P-E / Evolved on the held-out
test set) runs as in legacy mode.

---

## 3. Worker DAG changes (`run_graph_v3`)

### 3.1 Conversation transcript channel (W-2 + S-2)

`agent.inputs` wiring **stays unchanged**. In addition, the orchestrator builds
a separate "Conversation so far" block by parsing `[SUMMARY]` blocks from each
prior agent's output and prepending it to every subsequent agent's user prompt.

Per-agent forced output schema (controller v3 system prompt enforces this on
every agent persona it authors; seed `planner` and `executor` are also updated):

```
<main response — agent's actual reasoning / answer to the task>

[SUMMARY]
claim: <one sentence: the agent's main conclusion or decision>
evidence: <one sentence: what data / reasoning supports this>
confidence: low | medium | high
[/SUMMARY]
```

The orchestrator regex-extracts the block. If an agent fails to emit one, the
orchestrator records `claim: <truncated last sentence>, evidence: -, confidence: low`
as a fallback (no INVALID — the iter still proceeds).

The "Conversation so far" prefix on agent N's prompt looks like:

```
[Conversation so far]
- planner — claim: "4-step plan, final answer = B" | evidence: "step-by-step from symptoms" | confidence: medium
- differential_diagnostician — claim: "Top differential = bulimia nervosa" | evidence: "17yo female + behavior concerns" | confidence: high
```

### 3.2 Side-channel Q&A (Q-3 prompt-driven)

A standard instruction is appended to **every** worker prompt (system or user
side):

```
You may call ONE other agent in this graph for a clarifying question.
Other agents available:
  - planner: <persona snippet, ~80 chars>
  - executor: <persona snippet, ~80 chars>
  - differential_diagnostician: <persona snippet, ~80 chars>
  ...

To call, output exactly one line:
    [QUERY <agent_name>] <your question, one sentence>
Then STOP your output. The system will fetch the answer and resume your turn.
If you do not need to query, just produce your answer directly.

You may call AT MOST ONE agent (no recursion — answers will not query further).
```

LLM call sequence per node:

1. **Call A** (main, with stop-token-style detection): generate up to `max_tokens`.
   - If the output contains `[QUERY <name>] ...` (stop here), parse `name` and `question`.
2. **Call B** (lite-mode answer fetch, only if QUERY was issued):
   ```
   system = target_node.persona
   user   = f"You are answering a clarifying question from {asking_agent}.
             Provide a brief, factual answer in 1–3 sentences.
             Do NOT query other agents.
             Question: {question}"
   max_tokens = 256
   ```
3. **Call C** (resume main, only if QUERY was issued): re-issue Call A's prompt
   with the answer appended:
   ```
   <Call A prompt>
   <Call A output up to and including [QUERY ...]>
   [ANSWER from <target>]: <Call B output>
   Now continue your reasoning and produce your final answer.
   ```

So per node the worker cost is **1 call** (no QUERY) or **3 calls** (QUERY
fired). Average expected ≈ 2 calls/node → ~2× the legacy worker cost.

Hard rules:
- Answering agent may not query (Call B prompt forbids it).
- Maximum one QUERY per node per task (tracked by orchestrator).
- If LLM emits malformed `[QUERY ...]`, treat as no query and use Call A output as-is.

### 3.3 Recording in the tape

Each `AgentStep` gains optional fields:

```python
@dataclass
class AgentStep:
    agent: str
    prompt: str
    output: str
    prompt_tokens: int
    completion_tokens: int
    summary_block: dict | None = None         # parsed [SUMMARY] {claim, evidence, confidence}
    side_query: dict | None = None            # {target, question, answer} when QUERY fired
```

These are written into `evolve_log.json` per iteration so the controller
sample-level eval (next section) can read them.

---

## 4. Controller v3 — three call types

The controller LLM is invoked three times per iter (per sample, mid, final),
each with its own system + user prompt template.

### 4.1 `controller.eval_sample(graph, brief, tape)`

**Input**: current graph description, full domain brief, one full tape
(question + every agent's main output + their `[SUMMARY]` block + any
`side_query` records).

**System prompt** (fixed):

```
You are an architecture controller observing one task execution by a multi-agent
graph. Read the trajectory tape and assess whether the current org chart is fit
for THIS sample's question.

You output:
  - rationale: 2-4 sentences citing concrete moments in this tape
  - suggested_edits: 0-3 candidate edit operations (same schema as
    propose_edits — add_agent / remove_agent / rewrite_persona / add_edge /
    remove_edge); when you author personas, follow the v2 specialist rules
    (cited expertise + procedure)
  - priority: 0–100 — how strongly you want the suggested edits applied
    (0 = current graph is fine for this sample; 100 = the graph cannot solve
    this class of question without these edits)
  - target_aspect: "structure" | "role" | "length" | "expertise" — what
    dimension you're targeting

The graph WILL NOT be edited based on a single sample. Your output is one of
~30 evals that will be aggregated. Be honest about priority — calibrate.
```

**Output JSON schema**:

```json
{
  "rationale": "...",
  "suggested_edits": [
    {"op": "add_agent", "name": "...", "persona": "...", "inputs": [...], "outputs": [...]},
    ...
  ],
  "priority": 0,
  "target_aspect": "structure"
}
```

Stored as one JSONL line in `results/<run_id>/iter_K/evals.jsonl` per task.

### 4.2 `controller.aggregate_mid(graph, brief, group_of_10_evals)`

**Input**: 10 sample-evals (sorted high→low by priority before serialization).

**System prompt**:

```
You receive 10 sample-level evaluations of how the current graph is performing.
Aggregate them into ONE mid-level recommendation.

Synthesize patterns appearing in MULTIPLE samples; do not over-weight a single
priority=100 outlier unless multiple samples corroborate it. Use the priority
score as a guide, not as a vote count.
```

**Output JSON schema** (intentionally same shape as sample-eval, minus
`target_aspect`):

```json
{
  "rationale": "...",
  "suggested_edits": [...],
  "aggregate_priority": 0
}
```

3 mid_decisions are produced per iter (n_train=30 / 10 = 3).

### 4.3 `controller.aggregate_final(graph, brief, mid_decisions, max_agents=10, max_edges=50)`

**Input**: 3 mid_decisions (sorted by aggregate_priority desc).

**System prompt**:

```
You receive 3 mid-level decisions, each derived from 10 sample evals, on the
same train set. Synthesize them into the FINAL EditBatch to apply this
iteration.

Constraints:
- max_agents = 10 (HARD — the system rejects edits that grow the graph
  beyond 10 agents).
- max_edges = 50 (soft — exceeding this is allowed but discouraged; large
  graphs are expensive and noisy).
- DAG validity required after edits.
- Output 1–3 edits — small, focused changes.
```

**Output JSON schema** (= legacy `EditBatch`):

```json
{
  "rationale": "...",
  "edits": [...]
}
```

Applied via `apply_edits(best_graph, final_batch, max_agents=10)`.

---

## 5. Per-iter dump format (`results/<run_id>/iter_K/`)

```
results/<run_id>/iter_K/
├── evals.jsonl              # one line per train task = sample-eval (O-2 schema)
├── mid_decisions.json       # list of 3 mid-decision objects
├── final_edit.json          # the EditBatch applied (or {"rationale": ..., "edits": []} on INVALID)
├── train_eval.json          # {"best": {"acc": ..., "n_correct": ..., "n_tasks": ...},
│                            #  "candidate": {... or null on INVALID}}
└── evolve_state.json        # {"iter": K, "best_graph": {...}, "accepted": bool,
                             #  "edits_applied": [...], "verdict": "ACCEPT|reject|INVALID"}
```

The user can `tail -f results/<run_id>/iter_K/evals.jsonl` mid-run for live
visibility — each line is appended atomically as samples complete.

A top-level `results/<run_id>/evolve_log.json` accumulates a thin index of
all iters (mode, config, iter list with verdicts and acc, best_graph at end).

---

## 6. CLI / orchestration

`scripts/run_pilot.py` gains `--mode v3`:

```
uv run python scripts/run_pilot.py \
  --benchmark mediq \
  --mode v3 \
  --n-train 30 --n-val 0 --n-test 50 \
  --max-iters 10 \
  --max-agents 10 \
  --max-edges 50 \
  --seed 0 \
  --run-name v3_mediq_s0
```

Notes:
- `--n-val` is unused in v3 (accept rule is on train; val held out).
- `--max-rounds`, `--batch-size`, `--accept-epsilon` are streaming-mode
  flags and remain ignored in v3.
- `--max-edges` is a new arg, default 50, threaded only into prompts (soft).

---

## 7. Wall-clock estimate

Per iter (n_train = 30, average 4–6 agents in graph, with Q&A):

| Stage | Calls | Wall (rough) |
|---|---:|---:|
| best train pass (30 × n_agents × ~2 calls/node) | ~360 worker calls | ~30 min |
| sample-level controller evals (30) | 30 controller calls | ~5 min |
| mid + final aggregation | 4 controller calls | <1 min |
| candidate train pass | ~360 worker calls | ~30 min |
| **Iter total** | | **~70 min** |
| **10 iters** | | **~12 h / run** |

(About 1.2× streaming run #1's 9h45m, at significantly higher reflection
density per token.)

---

## 8. What does NOT change

- `data/briefs/{financebench,mediq,agentclinic}.md` — same as v2.
- `src/score.py` — no change.
- `src/baselines.py::cot_graph()` — no change (CoT is a single-agent
  baseline, no Q&A possible).
- `src/baselines.py::planner_executor_graph()` — `planner` and `executor`
  personas updated to emit `[SUMMARY]` blocks.
- legacy `evolve()` and `evolve_streaming()` — kept untouched, accessible
  via `--mode legacy|streaming` for ablation / reruns of run #1, run #2.
- Test eval loop (CoT / P-E / Evolved on held-out test) — same.
- `references/roadmap.md` §5.2 sweep plan — *needs update* once v3 lands
  (sweep becomes "v3 multi-seed" instead of "v2 streaming multi-seed").

---

## 9. Implementation breakdown (rough)

1. `src/types.py` — extend `AgentStep` with `summary_block`, `side_query`.
2. `src/orchestrator.py` — add `run_graph_v3()` with W-2 transcript + Q&A
   3-call sequence. Keep `run_graph()` (legacy) intact.
3. `src/controller.py` — add `CONTROLLER_V3_SYSTEM_*` (3 prompts), and
   `eval_sample()` / `aggregate_mid()` / `aggregate_final()` functions.
4. `src/baselines.py` — update `planner` / `executor` personas to emit
   `[SUMMARY]`.
5. `src/evolve.py` — add `evolve_v3()` per §2 flow, with per-iter dump.
6. `scripts/run_pilot.py` — `--mode v3`, `--max-edges`, run-name plumb.
7. (Optional) `scripts/analyze_v3.py` — read `evals.jsonl` + `evolve_state.json`
   sequence, produce a v3-specific read-out (per-iter accept/reject, priority
   distribution, target_aspect distribution).

Sanity validation (B=5 R=1 mediq) before launching the full v3 sweep:
- Smoke that `run_graph_v3` parses `[SUMMARY]` correctly and the Q&A 3-call
  sequence resolves on a tiny n=3.
- Smoke that 1 iter of `evolve_v3` writes the expected `iter_0/` artifacts.

---

## 10. Open risks (carry to limitations / future work)

1. **Sample-level eval is high-variance**. One sample's tape can read
   noisy as architectural feedback (same structural risk as the broken
   `best_val_acc > seed_batch_acc` in §8.4). Hierarchical aggregation
   *meant* to mitigate this — but only if `aggregate_mid` actually
   cross-references samples rather than concatenating. Worth checking
   in v3 sanity.
2. **Concept-level repeat is still soft**. The new design adds priority
   weighting but does not fundamentally prevent the controller from
   suggesting the same role with a different name across iterations.
   Consider an orchestration-layer concept-tag dictionary as future work.
3. **Wall budget**. ~12 h per run × 3 seeds × 3 domains = 108 h sweep.
   D-31 to EMNLP 2026 ARR (2026-05-25). Tight. Plan to run MEDIQ first
   and decide whether to abbreviate seeds=2 to seed=2-only after MEDIQ
   results.
4. **Max_agents=10 hard cap may bind**. v2 streaming run #1 hit cap=6 in
   3 of 4 INVALIDs; raising to 8 helped but R=4 still saw cap binding.
   Ten may be tight for triage + 2-3 specialty + answer chains in
   AgentClinic. Surface in iter dump and re-evaluate.
5. **Q&A fidelity**. Three-call sequence depends on the LLM's adherence
   to `[QUERY]` token convention. Plan a smoke that measures `[QUERY]`
   parse rate ≥ 95% on n=10 before trusting v3 numbers.

---

*Spec author: thyun.park (with Claude). Conversation reference: 2026-04-26
session, brainstorming → forks (B / accept rule 2 / Q-3 / I-2 / O-2 / W-2 /
S-2 / max_iters=10 / max_agents=10 hard / max_edges=50 soft).*
