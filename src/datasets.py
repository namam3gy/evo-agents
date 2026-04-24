from __future__ import annotations

import random
from dataclasses import dataclass

from datasets import load_dataset


@dataclass
class Task:
    task_id: str
    question: str
    answer: str


def _extract_gold_answer(raw: str) -> str:
    if "####" in raw:
        tail = raw.split("####")[-1].strip()
    else:
        tail = raw.strip().splitlines()[-1].strip()
    return tail.replace(",", "").replace("$", "").strip()


def load_gsm8k(
    n_train: int = 20,
    n_val: int = 10,
    n_test: int = 50,
    seed: int = 0,
) -> tuple[list[Task], list[Task], list[Task]]:
    train_raw = load_dataset("openai/gsm8k", "main", split="train")
    test_raw = load_dataset("openai/gsm8k", "main", split="test")
    rng = random.Random(seed)
    train_idx = rng.sample(range(len(train_raw)), n_train)
    val_idx_pool = [i for i in range(len(train_raw)) if i not in set(train_idx)]
    val_idx = rng.sample(val_idx_pool, n_val)
    test_idx = rng.sample(range(len(test_raw)), n_test)

    def _pack(ds, idxs, prefix):
        out = []
        for i in idxs:
            row = ds[int(i)]
            out.append(
                Task(
                    task_id=f"{prefix}-{i}",
                    question=row["question"].strip(),
                    answer=_extract_gold_answer(row["answer"]),
                )
            )
        return out

    return (
        _pack(train_raw, train_idx, "train"),
        _pack(train_raw, val_idx, "val"),
        _pack(test_raw, test_idx, "test"),
    )
