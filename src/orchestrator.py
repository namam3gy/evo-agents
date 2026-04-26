from __future__ import annotations

import re

from .datasets import Task
from .graph import topological_order
from .llm import LLMClient
from .types import END, START, AgentStep, Graph, Tape


def _format_inputs(
    agent_name: str,
    agent_inputs: list[str],
    task: Task,
    context: dict[str, dict[str, str]],
) -> str:
    parts: list[str] = [f"Task:\n{task.question}"]
    for spec in agent_inputs:
        if spec == "task":
            continue
        if "." not in spec:
            continue
        src, key = spec.split(".", 1)
        val = context.get(src, {}).get(key) or context.get(src, {}).get("output")
        if val is None:
            continue
        parts.append(f"From {src} ({key}):\n{val}")
    return "\n\n".join(parts)


def _parse_agent_output(text: str, agent_outputs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {"output": text.strip()}
    for key in agent_outputs:
        out[key] = text.strip()
    return out


def run_graph(
    graph: Graph,
    task: Task,
    llm: LLMClient,
    temperature: float = 0.2,
    max_tokens: int = 768,
) -> Tape:
    order = topological_order(graph)
    tape = Tape(task_id=task.task_id, question=task.question)
    context: dict[str, dict[str, str]] = {START: {"task": task.question, "output": task.question}}

    for name in order:
        agent = graph.agents[name]
        prompt = _format_inputs(name, agent.inputs, task, context)
        text, pt, ct = llm.chat(
            system=agent.persona,
            user=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        tape.steps.append(
            AgentStep(agent=name, prompt=prompt, output=text, prompt_tokens=pt, completion_tokens=ct)
        )
        context[name] = _parse_agent_output(text, agent.outputs)

    end_preds = graph.predecessors(END)
    if end_preds:
        last = end_preds[-1]
        tape.final = context.get(last, {}).get("output", "")
    elif tape.steps:
        tape.final = tape.steps[-1].output
    return tape


# ---------------------------------------------------------------------------
# v3 — conversation transcript channel (W-2) + side-channel Q&A (Q-3 prompt-driven)
# ---------------------------------------------------------------------------

_SUMMARY_RE = re.compile(
    r"\[SUMMARY\](.*?)\[/SUMMARY\]", re.DOTALL | re.IGNORECASE
)
_SUMMARY_FIELD_RE = re.compile(
    r"^\s*(claim|evidence|confidence)\s*:\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_QUERY_RE = re.compile(
    r"\[QUERY\s+([a-zA-Z0-9_]+)\]\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)


def _parse_summary_block(text: str) -> dict | None:
    """Parse the [SUMMARY] block at the end of an agent's main response.

    Returns {"claim": ..., "evidence": ..., "confidence": ...} or None on miss.
    """
    m = _SUMMARY_RE.search(text)
    if not m:
        return None
    body = m.group(1)
    fields: dict[str, str] = {}
    for fm in _SUMMARY_FIELD_RE.finditer(body):
        key = fm.group(1).lower().strip()
        val = fm.group(2).strip()
        fields[key] = val
    if not fields.get("claim"):
        return None
    # Normalize confidence to one of {low, medium, high}; fall back to "low" if missing/odd.
    conf = fields.get("confidence", "low").lower()
    if conf not in {"low", "medium", "high"}:
        conf = "low"
    return {
        "claim": fields["claim"],
        "evidence": fields.get("evidence", "-"),
        "confidence": conf,
    }


def _fallback_summary(text: str) -> dict:
    """Build a fallback summary when the agent forgot to emit [SUMMARY]."""
    cleaned = text.strip().replace("\n", " ")
    last_sentence = cleaned.rsplit(".", 2)[-2 if "." in cleaned else -1]
    last_sentence = last_sentence.strip()[:240] if last_sentence else cleaned[:240]
    return {"claim": last_sentence or "(no summary emitted)", "evidence": "-", "confidence": "low"}


def _strip_summary(text: str) -> str:
    """Remove the [SUMMARY] block from agent output for downstream display."""
    return _SUMMARY_RE.sub("", text).rstrip()


def _parse_query(text: str) -> tuple[str, str] | None:
    """Detect a [QUERY <agent>] <question> directive in the agent output."""
    m = _QUERY_RE.search(text)
    if not m:
        return None
    target = m.group(1).strip()
    question = m.group(2).strip()
    return target, question


def _build_transcript_block(steps_so_far: list[AgentStep]) -> str:
    """Build the 'Conversation so far' block from prior agents' parsed [SUMMARY]."""
    if not steps_so_far:
        return ""
    lines: list[str] = ["[Conversation so far]"]
    for step in steps_so_far:
        sb = step.summary_block or _fallback_summary(step.output)
        lines.append(
            f"- {step.agent} — claim: \"{sb['claim']}\" "
            f"| evidence: \"{sb['evidence']}\" | confidence: {sb['confidence']}"
        )
    return "\n".join(lines)


def _build_other_agents_block(graph: Graph, current_name: str) -> str:
    parts = ["Other agents in this graph (you may call ONE for a clarifying question):"]
    for name, agent in graph.agents.items():
        if name == current_name:
            continue
        snippet = agent.persona.strip().splitlines()[0][:90]
        parts.append(f"  - {name}: {snippet}")
    return "\n".join(parts)


_QA_INSTRUCTION = (
    "You may call ONE other agent in this graph for a clarifying question (or skip).\n"
    "To call, output exactly one line in this format:\n"
    "    [QUERY <agent_name>] <your question, one sentence>\n"
    "Then STOP your output. The system will fetch the answer and resume your turn.\n"
    "If you do not need to query, just produce your answer directly.\n"
    "You may call AT MOST ONE agent (no recursion — answers will not query further)."
)

_SUMMARY_INSTRUCTION = (
    "At the end of your response, ALWAYS emit a structured summary block:\n"
    "[SUMMARY]\n"
    "claim: <one sentence: your main conclusion or decision>\n"
    "evidence: <one sentence: what data / reasoning supports this>\n"
    "confidence: low | medium | high\n"
    "[/SUMMARY]"
)


def _run_node_with_qa(
    graph: Graph,
    name: str,
    base_user_prompt: str,
    transcript: str,
    llm: LLMClient,
    temperature: float,
    max_tokens: int,
) -> AgentStep:
    """Run one agent node with conversation-transcript prefix + side-channel Q&A.

    LLM call sequence:
      A. Main call with stop=['[/QUERY]'] — agent may emit [QUERY <name>] <q>
         (parser also tolerates absence of the closing tag).
      B. If QUERY fired: lite-mode answer call to the target agent (no recursion).
      C. Resume the asking agent with the answer appended.

    Returns a single AgentStep capturing the FINAL main output (transcript-relevant),
    along with parsed summary_block and side_query metadata.
    """
    agent = graph.agents[name]

    # Build the user prompt: base inputs + transcript block + Q&A + summary instructions
    sections = [base_user_prompt]
    if transcript:
        sections.append(transcript)
    sections.append(_build_other_agents_block(graph, name))
    sections.append(_QA_INSTRUCTION)
    sections.append(_SUMMARY_INSTRUCTION)
    user_prompt = "\n\n".join(sections)

    # --- Call A: main, stop on [/QUERY] OR end of [SUMMARY] block
    call_a_text, pt_a, ct_a = llm.chat(
        system=agent.persona,
        user=user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        stop=["[/QUERY]", "[/SUMMARY]"],
    )
    pt_total, ct_total = pt_a, ct_a
    side_query: dict | None = None

    qa = _parse_query(call_a_text)
    final_text = call_a_text

    if qa is not None and qa[0] in graph.agents and qa[0] != name:
        target, question = qa
        # --- Call B: lite-mode answer fetch
        target_persona = graph.agents[target].persona
        ans_user = (
            f"You are answering a clarifying question from agent `{name}` while it works on a task.\n"
            f"Provide a brief, factual answer in 1-3 sentences.\n"
            f"DO NOT query other agents (no recursion).\n\n"
            f"Question from {name}: {question}"
        )
        ans_text, pt_b, ct_b = llm.chat(
            system=target_persona,
            user=ans_user,
            temperature=temperature,
            max_tokens=256,
        )
        pt_total += pt_b
        ct_total += ct_b
        side_query = {"target": target, "question": question, "answer": ans_text.strip()}

        # --- Call C: resume asking agent with the answer in context
        # The Call A text was cut at [/QUERY] (if stop fired) or wherever LLM stopped.
        partial = call_a_text.rstrip()
        # If LLM included the closing tag inline, drop it; the stop param strips it as well.
        partial = partial.split("[/QUERY]")[0].rstrip()
        resume_user = (
            f"{user_prompt}\n\n"
            f"--- Your output so far ---\n"
            f"{partial}\n"
            f"[/QUERY]\n\n"
            f"[ANSWER from {target}]: {ans_text.strip()}\n\n"
            f"Now continue your reasoning and produce your final answer "
            f"(remember the [SUMMARY] block at the end)."
        )
        cont_text, pt_c, ct_c = llm.chat(
            system=agent.persona,
            user=resume_user,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=["[/SUMMARY]"],
        )
        pt_total += pt_c
        ct_total += ct_c
        # Stitch: keep the partial (sans [QUERY ...] line for cleanliness) + continuation
        final_text = (partial + "\n\n" + cont_text).strip()

    # If LLM stopped at [/SUMMARY], re-append the closer for downstream parsing
    if "[SUMMARY]" in final_text and "[/SUMMARY]" not in final_text:
        final_text = final_text + "\n[/SUMMARY]"

    summary_block = _parse_summary_block(final_text)

    return AgentStep(
        agent=name,
        prompt=user_prompt,
        output=final_text,
        prompt_tokens=pt_total,
        completion_tokens=ct_total,
        summary_block=summary_block,
        side_query=side_query,
    )


def run_graph_v3(
    graph: Graph,
    task: Task,
    llm: LLMClient,
    temperature: float = 0.2,
    max_tokens: int = 768,
) -> Tape:
    """v3 worker pass: keeps agent.inputs wiring, adds transcript channel + Q&A.

    Each agent receives the standard `_format_inputs` block, plus a
    "Conversation so far" prefix built from prior agents' parsed [SUMMARY]
    blocks (W-2 + S-2). Each agent may issue ONE side-channel [QUERY <agent>]
    before producing its main answer (Q-3 prompt-driven).
    """
    order = topological_order(graph)
    tape = Tape(task_id=task.task_id, question=task.question)
    context: dict[str, dict[str, str]] = {START: {"task": task.question, "output": task.question}}

    for name in order:
        base_prompt = _format_inputs(name, graph.agents[name].inputs, task, context)
        transcript = _build_transcript_block(tape.steps)
        step = _run_node_with_qa(
            graph,
            name,
            base_prompt,
            transcript,
            llm,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        tape.steps.append(step)
        # downstream agents see the cleaned (no [SUMMARY]) main response in context
        clean_out = _strip_summary(step.output)
        ctx_entry = {"output": clean_out}
        for k in graph.agents[name].outputs:
            ctx_entry[k] = clean_out
        context[name] = ctx_entry

    end_preds = graph.predecessors(END)
    if end_preds:
        last = end_preds[-1]
        tape.final = context.get(last, {}).get("output", "")
    elif tape.steps:
        tape.final = _strip_summary(tape.steps[-1].output)
    return tape
