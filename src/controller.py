from __future__ import annotations

import json
import re
from dataclasses import dataclass

from pydantic import ValidationError

from .datasets import Task
from .graph import describe
from .llm import LLMClient
from .types import EditBatch, Graph, Tape


CONTROLLER_SYSTEM = """You are an ARCHITECTURE CONTROLLER for a multi-agent system.
Your job is to read a batch of trajectories produced by the CURRENT agent graph
and propose a small number of edits that will improve accuracy on the TASK FAMILY.

You edit the system by emitting a JSON object with this exact shape:
{
  "rationale": "<why these edits>",
  "edits": [
    {"op": "add_agent", "name": "<id>", "persona": "<role prompt>", "inputs": ["task", "<src>.<key>"], "outputs": ["<key>"]},
    {"op": "remove_agent", "name": "<id>"},
    {"op": "rewrite_persona", "name": "<id>", "persona": "<new role prompt>"},
    {"op": "add_edge", "from": "<src>", "to": "<dst>"},
    {"op": "remove_edge", "from": "<src>", "to": "<dst>"}
  ]
}

Hard rules:
- Names must be lowercase snake_case. Reserved: START, END.
- The graph must remain a DAG. Every agent must be reachable from START and reach END.
- Prefer SMALL edits (1-3 per round). Do not rebuild the graph from scratch.
- Propose architectural change that would fix observed failures. Examples of useful
  patterns: add a verifier/critic that checks the executor's arithmetic; split a
  monolithic solver into decomposer + arithmetic specialist; add a reformulator
  that rewrites the question; remove agents whose outputs never influence END.
- Do NOT merely reword an existing persona unless you point to a specific failure
  mode that the reword addresses.
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
    max_examples: int = 6,
) -> str:
    acc = sum(o.correct for o in outcomes) / max(1, len(outcomes))
    incorrect = [o for o in outcomes if not o.correct]
    correct = [o for o in outcomes if o.correct]
    show = incorrect[:max_examples]
    if len(show) < max_examples:
        show += correct[: max_examples - len(show)]

    parts = [
        f"# Current graph\n{describe(graph)}",
        f"# Train accuracy this iteration: {acc:.2%} ({sum(o.correct for o in outcomes)}/{len(outcomes)})",
        "# Sampled trajectories (incorrect first):",
        *[_summarize_tape(o.tape, o.correct) for o in show],
    ]
    if prior_edits:
        parts.append("# Edits applied in prior rounds (most recent last):")
        parts.extend(prior_edits[-3:])
    parts.append(
        "Now emit the JSON object with your rationale and edits. "
        "Focus on what will reduce the observed errors."
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
    temperature: float = 0.7,
) -> EditBatch:
    prior = prior_edits or []
    user = _build_user_prompt(graph, outcomes, prior)
    last_err: Exception | None = None
    for attempt in range(2):
        text, _, _ = llm.chat(
            system=CONTROLLER_SYSTEM,
            user=user if attempt == 0 else user + "\n\nPrior attempt produced invalid JSON. Emit ONLY the JSON object.",
            temperature=temperature,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
        try:
            return _parse_edit_batch(text)
        except (ValueError, json.JSONDecodeError, ValidationError) as e:
            last_err = e
    raise RuntimeError(f"controller failed to emit valid edits: {last_err}")
