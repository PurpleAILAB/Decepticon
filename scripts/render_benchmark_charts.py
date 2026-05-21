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
    ("Decepticon", 98.08, "us"),
    ("PentestAgent", 50.00, "other"),
    ("AutoPT", 46.00, "other"),
    ("VulnBot", 6.00, "other"),
]

# Per-difficulty data (where the project published it).
DIFFICULTY = {
    "Strix": [100.0, 96.0, 75.0],
    "PentestGPT": [91.1, 74.5, 62.5],
    "Decepticon": [100.0, 98.0, 87.5],  # L2 sweep ongoing (1 fail), L3 ongoing (1 fail)
}
LEVELS = ["L1 (Easy)", "L2 (Medium)", "L3 (Hard)"]

# Decepticon — all-level pass/fail (L1+L2+L3 combined view).
# L2 sweep still has 1 outstanding fail; L3 still has 1 outstanding fail.
DECEPTICON_PIE = [
    ("L1 passed (45 / 45)", 45, "#27ae60"),
    ("L2 passed (50 / 51)", 50, "#2ecc71"),
    ("L3 passed (7 / 8)", 7, "#16a085"),
    ("Not solved (2 / 104)", 2, "#bdc3c7"),
]

# Decepticon attack-class coverage — L1 + L2 + L3 totals.
COVERAGE = [
    ("XSS", 14),  # 8 L1 + 3 L2 + 3 L3
    ("Command Injection", 8),  # 6 L1 + 2 L2
    ("Default Credentials", 8),  # 4 L1 + 3 L2 + 1 L3
    ("SSTI", 7),  # 4 L1 + 2 L2 + 1 L3
    ("IDOR", 7),  # 4 L1 + 3 L2
    ("LFI", 6),  # 4 L1 + 2 L2
    ("Arbitrary Upload", 5),  # 3 L1 + 2 L2
    ("SQL Injection", 5),  # 5 L1
    ("Privilege Escalation", 5),  # 4 L1 + 1 L2
    ("Information Disc.", 4),  # 4 L1
    ("Business Logic", 4),  # 4 L1
    ("Path Traversal", 4),  # 3 L1 + 1 L2
    ("Insecure Deserial.", 3),  # 1 L1 + 1 L2 + 1 L3
    ("SSRF", 3),  # 3 L1
    ("XXE", 3),  # 3 L1
    ("Known-CVE", 3),  # 2 L1 + 1 L2
    ("Blind SQLi", 2),  # 1 L1 + 1 L2
    ("GraphQL", 2),  # 1 L1 + 1 L2
    ("JWT", 1),  # 1 L1
    ("SSH", 1),  # 1 L1
    ("Brute Force", 1),  # 1 L2
    ("Race Condition", 1),  # 1 L3
    ("Cryptography", 1),  # 1 L3
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
    is_us = [r[2] == "us" for r in items]
    colors = [US_COLOR if u else BAR_COLOR for u in is_us]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(labels, values, color=colors, edgecolor="white")
    for bar, v, u in zip(bars, values, is_us):
        ax.text(
            v + 1,
            bar.get_y() + bar.get_height() / 2,
            f"{v:.2f} %" if v % 1 else f"{v:.0f} %",
            va="center",
            fontsize=11 if u else 9,
            fontweight="bold" if u else "normal",
            color=US_COLOR if u else "#222",
        )
    # Bold the Decepticon y-tick label.
    for tick, u in zip(ax.get_yticklabels(), is_us):
        if u:
            tick.set_fontweight("bold")
            tick.set_color(US_COLOR)
    ax.set_xlim(0, 105)
    ax.set_xlabel("Pass rate on XBOW (104 challenges) — %")
    ax.set_title("XBOW Validation Benchmark — Published Results", fontweight="bold")
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    fig.text(
        0.01,
        0.01,
        "Shannon: white-box, hint-removed.  Decepticon: black-box, vulnerability tags as hint — 102 / 104.",
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
        for bar, v in zip(bars, DIFFICULTY[sys]):
            label = f"{v:.1f} %"
            ax.text(bar.get_x() + bar.get_width() / 2, v + 1.5, label, ha="center", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(LEVELS)
    ax.set_ylim(0, 110)
    ax.set_ylabel("Pass rate (%)")
    ax.set_title("Pass Rate by Difficulty — Strix · PentestGPT · Decepticon")
    ax.legend(loc="upper right", frameon=False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    return save(fig, "difficulty.png")


# ---------------------------------------------------------------------------
# 3) Decepticon donut by difficulty.
# ---------------------------------------------------------------------------


def chart_decepticon_donut() -> Path:
    labels = [r[0] for r in DECEPTICON_PIE]
    sizes = [r[1] for r in DECEPTICON_PIE]
    colors = [r[2] for r in DECEPTICON_PIE]
    total = sum(sizes)
    passed = sum(n for lab, n, _ in DECEPTICON_PIE if "Not solved" not in lab)

    fig, ax = plt.subplots(figsize=(8, 7))
    wedges, _ = ax.pie(
        sizes,
        colors=colors,
        startangle=90,
        counterclock=False,
        wedgeprops={"edgecolor": "white", "linewidth": 3, "width": 0.42},
    )
    # Centre callout — the headline metric.
    ax.text(
        0,
        0.18,
        f"{passed / total:.2%}",
        ha="center",
        va="center",
        fontsize=44,
        fontweight="bold",
        color="#1d3557",
    )
    ax.text(
        0,
        -0.08,
        f"{passed} / {total}",
        ha="center",
        va="center",
        fontsize=20,
        color="#457b9d",
    )
    ax.text(
        0,
        -0.22,
        "XBOW pass rate",
        ha="center",
        va="center",
        fontsize=11,
        color="#6c757d",
    )
    legend = [f"{lab} — {n} ({n / total:.1%})" for lab, n in zip(labels, sizes)]
    ax.legend(
        wedges,
        legend,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.08),
        ncol=2,
        frameon=False,
        fontsize=10,
    )
    ax.set_title(
        "Decepticon — XBOW Validation Benchmark",
        fontsize=14,
        fontweight="bold",
        pad=18,
    )
    fig.text(
        0.5,
        0.02,
        "L1 100 %  ·  L2 98.0 %  ·  L3 87.5 %  ·  black-box (vulnerability tags as hint)",
        ha="center",
        fontsize=9,
        color="#6c757d",
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
    ax.set_xlabel("Confirmed end-to-end exploits (L1 + L2 + L3)")
    ax.set_title("Decepticon — Web Attack Class Coverage on XBOW (L1 + L2 + L3)")
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    fig.text(
        0.01,
        0.01,
        "Per-level breakdown lives in benchmark/results/README.md (Confirmed Exploit Coverage matrix).",
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
