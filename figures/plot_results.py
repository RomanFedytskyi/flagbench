"""
Generate Figures 1–4 from results/summary_*.json files.

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

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

RESULTS_DIR = Path(__file__).parent.parent / "results"
FIGURES_DIR = Path(__file__).parent

GROUPS = ["normal_ops", "boundary_conditions", "fallback_trigger", "adversarial"]
GROUP_LABELS = ["Normal ops", "Boundary", "Fallback trigger", "Adversarial"]


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


def fig1_accuracy_heatmap(summaries: dict[str, dict]) -> None:
    """Heatmap: adapter × scenario group → resolution accuracy."""
    adapters = list(summaries.keys())
    data = np.zeros((len(adapters), len(GROUPS)))
    for i, adapter in enumerate(adapters):
        pg = summaries[adapter].get("per_group", {})
        for j, group in enumerate(GROUPS):
            data[i, j] = pg.get(group, {}).get("accuracy", 0.0)

    fig, ax = plt.subplots(figsize=(7, max(2.5, len(adapters) * 1.2)))
    im = ax.imshow(data, vmin=0, vmax=1, cmap="YlGn", aspect="auto")
    plt.colorbar(im, ax=ax, label="Resolution accuracy")
    ax.set_xticks(range(len(GROUPS)))
    ax.set_xticklabels(GROUP_LABELS, rotation=20, ha="right", fontsize=9)
    ax.set_yticks(range(len(adapters)))
    ax.set_yticklabels(adapters, fontsize=9)
    for i in range(len(adapters)):
        for j in range(len(GROUPS)):
            ax.text(j, i, f"{data[i, j]:.2f}", ha="center", va="center",
                    fontsize=8, color="black" if data[i, j] > 0.4 else "white")
    ax.set_title("Fig 1 — Resolution accuracy by adapter and scenario group", fontsize=10)
    fig.tight_layout()
    out = FIGURES_DIR / "fig1_accuracy_heatmap.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Saved {out}")


def fig2_latency_cdf(summaries: dict[str, dict]) -> None:
    """Latency CDF — P50/P90/P99 bar chart per adapter."""
    adapters = list(summaries.keys())
    p50 = [summaries[a]["overall"]["latency_ms"].get("p50", 0) for a in adapters]
    p90 = [summaries[a]["overall"]["latency_ms"].get("p90", 0) for a in adapters]
    p99 = [summaries[a]["overall"]["latency_ms"].get("p99", 0) for a in adapters]

    x = np.arange(len(adapters))
    w = 0.25
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(x - w, p50, w, label="P50", color="#4a90d9")
    ax.bar(x,     p90, w, label="P90", color="#f5a623")
    ax.bar(x + w, p99, w, label="P99", color="#d0021b")
    ax.set_xticks(x)
    ax.set_xticklabels(adapters, fontsize=9)
    ax.set_ylabel("Latency (ms)", fontsize=9)
    ax.set_title("Fig 2 — Resolution latency percentiles by adapter", fontsize=10)
    ax.legend(fontsize=8)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f"))
    fig.tight_layout()
    out = FIGURES_DIR / "fig2_latency_cdf.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Saved {out}")


def fig3_compliance_violations(summaries: dict[str, dict]) -> None:
    """Compliance violation count per scenario group per adapter."""
    adapters = list(summaries.keys())
    x = np.arange(len(GROUPS))
    w = 0.8 / max(len(adapters), 1)

    fig, ax = plt.subplots(figsize=(7, 3.5))
    colors = ["#4a90d9", "#f5a623", "#7ed321", "#d0021b"]
    for i, adapter in enumerate(adapters):
        pg = summaries[adapter].get("per_group", {})
        vals = [pg.get(g, {}).get("compliance_violations", 0) for g in GROUPS]
        offset = (i - len(adapters) / 2 + 0.5) * w
        ax.bar(x + offset, vals, w * 0.9, label=adapter, color=colors[i % len(colors)])

    ax.set_xticks(x)
    ax.set_xticklabels(GROUP_LABELS, rotation=15, ha="right", fontsize=9)
    ax.set_ylabel("Compliance violations", fontsize=9)
    ax.set_title("Fig 3 — Compliance violation count by scenario group", fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()
    out = FIGURES_DIR / "fig3_compliance_violations.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Saved {out}")


def fig4_property_matrix(summaries: dict[str, dict]) -> None:
    """
    Property pass/fail matrix — placeholder until oracle results are piped in.
    Reads results/properties_<adapter>.json if available, else shows N/A.
    """
    PROPERTIES = ["Determinism", "Fallback safety", "Compliance precedence", "Monotonic rollout"]
    adapters = list(summaries.keys())
    data = np.full((len(adapters), len(PROPERTIES)), 0.5)  # 0.5 = unknown

    for i, adapter in enumerate(adapters):
        prop_file = RESULTS_DIR / f"properties_{adapter}.json"
        if prop_file.exists():
            props = json.loads(prop_file.read_text())
            for j, p in enumerate(["determinism", "fallback_safety",
                                    "compliance_precedence", "monotonic_rollout"]):
                data[i, j] = 1.0 if props.get(p, {}).get("passed", False) else 0.0

    fig, ax = plt.subplots(figsize=(7, max(2.5, len(adapters) * 1.2)))
    im = ax.imshow(data, vmin=0, vmax=1, cmap="RdYlGn", aspect="auto")
    ax.set_xticks(range(len(PROPERTIES)))
    ax.set_xticklabels(PROPERTIES, rotation=20, ha="right", fontsize=9)
    ax.set_yticks(range(len(adapters)))
    ax.set_yticklabels(adapters, fontsize=9)
    for i in range(len(adapters)):
        for j in range(len(PROPERTIES)):
            v = data[i, j]
            label = "PASS" if v == 1.0 else ("FAIL" if v == 0.0 else "N/A")
            ax.text(j, i, label, ha="center", va="center", fontsize=8,
                    color="black" if 0.3 < v < 0.8 else "white")
    ax.set_title("Fig 4 — Property pass/fail matrix", fontsize=10)
    fig.tight_layout()
    out = FIGURES_DIR / "fig4_property_matrix.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Saved {out}")


if __name__ == "__main__":
    print("[flagbench] Generating figures...")
    summaries = _load_summaries()
    fig1_accuracy_heatmap(summaries)
    fig2_latency_cdf(summaries)
    fig3_compliance_violations(summaries)
    fig4_property_matrix(summaries)
    print("[flagbench] All figures written to figures/")
