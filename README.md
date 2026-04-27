# Self-Evolving Multi-Agent Orchestration (Pilot)

Reflection-based controller that progressively edits a multi-agent DAG
(topology + personas + edges) over a repetitive task family, without
training the controller and without an explicit search procedure.

## Setup

```bash
# Python env (managed by uv); resmgr is a pinned dep
uv sync
```

vLLM lifecycle is owned by the workspace `resmgr` daemon, not by this
project. The first call into `LLMClient` invokes
`resmgr.vllm_client(EVO_MODEL)`, which blocks until the daemon has the
server ready (cold-load 1–3 min for 32B on first call; ~5 s wake-up
otherwise) and returns an OpenAI client wired to the daemon-managed
endpoint. There is no `serve_vllm.sh` to run.

```bash
# Verify the daemon and inspect what's loaded
resmgr daemon status
resmgr status
```

All Python commands below run through `uv run` so they use the project's
pinned interpreter and `.venv/`.

Environment variable read by `src/llm.py`:

| Var | Default |
|---|---|
| `EVO_MODEL` | `Qwen/Qwen2.5-32B-Instruct` |

## Quick checks

```bash
# smoke test: one chat round-trip
uv run python -m src.llm --smoke

# baselines only (CoT + Planner-Executor on val)
uv run python scripts/run_pilot.py --only-baselines

# 1-iteration evolution (validates the controller emits usable edits)
uv run python scripts/run_pilot.py --max-iters 1
```

## Full pilot

```bash
uv run python scripts/run_pilot.py
```

Writes `results/<run_id>/` with:
- `results.json` — baseline + evolved accuracy on val and test
- `evolve_log.json` — per-iteration train/val accuracy, edit batch, token cost
- `evolved_graph_final.json` — the final architecture
- `plots/accuracy_vs_iter.png` — evolution curve vs. baseline lines
- `plots/arch_size.png` — |agents| and |edges| over iterations
- `plots/edit_mix.png` — frequency of each edit op (controller behavior)

## What to look for

1. `accuracy_vs_iter.png` — evolved val accuracy should rise above the
   planner-executor baseline within 2–3 iterations and plateau.
2. `evolved_graph_final.json` — expect an extra agent (verifier / critic /
   arithmetic-specialist) and at least one non-trivial edge beyond the
   linear seed.
3. Test-set table in `results.json` — the evolved architecture should
   transfer to held-out problems with <3pp gap vs. val.

If the graph stays identical to the seed, the controller is being too
conservative — tighten its prompt or raise its temperature.

## Reference

Related work this pilot is positioned against:
- ADAS (Hu et al., ICLR 2025)
- AFlow (Zhang et al., ICLR 2025 Oral)
- GPTSwarm (Zhuge et al., ICML 2024 Oral)
- MaAS (Zhang et al., ICML 2025 Oral)
- Multi-Agent Collaboration via Evolving Orchestration (NeurIPS 2025)
- AgentNet (NeurIPS 2025)

The gap: all prior methods use search (archive / MCTS / supernet) or RL.
This pilot uses purely *in-context reflection* over trajectory tapes to
co-evolve topology + personas + edges on a frozen 32B backbone.
