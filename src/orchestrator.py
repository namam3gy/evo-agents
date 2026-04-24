from __future__ import annotations

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
