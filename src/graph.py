from __future__ import annotations

import copy

import networkx as nx

from .types import END, START, Agent, Edit, EditBatch, Graph


class GraphEditError(ValueError):
    pass


def seed_planner_executor() -> Graph:
    planner = Agent(
        name="planner",
        persona=(
            "You are a planner. Read the user task and produce a numbered, concrete plan "
            "of at most 4 solution steps. Do not solve the task; only plan."
        ),
        inputs=["task"],
        outputs=["plan"],
    )
    executor = Agent(
        name="executor",
        persona=(
            "You are an executor. Given the task and a plan, follow the plan to compute the answer. "
            "Show your arithmetic step by step. End with a line: 'Final Answer: <number>'."
        ),
        inputs=["task", "planner.plan"],
        outputs=["answer"],
    )
    g = Graph(
        agents={"planner": planner, "executor": executor},
        edges=[
            (START, "planner"),
            ("planner", "executor"),
            (START, "executor"),
            ("executor", END),
        ],
    )
    validate(g)
    return g


def seed_cot() -> Graph:
    solver = Agent(
        name="solver",
        persona=(
            "You are a careful problem solver. Think step by step, show arithmetic, "
            "and end with a line: 'Final Answer: <number>'."
        ),
        inputs=["task"],
        outputs=["answer"],
    )
    g = Graph(
        agents={"solver": solver},
        edges=[(START, "solver"), ("solver", END)],
    )
    validate(g)
    return g


def _to_nx(g: Graph) -> nx.DiGraph:
    dg = nx.DiGraph()
    for n in g.nodes():
        dg.add_node(n)
    for u, v in g.edges:
        dg.add_edge(u, v)
    return dg


def validate(g: Graph) -> None:
    for name in g.agents:
        if name in (START, END):
            raise GraphEditError(f"reserved name: {name}")
    node_set = set(g.nodes())
    for u, v in g.edges:
        if u not in node_set or v not in node_set:
            raise GraphEditError(f"edge references unknown node: {u}->{v}")
    dg = _to_nx(g)
    if not nx.is_directed_acyclic_graph(dg):
        raise GraphEditError("graph is cyclic")
    for name in g.agents:
        if not dg.has_node(name):
            continue
        if dg.in_degree(name) == 0:
            raise GraphEditError(f"agent {name} has no incoming edges")
        if not nx.has_path(dg, START, name):
            raise GraphEditError(f"agent {name} is unreachable from START")
        if not nx.has_path(dg, name, END):
            raise GraphEditError(f"agent {name} cannot reach END")


def topological_order(g: Graph) -> list[str]:
    dg = _to_nx(g)
    return [n for n in nx.topological_sort(dg) if n not in (START, END)]


def apply_edits(g: Graph, batch: EditBatch, max_agents: int = 6) -> Graph:
    g2 = copy.deepcopy(g)
    for e in batch.edits:
        if e.op == "add_agent":
            if not e.name or not e.persona:
                raise GraphEditError("add_agent requires name and persona")
            if e.name in g2.agents:
                raise GraphEditError(f"agent {e.name} already exists")
            if len(g2.agents) >= max_agents:
                raise GraphEditError("max agents reached")
            g2.agents[e.name] = Agent(
                name=e.name,
                persona=e.persona,
                inputs=e.inputs or ["task"],
                outputs=e.outputs or ["output"],
            )
        elif e.op == "remove_agent":
            if not e.name or e.name not in g2.agents:
                raise GraphEditError(f"cannot remove unknown agent {e.name}")
            del g2.agents[e.name]
            g2.edges = [(u, v) for (u, v) in g2.edges if u != e.name and v != e.name]
        elif e.op == "rewrite_persona":
            if not e.name or e.name not in g2.agents:
                raise GraphEditError(f"cannot rewrite unknown agent {e.name}")
            if not e.persona:
                raise GraphEditError("rewrite_persona requires persona")
            g2.agents[e.name].persona = e.persona
        elif e.op == "add_edge":
            if not e.from_ or not e.to:
                raise GraphEditError("add_edge requires from/to")
            pair = (e.from_, e.to)
            if pair in g2.edges:
                continue
            g2.edges.append(pair)
        elif e.op == "remove_edge":
            if not e.from_ or not e.to:
                raise GraphEditError("remove_edge requires from/to")
            pair = (e.from_, e.to)
            if pair not in g2.edges:
                raise GraphEditError(f"no such edge {pair}")
            g2.edges = [p for p in g2.edges if p != pair]
    validate(g2)
    return g2


def describe(g: Graph) -> str:
    lines = [f"Agents ({len(g.agents)}):"]
    for a in g.agents.values():
        lines.append(f"  - {a.name}: {a.persona[:120]}")
    lines.append(f"Edges ({len(g.edges)}):")
    for u, v in g.edges:
        lines.append(f"  - {u} -> {v}")
    return "\n".join(lines)
