"""Build notebooks/calib_01_analysis.ipynb programmatically.

Run from the project root:

    uv run python notebooks/_build_calib_01_analysis.py

It rebuilds the notebook and then executes every cell so outputs are
already embedded when a cold reader opens it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import nbformat as nbf

NB_PATH = Path(__file__).parent / "calib_01_analysis.ipynb"


def md(text: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(text)


def code(text: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(text)


def build() -> nbf.NotebookNode:
    nb = nbf.v4.new_notebook()

    nb.cells = [
        md(
            "# `calib_01` analysis\n"
            "\n"
            "Reproducible read-out of the first middle-size pilot run "
            "(`results/calib_01/`, 2026-04-24).\n"
            "\n"
            "- Config: `n_train=20`, `n_val=50`, `n_test=50`, `seed=0`, "
            "`max_iters=3`, GSM8K, Qwen2.5-32B-Instruct, vLLM 0.19.1.\n"
            "- Total wall time ≈ 66 min on one shared H200.\n"
            "- Companion narrative: `docs/insights/pilot.md` §4 (EN) / "
            "`docs/insights/pilot_ko.md` §4 (KO).\n"
            "\n"
            "Every cell below is meant to run top-to-bottom under "
            "`uv run jupyter ...`."
        ),
        md("## 1. Imports and config"),
        code(
            "from pathlib import Path\n"
            "import json\n"
            "\n"
            "import pandas as pd\n"
            "import matplotlib.pyplot as plt\n"
            "\n"
            "RUN_DIR = Path('../results/calib_01').resolve()\n"
            "RESULTS_PATH = RUN_DIR / 'results.json'\n"
            "EVOLVE_LOG_PATH = RUN_DIR / 'evolve_log.json'\n"
            "EVOLVED_GRAPH_PATH = RUN_DIR / 'evolved_graph_final.json'\n"
            "\n"
            "assert RESULTS_PATH.exists(), RESULTS_PATH\n"
            "assert EVOLVE_LOG_PATH.exists(), EVOLVE_LOG_PATH\n"
            "assert EVOLVED_GRAPH_PATH.exists(), EVOLVED_GRAPH_PATH\n"
            "\n"
            "print(f'run dir: {RUN_DIR}')"
        ),
        md("## 2. Load run artifacts"),
        code(
            "with open(RESULTS_PATH) as f:\n"
            "    results = json.load(f)\n"
            "with open(EVOLVE_LOG_PATH) as f:\n"
            "    evolve_log = json.load(f)\n"
            "with open(EVOLVED_GRAPH_PATH) as f:\n"
            "    evolved_graph = json.load(f)\n"
            "\n"
            "print('keys in results.json     :', sorted(results))\n"
            "print('keys in evolve_log.json  :', sorted(evolve_log))\n"
            "print('keys in evolved_graph    :', sorted(evolved_graph))"
        ),
        md(
            "## 3. Baselines and evolved-graph accuracy\n"
            "\n"
            "`results.json` holds the val numbers for the two baselines "
            "and the test numbers for all three methods (CoT, P-E, and "
            "the evolved graph). The evolved graph has no val entry here "
            "because the evolution loop tracks its own val curve in "
            "`evolve_log.json` (see section 4)."
        ),
        code(
            "val_rows = []\n"
            "for name, payload in results['baselines_val'].items():\n"
            "    val_rows.append({'method': name, **payload})\n"
            "val_df = pd.DataFrame(val_rows)\n"
            "\n"
            "test_rows = []\n"
            "for name, payload in results['test'].items():\n"
            "    test_rows.append({'method': name, **payload})\n"
            "test_df = pd.DataFrame(test_rows)\n"
            "\n"
            "val_df"
        ),
        code("test_df"),
        md(
            "### Observation: evolved graph is *worse on test* than both "
            "baselines, at 2–3.7× the tokens\n"
            "\n"
            "With `n=50`, a 4–6 pp gap is near the sample-error floor "
            "(3-sample difference ≈ ±7 pp at 95% CI), so the regression "
            "isn't *proven* here. But the gap is consistently on the "
            "wrong side of zero, and the token cost is not small."
        ),
        code(
            "summary = test_df.copy()\n"
            "summary['tokens_per_task'] = summary['tokens'] / summary['n']\n"
            "summary[['method', 'accuracy', 'tokens', 'tokens_per_task']]"
        ),
        md(
            "## 4. Iteration trajectory\n"
            "\n"
            "Each iteration reports train accuracy (n=20) and val accuracy "
            "(n=50), plus an `accepted` flag from `evolve.py:139`. The "
            "seed iter (`iteration == 0`) has `NaN` train acc because it "
            "isn't evaluated on train."
        ),
        code(
            "iters = evolve_log['iterations']\n"
            "iter_df = pd.DataFrame([\n"
            "    {\n"
            "        'iter': it['iteration'],\n"
            "        'train_acc': it['train_acc'],\n"
            "        'val_acc':   it['val_acc'],\n"
            "        'accepted':  it['accepted'],\n"
            "        'n_agents':  it['n_agents'],\n"
            "        'n_edges':   it['n_edges'],\n"
            "        'is_noop':   it['is_noop'],\n"
            "        'worker_tokens':     it['worker_tokens'],\n"
            "        'controller_tokens': it['controller_tokens'],\n"
            "        'elapsed_s':         it['elapsed_s'],\n"
            "        'edits_summary': ' | '.join(\n"
            "            f\"{e['op']}({e.get('name') or ''})\".rstrip('()')\n"
            "            for e in it['edit_batch']['edits']\n"
            "        ) or 'seed',\n"
            "    }\n"
            "    for it in iters\n"
            "])\n"
            "iter_df"
        ),
        md(
            "### 4.1 Val trajectory and the accept_slack quirk\n"
            "\n"
            "`iter 1` and `iter 2` regressed from the seed's 94% val to "
            "92%, yet both were ACCEPTED. This is because "
            "`evolve.py:139` allows `val_acc >= best_val_acc - "
            "accept_slack`, and `best_val_acc` is only updated when the "
            "new val is strictly higher (`evolve.py:146–147`). The graph "
            "that gets persisted as `best_graph` is therefore *not* the "
            "graph that achieved `best_val_acc`."
        ),
        code(
            "fig, ax = plt.subplots(figsize=(7, 4))\n"
            "ax.plot(iter_df['iter'], iter_df['val_acc'] * 100, 'o-', label='val acc (%)')\n"
            "ax.plot(iter_df['iter'], iter_df['train_acc'] * 100, 's--', label='train acc (%)')\n"
            "for _, row in iter_df.iterrows():\n"
            "    marker = 'ACCEPTED' if row['accepted'] else 'REJECTED'\n"
            "    ax.annotate(\n"
            "        marker,\n"
            "        xy=(row['iter'], row['val_acc'] * 100),\n"
            "        xytext=(5, 8),\n"
            "        textcoords='offset points',\n"
            "        fontsize=9,\n"
            "    )\n"
            "ax.set_xlabel('iteration')\n"
            "ax.set_ylabel('accuracy (%)')\n"
            "ax.set_title('calib_01 iteration trajectory (n_val=50, n_train=20)')\n"
            "ax.set_xticks(iter_df['iter'])\n"
            "ax.grid(alpha=0.3)\n"
            "ax.legend()\n"
            "fig.tight_layout()"
        ),
        md(
            "### 4.2 `best_graph` vs `best_val_acc` discrepancy\n"
            "\n"
            "Confirm the decoupling directly from the run artifacts."
        ),
        code(
            "print('best_val_acc recorded  :', evolve_log['best_val_acc'])\n"
            "print('seed iter val_acc      :', iter_df.loc[iter_df[\"iter\"] == 0, \"val_acc\"].item())\n"
            "print('n_agents in best_graph :', len(evolve_log['best_graph']['agents']))\n"
            "print('n_edges  in best_graph :', len(evolve_log['best_graph']['edges']))\n"
            "print('agents   in best_graph :', sorted(evolve_log['best_graph']['agents']))"
        ),
        md(
            "The `best_val_acc` cell is the seed's 94% (2 agents). The "
            "`best_graph` stored next to it is the 4-agent graph from "
            "iter 2 (val=92%). The two numbers belong to different "
            "graphs — that is the bug / design flaw to resolve before "
            "the scaled run."
        ),
        md(
            "## 5. Cost: tokens and wall-clock\n"
            "\n"
            "Worker tokens scale with graph size and sample count; "
            "controller tokens are near-constant. At `n_train=20 + "
            "n_val=50` per iter the ratio is ~20×, larger than the "
            "3–4× estimate from the earlier 5-sample smoke run."
        ),
        code(
            "cost_df = iter_df[['iter', 'n_agents', 'worker_tokens', 'controller_tokens', 'elapsed_s']].copy()\n"
            "cost_df['worker_over_controller'] = cost_df['worker_tokens'] / cost_df['controller_tokens'].replace(0, pd.NA)\n"
            "cost_df['elapsed_min'] = cost_df['elapsed_s'] / 60\n"
            "cost_df[['iter', 'n_agents', 'worker_tokens', 'controller_tokens', 'worker_over_controller', 'elapsed_min']]"
        ),
        md(
            "### 5.1 Token cost per test prediction, by method"
        ),
        code(
            "per_task = test_df.copy()\n"
            "per_task['tokens_per_task'] = per_task['tokens'] / per_task['n']\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(6, 3.5))\n"
            "ax.barh(per_task['method'], per_task['tokens_per_task'])\n"
            "ax.set_xlabel('tokens / test task')\n"
            "ax.set_title('calib_01 test-phase token cost, by method')\n"
            "for i, (method, tpt) in enumerate(zip(per_task['method'], per_task['tokens_per_task'])):\n"
            "    ax.text(tpt + 20, i, f'{tpt:,.0f}', va='center', fontsize=9)\n"
            "ax.invert_yaxis()\n"
            "fig.tight_layout()"
        ),
        md(
            "## 6. Edits emitted by the controller\n"
            "\n"
            "Non-seed iters each added one agent and two or three edges. "
            "The `is_noop` column is False in every row, confirming that "
            "the controller did *not* collapse to an empty edit batch "
            "under saturated val — the pilot's intended behavior."
        ),
        code(
            "for it in iters:\n"
            "    print(f\"--- iter {it['iteration']} (accepted={it['accepted']}, is_noop={it['is_noop']}) ---\")\n"
            "    print('rationale:', it['edit_batch']['rationale'])\n"
            "    for e in it['edit_batch']['edits']:\n"
            "        if e['op'] == 'add_agent':\n"
            "            print(f\"  add_agent({e['name']})  persona={e['persona'][:60]!r}...\")\n"
            "        elif e['op'] == 'add_edge':\n"
            "            print(f\"  add_edge({e['from_']} -> {e['to']})\")\n"
            "        else:\n"
            "            print(' ', e)\n"
            "    print()"
        ),
        md(
            "## 7. What this run validates — and what it does not\n"
            "\n"
            "**Validates:**\n"
            "- End-to-end pipeline at `n=50` (baselines + evolution + "
            "test phase).\n"
            "- `is_noop` field lands correctly in `evolve_log.json`.\n"
            "- Controller emits non-trivial edits even on saturated val "
            "(re-confirms §2.2 of `docs/insights/pilot.md`).\n"
            "\n"
            "**Does not validate (and surfaces instead):**\n"
            "- That evolution improves accuracy. Test went **down**, "
            "while token cost went **up** 2–3.7×.\n"
            "- That `best_graph` is the graph of `best_val_acc`. They "
            "diverge under `accept_slack`.\n"
            "- That methods are distinguishable at this sample size. "
            "val has CoT = P-E = 94%.\n"
            "\n"
            "**Next:**\n"
            "1. Pick one of Opt-1 / Opt-2 for `evolve.py:139–147` "
            "(see `references/roadmap.md` §5.2 and §6).\n"
            "2. Scale to `n_val = n_test = 300, seed ∈ {0,1,2}, "
            "max_iters = 5` per `references/roadmap.md` §5.1.\n"
            "3. After the scaled run, revisit the controller rationale "
            "quality question — `calib_01`'s rationales looked more like "
            "generic 'add X agent' defaults than tape-grounded causal "
            "reads. Tracking this feeds directly into the Framing A "
            "paper direction."
        ),
    ]

    nb.metadata.kernelspec = {
        "name": "evo_agents",
        "display_name": "Python (evo_agents)",
        "language": "python",
    }
    nb.metadata.language_info = {"name": "python"}

    return nb


def main() -> None:
    nb = build()
    with NB_PATH.open("w") as f:
        nbf.write(nb, f)
    print(f"wrote {NB_PATH}")

    print("executing in-place (this will take a minute)...")
    subprocess.check_call(
        [
            "uv",
            "run",
            "jupyter",
            "nbconvert",
            "--to",
            "notebook",
            "--execute",
            "--inplace",
            str(NB_PATH),
        ],
        cwd=NB_PATH.parent.parent,
    )
    print(f"executed {NB_PATH}")


if __name__ == "__main__":
    main()
