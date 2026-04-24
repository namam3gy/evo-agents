from __future__ import annotations

from .graph import seed_cot, seed_planner_executor
from .types import Graph


def cot_graph() -> Graph:
    return seed_cot()


def planner_executor_graph() -> Graph:
    return seed_planner_executor()
