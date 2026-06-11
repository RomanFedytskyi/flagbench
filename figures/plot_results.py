"""
Generate Figures 1–4 in IEEE publication style.

Usage:
    python figures/plot_results.py

Output: figures/fig1_accuracy_heatmap.png
        figures/fig2_latency_cdf.png
        figures/fig3_compliance_violations.png
        figures/fig4_property_matrix.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# IEEE style base
# ---------------------------------------------------------------------------
mpl.rcParams.update({
    "font.family":        "serif",
    "font.serif":         ["Times New Roman", "DejaVu Serif", "serif"],
    "font.size":          10,
    "axes.titlesize":     10,
    "axes.labelsize":     10,
    "xtick.labelsize":    9,
    "ytick.labelsize":    9,
    "legend.fontsize":    9,
    "figure.dpi":         300,
    "savefig.dpi":        300,
    "savefig.bbox":       "tight",
    "savefig.pad_inches": 0.12,
    "axes.linewidth":     0.8,
    "axes.spines.top":    False,
    "axes.spines.right":  False,
    "axes.grid":          True,
    "grid.color":         "#e0e0e0",
    "grid.linewidth":     0.5,
    "grid.linestyle":     "--",
    "axes.axisbelow":     True,
    "xtick.direction":    "out",
    "ytick.direction":    "out",
    "xtick.major.size":   3,
    "ytick.major.size":   3,
})

# ---------------------------------------------------------------------------
# Colour palette — Okabe–Ito (colour-blind safe, prints well in greyscale)
# ---------------------------------------------------------------------------
COLORS = {
    "reference":   "#0072B2",   # blue
    "unleash_sim": "#D55E00",   # vermillion
    "pass":        "#009E73",   # green
    "fail":        "#CC0000",   # red
    "neutral":     "#AAAAAA",   # grey
    "p50":         "#0072B2",
    "p90":         "#E69F00",
    "p99":         "#D55E00",
}

ADAPTER_COLORS = [COLORS["reference"], COLORS["unleash_sim"],
                  "#009E73", "#CC79A7"]

RESULTS_DIR = Path(__file__).parent.parent / "results"
FIGURES_DIR = Path(__file__).parent

GROUPS       = ["normal_ops", "boundary_conditions", "fallback_trigger", "adversarial"]
GROUP_LABELS = ["Normal ops", "Boundary\nconditions", "Fallback\ntrigger", "Adversarial"]

# Shorter labels so column headers don't collide in Fig 4
PROP_KEYS    = ["determinism", "fallback_safety", "compliance_precedence", "monotonic_rollout"]
PROP_LABELS  = ["Determinism", "Fallback\nSafety", "Compliance\nPrec.", "Monotonic\nRollout"]


def _load_summaries() -> dict[str, dict]:
    summaries = {}
    for f in sorted(RESULTS_DIR.glob("summary_*.json")):
        adapter = f.stem.replace("summary_", "")
        summaries[adapter] = json.loads(f.read_text())
    if not summaries:
        raise FileNotFoundError(
            f"No summary JSON files found in {RESULTS_DIR}.\n"
            "Run: python -m flagbench.harness --adapter reference"
        )
    return summaries


# ---------------------------------------------------------------------------
# Fig 1 — Accuracy heatmap
# ---------------------------------------------------------------------------
def fig1_accuracy_heatmap(summaries: dict[str, dict]) -> None:
    adapters = list(summaries.keys())
    n_rows = len(adapters)
    data = np.zeros((n_rows, len(GROUPS)))
    for i, adapter in enumerate(adapters):
        pg = summaries[adapter].get("per_group", {})
        for j, group in enumerate(GROUPS):
            data[i, j] = pg.get(group, {}).get("accuracy", 0.0)

    # Size: wide enough for 4 columns + colorbar, tall per row
    fig, ax = plt.subplots(figsize=(5.5, 1.4 + n_rows * 0.9))

    cmap = mpl.colors.LinearSegmentedColormap.from_list(
        "ieee_blue", ["#FFFFFF", "#C6DBEF", "#6BAED6", "#2171B5", "#08306B"]
    )
    im = ax.imshow(data, vmin=0, vmax=1, cmap=cmap, aspect="auto")

    cbar = plt.colorbar(im, ax=ax, fraction=0.03, pad=0.04)
    cbar.set_label("Resolution accuracy", fontsize=9)
    cbar.ax.tick_params(labelsize=8)

    ax.set_xticks(range(len(GROUPS)))
    ax.set_xticklabels(GROUP_LABELS, fontsize=9)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(adapters, fontsize=9)
    ax.grid(False)
    ax.tick_params(axis="x", bottom=False)

    for i in range(n_rows):
        for j in range(len(GROUPS)):
            v = data[i, j]
            color = "white" if v > 0.55 else "black"
            ax.text(j, i, f"{v:.3f}", ha="center", va="center",
                    fontsize=9, color=color, fontweight="bold")

    ax.set_title("Fig. 1 — Resolution accuracy by adapter and scenario group",
                 pad=8, loc="left", fontsize=10)
    fig.tight_layout()
    out = FIGURES_DIR / "fig1_accuracy_heatmap.png"
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved {out.name}")


# ---------------------------------------------------------------------------
# Fig 2 — Latency percentile bar chart
# ---------------------------------------------------------------------------
def fig2_latency_cdf(summaries: dict[str, dict]) -> None:
    adapters = list(summaries.keys())
    p50 = [summaries[a]["overall"]["latency_ms"].get("p50", 0) * 1000 for a in adapters]
    p90 = [summaries[a]["overall"]["latency_ms"].get("p90", 0) * 1000 for a in adapters]
    p99 = [summaries[a]["overall"]["latency_ms"].get("p99", 0) * 1000 for a in adapters]

    x = np.arange(len(adapters))
    w = 0.22
    fig, ax = plt.subplots(figsize=(5.5, 3.2))

    b1 = ax.bar(x - w, p50, w, label="P50", color=COLORS["p50"],
                edgecolor="white", linewidth=0.5)
    b2 = ax.bar(x,     p90, w, label="P90", color=COLORS["p90"],
                edgecolor="white", linewidth=0.5)
    b3 = ax.bar(x + w, p99, w, label="P99", color=COLORS["p99"],
                edgecolor="white", linewidth=0.5)

    # Value labels — placed inside bars near the top (avoids clipping legend)
    for bars in [b1, b2, b3]:
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                # place label inside bar if tall enough, otherwise above
                inside = h > max(p99) * 0.15
                y_pos  = h * 0.88 if inside else h + max(p99) * 0.02
                v_align = "top" if inside else "bottom"
                txt_color = "white" if inside else "black"
                ax.text(bar.get_x() + bar.get_width() / 2, y_pos,
                        f"{h:.1f}",
                        ha="center", va=v_align,
                        fontsize=8, color=txt_color, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(adapters, fontsize=9)
    ax.set_ylabel("Latency (μs)")
    max_val = max(p99) if p99 else 1
    ax.set_ylim(0, max_val * 1.18)

    # Legend in lower-right where bars are shortest
    ax.legend(loc="lower right", framealpha=0.95, edgecolor="#cccccc")
    ax.set_title("Fig. 2 — Resolution latency percentiles (μs)", pad=8, loc="left")
    fig.tight_layout()
    out = FIGURES_DIR / "fig2_latency_cdf.png"
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved {out.name}")


# ---------------------------------------------------------------------------
# Fig 3 — Compliance violations grouped bar
# ---------------------------------------------------------------------------
def fig3_compliance_violations(summaries: dict[str, dict]) -> None:
    adapters = list(summaries.keys())
    x = np.arange(len(GROUPS))
    w = 0.7 / max(len(adapters), 1)

    # Extra bottom margin for the two-line group labels
    fig, ax = plt.subplots(figsize=(5.5, 3.6))

    max_val = 0
    for i, adapter in enumerate(adapters):
        pg = summaries[adapter].get("per_group", {})
        vals = [pg.get(g, {}).get("compliance_violations", 0) for g in GROUPS]
        max_val = max(max_val, max(vals))
        offset = (i - len(adapters) / 2 + 0.5) * w
        bars = ax.bar(x + offset, vals, w * 0.90,
                      label=adapter,
                      color=ADAPTER_COLORS[i % len(ADAPTER_COLORS)],
                      edgecolor="white", linewidth=0.5)
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h + max_val * 0.01,
                        str(int(h)), ha="center", va="bottom",
                        fontsize=8, fontweight="bold")

    ax.set_xticks(x)
    # Two-line labels sit cleanly without rotation
    ax.set_xticklabels(GROUP_LABELS, fontsize=9, linespacing=1.4)
    ax.set_ylabel("Compliance violations (count)")
    ax.set_ylim(0, max_val * 1.20)
    ax.legend(loc="upper right", framealpha=0.95, edgecolor="#cccccc")
    ax.set_title("Fig. 3 — Compliance violations by scenario group", pad=8, loc="left")
    fig.tight_layout()
    out = FIGURES_DIR / "fig3_compliance_violations.png"
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved {out.name}")


# ---------------------------------------------------------------------------
# Fig 4 — Property pass/fail matrix (drawn as explicit rectangles)
# ---------------------------------------------------------------------------
def fig4_property_matrix(summaries: dict[str, dict]) -> None:
    adapters = list(summaries.keys())
    n_rows = len(adapters)
    n_cols = len(PROP_KEYS)

    # Resolve pass/fail/unknown for each cell
    cell_state: list[list[str]] = []   # "pass" | "fail" | "na"
    for adapter in adapters:
        row = []
        prop_file = RESULTS_DIR / f"properties_{adapter}.json"
        if prop_file.exists():
            props = json.loads(prop_file.read_text())
            for key in PROP_KEYS:
                entry = props.get(key, {})
                if "passed" not in entry:
                    row.append("na")
                elif entry["passed"]:
                    row.append("pass")
                else:
                    row.append("fail")
        else:
            row = ["na"] * n_cols
        cell_state.append(row)

    # --- Figure geometry ---
    cell_w = 1.15   # inches per column
    cell_h = 0.70   # inches per row
    margin_l, margin_r = 0.95, 0.20
    margin_t, margin_b = 0.55, 1.05  # extra bottom: 2-line labels + legend
    fig_w = margin_l + n_cols * cell_w + margin_r
    fig_h = margin_t + n_rows * cell_h + margin_b

    fig = plt.figure(figsize=(fig_w, fig_h))

    # Axes covering the cell grid only (no ticks — we draw everything manually)
    ax = fig.add_axes([
        margin_l / fig_w,
        margin_b / fig_h,
        (n_cols * cell_w) / fig_w,
        (n_rows * cell_h) / fig_h,
    ])
    ax.set_xlim(0, n_cols)
    ax.set_ylim(0, n_rows)
    ax.axis("off")

    STATE_COLOR = {
        "pass": COLORS["pass"],
        "fail": COLORS["fail"],
        "na":   COLORS["neutral"],
    }
    STATE_LABEL = {
        "pass": "PASS",
        "fail": "FAIL",
        "na":   "N/A",
    }

    # Draw cells bottom-up (row 0 = top adapter visually → y = n_rows-1)
    for i, adapter in enumerate(adapters):
        y_center = n_rows - i - 0.5   # vertical centre of row i
        for j, key in enumerate(PROP_KEYS):
            state = cell_state[i][j]
            color = STATE_COLOR[state]
            x0, y0 = j + 0.04, y_center - 0.42

            # Coloured rectangle
            rect = mpatches.FancyBboxPatch(
                (x0, y0), cell_w - 0.08, 0.84,
                boxstyle="round,pad=0.03",
                facecolor=color, edgecolor="white", linewidth=1.5,
                transform=ax.transData, clip_on=False,
            )
            ax.add_patch(rect)

            # Centred label in white bold
            ax.text(j + cell_w / 2, y_center,
                    STATE_LABEL[state],
                    ha="center", va="center",
                    fontsize=11, color="white", fontweight="bold",
                    transform=ax.transData)

    # Y-axis adapter labels (right-align, centred vertically per row)
    for i, adapter in enumerate(adapters):
        y_center = n_rows - i - 0.5
        ax.text(-0.08, y_center, adapter,
                ha="right", va="center",
                fontsize=9, transform=ax.transData)

    # X-axis property labels (centred under each column)
    for j, label in enumerate(PROP_LABELS):
        ax.text(j + cell_w / 2, -0.15, label,
                ha="center", va="top",
                fontsize=9, transform=ax.transData,
                linespacing=1.4)

    # Title
    fig.text(margin_l / fig_w, (margin_b + n_rows * cell_h + 0.12) / fig_h,
             "Fig. 4 — Correctness property pass/fail matrix",
             ha="left", va="bottom", fontsize=10,
             fontfamily="serif")

    # Legend
    patches = [
        mpatches.Patch(color=COLORS["pass"],    label="Pass"),
        mpatches.Patch(color=COLORS["fail"],    label="Fail"),
        mpatches.Patch(color=COLORS["neutral"], label="N/A"),
    ]
    fig.legend(handles=patches, loc="lower center",
               bbox_to_anchor=(0.5, 0.01), ncol=3,
               fontsize=9, framealpha=0.95, edgecolor="#cccccc")

    out = FIGURES_DIR / "fig4_property_matrix.png"
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved {out.name}")


if __name__ == "__main__":
    print("[flagbench] Generating IEEE-style figures...")
    summaries = _load_summaries()
    fig1_accuracy_heatmap(summaries)
    fig2_latency_cdf(summaries)
    fig3_compliance_violations(summaries)
    fig4_property_matrix(summaries)
    print("[flagbench] Done — figures written to figures/")
