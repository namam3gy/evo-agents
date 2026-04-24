from __future__ import annotations

import re

_NUM_RE = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")
_FINAL_LINE_RE = re.compile(r"final\s*answer\s*[:\-]?\s*(.+)", re.IGNORECASE)


def extract_number(text: str) -> str | None:
    if not text:
        return None
    m = _FINAL_LINE_RE.search(text)
    candidates: list[str] = []
    if m:
        candidates.extend(_NUM_RE.findall(m.group(1)))
    if not candidates:
        candidates.extend(_NUM_RE.findall(text))
    if not candidates:
        return None
    raw = candidates[-1].replace(",", "")
    try:
        f = float(raw)
    except ValueError:
        return None
    return str(int(f)) if f.is_integer() else str(f)


def normalize_gold(ans: str) -> str:
    raw = ans.replace(",", "").replace("$", "").strip()
    try:
        f = float(raw)
    except ValueError:
        return raw
    return str(int(f)) if f.is_integer() else str(f)


def score(prediction_text: str, gold: str) -> int:
    pred = extract_number(prediction_text)
    gold_n = normalize_gold(gold)
    return int(pred is not None and pred == gold_n)
