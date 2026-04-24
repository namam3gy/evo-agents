from __future__ import annotations

import json
import random
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from datasets import load_dataset

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"


@dataclass
class Task:
    task_id: str
    question: str
    answer: str
    benchmark: str


def _download(url: str, dest: Path) -> None:
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)


def _three_way_split(
    items: list[Task],
    n_train: int,
    n_val: int,
    n_test: int,
    seed: int,
) -> tuple[list[Task], list[Task], list[Task]]:
    total = len(items)
    need = n_train + n_val + n_test
    if need > total:
        raise ValueError(
            f"requested {n_train}+{n_val}+{n_test}={need} samples but only {total} available"
        )
    rng = random.Random(seed)
    idx = list(range(total))
    rng.shuffle(idx)
    picked = [items[i] for i in idx[:need]]
    return (
        picked[:n_train],
        picked[n_train : n_train + n_val],
        picked[n_train + n_val : need],
    )


def load_financebench(
    n_train: int, n_val: int, n_test: int, seed: int = 0
) -> tuple[list[Task], list[Task], list[Task]]:
    ds = load_dataset("PatronusAI/financebench", split="train")
    items: list[Task] = []
    for i, row in enumerate(ds):
        ev_raw = row.get("evidence") or []
        ev_texts = [e["evidence_text"].strip() for e in ev_raw if e.get("evidence_text")]
        ev_block = "\n\n".join(
            f"[Evidence {j + 1}]\n{t}" for j, t in enumerate(ev_texts[:3])
        )
        q_parts = [row["question"].strip()]
        if ev_block:
            q_parts.append(f"Relevant excerpts from the company's filings:\n{ev_block}")
        items.append(
            Task(
                task_id=f"fb-{row.get('financebench_id', i)}",
                question="\n\n".join(q_parts),
                answer=str(row["answer"]).strip(),
                benchmark="financebench",
            )
        )
    return _three_way_split(items, n_train, n_val, n_test, seed)


def load_mediq(
    n_train: int, n_val: int, n_test: int, seed: int = 0
) -> tuple[list[Task], list[Task], list[Task]]:
    """MEDIQ Non-interactive Initial mode (frozen first-turn).

    The paper reports that Non-interactive-Initial beats Basic interactive on
    GPT-3.5 (45.6% vs 42.2%), so this mode is the documented *single-pass*
    baseline of the benchmark. Here we give only `context[0]` (the initial
    presentation) plus the MCQ options, as defined in Li et al. 2024.
    """
    path = DATA_DIR / "mediq" / "all_dev_good.jsonl"
    _download(
        "https://raw.githubusercontent.com/stellalisy/MediQ/main/data/all_dev_good.jsonl",
        path,
    )
    items: list[Task] = []
    with path.open() as f:
        for line in f:
            r = json.loads(line)
            opts = r["options"]
            initial = r["context"][0] if r.get("context") else ""
            opts_block = "\n".join(f"{k}. {v}" for k, v in opts.items())
            q = (
                f"Clinical presentation:\n{initial}\n\n"
                f"Question: {r['question'].strip()}\n\n"
                f"Options:\n{opts_block}\n\n"
                f"Respond with a single letter ({', '.join(opts.keys())}) "
                f"on the final line in the form 'Answer: <letter>'."
            )
            items.append(
                Task(
                    task_id=f"mediq-{r['id']}",
                    question=q,
                    answer=str(r["answer_idx"]).strip(),
                    benchmark="mediq",
                )
            )
    return _three_way_split(items, n_train, n_val, n_test, seed)


def load_agentclinic(
    n_train: int, n_val: int, n_test: int, seed: int = 0
) -> tuple[list[Task], list[Task], list[Task]]:
    """AgentClinic single-pass mode (not the original multi-turn simulator).

    We feed the full `OSCE_Examination` (minus the gold diagnosis) as one prompt
    and ask for a one-shot diagnosis. This measures pattern recognition on full
    cases rather than AgentClinic's intended "ask-to-diagnose" loop; the
    multi-turn evaluation is deferred to a later phase.
    """
    path = DATA_DIR / "agentclinic" / "agentclinic_medqa.jsonl"
    _download(
        "https://raw.githubusercontent.com/SamuelSchmidgall/AgentClinic/main/agentclinic_medqa.jsonl",
        path,
    )
    items: list[Task] = []
    with path.open() as f:
        for i, line in enumerate(f):
            r = json.loads(line)
            osce = dict(r.get("OSCE_Examination", r))
            gold = osce.pop("Correct_Diagnosis", "")
            q = (
                "You are given a complete OSCE-style clinical case. Based on all "
                "of the information below, state the single most likely primary "
                "diagnosis.\n\n"
                f"Case details (JSON):\n{json.dumps(osce, indent=2, ensure_ascii=False)}\n\n"
                "What is the most likely primary diagnosis? Give a concise "
                "medical term as your final answer."
            )
            items.append(
                Task(
                    task_id=f"ac-{i}",
                    question=q,
                    answer=str(gold).strip(),
                    benchmark="agentclinic",
                )
            )
    return _three_way_split(items, n_train, n_val, n_test, seed)


_LOADERS = {
    "financebench": load_financebench,
    "mediq": load_mediq,
    "agentclinic": load_agentclinic,
}


def load_benchmark(
    name: str, n_train: int, n_val: int, n_test: int, seed: int = 0
) -> tuple[list[Task], list[Task], list[Task]]:
    if name not in _LOADERS:
        raise ValueError(f"unknown benchmark '{name}'; options: {sorted(_LOADERS)}")
    return _LOADERS[name](n_train, n_val, n_test, seed)
