#!/usr/bin/env python3
"""
Funnel and mix EDA for the online retail dataset.

Key design choice:
- Funnel grain is `user_session + product_id`, not raw event rows.
- Stage counts are cumulative:
  purchase implies cart reached and view reached
  cart implies view reached

This keeps the funnel monotonic and reduces distortion from repeated views.
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


def build_views(con: duckdb.DuckDBPyConnection) -> None:
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
        CREATE OR REPLACE VIEW retail_events AS
        SELECT
            CAST(event_time AS TIMESTAMP) AS event_ts,
            lower(trim(event_type)) AS event_type,
            CAST(product_id AS BIGINT) AS product_id,
            COALESCE(NULLIF(trim(category_code), ''), 'Unknown') AS category_code,
            COALESCE(NULLIF(trim(brand), ''), 'Unknown') AS brand,
            CAST(price AS DOUBLE) AS price,
            CAST(user_id AS BIGINT) AS user_id,
            NULLIF(trim(user_session), '') AS user_session
        FROM retail_raw
        WHERE product_id IS NOT NULL
          AND NULLIF(trim(user_session), '') IS NOT NULL
          AND lower(trim(event_type)) IN ('view', 'cart', 'purchase')
        """
    )

    con.execute(
        """
        CREATE OR REPLACE TABLE funnel_session_product AS
        WITH stage_flags AS (
            SELECT
                user_session,
                product_id,
                any_value(category_code) AS category_code,
                any_value(brand) AS brand,
                MAX(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END) AS saw_view_event,
                MAX(CASE WHEN event_type = 'cart' THEN 1 ELSE 0 END) AS saw_cart_event,
                MAX(CASE WHEN event_type = 'purchase' AND price > 0 THEN 1 ELSE 0 END) AS saw_purchase_event,
                SUM(CASE WHEN event_type = 'purchase' AND price > 0 THEN price ELSE 0 END) AS revenue_proxy,
                any_value(user_id) AS user_id
            FROM retail_events
            GROUP BY 1, 2
        )
        SELECT
            user_session,
            product_id,
            category_code,
            brand,
            user_id,
            CASE
                WHEN saw_view_event = 1 OR saw_cart_event = 1 OR saw_purchase_event = 1 THEN 1
                ELSE 0
            END AS reached_view,
            CASE
                WHEN saw_cart_event = 1 OR saw_purchase_event = 1 THEN 1
                ELSE 0
            END AS reached_cart,
            saw_purchase_event AS reached_purchase,
            revenue_proxy
        FROM stage_flags
        """
    )


def export_csv(con: duckdb.DuckDBPyConnection, query: str, file_name: str) -> pd.DataFrame:
    df = con.execute(query).fetchdf()
    df.to_csv(OUTPUT_DIR / file_name, index=False)
    return df


def category_funnel(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return export_csv(
        con,
        """
        SELECT
            category_code,
            SUM(reached_view) AS view_interactions,
            SUM(reached_cart) AS cart_interactions,
            SUM(reached_purchase) AS purchase_interactions,
            ROUND(100.0 * SUM(reached_cart) / NULLIF(SUM(reached_view), 0), 2) AS cart_to_view_pct,
            ROUND(100.0 * SUM(reached_purchase) / NULLIF(SUM(reached_view), 0), 2) AS purchase_to_view_pct,
            ROUND(100.0 * SUM(reached_purchase) / NULLIF(SUM(reached_cart), 0), 2) AS purchase_to_cart_pct,
            COUNT(DISTINCT CASE WHEN reached_purchase = 1 THEN user_id END) AS buyers,
            ROUND(SUM(revenue_proxy), 2) AS revenue_proxy,
            ROUND(AVG(CASE WHEN reached_purchase = 1 THEN revenue_proxy END), 2) AS avg_purchase_value
        FROM funnel_session_product
        GROUP BY 1
        ORDER BY revenue_proxy DESC
        """,
        "category_funnel_summary.csv",
    )


def category_mix(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return export_csv(
        con,
        """
        WITH totals AS (
            SELECT SUM(revenue_proxy) AS total_revenue
            FROM funnel_session_product
            WHERE reached_purchase = 1
        )
        SELECT
            category_code,
            COUNT(*) FILTER (WHERE reached_purchase = 1) AS purchase_interactions,
            COUNT(DISTINCT user_id) FILTER (WHERE reached_purchase = 1) AS buyers,
            ROUND(SUM(revenue_proxy), 2) AS revenue_proxy,
            ROUND(100.0 * SUM(revenue_proxy) / MAX(total_revenue), 2) AS revenue_share_pct,
            ROUND(AVG(CASE WHEN reached_purchase = 1 THEN revenue_proxy END), 2) AS avg_purchase_value
        FROM funnel_session_product, totals
        GROUP BY 1
        ORDER BY revenue_proxy DESC
        """,
        "category_mix_summary.csv",
    )


def brand_mix(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return export_csv(
        con,
        """
        WITH totals AS (
            SELECT SUM(revenue_proxy) AS total_revenue
            FROM funnel_session_product
            WHERE reached_purchase = 1
        )
        SELECT
            brand,
            COUNT(*) FILTER (WHERE reached_purchase = 1) AS purchase_interactions,
            COUNT(DISTINCT user_id) FILTER (WHERE reached_purchase = 1) AS buyers,
            ROUND(SUM(revenue_proxy), 2) AS revenue_proxy,
            ROUND(100.0 * SUM(revenue_proxy) / MAX(total_revenue), 2) AS revenue_share_pct,
            ROUND(AVG(CASE WHEN reached_purchase = 1 THEN revenue_proxy END), 2) AS avg_purchase_value
        FROM funnel_session_product, totals
        GROUP BY 1
        ORDER BY revenue_proxy DESC
        """,
        "brand_mix_summary.csv",
    )


def category_monthly_funnel(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return export_csv(
        con,
        """
        WITH monthly_stage AS (
            SELECT
                CAST(date_trunc('month', event_ts) AS DATE) AS month_date,
                user_session,
                product_id,
                COALESCE(NULLIF(trim(category_code), ''), 'Unknown') AS category_code,
                MAX(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END) AS saw_view_event,
                MAX(CASE WHEN event_type = 'cart' THEN 1 ELSE 0 END) AS saw_cart_event,
                MAX(CASE WHEN event_type = 'purchase' AND price > 0 THEN 1 ELSE 0 END) AS saw_purchase_event
            FROM retail_events
            GROUP BY 1, 2, 3, 4
        )
        SELECT
            month_date,
            category_code,
            SUM(
                CASE
                    WHEN saw_view_event = 1 OR saw_cart_event = 1 OR saw_purchase_event = 1 THEN 1
                    ELSE 0
                END
            ) AS view_interactions,
            SUM(
                CASE
                    WHEN saw_cart_event = 1 OR saw_purchase_event = 1 THEN 1
                    ELSE 0
                END
            ) AS cart_interactions,
            SUM(saw_purchase_event) AS purchase_interactions,
            ROUND(
                100.0 * SUM(saw_purchase_event)
                / NULLIF(
                    SUM(
                        CASE
                            WHEN saw_view_event = 1 OR saw_cart_event = 1 OR saw_purchase_event = 1 THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ),
                2
            ) AS purchase_to_view_pct
        FROM monthly_stage
        GROUP BY 1, 2
        ORDER BY 1, purchase_interactions DESC
        """,
        "category_monthly_funnel.csv",
    )


def plot_category_conversion(category_funnel_df: pd.DataFrame) -> None:
    chart_df = category_funnel_df[
        (category_funnel_df["view_interactions"] >= 10000)
        & (category_funnel_df["category_code"] != "Unknown")
    ].copy()
    chart_df = chart_df.nlargest(15, "purchase_to_view_pct").sort_values("purchase_to_view_pct")

    fig, ax = plt.subplots(figsize=(12, 8))
    sns.barplot(data=chart_df, y="category_code", x="purchase_to_view_pct", ax=ax, color="#2a9d8f")
    ax.set_title("Top Categories by View-to-Purchase Conversion")
    ax.set_xlabel("Purchase to view conversion (%)")
    ax.set_ylabel("Category")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "category_conversion.png", dpi=160)
    plt.close(fig)


def plot_category_revenue_mix(category_mix_df: pd.DataFrame) -> None:
    chart_df = category_mix_df[category_mix_df["category_code"] != "Unknown"].nlargest(15, "revenue_proxy").copy()
    chart_df = chart_df.sort_values("revenue_proxy")

    fig, ax = plt.subplots(figsize=(12, 8))
    sns.barplot(data=chart_df, y="category_code", x="revenue_proxy", ax=ax, color="#e76f51")
    ax.set_title("Top Categories by Revenue Proxy")
    ax.set_xlabel("Revenue proxy")
    ax.set_ylabel("Category")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "category_revenue_mix.png", dpi=160)
    plt.close(fig)


def plot_brand_revenue_mix(brand_mix_df: pd.DataFrame) -> None:
    chart_df = brand_mix_df[brand_mix_df["brand"] != "Unknown"].nlargest(15, "revenue_proxy").copy()
    chart_df = chart_df.sort_values("revenue_proxy")

    fig, ax = plt.subplots(figsize=(12, 8))
    sns.barplot(data=chart_df, y="brand", x="revenue_proxy", ax=ax, color="#264653")
    ax.set_title("Top Brands by Revenue Proxy")
    ax.set_xlabel("Revenue proxy")
    ax.set_ylabel("Brand")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "brand_revenue_mix.png", dpi=160)
    plt.close(fig)


def write_report(
    category_funnel_df: pd.DataFrame,
    category_mix_df: pd.DataFrame,
    brand_mix_df: pd.DataFrame,
) -> None:
    top_conv = (
        category_funnel_df[
            (category_funnel_df["view_interactions"] >= 10000)
            & (category_funnel_df["category_code"] != "Unknown")
        ]
        .nlargest(1, "purchase_to_view_pct")
        .iloc[0]
    )
    top_category = category_mix_df[category_mix_df["category_code"] != "Unknown"].iloc[0]
    top_brand = brand_mix_df[brand_mix_df["brand"] != "Unknown"].iloc[0]

    report = f"""
FUNNEL AND MIX EDA

1. Category funnel
- Highest large-category view-to-purchase conversion: {top_conv['category_code']} at {top_conv['purchase_to_view_pct']}%
- This category also has {int(top_conv['view_interactions']):,} session-product interactions that reached view stage.

Business interpretation:
- High-conversion categories usually indicate stronger purchase intent, better product-market fit, or lower friction in the decision process.
- Low-conversion but high-traffic categories can be merchandising or UX opportunity areas.

Potential issue:
- This is a session-product funnel, not a user funnel and not an order funnel.
- We use cumulative stages so that purchase implies cart and view reached. That improves stability but slightly smooths tracking gaps.

2. Category mix
- Top category by revenue proxy: {top_category['category_code']} with {top_category['revenue_proxy']:,}
- Revenue share of this category: {top_category['revenue_share_pct']}%
- Buyers in this category: {int(top_category['buyers']):,}

Business interpretation:
- High-revenue categories can win because of strong demand, high price points, or both.
- Revenue concentration matters because dependency on a narrow category mix increases assortment risk.

Potential issue:
- Missing category values are preserved as 'Unknown', so category-level insights remain directionally useful but not perfect.

3. Brand mix
- Top brand by revenue proxy: {top_brand['brand']} with {top_brand['revenue_proxy']:,}
- Revenue share of this brand: {top_brand['revenue_share_pct']}%
- Buyers of this brand: {int(top_brand['buyers']):,}

Business interpretation:
- If a few brands dominate, supplier concentration and brand bargaining power become strategic issues.
- Strong brand concentration can also mean cross-sell opportunities are brand-led rather than category-led.

Potential issue:
- Missing brand values are grouped into 'Unknown', and this dataset covers only two months.

Recommended next step:
- Segment categories into four groups: high traffic/high conversion, high traffic/low conversion, low traffic/high conversion, and low traffic/low conversion.
- Then move into RFM on purchasers to separate high-value repeat customers from one-time holiday buyers.
""".strip()

    (OUTPUT_DIR / "funnel_mix_report.txt").write_text(report, encoding="utf-8")


def main() -> None:
    ensure_output_dir()
    con = connect()
    build_views(con)

    category_funnel_df = category_funnel(con)
    category_mix_df = category_mix(con)
    brand_mix_df = brand_mix(con)
    category_monthly_funnel(con)

    plot_category_conversion(category_funnel_df)
    plot_category_revenue_mix(category_mix_df)
    plot_brand_revenue_mix(brand_mix_df)
    write_report(category_funnel_df, category_mix_df, brand_mix_df)

    print(f"Funnel outputs saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
