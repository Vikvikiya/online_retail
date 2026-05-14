#!/usr/bin/env python3
"""
Retention and cohort analysis for the online retail dataset.

Important:
- Order frequency is approximated with distinct purchase sessions because there is no order_id.
- Cohorts are month-based because the data window covers only October and November 2019.
- Repeat revenue share is calculated from customers with more than one purchase session.
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


def build_customer_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE OR REPLACE TABLE customer_purchase_sessions AS
        SELECT
            user_id,
            user_session,
            MIN(event_date) AS session_date,
            ROUND(SUM(price), 2) AS session_value
        FROM purchase_clean
        GROUP BY 1, 2
        """
    )

    con.execute(
        """
        CREATE OR REPLACE TABLE customer_journey AS
        WITH ordered_sessions AS (
            SELECT
                user_id,
                session_date,
                session_value,
                ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY session_date, user_session) AS purchase_number
            FROM customer_purchase_sessions
        ),
        max_date AS (
            SELECT MAX(session_date) AS max_session_date
            FROM customer_purchase_sessions
        )
        SELECT
            user_id,
            MIN(session_date) AS first_purchase_date,
            CAST(date_trunc('month', MIN(session_date)) AS DATE) AS cohort_month,
            MAX(session_date) AS last_purchase_date,
            COUNT(*) AS purchase_sessions,
            ROUND(SUM(session_value), 2) AS customer_revenue_proxy,
            MAX(CASE WHEN purchase_number = 2 THEN session_date END) AS second_purchase_date,
            DATE_DIFF('day', MIN(session_date), MAX(CASE WHEN purchase_number = 2 THEN session_date END)) AS days_to_second_purchase,
            CASE WHEN COUNT(*) > 1 THEN 1 ELSE 0 END AS is_repeat_customer,
            DATE_DIFF('day', MIN(session_date), (SELECT max_session_date FROM max_date)) AS days_observed_since_first_purchase
        FROM ordered_sessions
        GROUP BY 1
        """
    )


def export_cohort_matrix(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    cohort_df = con.execute(
        """
        WITH cohort_activity AS (
            SELECT
                j.cohort_month,
                CAST(date_trunc('month', s.session_date) AS DATE) AS activity_month,
                DATE_DIFF('month', j.cohort_month, CAST(date_trunc('month', s.session_date) AS DATE)) AS month_number,
                COUNT(DISTINCT s.user_id) AS active_customers
            FROM customer_purchase_sessions s
            JOIN customer_journey j USING (user_id)
            GROUP BY 1, 2, 3
        ),
        cohort_sizes AS (
            SELECT
                cohort_month,
                COUNT(*) AS cohort_size
            FROM customer_journey
            GROUP BY 1
        )
        SELECT
            a.cohort_month,
            a.activity_month,
            a.month_number,
            a.active_customers,
            c.cohort_size,
            ROUND(100.0 * a.active_customers / c.cohort_size, 2) AS retention_pct
        FROM cohort_activity a
        JOIN cohort_sizes c USING (cohort_month)
        ORDER BY 1, 3
        """
    ).fetchdf()
    cohort_df.to_csv(OUTPUT_DIR / "cohort_retention_matrix.csv", index=False)
    return cohort_df


def export_repeat_summary(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    summary = con.execute(
        """
        WITH totals AS (
            SELECT
                COUNT(*) AS total_customers,
                SUM(customer_revenue_proxy) AS total_revenue
            FROM customer_journey
        ),
        repeat_revenue AS (
            SELECT
                SUM(customer_revenue_proxy) AS repeat_revenue
            FROM customer_journey
            WHERE is_repeat_customer = 1
        ),
        eligibility AS (
            SELECT
                COUNT(*) FILTER (WHERE days_observed_since_first_purchase >= 7) AS eligible_7d,
                COUNT(*) FILTER (WHERE days_observed_since_first_purchase >= 30) AS eligible_30d,
                COUNT(*) FILTER (
                    WHERE days_observed_since_first_purchase >= 7
                      AND second_purchase_date IS NOT NULL
                      AND days_to_second_purchase <= 7
                ) AS repeated_7d,
                COUNT(*) FILTER (
                    WHERE days_observed_since_first_purchase >= 30
                      AND second_purchase_date IS NOT NULL
                      AND days_to_second_purchase <= 30
                ) AS repeated_30d
            FROM customer_journey
        )
        SELECT
            t.total_customers,
            COUNT(*) FILTER (WHERE is_repeat_customer = 1) AS repeat_customers,
            ROUND(100.0 * COUNT(*) FILTER (WHERE is_repeat_customer = 1) / t.total_customers, 2) AS repeat_customer_share_pct,
            ROUND(r.repeat_revenue, 2) AS repeat_revenue_proxy,
            ROUND(100.0 * r.repeat_revenue / t.total_revenue, 2) AS repeat_revenue_share_pct,
            ROUND(AVG(days_to_second_purchase), 2) AS avg_days_to_second_purchase,
            ROUND(MEDIAN(days_to_second_purchase), 2) AS median_days_to_second_purchase,
            e.eligible_7d,
            e.repeated_7d,
            ROUND(100.0 * e.repeated_7d / NULLIF(e.eligible_7d, 0), 2) AS repeat_within_7d_pct,
            e.eligible_30d,
            e.repeated_30d,
            ROUND(100.0 * e.repeated_30d / NULLIF(e.eligible_30d, 0), 2) AS repeat_within_30d_pct
        FROM customer_journey, totals t, repeat_revenue r, eligibility e
        GROUP BY
            t.total_customers, r.repeat_revenue, t.total_revenue,
            e.eligible_7d, e.repeated_7d, e.eligible_30d, e.repeated_30d
        """
    ).fetchdf()
    summary.to_csv(OUTPUT_DIR / "retention_repeat_summary.csv", index=False)
    return summary


def export_monthly_repeat_mix(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    monthly_mix = con.execute(
        """
        WITH session_classification AS (
            SELECT
                CAST(date_trunc('month', s.session_date) AS DATE) AS month_date,
                CASE WHEN j.is_repeat_customer = 1 THEN 'Repeat customers' ELSE 'One-time customers' END AS customer_type,
                COUNT(*) AS purchase_sessions,
                ROUND(SUM(s.session_value), 2) AS revenue_proxy
            FROM customer_purchase_sessions s
            JOIN customer_journey j USING (user_id)
            GROUP BY 1, 2
        )
        SELECT *
        FROM session_classification
        ORDER BY 1, 2
        """
    ).fetchdf()
    monthly_mix.to_csv(OUTPUT_DIR / "retention_monthly_mix.csv", index=False)
    return monthly_mix


def plot_cohort_heatmap(cohort_df: pd.DataFrame) -> None:
    heatmap_df = cohort_df.pivot(index="cohort_month", columns="month_number", values="retention_pct").fillna(0)
    heatmap_df.index = heatmap_df.index.astype(str)
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.heatmap(heatmap_df, annot=True, fmt=".2f", cmap="Blues", ax=ax)
    ax.set_title("Monthly Cohort Retention")
    ax.set_xlabel("Months since first purchase")
    ax.set_ylabel("Cohort month")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "cohort_retention_heatmap.png", dpi=160)
    plt.close(fig)


def plot_repeat_mix(monthly_mix: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    sns.barplot(data=monthly_mix, x=monthly_mix["month_date"].astype(str), y="purchase_sessions", hue="customer_type", ax=axes[0])
    axes[0].set_title("Purchase Sessions by Customer Type")
    axes[0].set_xlabel("Month")
    axes[0].set_ylabel("Purchase sessions")

    sns.barplot(data=monthly_mix, x=monthly_mix["month_date"].astype(str), y="revenue_proxy", hue="customer_type", ax=axes[1])
    axes[1].set_title("Revenue Proxy by Customer Type")
    axes[1].set_xlabel("Month")
    axes[1].set_ylabel("Revenue proxy")

    for ax in axes:
        ax.legend(title="")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "retention_repeat_mix.png", dpi=160)
    plt.close(fig)


def plot_days_to_second_purchase(con: duckdb.DuckDBPyConnection) -> None:
    days_df = con.execute(
        """
        SELECT days_to_second_purchase
        FROM customer_journey
        WHERE days_to_second_purchase IS NOT NULL
          AND days_to_second_purchase <= 60
        """
    ).fetchdf()
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.histplot(days_df["days_to_second_purchase"], bins=30, ax=ax, color="#1d4ed8")
    ax.set_title("Days to Second Purchase (Up to 60 Days)")
    ax.set_xlabel("Days to second purchase")
    ax.set_ylabel("Customers")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "days_to_second_purchase.png", dpi=160)
    plt.close(fig)


def write_report(cohort_df: pd.DataFrame, repeat_summary: pd.DataFrame) -> None:
    summary = repeat_summary.iloc[0]
    october_row = cohort_df[(cohort_df["cohort_month"].astype(str) == "2019-10-01") & (cohort_df["month_number"] == 1)]
    october_month1_retention = float(october_row.iloc[0]["retention_pct"]) if not october_row.empty else 0.0

    lines = [
        "RETENTION AND COHORT ANALYSIS",
        "",
        f"Repeat customer share: {summary['repeat_customer_share_pct']}%",
        f"Repeat revenue share: {summary['repeat_revenue_share_pct']}%",
        f"Average days to second purchase: {summary['avg_days_to_second_purchase']}",
        f"Median days to second purchase: {summary['median_days_to_second_purchase']}",
        f"Repeat within 7 days: {summary['repeat_within_7d_pct']}%",
        f"Repeat within 30 days: {summary['repeat_within_30d_pct']}%",
        f"October cohort month-1 retention: {october_month1_retention}%",
        "",
        "Business interpretation:",
        "- Repeat revenue share shows how much the portfolio depends on retained customers rather than one-time demand.",
        "- The 7-day and 30-day repeat windows are especially useful for CRM and replenishment timing.",
        "- Cohort retention gives a stronger senior-level view of customer health than RFM alone because it shows behavior over time.",
        "",
        "Potential issues:",
        "- The dataset covers only two months, so long-term retention cannot be observed.",
        "- Frequency is still based on purchase sessions, not true orders.",
        "",
        "Recommended next step:",
        "- Use repeat timing and high-value segments to design CRM and lifecycle experiments.",
    ]
    (OUTPUT_DIR / "retention_cohort_report.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_output_dir()
    con = connect()
    prepare_purchase_table(con)
    build_customer_tables(con)
    cohort_df = export_cohort_matrix(con)
    repeat_summary = export_repeat_summary(con)
    monthly_mix = export_monthly_repeat_mix(con)
    plot_cohort_heatmap(cohort_df)
    plot_repeat_mix(monthly_mix)
    plot_days_to_second_purchase(con)
    write_report(cohort_df, repeat_summary)
    print(f"Retention outputs saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
