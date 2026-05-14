#!/usr/bin/env python3
"""
Business decision memo, prioritization matrix, and experiment roadmap.

This script intentionally combines analytical outputs with strategic framing:
- impact vs effort prioritization
- experiment design
- missing data and blocked decisions
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / ".cache"
OUTPUT_DIR = BASE_DIR / "analysis" / "output"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ["MPLCONFIGDIR"] = str(CACHE_DIR / "matplotlib")
os.environ["XDG_CACHE_HOME"] = str(CACHE_DIR)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


sns.set_theme(style="whitegrid")


def load_inputs() -> dict[str, pd.DataFrame]:
    cart_summary_path = OUTPUT_DIR / "cart_abandonment_overview.csv"
    return {
        "rfm": pd.read_csv(OUTPUT_DIR / "rfm_segment_summary.csv"),
        "opportunity": pd.read_csv(OUTPUT_DIR / "category_opportunity_detailed.csv"),
        "stats": pd.read_csv(OUTPUT_DIR / "statistical_tests_summary.csv"),
        "retention": pd.read_csv(OUTPUT_DIR / "retention_repeat_summary.csv"),
        "category_mix": pd.read_csv(OUTPUT_DIR / "category_mix_summary.csv"),
        "cart": pd.read_csv(cart_summary_path) if cart_summary_path.exists() else pd.DataFrame([{"cart_abandonment_rate_pct": None}]),
    }


def build_priorities(inputs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    opp = inputs["opportunity"]
    rfm = inputs["rfm"].set_index("segment")
    retention = inputs["retention"].iloc[0]
    category_mix = inputs["category_mix"]
    cart = inputs["cart"].iloc[0]
    smartphone_share = float(category_mix.loc[category_mix["category_code"] == "electronics.smartphone", "revenue_share_pct"].iloc[0])
    cart_rate = cart["cart_abandonment_rate_pct"]
    cart_text = f"Observed cart abandonment is {cart_rate:.2f}% at the session-product level." if pd.notna(cart_rate) else "Cart-stage loss is visible in the funnel and should be measured directly."

    priorities = pd.DataFrame(
        [
            {
                "initiative": "Improve high-traffic / low-conversion categories",
                "focus_area": "Conversion optimization",
                "evidence": f"21 categories sit in the high-traffic/low-conversion bucket with 13.96M revenue proxy at risk. {cart_text}",
                "impact_score": 5,
                "effort_score": 3,
                "priority_type": "Quick win",
                "primary_metric": "Purchase-to-view conversion",
                "expected_outcome": "Lift monetization of existing traffic without buying more demand.",
            },
            {
                "initiative": "Protect smartphone category economics",
                "focus_area": "Merchandising and pricing",
                "evidence": f"Smartphones contribute {smartphone_share:.2f}% of category revenue proxy and convert 132.59% better than the rest of the catalog.",
                "impact_score": 5,
                "effort_score": 2,
                "priority_type": "Defend core",
                "primary_metric": "Revenue proxy, conversion, stockout rate",
                "expected_outcome": "Preserve the portfolio’s largest commercial engine.",
            },
            {
                "initiative": "Retention play for Cannot Lose Them",
                "focus_area": "CRM and lifecycle marketing",
                "evidence": f"Cannot Lose Them drive {rfm.loc['Cannot Lose Them', 'revenue_share_pct']:.2f}% of revenue proxy with high historical value and weaker recency.",
                "impact_score": 5,
                "effort_score": 3,
                "priority_type": "High leverage",
                "primary_metric": "30-day repeat rate, win-back rate",
                "expected_outcome": "Recover high-value customers before value decays further.",
            },
            {
                "initiative": "Convert Potential Loyalists into repeat buyers",
                "focus_area": "CRM nurture journeys",
                "evidence": f"Potential Loyalists account for {rfm.loc['Potential Loyalists', 'customer_share_pct']:.2f}% of customers but only {rfm.loc['Potential Loyalists', 'revenue_share_pct']:.2f}% of revenue.",
                "impact_score": 4,
                "effort_score": 2,
                "priority_type": "Scalable growth",
                "primary_metric": "7-day and 30-day repeat rate",
                "expected_outcome": "Increase LTV by moving recent buyers into repeat behavior.",
            },
            {
                "initiative": "Cross-sell and bundling improvement",
                "focus_area": "Basket expansion",
                "evidence": "Most purchase sessions are single-item and repeat revenue share is materially lower than top-category concentration.",
                "impact_score": 4,
                "effort_score": 4,
                "priority_type": "Medium-term bet",
                "primary_metric": "Items per purchase session",
                "expected_outcome": "Raise basket size and reduce dependency on hero SKUs.",
            },
            {
                "initiative": "Scale niche high-conversion categories",
                "focus_area": "Traffic allocation",
                "evidence": "Low-traffic/high-conversion categories appear underexposed but efficient.",
                "impact_score": 3,
                "effort_score": 2,
                "priority_type": "Test-and-scale",
                "primary_metric": "Qualified traffic and conversion",
                "expected_outcome": "Diversify growth beyond the smartphone-heavy mix.",
            },
            {
                "initiative": "Data foundation upgrade",
                "focus_area": "Measurement infrastructure",
                "evidence": f"Repeat within 30 days is {retention['repeat_within_30d_pct']:.2f}%, but true order economics are blocked by missing order_id, quantity, and geography.",
                "impact_score": 4,
                "effort_score": 5,
                "priority_type": "Strategic enabler",
                "primary_metric": "Data completeness",
                "expected_outcome": "Enable cleaner revenue, basket, and geo decision-making.",
            },
        ]
    )
    priorities.to_csv(OUTPUT_DIR / "decision_priority_matrix.csv", index=False)
    return priorities


def build_experiments() -> pd.DataFrame:
    experiments = pd.DataFrame(
        [
            {
                "experiment_name": "Desktop category PDP redesign",
                "hypothesis": "Improving trust, specifications, and comparison clarity on high-traffic low-conversion desktop pages will increase purchase conversion.",
                "target_group": "computers.desktop visitors",
                "primary_metric": "Purchase-to-view conversion",
                "guardrail_metrics": "Bounce rate, add-to-cart rate, average order value proxy",
                "test_type": "A/B test",
                "expected_impact": "High",
            },
            {
                "experiment_name": "Bundle recommendations on single-item flows",
                "hypothesis": "Adding accessory bundles and cart recommendations will increase items per purchase session.",
                "target_group": "Single-item purchase journeys",
                "primary_metric": "Items per purchase session",
                "guardrail_metrics": "Conversion rate, session value proxy, cart abandonment",
                "test_type": "A/B test",
                "expected_impact": "Medium to high",
            },
            {
                "experiment_name": "Potential Loyalists repeat-purchase CRM flow",
                "hypothesis": "A lifecycle email or push sequence within 7 to 30 days of first purchase will increase repeat rate among Potential Loyalists.",
                "target_group": "Potential Loyalists",
                "primary_metric": "30-day repeat rate",
                "guardrail_metrics": "Unsubscribe rate, promo dependency, margin proxy",
                "test_type": "CRM experiment",
                "expected_impact": "High",
            },
            {
                "experiment_name": "Win-back campaign for Cannot Lose Them",
                "hypothesis": "A targeted win-back offer or reminder for high-value dormant customers will recover revenue more efficiently than broad retention campaigns.",
                "target_group": "Cannot Lose Them",
                "primary_metric": "Reactivation rate",
                "guardrail_metrics": "Discount cost, net revenue proxy, unsubscribes",
                "test_type": "CRM experiment",
                "expected_impact": "High",
            },
            {
                "experiment_name": "Traffic reallocation to niche converters",
                "hypothesis": "Increasing exposure for low-traffic high-conversion categories will generate more efficient revenue than adding traffic to weak categories.",
                "target_group": "High-conversion niche categories",
                "primary_metric": "Incremental revenue proxy per 1,000 views",
                "guardrail_metrics": "Overall conversion mix, traffic quality",
                "test_type": "Merchandising / paid traffic test",
                "expected_impact": "Medium",
            },
        ]
    )
    experiments.to_csv(OUTPUT_DIR / "ab_test_roadmap.csv", index=False)
    return experiments


def build_missing_data_table() -> pd.DataFrame:
    missing_data = pd.DataFrame(
        [
            {"missing_field": "order_id", "blocked_decision": "True order-level basket and checkout analysis", "why_it_matters": "Purchase sessions are only a proxy for real orders."},
            {"missing_field": "quantity", "blocked_decision": "True revenue and basket economics", "why_it_matters": "A single purchase event may represent different unit counts."},
            {"missing_field": "country / geography", "blocked_decision": "Geo expansion and localization decisions", "why_it_matters": "Country-level analysis cannot be done honestly without geography."},
            {"missing_field": "margin / cost", "blocked_decision": "Profitability prioritization", "why_it_matters": "Revenue concentration does not necessarily mean profit concentration."},
            {"missing_field": "traffic source", "blocked_decision": "Acquisition efficiency analysis", "why_it_matters": "Low conversion may come from lower-intent traffic rather than poor onsite experience."},
        ]
    )
    missing_data.to_csv(OUTPUT_DIR / "missing_data_decision_gaps.csv", index=False)
    return missing_data


def plot_priority_matrix(priorities: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(12, 8))
    sns.scatterplot(
        data=priorities,
        x="effort_score",
        y="impact_score",
        hue="priority_type",
        size="impact_score",
        sizes=(120, 500),
        ax=ax,
    )
    for _, row in priorities.iterrows():
        ax.text(row["effort_score"] + 0.03, row["impact_score"] + 0.03, row["initiative"], fontsize=8)
    ax.set_title("Impact vs Effort Priority Matrix")
    ax.set_xlabel("Effort")
    ax.set_ylabel("Impact")
    ax.set_xlim(1.5, 5.5)
    ax.set_ylim(1.5, 5.5)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "impact_effort_matrix.png", dpi=160)
    plt.close(fig)


def plot_experiment_roadmap(experiments: pd.DataFrame) -> None:
    impact_map = {"High": 3, "Medium to high": 2, "Medium": 1}
    plot_df = experiments.copy()
    plot_df["impact_rank"] = plot_df["expected_impact"].map(impact_map)
    plot_df = plot_df.sort_values("impact_rank")
    fig, ax = plt.subplots(figsize=(11, 6))
    sns.barplot(data=plot_df, y="experiment_name", x="impact_rank", ax=ax, color="#ea580c")
    ax.set_title("Experiment Roadmap Priority")
    ax.set_xlabel("Expected impact rank")
    ax.set_ylabel("")
    ax.set_xticks([1, 2, 3], ["Medium", "Medium-High", "High"])
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "ab_test_roadmap.png", dpi=160)
    plt.close(fig)


def write_memo(priorities: pd.DataFrame, experiments: pd.DataFrame, missing_data: pd.DataFrame) -> None:
    top3 = priorities.sort_values(["impact_score", "effort_score"], ascending=[False, True]).head(3)
    lines = [
        "# Final Business Decision Memo",
        "",
        "## Context",
        "",
        "This portfolio is commercially strong but structurally concentrated. Smartphones, Apple, and Samsung account for a disproportionate share of value. At the same time, there are clear conversion gaps, meaningful cart-stage leakage, retention opportunities, and measurement limits.",
        "",
        "## Top Priorities",
        "",
    ]
    for _, row in top3.iterrows():
        lines.extend(
            [
                f"### {row['initiative']}",
                f"- Focus area: {row['focus_area']}",
                f"- Evidence: {row['evidence']}",
                f"- Expected outcome: {row['expected_outcome']}",
                f"- Primary metric: {row['primary_metric']}",
                "",
            ]
        )

    lines.extend(
        [
            "## Recommended Experiment Roadmap",
            "",
        ]
    )
    for _, row in experiments.iterrows():
        lines.extend(
            [
                f"### {row['experiment_name']}",
                f"- Hypothesis: {row['hypothesis']}",
                f"- Target group: {row['target_group']}",
                f"- Primary metric: {row['primary_metric']}",
                f"- Guardrails: {row['guardrail_metrics']}",
                "",
            ]
        )

    lines.extend(
        [
            "## Missing Data That Blocks Better Decisions",
            "",
        ]
    )
    for _, row in missing_data.iterrows():
        lines.append(
            f"- {row['missing_field']}: blocks {row['blocked_decision']} because {row['why_it_matters']}"
        )

    lines.extend(
        [
            "",
            "## Final Recommendation",
            "",
            "The best senior-level recommendation from this analysis is not to chase more top-line traffic first. The better move is to protect the concentrated revenue engine, repair cart-stage leakage and conversion in wasted-traffic categories, and build a CRM retention layer around high-value and high-potential segments.",
        ]
    )
    (OUTPUT_DIR / "final_business_decision_memo.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    inputs = load_inputs()
    priorities = build_priorities(inputs)
    experiments = build_experiments()
    missing_data = build_missing_data_table()
    plot_priority_matrix(priorities)
    plot_experiment_roadmap(experiments)
    write_memo(priorities, experiments, missing_data)
    print(f"Decision memo outputs saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
