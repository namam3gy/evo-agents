from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

START = "START"
END = "END"
RESERVED = {START, END}


class Agent(BaseModel):
    name: str
    persona: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=lambda: ["output"])

    @field_validator("name")
    @classmethod
    def _name_valid(cls, v: str) -> str:
        if v in RESERVED:
            raise ValueError(f"agent name '{v}' is reserved")
        if not v.replace("_", "").isalnum():
            raise ValueError(f"agent name must be alphanumeric/underscore, got '{v}'")
        return v


class Graph(BaseModel):
    agents: dict[str, Agent] = Field(default_factory=dict)
    edges: list[tuple[str, str]] = Field(default_factory=list)

    def nodes(self) -> list[str]:
        return [START, *self.agents.keys(), END]

    def successors(self, node: str) -> list[str]:
        return [v for (u, v) in self.edges if u == node]

    def predecessors(self, node: str) -> list[str]:
        return [u for (u, v) in self.edges if v == node]


class AgentStep(BaseModel):
    agent: str
    prompt: str
    output: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class Tape(BaseModel):
    task_id: str
    question: str
    steps: list[AgentStep] = Field(default_factory=list)
    final: str = ""

    def total_tokens(self) -> int:
        return sum(s.prompt_tokens + s.completion_tokens for s in self.steps)


EditOp = Literal[
    "add_agent",
    "remove_agent",
    "rewrite_persona",
    "add_edge",
    "remove_edge",
]


class Edit(BaseModel):
    op: EditOp
    name: str | None = None
    persona: str | None = None
    inputs: list[str] | None = None
    outputs: list[str] | None = None
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None

    model_config = {"populate_by_name": True}


class EditBatch(BaseModel):
    rationale: str
    edits: list[Edit]
