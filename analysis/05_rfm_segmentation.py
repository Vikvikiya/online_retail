#!/usr/bin/env python3
"""
RFM segmentation for the online retail dataset.

Important:
- Frequency is measured as distinct purchase sessions because there is no order_id.
- Monetary is purchase-value proxy from purchase events with positive price.
- Recency is counted in days from the latest purchase date in the dataset.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / ".cache"
OUTPUT_DIR = BASE_DIR / "analysis" / "output"
DB_PATH = BASE_DIR / "online_retail.duckdb"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ["MPLCONFIGDIR"] = str(CACHE_DIR / "matplotlib")
os.environ["XDG_CACHE_HOME"] = str(CACHE_DIR)

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


sns.set_theme(style="whitegrid")


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(DB_PATH))
    con.execute("PRAGMA threads=4;")
    return con


def prepare_purchase_table(con: duckdb.DuckDBPyConnection) -> None:
    exists = con.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = 'purchase_clean'
        """
    ).fetchone()[0]
    if exists:
        return

    con.execute(
        """
        CREATE OR REPLACE VIEW retail_raw AS
        SELECT * FROM read_csv_auto('2019-Oct.csv', header=True, union_by_name=True)
        UNION ALL
        SELECT * FROM read_csv_auto('2019-Nov.csv', header=True, union_by_name=True)
        """
    )

    con.execute(
        """
        CREATE OR REPLACE TABLE purchase_clean AS
        SELECT
            CAST(event_time AS TIMESTAMP) AS event_ts,
            CAST(date_trunc('day', CAST(event_time AS TIMESTAMP)) AS DATE) AS event_date,
            lower(trim(event_type)) AS event_type,
            CAST(product_id AS BIGINT) AS product_id,
            COALESCE(NULLIF(trim(category_code), ''), 'Unknown') AS category_code,
            COALESCE(NULLIF(trim(brand), ''), 'Unknown') AS brand,
            CAST(price AS DOUBLE) AS price,
            CAST(user_id AS BIGINT) AS user_id,
            NULLIF(trim(user_session), '') AS user_session
        FROM retail_raw
        WHERE lower(trim(event_type)) = 'purchase'
          AND CAST(event_time AS TIMESTAMP) IS NOT NULL
          AND CAST(user_id AS BIGINT) IS NOT NULL
          AND NULLIF(trim(user_session), '') IS NOT NULL
          AND CAST(price AS DOUBLE) IS NOT NULL
          AND CAST(price AS DOUBLE) > 0
        """
    )


def build_rfm(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    con.execute(
        """
        CREATE OR REPLACE TABLE rfm_customer AS
        WITH max_date AS (
            SELECT MAX(event_date) AS max_event_date
            FROM purchase_clean
        ),
        customer_base AS (
            SELECT
                user_id,
                COUNT(DISTINCT user_session) AS frequency_orders_proxy,
                COUNT(*) AS purchase_events,
                ROUND(SUM(price), 2) AS monetary_value,
                ROUND(AVG(price), 2) AS avg_purchase_price,
                MAX(event_date) AS last_purchase_date,
                DATE_DIFF('day', MAX(event_date), (SELECT max_event_date FROM max_date) + INTERVAL 1 DAY) AS recency_days
            FROM purchase_clean
            GROUP BY 1
        ),
        scored AS (
            SELECT
                *,
                NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,
                NTILE(5) OVER (ORDER BY frequency_orders_proxy ASC) AS f_score,
                NTILE(5) OVER (ORDER BY monetary_value ASC) AS m_score
            FROM customer_base
        )
        SELECT
            *,
            CAST(r_score AS VARCHAR) || CAST(f_score AS VARCHAR) || CAST(m_score AS VARCHAR) AS rfm_code,
            CASE
                WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'
                WHEN r_score >= 3 AND f_score >= 4 AND m_score >= 3 THEN 'Loyal Customers'
                WHEN r_score >= 4 AND f_score BETWEEN 2 AND 3 THEN 'Potential Loyalists'
                WHEN r_score = 5 AND f_score = 1 THEN 'New Customers'
                WHEN r_score <= 2 AND f_score >= 4 AND m_score >= 4 THEN 'Cannot Lose Them'
                WHEN r_score <= 2 AND f_score >= 3 THEN 'At Risk'
                WHEN r_score <= 2 AND f_score <= 2 THEN 'Hibernating'
                WHEN r_score = 3 AND f_score <= 2 THEN 'Need Attention'
                ELSE 'Regular Customers'
            END AS segment
        FROM scored
        """
    )

    customer_df = con.execute("SELECT * FROM rfm_customer").fetchdf()
    customer_df.to_csv(OUTPUT_DIR / "rfm_customer_segments.csv", index=False)
    return customer_df


def export_segment_summary(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    summary = con.execute(
        """
        SELECT
            segment,
            COUNT(*) AS customers,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS customer_share_pct,
            ROUND(SUM(monetary_value), 2) AS revenue_proxy,
            ROUND(100.0 * SUM(monetary_value) / SUM(SUM(monetary_value)) OVER (), 2) AS revenue_share_pct,
            ROUND(AVG(recency_days), 2) AS avg_recency_days,
            ROUND(AVG(frequency_orders_proxy), 2) AS avg_frequency_orders,
            ROUND(AVG(monetary_value), 2) AS avg_customer_value
        FROM rfm_customer
        GROUP BY 1
        ORDER BY revenue_proxy DESC
        """
    ).fetchdf()
    summary.to_csv(OUTPUT_DIR / "rfm_segment_summary.csv", index=False)
    return summary


def export_score_grid(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    score_grid = con.execute(
        """
        SELECT
            r_score,
            f_score,
            COUNT(*) AS customers,
            ROUND(SUM(monetary_value), 2) AS revenue_proxy
        FROM rfm_customer
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).fetchdf()
    score_grid.to_csv(OUTPUT_DIR / "rfm_score_grid.csv", index=False)
    return score_grid


def plot_segment_revenue(summary: pd.DataFrame) -> None:
    plot_df = summary.sort_values("revenue_proxy")
    fig, ax = plt.subplots(figsize=(12, 7))
    sns.barplot(data=plot_df, y="segment", x="revenue_proxy", ax=ax, color="#7c3aed")
    ax.set_title("RFM Segments by Revenue Proxy")
    ax.set_xlabel("Revenue proxy")
    ax.set_ylabel("Segment")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "rfm_segment_revenue.png", dpi=160)
    plt.close(fig)


def plot_score_heatmap(score_grid: pd.DataFrame) -> None:
    pivot = score_grid.pivot(index="r_score", columns="f_score", values="customers").fillna(0)
    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(pivot, annot=True, fmt=".0f", cmap="YlGnBu", ax=ax)
    ax.set_title("RFM Customer Count Heatmap")
    ax.set_xlabel("Frequency score")
    ax.set_ylabel("Recency score")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "rfm_heatmap.png", dpi=160)
    plt.close(fig)


def plot_segment_scatter(customer_df: pd.DataFrame) -> None:
    focus_segments = [
        "Champions",
        "Loyal Customers",
        "Potential Loyalists",
        "At Risk",
        "Cannot Lose Them",
        "Hibernating",
    ]
    plot_df = customer_df[customer_df["segment"].isin(focus_segments)].copy()
    plot_df = plot_df.nlargest(60000, "monetary_value")

    fig, ax = plt.subplots(figsize=(12, 7))
    sns.scatterplot(
        data=plot_df,
        x="frequency_orders_proxy",
        y="monetary_value",
        hue="segment",
        size="recency_days",
        sizes=(15, 180),
        alpha=0.65,
        ax=ax,
    )
    ax.set_title("RFM Segment Map")
    ax.set_xlabel("Frequency (purchase sessions)")
    ax.set_ylabel("Monetary value")
    ax.set_xscale("log")
    ax.set_yscale("log")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "rfm_segment_map.png", dpi=160)
    plt.close(fig)


def write_report(summary: pd.DataFrame) -> None:
    champions = summary[summary["segment"] == "Champions"].iloc[0]
    loyal = summary[summary["segment"] == "Loyal Customers"].iloc[0]
    at_risk = summary[summary["segment"] == "At Risk"].iloc[0] if "At Risk" in summary["segment"].values else None
    cannot_lose = summary[summary["segment"] == "Cannot Lose Them"].iloc[0] if "Cannot Lose Them" in summary["segment"].values else None

    lines = [
        "RFM SEGMENTATION",
        "",
        f"Champions: {int(champions['customers']):,} customers | revenue share={champions['revenue_share_pct']}% | avg customer value={champions['avg_customer_value']:,.2f}",
        f"Loyal Customers: {int(loyal['customers']):,} customers | revenue share={loyal['revenue_share_pct']}% | avg customer value={loyal['avg_customer_value']:,.2f}",
    ]
    if at_risk is not None:
        lines.append(
            f"At Risk: {int(at_risk['customers']):,} customers | revenue share={at_risk['revenue_share_pct']}% | avg recency={at_risk['avg_recency_days']:.2f} days"
        )
    if cannot_lose is not None:
        lines.append(
            f"Cannot Lose Them: {int(cannot_lose['customers']):,} customers | revenue share={cannot_lose['revenue_share_pct']}% | avg customer value={cannot_lose['avg_customer_value']:,.2f}"
        )

    lines.extend(
        [
            "",
            "Business interpretation:",
            "- Champions and Loyal Customers show where the core retained value sits.",
            "- Potential Loyalists are the best CRM upgrade target because they are recent but not fully habitual yet.",
            "- At Risk and Cannot Lose Them should be the first retention campaign audience because they combine historical value with weakening recency.",
            "",
            "Potential issues:",
            "- Frequency is based on purchase sessions, not true orders.",
            "- The dataset covers only two months, so recency and loyalty are compressed relative to a real annual customer lifecycle.",
            "",
            "Recommended next step:",
            "- Use these segments in the final portfolio story and connect them to merchandising and retention recommendations.",
        ]
    )
    (OUTPUT_DIR / "rfm_report.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_output_dir()
    con = connect()
    prepare_purchase_table(con)
    customer_df = build_rfm(con)
    summary = export_segment_summary(con)
    score_grid = export_score_grid(con)
    plot_segment_revenue(summary)
    plot_score_heatmap(score_grid)
    plot_segment_scatter(customer_df)
    write_report(summary)
    print(f"RFM outputs saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
