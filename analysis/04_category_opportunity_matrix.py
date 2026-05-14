#!/usr/bin/env python3
"""
Category opportunity matrix based on category funnel summary output.

Goal:
- Separate categories into action buckets based on traffic and conversion.
- Preserve a business-friendly output with both tables and a chart.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / ".cache"
OUTPUT_DIR = BASE_DIR / "analysis" / "output"
SOURCE_FILE = OUTPUT_DIR / "category_funnel_summary.csv"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ["MPLCONFIGDIR"] = str(CACHE_DIR / "matplotlib")
os.environ["XDG_CACHE_HOME"] = str(CACHE_DIR)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


sns.set_theme(style="whitegrid")


def load_data() -> pd.DataFrame:
    df = pd.read_csv(SOURCE_FILE)
    return df


def build_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, float, float]:
    matrix_df = df[
        (df["category_code"] != "Unknown")
        & (df["view_interactions"] >= 10000)
    ].copy()

    traffic_cut = float(matrix_df["view_interactions"].median())
    conversion_cut = float(matrix_df["purchase_to_view_pct"].median())

    matrix_df["segment"] = np.select(
        [
            (matrix_df["view_interactions"] >= traffic_cut)
            & (matrix_df["purchase_to_view_pct"] >= conversion_cut),
            (matrix_df["view_interactions"] >= traffic_cut)
            & (matrix_df["purchase_to_view_pct"] < conversion_cut),
            (matrix_df["view_interactions"] < traffic_cut)
            & (matrix_df["purchase_to_view_pct"] >= conversion_cut),
            (matrix_df["view_interactions"] < traffic_cut)
            & (matrix_df["purchase_to_view_pct"] < conversion_cut),
        ],
        [
            "High Traffic / High Conversion",
            "High Traffic / Low Conversion",
            "Low Traffic / High Conversion",
            "Low Traffic / Low Conversion",
        ],
        default="Other",
    )

    return matrix_df, traffic_cut, conversion_cut


def export_tables(matrix_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary = (
        matrix_df.groupby("segment", as_index=False)
        .agg(
            categories=("category_code", "count"),
            total_views=("view_interactions", "sum"),
            total_purchases=("purchase_interactions", "sum"),
            total_revenue=("revenue_proxy", "sum"),
            avg_conversion_pct=("purchase_to_view_pct", "mean"),
        )
        .sort_values("total_revenue", ascending=False)
    )

    detailed = matrix_df.sort_values(
        ["segment", "revenue_proxy"],
        ascending=[True, False],
    ).copy()

    summary.to_csv(OUTPUT_DIR / "category_opportunity_summary.csv", index=False)
    detailed.to_csv(OUTPUT_DIR / "category_opportunity_detailed.csv", index=False)
    return summary, detailed


def plot_matrix(matrix_df: pd.DataFrame, traffic_cut: float, conversion_cut: float) -> None:
    label_df = matrix_df.nlargest(15, "revenue_proxy").copy()

    fig, ax = plt.subplots(figsize=(13, 9))
    sns.scatterplot(
        data=matrix_df,
        x="view_interactions",
        y="purchase_to_view_pct",
        size="revenue_proxy",
        hue="segment",
        sizes=(40, 1200),
        alpha=0.8,
        ax=ax,
        palette={
            "High Traffic / High Conversion": "#2a9d8f",
            "High Traffic / Low Conversion": "#e76f51",
            "Low Traffic / High Conversion": "#264653",
            "Low Traffic / Low Conversion": "#bcb8b1",
        },
    )

    for _, row in label_df.iterrows():
        ax.text(
            row["view_interactions"],
            row["purchase_to_view_pct"],
            row["category_code"],
            fontsize=8,
            ha="left",
            va="bottom",
        )

    ax.axvline(traffic_cut, linestyle="--", color="#6c757d")
    ax.axhline(conversion_cut, linestyle="--", color="#6c757d")
    ax.set_xscale("log")
    ax.set_title("Category Opportunity Matrix")
    ax.set_xlabel("View Interactions (log scale)")
    ax.set_ylabel("Purchase-to-View Conversion (%)")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "category_opportunity_matrix.png", dpi=160)
    plt.close(fig)


def write_report(summary: pd.DataFrame, detailed: pd.DataFrame, traffic_cut: float, conversion_cut: float) -> None:
    top_fix = detailed[detailed["segment"] == "High Traffic / Low Conversion"].head(5)
    top_scale = detailed[detailed["segment"] == "Low Traffic / High Conversion"].head(5)
    top_defend = detailed[detailed["segment"] == "High Traffic / High Conversion"].head(5)

    lines = [
        "CATEGORY OPPORTUNITY MATRIX",
        "",
        f"Traffic median cutoff: {traffic_cut:,.0f} view interactions",
        f"Conversion median cutoff: {conversion_cut:.2f}%",
        "",
        "Segment summary:",
    ]

    for _, row in summary.iterrows():
        lines.append(
            f"- {row['segment']}: {int(row['categories'])} categories | "
            f"revenue={row['total_revenue']:,.2f} | "
            f"avg_conversion={row['avg_conversion_pct']:.2f}%"
        )

    lines.extend(
        [
            "",
            "Business interpretation:",
            "- High Traffic / High Conversion categories are the core portfolio. Protect stock, pricing, and merchandising here.",
            "- High Traffic / Low Conversion categories are the biggest optimization targets because they already attract demand.",
            "- Low Traffic / High Conversion categories are likely underexposed winners that may benefit from more visibility.",
            "- Low Traffic / Low Conversion categories are lower priority unless strategically important.",
            "",
            "Top categories to fix:",
        ]
    )

    for _, row in top_fix.iterrows():
        lines.append(
            f"- {row['category_code']}: views={row['view_interactions']:,.0f}, "
            f"conversion={row['purchase_to_view_pct']:.2f}%, revenue={row['revenue_proxy']:,.2f}"
        )

    lines.append("")
    lines.append("Top categories to scale:")
    for _, row in top_scale.iterrows():
        lines.append(
            f"- {row['category_code']}: views={row['view_interactions']:,.0f}, "
            f"conversion={row['purchase_to_view_pct']:.2f}%, revenue={row['revenue_proxy']:,.2f}"
        )

    lines.append("")
    lines.append("Top categories to defend:")
    for _, row in top_defend.iterrows():
        lines.append(
            f"- {row['category_code']}: views={row['view_interactions']:,.0f}, "
            f"conversion={row['purchase_to_view_pct']:.2f}%, revenue={row['revenue_proxy']:,.2f}"
        )

    lines.extend(
        [
            "",
            "Potential issues:",
            "- This is still a session-product funnel, not a true order-level conversion model.",
            "- Median cutoffs are relative to this dataset, so the segments are useful for prioritization, not absolute performance grading.",
            "- Categories with high prices can still look strategically important even with modest conversion.",
            "",
            "Recommended next step:",
            "- Build RFM segmentation on purchasers to identify VIPs, repeat customers, and one-time buyers.",
        ]
    )

    (OUTPUT_DIR / "category_opportunity_report.txt").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main() -> None:
    df = load_data()
    matrix_df, traffic_cut, conversion_cut = build_matrix(df)
    summary, detailed = export_tables(matrix_df)
    plot_matrix(matrix_df, traffic_cut, conversion_cut)
    write_report(summary, detailed, traffic_cut, conversion_cut)
    print(f"Category opportunity outputs saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
