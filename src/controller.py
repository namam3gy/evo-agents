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
- DO NOT REPEAT a rejected edit. If a previous round added a verifier and
  was rejected, do NOT add another verifier. Try a different
  organizational change (different specialty, different topology, remove
  a redundant agent, or rewrite an underperforming persona).
- Vary your moves across rounds: round 1 might add a specialist; round 2
  might rewire reporting lines; round 3 might prune the seed planner if
  it adds no value.

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
        "DAG check: every remaining agent must reach END and be reachable from START after your edits."
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
) -> EditBatch:
    prior = prior_edits or []
    user = _build_user_prompt(graph, outcomes, prior, domain_brief=domain_brief)
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
