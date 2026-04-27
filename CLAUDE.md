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
- `results/<run_id>/` — per-run outputs (git-ignored).

## vLLM via `resmgr` (workspace-managed)

This project does **not** launch its own vLLM. `src/llm.py::LLMClient` calls
`resmgr.vllm_client(model)` and gets back an `openai.OpenAI` pre-configured
for the daemon-managed server. The actual `vllm serve` process is owned by
the `resmgr` daemon (one server per `(model, kwargs)`, shared across
projects). See `/mnt/ddn/prod-runs/thyun.park/src/resmgr/docs/MIGRATING_PROJECTS.md`.

Implications:
- No `serve_vllm.sh` in this repo. Don't reintroduce one.
- The first `LLMClient()` call cold-loads vLLM (1–3 min for 32B). Subsequent
  calls hit a hot or sleeping (re-wakable in ~5 s) server.
- Idle reaper: server sleeps after 30 min, full unload after 4 h further idle.
- Do not launch `vllm serve` directly via Bash; resmgr's PreToolUse hook
  (registered in `.claude/settings.json`) will reap any orphan vLLM you
  start outside the daemon.

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

`base_url` and `api_key` are owned by `resmgr.vllm_client(model)`; the
project no longer reads `EVO_BASE_URL` / `EVO_API_KEY`. Override the model
via `EVO_MODEL` only if you need a non-default backbone (each
`(model, kwargs)` pair spawns a separate daemon-managed server).
