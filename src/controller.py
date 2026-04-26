from __future__ import annotations

import json
import re
from dataclasses import dataclass

from pydantic import ValidationError

from .datasets import Task
from .graph import describe
from .llm import LLMClient
from .types import EditBatch, Graph, Tape


CONTROLLER_SYSTEM = """You are an ARCHITECTURE CONTROLLER designing a multi-agent
*organization* for a recurring task family. Think of the agent graph as an
**org chart of domain experts** — each agent is a specialist with concrete
expertise, edges are reporting / hand-off lines. Your job is to **redesign
this organization** based on observed performance.

The user prompt provides:
1. A DOMAIN BRIEF describing the task family, common failure modes, and
   useful expertise to draw from.
2. The current graph (agents with personas, edges).
3. Sampled trajectories showing each agent's output and whether the final
   answer was correct.
4. A summary of edits you (or your predecessors) tried in prior rounds.

You edit the system by emitting a JSON object with this exact shape:
{
  "rationale": "<2-4 sentences citing SPECIFIC failure modes from the trajectories or brief that motivate these edits>",
  "edits": [
    {"op": "add_agent", "name": "<id>", "persona": "<DETAILED specialist role prompt>", "inputs": ["task", "<src>.<key>"], "outputs": ["<key>"]},
    {"op": "remove_agent", "name": "<id>"},
    {"op": "rewrite_persona", "name": "<id>", "persona": "<new role prompt>"},
    {"op": "add_edge", "from": "<src>", "to": "<dst>"},
    {"op": "remove_edge", "from": "<src>", "to": "<dst>"}
  ]
}

# Persona authoring rules (the most important part)

A persona MUST cite **specific domain expertise**:
- BAD: "You are a verifier. Check the executor's output for accuracy."
- BAD: "You are a summarizer. Make the answer concise."
- BAD: "You are a critic. Identify any errors."
- GOOD: "You are an internal-medicine attending with 10 years' experience
         in differential diagnosis of vague abdominal complaints. Given a
         patient case, list the top-3 differentials weighted by base rate
         × clinical fit, then commit to the most likely with one-line
         justifications for the rejected alternatives."
- GOOD: "You are a GAAP-trained financial analyst specializing in 10-K
         MD&A interpretation. Given a finance question and SEC filing
         excerpts, first identify the time period and reporting standard
         the question implies, then locate the precise number with units."

A persona MUST describe the agent's task in 2-3 concrete sentences,
including the domain-specific procedure it follows.

Generic role names are FORBIDDEN: do not use "verifier", "checker",
"summarizer", "critic", "reviewer", "validator" as agent names UNLESS
paired with a concrete specialty (e.g., "cardiology_consultant",
"financial_disclosure_auditor", "differential_diagnostician").

# Org-design incentives

- PREFER specialists over generalists. If the brief mentions cardiology,
  pulmonology, GI as relevant — and your trajectories show diagnostic
  errors — add a specialist for the relevant system, not a catch-all
  "verifier".
- ACTIVELY USE remove_agent: if an agent's output was identical to or
  ignored by downstream agents in the trajectories, prune it.
- When you remove an agent X, every agent that consumed X's output AND
  every agent X consumed from must still reach END / be reachable from
  START via the remaining edges. If you prune X, also rewire its
  upstream→downstream as needed in the same edit batch — leaving X's
  ex-downstream with no incoming path silently INVALIDates the round.
- DO NOT REPEAT a rejected edit. If a previous round added a verifier and
  was rejected, do NOT add another verifier. Try a different
  organizational change (different specialty, different topology, remove
  a redundant agent, or rewrite an underperforming persona). The
  string-level rule is concept-level: renaming a "case feature
  extractor" agent across rounds (`differential_generator` →
  `clinical_filter` → `pediatrician`) **counts as a repeat** if the role
  is the same.
- Vary your moves across rounds: round 1 might add a specialist; round 2
  might rewire reporting lines; round 3 might prune the seed planner if
  it adds no value.
- Respect the `max_agents` budget shown in `# Constraints`. If
  `n_agents == max_agents`, do NOT add a new agent — choose
  `remove_agent`, `rewrite_persona`, or topology edits instead.

# Hard structural rules

- Names must be lowercase snake_case. Reserved: START, END.
- The graph must remain a DAG, AND after edits every remaining agent must
  still (a) be reachable from START and (b) be able to reach END.
  The entire batch is silently rejected if violated — wasted iteration.
  * Multiple outgoing edges to END are allowed; you do NOT need to remove
    an existing X->END edge when inserting an agent after X.
  * Safe insertion of a new agent after X:
        add_agent(new_agent)
        add_edge(X, new_agent)
        add_edge(new_agent, END)
    (leave X->END alone — the extra path is harmless).
- Prefer SMALL edits (1-3 per round). Do not rebuild from scratch.
- Output ONLY the JSON object. No prose before or after.
- For agent ops (add_agent, remove_agent, rewrite_persona), the agent
  identifier MUST be in the `name` field — do NOT use `agent`, `target`,
  or `id`. add_agent and rewrite_persona MUST include a non-empty `persona`
  string.
- For edge ops (add_edge, remove_edge), source / destination MUST be in
  `from` and `to` (NOT `src` / `dst`). Both fields MUST be non-empty
  agent names (or START / END).
"""


@dataclass
class Outcome:
    task: Task
    tape: Tape
    correct: int


def _summarize_tape(tape: Tape, correct: int, max_chars: int = 800) -> str:
    chunks = [f"[task {tape.task_id}] correct={bool(correct)}"]
    chunks.append(f"Q: {tape.question[:240]}")
    for s in tape.steps:
        o = s.output.strip().replace("\n", " ")
        if len(o) > max_chars:
            o = o[:max_chars] + " …"
        chunks.append(f"  {s.agent} -> {o}")
    chunks.append(f"FINAL: {tape.final.strip().replace(chr(10), ' ')[:300]}")
    return "\n".join(chunks)


def _build_user_prompt(
    graph: Graph,
    outcomes: list[Outcome],
    prior_edits: list[str],
    domain_brief: str | None = None,
    max_examples: int = 6,
    max_agents: int | None = None,
) -> str:
    acc = sum(o.correct for o in outcomes) / max(1, len(outcomes))
    incorrect = [o for o in outcomes if not o.correct]
    correct = [o for o in outcomes if o.correct]
    show = incorrect[:max_examples]
    if len(show) < max_examples:
        show += correct[: max_examples - len(show)]

    parts: list[str] = []
    if domain_brief and domain_brief.strip():
        parts.append(f"# DOMAIN BRIEF (read first, ground edits in this)\n{domain_brief.strip()}")
    if max_agents is not None:
        n_now = len(graph.agents)
        slack = max_agents - n_now
        slack_msg = (
            f"AT CAP — only `remove_agent`, `rewrite_persona`, or topology edits are allowed."
            if slack <= 0
            else f"{slack} agent slot{'s' if slack != 1 else ''} remaining before the cap."
        )
        parts.append(
            f"# Constraints\n"
            f"max_agents = {max_agents}, current n_agents = {n_now}. {slack_msg}"
        )
    parts.extend([
        f"# Current graph\n{describe(graph)}",
        f"# Train accuracy this iteration: {acc:.2%} ({sum(o.correct for o in outcomes)}/{len(outcomes)})",
        "# Sampled trajectories (incorrect first):",
        *[_summarize_tape(o.tape, o.correct) for o in show],
    ])
    if prior_edits:
        parts.append("# Edits applied in prior rounds (most recent last):")
        parts.extend(prior_edits[-3:])
    parts.append(
        "# Reminder\n"
        "Ground your rationale in the DOMAIN BRIEF and CITE specific tape examples. "
        "Author SPECIALIST personas (per persona authoring rules) — generic verifier/summarizer/critic is forbidden. "
        "If a prior edit was rejected, propose a DIFFERENT TYPE of change (different specialty, prune, rewire). "
        "Concept-level anti-repeat: don't just rename a previously rejected role and re-submit. "
        "DAG check: every remaining agent must reach END and be reachable from START after your edits — "
        "if you `remove_agent`, also rewire its upstream→downstream so the chain stays connected. "
        "Respect the max_agents constraint above."
    )
    parts.append(
        "Now emit the JSON object with your rationale and edits."
    )
    return "\n\n".join(parts)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_edit_batch(text: str) -> EditBatch:
    m = _JSON_RE.search(text)
    if not m:
        raise ValueError("no JSON object found in controller output")
    raw = m.group(0)
    data = json.loads(raw)
    return EditBatch.model_validate(data)


def propose_edits(
    llm: LLMClient,
    graph: Graph,
    outcomes: list[Outcome],
    prior_edits: list[str] | None = None,
    domain_brief: str | None = None,
    temperature: float = 0.7,
    max_agents: int | None = None,
) -> EditBatch:
    prior = prior_edits or []
    user = _build_user_prompt(graph, outcomes, prior, domain_brief=domain_brief, max_agents=max_agents)
    last_err: Exception | None = None
    for attempt in range(2):
        text, _, _ = llm.chat(
            system=CONTROLLER_SYSTEM,
            user=user if attempt == 0 else user + "\n\nPrior attempt produced invalid JSON. Emit ONLY the JSON object.",
            temperature=temperature,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )
        try:
            return _parse_edit_batch(text)
        except (ValueError, json.JSONDecodeError, ValidationError) as e:
            last_err = e
    raise RuntimeError(f"controller failed to emit valid edits: {last_err}")


# ===========================================================================
# v3 — sample-level eval + hierarchical aggregation
# ===========================================================================


CONTROLLER_V3_EVAL_SAMPLE_SYSTEM = """\
You are an architecture controller observing ONE task execution by a multi-agent
graph. Read the trajectory tape and assess whether the current org chart is fit
for THIS sample's question.

You output JSON with this exact shape:
{
  "rationale": "<2-4 sentences citing concrete moments in this tape>",
  "suggested_edits": [
    {"op": "add_agent", "name": "<id>", "persona": "<DETAILED specialist role>",
     "inputs": ["task", "<src>.<key>"], "outputs": ["<key>"]},
    {"op": "remove_agent", "name": "<id>"},
    {"op": "rewrite_persona", "name": "<id>", "persona": "<new role>"},
    {"op": "add_edge", "from": "<src>", "to": "<dst>"},
    {"op": "remove_edge", "from": "<src>", "to": "<dst>"}
  ],
  "priority": <integer 0-100>,
  "target_aspect": "structure" | "role" | "length" | "expertise"
}

Rules:
- 0-3 suggested_edits. May be empty if the graph is fine for this sample.
- priority 0 = current graph is perfectly fine for this sample;
  priority 100 = the graph cannot solve this CLASS of question without these edits.
  Calibrate honestly — your output is one of ~30 evals that will be aggregated.
- target_aspect picks the dimension you're targeting:
  * "structure" — add/remove agents, change edges
  * "role" — change what an agent does
  * "length" — agent outputs too long/short
  * "expertise" — agent persona lacks domain expertise
- Persona authoring follows v2 rules: cited specialty + concrete procedure.
  Generic "verifier", "summarizer", "critic" names are forbidden unless paired
  with a concrete specialty (e.g., "cardiology_consultant").
- Output ONLY the JSON object. No prose before or after.
- For agent ops (add_agent, remove_agent, rewrite_persona), the agent
  identifier MUST be in the `name` field — do NOT use `agent`, `target`,
  or `id`. add_agent and rewrite_persona MUST include a non-empty `persona`
  string.
- For edge ops (add_edge, remove_edge), source / destination MUST be in
  `from` and `to` (NOT `src` / `dst`). Both fields MUST be non-empty
  agent names (or START / END).
"""


CONTROLLER_V3_AGGREGATE_MID_SYSTEM = """\
You receive 10 sample-level evaluations of how the current graph is performing.
Aggregate them into ONE mid-level recommendation.

Synthesize patterns appearing in MULTIPLE samples; do not over-weight a single
priority=100 outlier unless multiple samples corroborate it. Use the priority
score as a guide, not as a vote count.

You output JSON with this exact shape:
{
  "rationale": "<2-4 sentences citing the patterns across the 10 samples>",
  "suggested_edits": [
    {"op": "add_agent" | "remove_agent" | "rewrite_persona" | "add_edge" | "remove_edge", ...}
  ],
  "aggregate_priority": <integer 0-100>
}

Rules:
- 0-3 suggested_edits.
- aggregate_priority reflects how strongly THIS group of 10 endorses change.
- Persona authoring follows v2 rules: cited specialty + concrete procedure.
- Output ONLY the JSON object.
"""


CONTROLLER_V3_AGGREGATE_FINAL_SYSTEM = """\
You receive 3 mid-level decisions, each derived from 10 sample evals on the
SAME train set. Synthesize them into the FINAL EditBatch to apply this
iteration.

Use aggregate_priority to weight the mid-decisions (higher = stronger).
Prefer edits that appear in 2+ mid-decisions.

You output JSON (the standard EditBatch shape) with this exact form:
{
  "rationale": "<2-4 sentences citing which mid-decisions support these edits>",
  "edits": [
    {"op": "add_agent" | "remove_agent" | "rewrite_persona" | "add_edge" | "remove_edge", ...}
  ]
}

Rules:
- 1-3 edits. Small, focused changes.
- Constraints (the runtime ENFORCES max_agents):
  * max_agents = 10 (HARD — the system rejects edits that grow the graph beyond 10).
  * max_edges = 50 (soft — exceeding is allowed but discouraged; large graphs
    are expensive and noisy).
- DAG validity required after edits: every remaining agent must reach END
  and be reachable from START.
- Persona authoring follows v2 rules: cited specialty + concrete procedure.
- Output ONLY the JSON object.
"""


def _summarize_tape_v3(tape: Tape, correct: int, max_chars: int = 800) -> str:
    """Render a tape so the controller sees [SUMMARY] blocks + side queries."""
    chunks = [f"[task {tape.task_id}] correct={bool(correct)}"]
    chunks.append(f"Q: {tape.question[:320]}")
    for s in tape.steps:
        out = s.output.strip().replace("\n", " ")
        if len(out) > max_chars:
            out = out[:max_chars] + " …"
        chunks.append(f"  {s.agent} -> {out}")
        if s.side_query:
            sq = s.side_query
            chunks.append(
                f"    [side-query: {s.agent} → {sq.get('target')}: "
                f"{(sq.get('question') or '')[:160]}]"
            )
            ans = (sq.get("answer") or "").strip().replace("\n", " ")[:200]
            chunks.append(f"    [side-answer: {ans}]")
        if s.summary_block:
            sb = s.summary_block
            chunks.append(
                f"    [summary] claim: \"{sb.get('claim','')}\" | "
                f"evidence: \"{sb.get('evidence','-')}\" | "
                f"confidence: {sb.get('confidence','low')}"
            )
    chunks.append(f"FINAL: {tape.final.strip().replace(chr(10), ' ')[:300]}")
    return "\n".join(chunks)


def _parse_json_object(text: str) -> dict:
    m = _JSON_RE.search(text)
    if not m:
        raise ValueError("no JSON object found in controller output")
    return json.loads(m.group(0))


def _coerce_priority(d: dict, key: str = "priority") -> int:
    v = d.get(key, 0)
    try:
        v = int(v)
    except (TypeError, ValueError):
        v = 0
    return max(0, min(100, v))


def _coerce_edits(raw: list[dict]) -> list[dict]:
    """Pass through edits as plain dicts, normalizing common key aliases.

    Controller LLMs sometimes emit `agent`/`target` instead of `name`, or
    `src`/`from_` instead of `from`. Normalize before downstream consumers
    parse them.
    """
    out: list[dict] = []
    for e in raw or []:
        if not isinstance(e, dict):
            continue
        op = e.get("op")
        if op not in {"add_agent", "remove_agent", "rewrite_persona", "add_edge", "remove_edge"}:
            continue
        normalized = dict(e)  # shallow copy
        # name aliases
        if not normalized.get("name"):
            for alt in ("agent", "target", "agent_name"):
                if normalized.get(alt):
                    normalized["name"] = normalized[alt]
                    break
        # from / to aliases (kept under "from" + "to" for EditBatch model_validate)
        if not normalized.get("from"):
            for alt in ("from_", "src", "source"):
                if normalized.get(alt):
                    normalized["from"] = normalized[alt]
                    break
        if not normalized.get("to"):
            for alt in ("dst", "target_node", "destination"):
                if normalized.get(alt):
                    normalized["to"] = normalized[alt]
                    break
        out.append(normalized)
    return out


def eval_sample(
    llm: LLMClient,
    graph: Graph,
    domain_brief: str | None,
    tape: Tape,
    correct: int,
    *,
    temperature: float = 0.5,
    max_tokens: int = 1200,
) -> dict:
    """Per-sample reflection. Returns {rationale, suggested_edits, priority, target_aspect}."""
    brief_block = (
        f"# DOMAIN BRIEF (read first, ground assessments here)\n{domain_brief.strip()}"
        if domain_brief and domain_brief.strip()
        else "# DOMAIN BRIEF\n(none)"
    )
    user = "\n\n".join([
        brief_block,
        f"# Current graph\n{describe(graph)}",
        f"# This sample's tape\n{_summarize_tape_v3(tape, correct)}",
        "# Reminder\n"
        "Assess THIS sample only. priority=0 if the current graph handled it cleanly; "
        "priority=100 if this entire class of question requires structural change. "
        "Author SPECIALIST personas (cited expertise + procedure); generic "
        "verifier/summarizer is forbidden unless paired with specialty. "
        "Output ONLY the JSON object.",
    ])
    last_err: Exception | None = None
    for attempt in range(2):
        text, _, _ = llm.chat(
            system=CONTROLLER_V3_EVAL_SAMPLE_SYSTEM,
            user=user if attempt == 0 else user + "\n\nPrior attempt produced invalid JSON. Emit ONLY the JSON object.",
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        try:
            data = _parse_json_object(text)
            return {
                "task_id": tape.task_id,
                "rationale": str(data.get("rationale", ""))[:2000],
                "suggested_edits": _coerce_edits(data.get("suggested_edits", [])),
                "priority": _coerce_priority(data, "priority"),
                "target_aspect": str(data.get("target_aspect", "structure"))[:32],
            }
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    # graceful fallback — never raise; per-sample eval shouldn't kill the iter
    return {
        "task_id": tape.task_id,
        "rationale": f"(eval_sample parse failure: {last_err})",
        "suggested_edits": [],
        "priority": 0,
        "target_aspect": "structure",
    }


def _edit_brief(e: dict) -> str:
    """Render one edit dict as a one-line summary, robust to missing fields."""
    op = e.get("op", "?")
    if op in ("add_agent", "remove_agent", "rewrite_persona"):
        return f"{op}({e.get('name') or '?'})"
    if op in ("add_edge", "remove_edge"):
        src = e.get("from") or e.get("from_") or "?"
        dst = e.get("to") or "?"
        return f"{op}({src}->{dst})"
    return f"{op}(?)"


def _format_sample_evals_for_mid(evals: list[dict]) -> str:
    """Render 10 sample-evals into the prompt body, sorted by priority desc."""
    sorted_evals = sorted(evals, key=lambda e: -e.get("priority", 0))
    blocks: list[str] = []
    for ev in sorted_evals:
        edits_brief = ", ".join(_edit_brief(e) for e in ev.get("suggested_edits", [])) or "(none)"
        edits_full = json.dumps(ev.get("suggested_edits", []), ensure_ascii=False)
        if len(edits_full) > 1200:
            edits_full = edits_full[:1200] + " …"
        blocks.append(
            f"[task {ev.get('task_id','?')}  priority={ev.get('priority',0)}  "
            f"target={ev.get('target_aspect','?')}]\n"
            f"  rationale: {ev.get('rationale','')[:600]}\n"
            f"  suggested_edits (brief): {edits_brief}\n"
            f"  suggested_edits (full json): {edits_full}"
        )
    return "\n\n".join(blocks)


def aggregate_mid(
    llm: LLMClient,
    graph: Graph,
    domain_brief: str | None,
    group_evals: list[dict],
    *,
    temperature: float = 0.5,
    max_tokens: int = 1500,
) -> dict:
    """Aggregate one group of (typically 10) sample-evals → one mid_decision."""
    brief_block = (
        f"# DOMAIN BRIEF\n{domain_brief.strip()}"
        if domain_brief and domain_brief.strip()
        else "# DOMAIN BRIEF\n(none)"
    )
    user = "\n\n".join([
        brief_block,
        f"# Current graph\n{describe(graph)}",
        f"# Sample evaluations ({len(group_evals)}, sorted by priority desc):\n"
        f"{_format_sample_evals_for_mid(group_evals)}",
        "# Reminder\n"
        "Synthesize the 10 evals — emphasize patterns across MULTIPLE samples, "
        "use priority as a guide. Output ONLY the JSON object.",
    ])
    last_err: Exception | None = None
    for attempt in range(2):
        text, _, _ = llm.chat(
            system=CONTROLLER_V3_AGGREGATE_MID_SYSTEM,
            user=user if attempt == 0 else user + "\n\nPrior attempt invalid JSON. Emit ONLY the JSON object.",
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        try:
            data = _parse_json_object(text)
            return {
                "rationale": str(data.get("rationale", ""))[:2000],
                "suggested_edits": _coerce_edits(data.get("suggested_edits", [])),
                "aggregate_priority": _coerce_priority(data, "aggregate_priority"),
            }
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    return {
        "rationale": f"(aggregate_mid parse failure: {last_err})",
        "suggested_edits": [],
        "aggregate_priority": 0,
    }


def _format_mid_decisions_for_final(mids: list[dict]) -> str:
    sorted_mids = sorted(mids, key=lambda m: -m.get("aggregate_priority", 0))
    blocks: list[str] = []
    for i, m in enumerate(sorted_mids):
        edits_brief = ", ".join(_edit_brief(e) for e in m.get("suggested_edits", [])) or "(none)"
        edits_full = json.dumps(m.get("suggested_edits", []), ensure_ascii=False)
        if len(edits_full) > 1500:
            edits_full = edits_full[:1500] + " …"
        blocks.append(
            f"[Mid {i}  aggregate_priority={m.get('aggregate_priority',0)}]\n"
            f"  rationale: {m.get('rationale','')[:800]}\n"
            f"  suggested_edits (brief): {edits_brief}\n"
            f"  suggested_edits (full json): {edits_full}"
        )
    return "\n\n".join(blocks)


def aggregate_final(
    llm: LLMClient,
    graph: Graph,
    domain_brief: str | None,
    mid_decisions: list[dict],
    *,
    max_agents: int = 10,
    max_edges: int = 50,
    temperature: float = 0.5,
    max_tokens: int = 1500,
) -> EditBatch:
    """Aggregate mid_decisions → final EditBatch (legacy schema)."""
    brief_block = (
        f"# DOMAIN BRIEF\n{domain_brief.strip()}"
        if domain_brief and domain_brief.strip()
        else "# DOMAIN BRIEF\n(none)"
    )
    n_now = len(graph.agents)
    n_edges = len(graph.edges)
    constraints = (
        f"# Constraints\n"
        f"max_agents = {max_agents} (HARD), current n_agents = {n_now}.\n"
        f"max_edges  = {max_edges} (soft, prompt-only), current n_edges = {n_edges}."
    )
    user = "\n\n".join([
        brief_block,
        constraints,
        f"# Current graph\n{describe(graph)}",
        f"# Mid-level decisions ({len(mid_decisions)}, sorted by aggregate_priority desc):\n"
        f"{_format_mid_decisions_for_final(mid_decisions)}",
        "# Reminder\n"
        "Output the FINAL EditBatch (1-3 edits). Prefer edits supported by 2+ mid-decisions. "
        "DAG validity required: every remaining agent reachable from START + must reach END. "
        "Output ONLY the JSON object.",
    ])
    last_err: Exception | None = None
    for attempt in range(2):
        text, _, _ = llm.chat(
            system=CONTROLLER_V3_AGGREGATE_FINAL_SYSTEM,
            user=user if attempt == 0 else user + "\n\nPrior attempt invalid JSON. Emit ONLY the JSON object.",
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        try:
            return _parse_edit_batch(text)
        except (ValueError, json.JSONDecodeError, ValidationError) as e:
            last_err = e
    raise RuntimeError(f"aggregate_final failed to emit valid edits: {last_err}")
