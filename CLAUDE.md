# CLAUDE.md

Project-level guidance for `agent_orchestration/`. The workspace-level
`../CLAUDE.md` still applies; this file only adds project-specific rules.

## What this project is

Self-evolving multi-agent orchestration pilot. A reflection-based
controller progressively edits a multi-agent DAG (topology + personas +
edges) over a repetitive task family — no controller training, no
explicit search. See `README.md` for setup, quick checks, and the full
pilot workflow.

Layout:
- `src/` — library (`llm.py`, `graph.py`, `orchestrator.py`,
  `controller.py`, `evolve.py`, `baselines.py`, `datasets.py`,
  `score.py`, `types.py`).
- `scripts/run_pilot.py` — pilot entry point (baselines + evolution).
- `scripts/serve_vllm.sh` — launches the vLLM OpenAI-compatible server
  on `http://localhost:8000/v1`.
- `results/<run_id>/` — per-run outputs (git-ignored).

## Always use `uv` to run Python

Every Python invocation in this project must go through `uv` so it uses
the project's pinned interpreter (`.python-version`) and `.venv/`.

- Run scripts: `uv run python scripts/run_pilot.py ...`
- Run modules: `uv run python -m src.llm --smoke`
- Run tests / REPL / ad-hoc: `uv run python ...`
- Install deps: `uv sync` (or `uv add <pkg>`); use `uv pip install` only
  for packages like `vllm` that are intentionally kept outside
  `pyproject.toml`.
- Do **not** call bare `python`, `python3`, or `pip` — they will pick up
  the wrong environment.

This rule applies to commands you suggest in docs, in chat, and to any
command you run yourself via Bash.

## Environment variables (read by `src/llm.py`)

| Var | Default |
|---|---|
| `EVO_MODEL` | `Qwen/Qwen2.5-32B-Instruct` |
| `EVO_BASE_URL` | `http://localhost:8000/v1` |
| `EVO_API_KEY` | `EMPTY` |

The vLLM server must be running before any pilot command that hits the
model; `scripts/serve_vllm.sh` assumes a single H200.
