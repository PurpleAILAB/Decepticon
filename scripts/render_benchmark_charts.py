"""Render PNG charts for the XBOW benchmark write-ups.

Outputs go to assets/benchmark/. Re-run after updating numbers:
    python scripts/render_benchmark_charts.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Data — keep in one place so the script is the single source of truth.
# ---------------------------------------------------------------------------

OUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "benchmark"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Leaderboard — XBOW publishers only.
LEADERBOARD = [
    ("Shannon Lite (white-box)", 96.15, "other"),
    ("Strix", 96.15, "other"),
    ("PentestGPT", 86.50, "other"),
    ("Red-MIRROR", 86.00, "other"),
    ("XBOW (commercial)", 85.00, "other"),
    ("Cyber-AutoAgent (archived)", 84.62, "other"),
    ("MAPTA", 76.90, "other"),
    ("Decepticon (L1+L3, L2 ongoing)", 92.50, "us"),
    ("PentestAgent", 50.00, "other"),
    ("AutoPT", 46.00, "other"),
    ("VulnBot", 6.00, "other"),
]

# Per-difficulty data (where the project published it).
DIFFICULTY = {
    "Strix": [100.0, 96.0, 75.0],
    "PentestGPT": [91.1, 74.5, 62.5],
    "Decepticon": [93.3, 17.6, 87.5],  # L2 is in progress
}
LEVELS = ["L1 (Easy)", "L2 (Medium)", "L3 (Hard)"]

# Decepticon — pass/fail on L1+L3 only (the comparable, completed slice).
# L2 (51 challenges) is still being run, so it is intentionally excluded
# from the headline charts; tracked separately.
DECEPTICON_PIE = [
    ("L1 passed (42 / 45)", 42, "#2ecc71"),
    ("L3 passed (7 / 8)", 7, "#27ae60"),
    ("Not solved (L1+L3)", 4, "#bdc3c7"),
]

# Decepticon attack-class coverage — L1 + L3 contributions only.
# L2 confirmed solves are shown separately in the README matrix; excluded
# from this chart so the perspective stays "completed sweeps only."
COVERAGE = [
    ("XSS", 11),  # 8 L1 + 3 L3
    ("Command Injection", 6),  # 6 L1
    ("Default Credentials", 5),  # 4 L1 + 1 L3
    ("SSTI", 5),  # 4 L1 + 1 L3
    ("SQL Injection", 5),  # 5 L1
    ("IDOR", 4),  # 4 L1
    ("LFI", 4),  # 4 L1
    ("Privilege Escalation", 4),  # 4 L1
    ("Information Disc.", 4),  # 4 L1
    ("Business Logic", 4),  # 4 L1
    ("SSRF", 3),  # 3 L1
    ("Path Traversal", 3),  # 3 L1
    ("XXE", 3),  # 3 L1
    ("Arbitrary Upload", 3),  # 3 L1
    ("Insecure Deserial.", 2),  # 1 L1 + 1 L3
]

# ---------------------------------------------------------------------------
# Chart helpers.
# ---------------------------------------------------------------------------

US_COLOR = "#e74c3c"  # Decepticon red
BAR_COLOR = "#3498db"  # everyone else

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titleweight": "bold",
    }
)


def save(fig: plt.Figure, name: str) -> Path:
    out = OUT_DIR / name
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 1) Leaderboard — horizontal bar chart of overall pass rate.
# ---------------------------------------------------------------------------


def chart_leaderboard() -> Path:
    items = sorted(LEADERBOARD, key=lambda r: r[1])  # ascending so highest is on top
    labels = [r[0] for r in items]
    values = [r[1] for r in items]
    colors = [US_COLOR if r[2] == "us" else BAR_COLOR for r in items]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(labels, values, color=colors, edgecolor="white")
    for bar, v in zip(bars, values):
        ax.text(
            v + 1,
            bar.get_y() + bar.get_height() / 2,
            f"{v:.2f} %" if v % 1 else f"{v:.0f} %",
            va="center",
            fontsize=9,
        )
    ax.set_xlim(0, 105)
    ax.set_xlabel("Pass rate on XBOW (104 challenges) — %")
    ax.set_title("XBOW Validation Benchmark — Published Results")
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    fig.text(
        0.01,
        0.01,
        "Shannon: white-box, hint-removed.  Decepticon: black-box, L2 sweep ongoing (L1+L3 only).",
        fontsize=8,
        style="italic",
        color="#555",
    )
    return save(fig, "leaderboard.png")


# ---------------------------------------------------------------------------
# 2) Per-difficulty grouped bars.
# ---------------------------------------------------------------------------


def chart_difficulty() -> Path:
    systems = list(DIFFICULTY.keys())
    n_levels = len(LEVELS)
    x = np.arange(n_levels)
    width = 0.25

    fig, ax = plt.subplots(figsize=(9, 5))
    palette = {"Strix": "#3498db", "PentestGPT": "#9b59b6", "Decepticon": US_COLOR}
    for i, sys in enumerate(systems):
        offset = (i - 1) * width
        bars = ax.bar(
            x + offset, DIFFICULTY[sys], width, label=sys, color=palette[sys], edgecolor="white"
        )
        for j, (bar, v) in enumerate(zip(bars, DIFFICULTY[sys])):
            label = f"{v:.1f} %"
            if sys == "Decepticon" and j == 1:
                label = f"{v:.1f} % *"
            ax.text(bar.get_x() + bar.get_width() / 2, v + 1.5, label, ha="center", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(LEVELS)
    ax.set_ylim(0, 110)
    ax.set_ylabel("Pass rate (%)")
    ax.set_title("Pass Rate by Difficulty — Strix · PentestGPT · Decepticon")
    ax.legend(loc="upper right", frameon=False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    fig.text(
        0.01,
        0.01,
        "* Decepticon L2 sweep is in progress — number will rise.",
        fontsize=8,
        style="italic",
        color="#555",
    )
    return save(fig, "difficulty.png")


# ---------------------------------------------------------------------------
# 3) Decepticon donut by difficulty.
# ---------------------------------------------------------------------------


def chart_decepticon_donut() -> Path:
    labels = [r[0] for r in DECEPTICON_PIE]
    sizes = [r[1] for r in DECEPTICON_PIE]
    colors = [r[2] for r in DECEPTICON_PIE]
    total = sum(sizes)

    fig, ax = plt.subplots(figsize=(7, 6))
    wedges, _ = ax.pie(
        sizes,
        colors=colors,
        startangle=90,
        counterclock=False,
        wedgeprops={"edgecolor": "white", "linewidth": 2, "width": 0.4},
    )
    legend = [f"{lab} — {n} ({n / total:.1%})" for lab, n in zip(labels, sizes)]
    ax.legend(
        wedges, legend, loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=10
    )
    ax.set_title(
        "Decepticon on XBOW — L1 + L3 (completed sweeps)\n"
        "49 / 53 = 92.5 %  ·  L2 sweep in progress (shown separately)",
        fontsize=12,
    )
    return save(fig, "decepticon_donut.png")


# ---------------------------------------------------------------------------
# 4) Decepticon attack-class coverage.
# ---------------------------------------------------------------------------


def chart_coverage() -> Path:
    items = list(reversed(COVERAGE))  # so largest is at the top after barh
    labels = [r[0] for r in items]
    values = [r[1] for r in items]

    fig, ax = plt.subplots(figsize=(9, 7))
    bars = ax.barh(labels, values, color=US_COLOR, edgecolor="white")
    for bar, v in zip(bars, values):
        ax.text(v + 0.15, bar.get_y() + bar.get_height() / 2, str(v), va="center", fontsize=9)
    ax.set_xlim(0, max(values) + 2)
    ax.set_xlabel("Confirmed end-to-end exploits (L1 + L3 only)")
    ax.set_title("Decepticon — Web Attack Class Coverage on XBOW (L1 + L3)")
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    fig.text(
        0.01,
        0.01,
        "L2 sweep is in progress — L2 contributions tracked separately in benchmark/results/README.md.",
        fontsize=8,
        style="italic",
        color="#555",
    )
    return save(fig, "coverage.png")


def main() -> None:
    for fn in (chart_leaderboard, chart_difficulty, chart_decepticon_donut, chart_coverage):
        path = fn()
        print(f"wrote {path.relative_to(OUT_DIR.parents[1])}")


if __name__ == "__main__":
    main()
