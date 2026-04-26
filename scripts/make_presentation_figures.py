"""Generate the six new figures used in the 2026-04-26 advisor / paper-style decks.

Outputs are written to docs/presentations/2026-04-26-evo-agents/assets/.
Run via:
    uv run python scripts/make_presentation_figures.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "docs" / "presentations" / "2026-04-26-evo-agents" / "assets"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Forest & Moss palette
C_FOREST = "#2C5F2D"
C_MOSS = "#97BC62"
C_CREAM = "#F5F5F5"
C_CHARCOAL = "#36454F"
C_ACCENT = "#B85042"  # terracotta — negative / failure
C_GREY = "#A0A0A0"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _draw_dag(ax, agents: list[str], edges: list[tuple[str, str]], title: str,
              positions: dict | None = None, *, node_size: int = 3200,
              fontsize: float = 10.5) -> None:
    """Draw a small DAG with rounded nodes + arrow edges in Forest & Moss palette."""
    G = nx.DiGraph()
    G.add_nodes_from(agents)
    G.add_edges_from(edges)
    pos = positions or nx.spring_layout(G, seed=1, k=1.4)

    # Node colors: START / END are cream-filled, agents forest-filled
    node_colors = []
    edge_colors = []
    for n in G.nodes():
        if n in ("START", "END"):
            node_colors.append(C_CREAM)
            edge_colors.append(C_CHARCOAL)
        else:
            node_colors.append(C_FOREST)
            edge_colors.append(C_FOREST)

    nx.draw_networkx_nodes(G, pos, node_size=node_size, node_color=node_colors,
                           edgecolors=edge_colors, linewidths=1.8, ax=ax)
    nx.draw_networkx_edges(G, pos, arrows=True, arrowsize=16, edge_color=C_CHARCOAL,
                           width=1.4, ax=ax, node_size=node_size,
                           connectionstyle="arc3,rad=0.06")

    labels = {n: n.replace("_", "\n") for n in G.nodes()}
    label_colors = {n: ("white" if n not in ("START", "END") else C_CHARCOAL) for n in G.nodes()}
    for n, (x, y) in pos.items():
        ax.text(x, y, labels[n], ha="center", va="center", fontsize=fontsize,
                color=label_colors[n], weight="bold")

    # padding around nodes
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    pad_x = (max(xs) - min(xs)) * 0.20 + 0.4
    pad_y = (max(ys) - min(ys)) * 0.30 + 0.4
    ax.set_xlim(min(xs) - pad_x, max(xs) + pad_x)
    ax.set_ylim(min(ys) - pad_y, max(ys) + pad_y)
    ax.set_title(title, fontsize=12, color=C_CHARCOAL, weight="bold", pad=10)
    ax.set_aspect("equal")
    ax.axis("off")


def _box(ax, x, y, w, h, text, *, fill=C_MOSS, edge=C_FOREST, fontcolor=C_CHARCOAL,
         fontsize=10, weight="normal", align="center"):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.04",
                         linewidth=1.4, edgecolor=edge, facecolor=fill)
    ax.add_patch(box)
    ax.text(x + w / 2, y + h / 2, text, ha=align, va="center",
            fontsize=fontsize, color=fontcolor, weight=weight, wrap=True)


def _arrow(ax, x1, y1, x2, y2, *, color=C_CHARCOAL, lw=1.4, style="-|>"):
    arr = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=14,
                          color=color, linewidth=lw)
    ax.add_patch(arr)


# ---------------------------------------------------------------------------
# 1. dag_baselines.png — CoT / P-E / Evolved (4-agent example)
# ---------------------------------------------------------------------------


def fig_dag_baselines() -> None:
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5))

    # CoT — single solver
    pos_cot = {"START": (0, 0), "solver": (1, 0), "END": (2, 0)}
    _draw_dag(axes[0], ["START", "solver", "END"],
              [("START", "solver"), ("solver", "END")],
              "CoT baseline (1 agent)", pos_cot, node_size=3600)

    # Planner-Executor — seed graph
    pos_pe = {"START": (0, 0.0), "planner": (1, 1.0), "executor": (2, 0.0),
              "END": (3, 0.0)}
    _draw_dag(axes[1], ["START", "planner", "executor", "END"],
              [("START", "planner"), ("planner", "executor"),
               ("START", "executor"), ("executor", "END")],
              "Planner-Executor seed (2 agents)", pos_pe, node_size=3200)

    # Evolved — 4-agent triage routed example (illustrative AgentClinic v2 iter 3)
    pos_ev = {
        "START": (0, 0.6), "triage": (1, 0.6),
        "gastro": (2, 1.4), "cardio": (2, -0.2),
        "answer": (3, 0.6), "END": (4, 0.6),
    }
    _draw_dag(axes[2], list(pos_ev.keys()),
              [("START", "triage"), ("triage", "gastro"), ("triage", "cardio"),
               ("gastro", "answer"), ("cardio", "answer"), ("answer", "END")],
              "Evolved (4-agent specialist DAG)", pos_ev, node_size=3000, fontsize=10)

    plt.tight_layout()
    plt.savefig(OUT_DIR / "dag_baselines.png", dpi=160, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print("wrote dag_baselines.png")


# ---------------------------------------------------------------------------
# 2. controller_v1_v2_loop.png — v1 thin vs v2 org-designer
# ---------------------------------------------------------------------------


def fig_controller_loop() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(15.5, 6.2))

    for ax, title, sys_prompt_label, output_label, output_color in (
        (axes[0], "v1 controller (thin)",
         "Generic\nedit-the-graph\nsystem prompt",
         'Edit:  "add verifier"\n(generic, no\ndomain vocab)',
         C_ACCENT),
        (axes[1], "v2 controller (organization designer)",
         "Org-designer\nsystem prompt\n+ domain brief\n+ persona rules",
         'Edit:  add\n"differential_diagnostician"\n(cited specialty\n+ procedure)',
         C_FOREST),
    ):
        ax.set_xlim(0, 12)
        ax.set_ylim(0, 8)
        ax.axis("off")
        ax.set_title(title, fontsize=14, weight="bold", color=C_CHARCOAL, pad=12)

        # Trajectory tape (top-left)
        _box(ax, 0.3, 5.5, 3.4, 1.6,
             "Trajectory tape\n(per-task agent steps,\ncorrectness)",
             fill=C_CREAM, fontsize=9.5)
        # System prompt (bottom-left)
        is_v2 = "v2" in title
        _box(ax, 0.3, 2.0, 3.4, 2.4, sys_prompt_label,
             fill=C_MOSS if is_v2 else C_GREY, fontsize=10,
             fontcolor="white" if is_v2 else C_CHARCOAL, weight="bold")
        # Controller LLM (center)
        _box(ax, 4.6, 4.0, 2.6, 1.6, "Controller\nLLM",
             fill=C_FOREST, edge=C_FOREST, fontcolor="white", fontsize=12, weight="bold")
        # Edit batch (top-right) — bigger to fit wrapped text
        _box(ax, 8.1, 5.3, 3.6, 1.9, output_label,
             fill=output_color, edge=output_color, fontcolor="white", fontsize=9.5, weight="bold")
        # Apply edits (bottom-right)
        _box(ax, 8.1, 2.4, 3.6, 1.7, "apply_edits()\n→ updated DAG",
             fill=C_CREAM, fontsize=10)
        # Evaluate (bottom-center)
        _box(ax, 4.6, 0.4, 2.6, 1.4, "Evaluate on val\naccept if Δ > 0",
             fill=C_CHARCOAL, edge=C_CHARCOAL, fontcolor="white", fontsize=10, weight="bold")

        # Arrows
        _arrow(ax, 3.7, 6.3, 4.6, 5.2)   # tape → controller
        _arrow(ax, 3.7, 3.2, 4.6, 4.4)   # sysprompt → controller
        _arrow(ax, 7.2, 5.0, 8.1, 6.0)   # controller → edit
        _arrow(ax, 9.9, 5.3, 9.9, 4.1)   # edit → apply
        _arrow(ax, 8.1, 3.0, 7.2, 1.4)   # apply → eval
        _arrow(ax, 4.6, 1.2, 2.0, 5.5, color=C_GREY)  # eval → tape (loop)

    plt.tight_layout()
    plt.savefig(OUT_DIR / "controller_v1_v2_loop.png", dpi=160, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print("wrote controller_v1_v2_loop.png")


# ---------------------------------------------------------------------------
# 3. paired_batch_flow.png — streaming round flow
# ---------------------------------------------------------------------------


def fig_paired_batch() -> None:
    fig, ax = plt.subplots(figsize=(13, 4.5))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.set_title("Streaming evolve — paired-batch round", fontsize=14, weight="bold",
                 color=C_CHARCOAL, pad=14)

    # Stream pool
    _box(ax, 0.2, 2.0, 2.0, 2.0, "Stream pool\n(train + val,\nbootstrap)",
         fill=C_CREAM, fontsize=10)
    # Sampled batch B
    _box(ax, 2.8, 2.5, 2.0, 1.0, "Sample batch\n(B tasks, replace)",
         fill=C_MOSS, fontsize=10, fontcolor="white", weight="bold")
    # Evaluate best
    _box(ax, 5.4, 4.2, 2.4, 1.0, "Run best_graph\non batch → b_acc",
         fill=C_FOREST, fontcolor="white", fontsize=10, weight="bold")
    # Controller propose edit
    _box(ax, 5.4, 0.8, 2.4, 1.0, "Controller proposes\nedit batch",
         fill=C_FOREST, fontcolor="white", fontsize=10, weight="bold")
    # Apply edits
    _box(ax, 8.4, 0.8, 2.0, 1.0, "apply_edits()\n→ candidate", fill=C_CREAM, fontsize=10)
    # Evaluate candidate (SAME batch)
    _box(ax, 8.4, 4.2, 2.0, 1.0, "Run candidate\non SAME batch → c_acc",
         fill=C_FOREST, fontcolor="white", fontsize=10, weight="bold")
    # Decision
    _box(ax, 11.0, 2.5, 2.6, 1.0, "Δ = c_acc − b_acc\nACCEPT if Δ > ε",
         fill=C_CHARCOAL, fontcolor="white", fontsize=10, weight="bold")

    # Arrows
    _arrow(ax, 2.2, 3.0, 2.8, 3.0)
    _arrow(ax, 4.8, 3.2, 5.4, 4.4)  # batch → eval best
    _arrow(ax, 4.8, 2.8, 5.4, 1.4)  # batch → controller
    _arrow(ax, 7.8, 1.3, 8.4, 1.3)  # controller → apply
    _arrow(ax, 9.4, 1.8, 9.4, 4.2)  # apply → eval candidate
    _arrow(ax, 7.8, 4.7, 8.4, 4.7)  # not actually needed; remove? Keep visual rhythm
    _arrow(ax, 10.4, 4.7, 11.0, 3.4)  # candidate → decision
    _arrow(ax, 7.8, 4.7, 11.0, 3.2, color=C_GREY)  # b_acc → decision

    # Highlight: same batch
    ax.text(9.4, 3.0, "same batch\n(paired)", ha="center", va="center",
            fontsize=10, style="italic", color=C_ACCENT, weight="bold")

    plt.tight_layout()
    plt.savefig(OUT_DIR / "paired_batch_flow.png", dpi=160, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print("wrote paired_batch_flow.png")


# ---------------------------------------------------------------------------
# 4. dag_evolution_seq.png — streaming run #1 R0..R4
# ---------------------------------------------------------------------------


def fig_dag_evolution() -> None:
    """Snapshot five DAGs from streaming run #1 (per pilot.md §8.3)."""
    fig, axes = plt.subplots(1, 5, figsize=(22, 5.0))

    NSIZE = 1900
    FSIZE = 8.0

    # R0 seed: planner + executor (P-E baseline)
    pos0 = {"START": (0, 0.0), "planner": (1, 1.2), "executor": (2, 0.0),
            "END": (3, 0.0)}
    _draw_dag(axes[0], list(pos0.keys()),
              [("START", "planner"), ("planner", "executor"),
               ("START", "executor"), ("executor", "END")],
              "R0 seed\n(2 agents)", pos0, node_size=NSIZE, fontsize=FSIZE)

    # R1 ACCEPT: +differential_diagnostician
    pos1 = {"START": (0, 0.0), "planner": (1, 1.2), "executor": (2, 0.0),
            "diff_dx": (1, 2.4), "END": (3, 0.0)}
    _draw_dag(axes[1], list(pos1.keys()),
              [("START", "planner"), ("planner", "executor"),
               ("START", "executor"), ("executor", "END"),
               ("START", "diff_dx"), ("diff_dx", "planner")],
              "R1 ACCEPT (Δ+1)\n+diff_dx (3 ag)", pos1, node_size=NSIZE, fontsize=FSIZE)

    # R2 ACCEPT: +epidemiology_consultant
    pos2 = {"START": (0, 0.0), "planner": (1.2, 1.2), "executor": (2.4, 0.0),
            "diff_dx": (1.2, 2.4), "epi": (0.0, 2.4), "END": (3.4, 0.0)}
    _draw_dag(axes[2], list(pos2.keys()),
              [("START", "planner"), ("planner", "executor"),
               ("START", "executor"), ("executor", "END"),
               ("START", "diff_dx"), ("diff_dx", "planner"),
               ("START", "epi"), ("epi", "planner")],
              "R2 ACCEPT (Δ+1)\n+epi (5 ag)", pos2, node_size=NSIZE, fontsize=FSIZE)

    # R4 ACCEPT: +adolescent_specialist (skip R3 reject)
    pos4 = {"START": (0, 0.0), "planner": (1.2, 1.2), "executor": (2.4, 0.0),
            "diff_dx": (1.2, 2.4), "epi": (0.0, 2.4), "adol": (2.4, 2.4),
            "END": (3.4, 0.0)}
    _draw_dag(axes[3], list(pos4.keys()),
              [("START", "planner"), ("planner", "executor"),
               ("START", "executor"), ("executor", "END"),
               ("START", "diff_dx"), ("diff_dx", "planner"),
               ("START", "epi"), ("epi", "planner"),
               ("START", "adol"), ("adol", "planner")],
              "R4 ACCEPT (Δ+8)\n+adol (6 ag)", pos4, node_size=NSIZE, fontsize=FSIZE)

    # R8 ACCEPT after R5-R7 reject/INVALID: -planner +differential_generator
    pos8 = {"START": (0, 0.0), "executor": (2.4, 0.0),
            "diff_dx": (1.2, 2.4), "epi": (0.0, 2.4), "adol": (2.4, 2.4),
            "diff_gen": (1.2, 1.2), "END": (3.4, 0.0)}
    _draw_dag(axes[4], list(pos8.keys()),
              [("START", "diff_gen"), ("diff_gen", "diff_dx"),
               ("START", "executor"), ("executor", "END"),
               ("diff_dx", "executor"),
               ("START", "epi"), ("epi", "executor"),
               ("START", "adol"), ("adol", "executor")],
              "R8 ACCEPT (Δ+4)\n−planner +diff_gen", pos8,
              node_size=NSIZE, fontsize=FSIZE)

    plt.tight_layout()
    plt.savefig(OUT_DIR / "dag_evolution_seq.png", dpi=160, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print("wrote dag_evolution_seq.png")


# ---------------------------------------------------------------------------
# 5. per_round_delta.png — streaming run #1 paired Δ
# ---------------------------------------------------------------------------


def fig_per_round_delta() -> None:
    # From pilot.md §8.3 streaming run #1 (B=100 R=10 seed=0)
    rounds = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    deltas = [+1.0, +1.0, -2.0, +8.0, -6.0, None, None, +4.0, None, None]  # None = INVALID
    verdicts = ["ACCEPT", "ACCEPT", "reject", "ACCEPT", "reject",
                "INVALID", "INVALID", "ACCEPT", "INVALID", "INVALID"]

    fig, ax = plt.subplots(figsize=(11, 5))
    bar_colors = []
    for d, v in zip(deltas, verdicts):
        if v == "ACCEPT":
            bar_colors.append(C_FOREST)
        elif v == "reject":
            bar_colors.append(C_CHARCOAL)
        else:
            bar_colors.append(C_ACCENT)

    plot_deltas = [d if d is not None else 0 for d in deltas]
    bars = ax.bar(rounds, plot_deltas, color=bar_colors, edgecolor="white", linewidth=1.0)

    # Annotate verdicts and INVALID bars
    for i, (r, d, v) in enumerate(zip(rounds, deltas, verdicts)):
        if v == "INVALID":
            ax.text(r, 0.5, "INVALID", ha="center", va="bottom", fontsize=9,
                    color=C_ACCENT, weight="bold", rotation=90)
        else:
            ax.text(r, d + (0.4 if d > 0 else -0.7), f"{d:+.0f}",
                    ha="center", va="center", fontsize=9, color=C_CHARCOAL, weight="bold")

    ax.axhline(0, color=C_CHARCOAL, linewidth=0.8)
    ax.set_xticks(rounds)
    ax.set_xlabel("Round", color=C_CHARCOAL)
    ax.set_ylabel("Paired Δ accuracy (pp)", color=C_CHARCOAL)
    ax.set_title("Streaming run #1 (MEDIQ B=100 R=10 seed=0) — per-round paired Δ",
                 fontsize=13, weight="bold", color=C_CHARCOAL, pad=12)
    ax.set_ylim(-9, 11)

    # Legend
    handles = [
        mpatches.Patch(color=C_FOREST, label="ACCEPT (4 / 10)"),
        mpatches.Patch(color=C_CHARCOAL, label="reject (2 / 10)"),
        mpatches.Patch(color=C_ACCENT, label="INVALID (4 / 10)"),
    ]
    ax.legend(handles=handles, loc="upper right", frameon=False)

    plt.tight_layout()
    plt.savefig(OUT_DIR / "per_round_delta.png", dpi=160, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print("wrote per_round_delta.png")


# ---------------------------------------------------------------------------
# 6. token_cost_pareto.png — token cost vs accuracy
# ---------------------------------------------------------------------------


def fig_token_pareto() -> None:
    """Approximate Pareto from pilot.md numbers: tokens-per-task vs test accuracy."""
    # Per-method dots (single representative numbers from various runs):
    # calib_01 (GSM8K, n=50): CoT 92% / P-E 90% / Evolved 86% — approx tokens via §4.5
    # n30_v2_mediq: CoT 43.3% / P-E 46.7% / Evolved 43.3% (approx tokens)
    # streaming_v2_mediq_b100r10_s0: CoT 68% / P-E 58% / Evolved 62%, tokens 23k/39.4k/144.8k
    #
    # We focus on the streaming run #1 numbers (most authoritative test eval):
    #   tokens_per_task = run_total / n_test
    streaming_data = {
        "CoT": (23000 / 50, 0.68),
        "P-E": (39400 / 50, 0.58),
        "Evolved (6 ag)": (144800 / 50, 0.62),
    }

    fig, ax = plt.subplots(figsize=(9.5, 6))
    color_map = {"CoT": C_MOSS, "P-E": C_CHARCOAL, "Evolved (6 ag)": C_FOREST}
    for label, (tok, acc) in streaming_data.items():
        ax.scatter(tok, acc, s=240, color=color_map[label], edgecolor="white",
                   linewidth=2, zorder=3)
        ax.annotate(label, (tok, acc), textcoords="offset points",
                    xytext=(12, 6), fontsize=11, color=C_CHARCOAL, weight="bold")

    # Pareto frontier hint
    ax.plot([23000 / 50, 144800 / 50], [0.68, 0.62], "--", color=C_GREY, linewidth=1.2,
            zorder=1, alpha=0.7)
    ax.text(1900, 0.71, "more tokens ↛ more accuracy\n(on this MEDIQ split)",
            fontsize=10, color=C_ACCENT, style="italic", weight="bold")

    ax.set_xlabel("Tokens per task (avg)", color=C_CHARCOAL)
    ax.set_ylabel("Test accuracy (n=50)", color=C_CHARCOAL)
    ax.set_title("Token vs accuracy — streaming run #1 (MEDIQ seed=0)",
                 fontsize=13, weight="bold", color=C_CHARCOAL, pad=12)
    ax.set_ylim(0.40, 0.80)
    ax.grid(alpha=0.25)

    plt.tight_layout()
    plt.savefig(OUT_DIR / "token_cost_pareto.png", dpi=160, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print("wrote token_cost_pareto.png")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fig_dag_baselines()
    fig_controller_loop()
    fig_paired_batch()
    fig_dag_evolution()
    fig_per_round_delta()
    fig_token_pareto()
    print(f"\nAll figures in {OUT_DIR}")
