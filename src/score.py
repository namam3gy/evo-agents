from __future__ import annotations

import re

from .datasets import Task
from .llm import LLMClient

_MCQ_LAST_RE = re.compile(r"\b([A-E])\b")
_ANSWER_PATTERN_RE = re.compile(
    r"(?:final\s+answer|answer)\s*[:\-]?\s*\(?([A-E])\)?", re.IGNORECASE
)

JUDGE_SYSTEM = (
    "You judge whether a predicted answer is semantically equivalent to the "
    "reference answer for the given question. Ignore format, verbosity, and "
    "synonyms — focus on meaning. Respond with exactly one word: YES or NO."
)


def score_mcq(prediction: str, gold: str) -> int:
    if not prediction:
        return 0
    target = gold.strip().upper()
    m = _ANSWER_PATTERN_RE.search(prediction)
    if m:
        return int(m.group(1).upper() == target)
    matches = _MCQ_LAST_RE.findall(prediction.upper())
    if not matches:
        return 0
    return int(matches[-1] == target)


def score_llm_judge(
    prediction: str,
    gold: str,
    question: str,
    llm: LLMClient,
    max_ctx_chars: int = 1200,
) -> int:
    if not prediction or not gold:
        return 0
    user = (
        f"Question (may be truncated):\n{question[:max_ctx_chars]}\n\n"
        f"Reference answer:\n{gold}\n\n"
        f"Predicted answer:\n{prediction[:max_ctx_chars]}\n\n"
        "Are they semantically equivalent? Answer YES or NO."
    )
    text, _, _ = llm.chat(
        system=JUDGE_SYSTEM,
        user=user,
        temperature=0.0,
        max_tokens=4,
    )
    return int(text.strip().upper().startswith("YES"))


def score(prediction: str, task: Task, llm: LLMClient) -> int:
    if task.benchmark == "mediq":
        return score_mcq(prediction, task.answer)
    if task.benchmark in ("financebench", "agentclinic"):
        return score_llm_judge(prediction, task.answer, task.question, llm)
    raise ValueError(f"unknown benchmark: {task.benchmark}")
