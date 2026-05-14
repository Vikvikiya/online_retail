#!/usr/bin/env python3
"""
EDA for the Online Retail event dataset.

Outputs:
- CSV summaries in analysis/output/
- PNG charts in analysis/output/
- A text report with business interpretation and caveats

Important:
- This is an event-level dataset, not an order-header dataset.
- Revenue is treated as a GMV proxy based on purchase-event prices.
- Basket size is approximated at the purchase-session level because no order_id exists.
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
import pandas as pd


matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
        CREATE OR REPLACE VIEW retail_typed AS
        SELECT
            CAST(event_time AS TIMESTAMP) AS event_ts,
            event_time,
            lower(trim(event_type)) AS event_type,
            CAST(product_id AS BIGINT) AS product_id,
            CAST(category_id AS BIGINT) AS category_id,
            NULLIF(trim(category_code), '') AS category_code,
            NULLIF(trim(brand), '') AS brand,
            CAST(price AS DOUBLE) AS price,
            CAST(user_id AS BIGINT) AS user_id,
            NULLIF(trim(user_session), '') AS user_session
        FROM retail_raw
        """
    )

    con.execute(
        """
        CREATE OR REPLACE VIEW purchase_clean AS
        SELECT
            event_ts,
            CAST(date_trunc('month', event_ts) AS DATE) AS month_date,
            CAST(date_trunc('day', event_ts) AS DATE) AS event_date,
            product_id,
            category_id,
            COALESCE(category_code, 'Unknown') AS category_code,
            COALESCE(brand, 'Unknown') AS brand,
            price,
            user_id,
            user_session
        FROM retail_typed
        WHERE event_type = 'purchase'
          AND event_ts IS NOT NULL
          AND user_id IS NOT NULL
          AND user_session IS NOT NULL
          AND price IS NOT NULL
          AND price > 0
        """
    )


def export_csv(con: duckdb.DuckDBPyConnection, query: str, file_name: str) -> pd.DataFrame:
    df = con.execute(query).fetchdf()
    df.to_csv(OUTPUT_DIR / file_name, index=False)
    return df


def plot_revenue_distribution(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    revenue_stats = export_csv(
        con,
        """
        SELECT
            COUNT(*) AS purchase_rows,
            ROUND(SUM(price), 2) AS total_revenue_proxy,
            ROUND(AVG(price), 2) AS avg_purchase_price,
            ROUND(MEDIAN(price), 2) AS median_purchase_price,
            ROUND(quantile_cont(price, 0.90), 2) AS p90_purchase_price,
            ROUND(quantile_cont(price, 0.99), 2) AS p99_purchase_price,
            ROUND(MAX(price), 2) AS max_purchase_price
        FROM purchase_clean
        """,
        "revenue_distribution_summary.csv",
    )

    purchase_prices = con.execute(
        """
        SELECT price
        FROM purchase_clean
        """
    ).fetchdf()

    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    sns.histplot(purchase_prices["price"], bins=60, ax=axes[0], color="#1f77b4")
    axes[0].set_title("Purchase Price Distribution")
    axes[0].set_xlabel("Purchase price")
    axes[0].set_ylabel("Count")

    sns.histplot(purchase_prices["price"], bins=60, ax=axes[1], color="#ff7f0e", log_scale=(True, True))
    axes[1].set_title("Purchase Price Distribution (Log Scale)")
    axes[1].set_xlabel("Purchase price")
    axes[1].set_ylabel("Count")

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "revenue_distribution.png", dpi=160)
    plt.close(fig)
    return revenue_stats


def plot_monthly_trend(con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, pd.DataFrame]:
    monthly = export_csv(
        con,
        """
        SELECT
            month_date,
            COUNT(*) AS purchase_events,
            COUNT(DISTINCT user_id) AS purchasing_users,
            ROUND(SUM(price), 2) AS revenue_proxy,
            ROUND(AVG(price), 2) AS avg_purchase_price
        FROM purchase_clean
        GROUP BY 1
        ORDER BY 1
        """,
        "monthly_trend.csv",
    )

    daily = export_csv(
        con,
        """
        SELECT
            event_date,
            COUNT(*) AS purchase_events,
            COUNT(DISTINCT user_id) AS purchasing_users,
            ROUND(SUM(price), 2) AS revenue_proxy
        FROM purchase_clean
        GROUP BY 1
        ORDER BY 1
        """,
        "daily_trend.csv",
    )

    fig, axes = plt.subplots(1, 2, figsize=(15, 5))

    sns.barplot(data=monthly, x="month_date", y="revenue_proxy", ax=axes[0], color="#2ca02c")
    axes[0].set_title("Monthly Revenue Proxy")
    axes[0].set_xlabel("Month")
    axes[0].set_ylabel("Revenue proxy")
    axes[0].tick_params(axis="x", rotation=20)

    sns.lineplot(data=daily, x="event_date", y="revenue_proxy", ax=axes[1], color="#d62728")
    axes[1].set_title("Daily Revenue Proxy")
    axes[1].set_xlabel("Date")
    axes[1].set_ylabel("Revenue proxy")
    axes[1].tick_params(axis="x", rotation=45)

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "monthly_daily_trend.png", dpi=160)
    plt.close(fig)
    return monthly, daily


def export_top_countries_note(con: duckdb.DuckDBPyConnection) -> str:
    columns = con.execute("DESCRIBE retail_typed").fetchdf()["column_name"].tolist()
    note = (
        "Top countries cannot be computed from this dataset because there is no country or geography field. "
        "Any country chart would be invented and analytically invalid."
    )
    if "country" in columns:
        note = "A country column exists and can be profiled in a follow-up step."
    (OUTPUT_DIR / "top_countries_note.txt").write_text(note, encoding="utf-8")
    return note


def plot_top_customers(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    top_customers = export_csv(
        con,
        """
        SELECT
            user_id,
            COUNT(*) AS purchase_events,
            COUNT(DISTINCT user_session) AS purchase_sessions,
            ROUND(SUM(price), 2) AS revenue_proxy,
            ROUND(AVG(price), 2) AS avg_purchase_price
        FROM purchase_clean
        GROUP BY 1
        ORDER BY revenue_proxy DESC
        LIMIT 15
        """,
        "top_customers.csv",
    )

    fig, ax = plt.subplots(figsize=(12, 7))
    sns.barplot(data=top_customers, y=top_customers["user_id"].astype(str), x="revenue_proxy", ax=ax, color="#9467bd")
    ax.set_title("Top Customers by Revenue Proxy")
    ax.set_xlabel("Revenue proxy")
    ax.set_ylabel("User ID")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "top_customers.png", dpi=160)
    plt.close(fig)
    return top_customers


def plot_top_products(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    top_products = export_csv(
        con,
        """
        SELECT
            product_id,
            brand,
            category_code,
            COUNT(*) AS purchase_events,
            COUNT(DISTINCT user_id) AS buyers,
            ROUND(SUM(price), 2) AS revenue_proxy
        FROM purchase_clean
        GROUP BY 1, 2, 3
        ORDER BY revenue_proxy DESC
        LIMIT 15
        """,
        "top_products.csv",
    )

    top_products["label"] = (
        top_products["product_id"].astype(str)
        + " | "
        + top_products["brand"].astype(str)
    )

    fig, ax = plt.subplots(figsize=(12, 7))
    sns.barplot(data=top_products, y="label", x="revenue_proxy", ax=ax, color="#8c564b")
    ax.set_title("Top Products by Revenue Proxy")
    ax.set_xlabel("Revenue proxy")
    ax.set_ylabel("Product | Brand")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "top_products.png", dpi=160)
    plt.close(fig)
    return top_products


def plot_basket_size(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    basket_summary = export_csv(
        con,
        """
        WITH purchase_sessions AS (
            SELECT
                user_session,
                user_id,
                COUNT(*) AS items_in_session,
                COUNT(DISTINCT product_id) AS distinct_products,
                ROUND(SUM(price), 2) AS session_revenue_proxy
            FROM purchase_clean
            GROUP BY 1, 2
        )
        SELECT
            COUNT(*) AS purchase_sessions,
            ROUND(AVG(items_in_session), 2) AS avg_items_per_purchase_session,
            ROUND(MEDIAN(items_in_session), 2) AS median_items_per_purchase_session,
            ROUND(quantile_cont(items_in_session, 0.90), 2) AS p90_items_per_purchase_session,
            ROUND(AVG(session_revenue_proxy), 2) AS avg_revenue_per_purchase_session,
            ROUND(MEDIAN(session_revenue_proxy), 2) AS median_revenue_per_purchase_session
        FROM purchase_sessions
        """,
        "basket_size_summary.csv",
    )

    basket_dist = export_csv(
        con,
        """
        WITH purchase_sessions AS (
            SELECT
                user_session,
                COUNT(*) AS items_in_session,
                ROUND(SUM(price), 2) AS session_revenue_proxy
            FROM purchase_clean
            GROUP BY 1
        )
        SELECT
            items_in_session,
            COUNT(*) AS session_count
        FROM purchase_sessions
        GROUP BY 1
        ORDER BY 1
        """,
        "basket_size_distribution.csv",
    )

    fig, axes = plt.subplots(1, 2, figsize=(15, 5))

    sns.barplot(data=basket_dist.head(20), x="items_in_session", y="session_count", ax=axes[0], color="#17becf")
    axes[0].set_title("Purchase Session Size Distribution")
    axes[0].set_xlabel("Items in purchase session")
    axes[0].set_ylabel("Session count")

    session_revenue_sample = con.execute(
        """
        WITH purchase_sessions AS (
            SELECT
                user_session,
                ROUND(SUM(price), 2) AS session_revenue_proxy
            FROM purchase_clean
            GROUP BY 1
        )
        SELECT session_revenue_proxy
        FROM purchase_sessions
        USING SAMPLE 200000 ROWS
        """
    ).fetchdf()

    sns.histplot(session_revenue_sample["session_revenue_proxy"], bins=60, ax=axes[1], color="#bcbd22")
    axes[1].set_title("Purchase Session Revenue Distribution")
    axes[1].set_xlabel("Revenue proxy per purchase session")
    axes[1].set_ylabel("Count")

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "basket_size.png", dpi=160)
    plt.close(fig)
    return basket_summary


def write_report(
    revenue_stats: pd.DataFrame,
    monthly: pd.DataFrame,
    country_note: str,
    top_customers: pd.DataFrame,
    top_products: pd.DataFrame,
    basket_summary: pd.DataFrame,
) -> None:
    oct_row = monthly.iloc[0]
    nov_row = monthly.iloc[1]

    report = f"""
EDA REPORT

1. Revenue distribution
- Purchase-event revenue proxy rows: {int(revenue_stats.loc[0, 'purchase_rows']):,}
- Total revenue proxy: {revenue_stats.loc[0, 'total_revenue_proxy']:,}
- Average purchase price: {revenue_stats.loc[0, 'avg_purchase_price']:,}
- Median purchase price: {revenue_stats.loc[0, 'median_purchase_price']:,}
- P90 purchase price: {revenue_stats.loc[0, 'p90_purchase_price']:,}
- P99 purchase price: {revenue_stats.loc[0, 'p99_purchase_price']:,}
- Max purchase price: {revenue_stats.loc[0, 'max_purchase_price']:,}

Business interpretation:
- The gap between average and median purchase price shows whether revenue is concentrated in a small number of expensive items.
- If the right tail is long, premium products can materially shape revenue even when most transactions are smaller.

Potential issue:
- This dataset has no quantity field, so revenue is a price-sum proxy, not audited net sales.

2. Monthly trend
- October revenue proxy: {oct_row['revenue_proxy']:,} from {int(oct_row['purchase_events']):,} purchase events
- November revenue proxy: {nov_row['revenue_proxy']:,} from {int(nov_row['purchase_events']):,} purchase events

Business interpretation:
- Month-over-month change should be read as a shift in purchase-event value and buyer activity, not a full accounting revenue statement.
- Because only two months are present, daily trend is more useful than monthly trend for spotting trading patterns.

Potential issue:
- Comparing only October and November can overstate seasonality because there is no longer baseline.

3. Top countries
- {country_note}

Business interpretation:
- Geography is currently a blind spot. Country-level expansion or localization decisions cannot be supported from this dataset alone.

Potential issue:
- Do not backfill country from brand or category. That would create fake segmentation.

4. Top customers
- Highest customer revenue proxy: user {int(top_customers.iloc[0]['user_id'])} with {top_customers.iloc[0]['revenue_proxy']:,}

Business interpretation:
- Heavy buyers can dominate revenue disproportionately. This matters for retention and VIP segmentation.
- A concentrated top-customer chart can justify later RFM or loyalty analysis.

Potential issue:
- Customer ID is available, but we only see two months. Some users may look “new” or “low frequency” simply because history is truncated.

5. Top products
- Highest product revenue proxy: product {int(top_products.iloc[0]['product_id'])} with {top_products.iloc[0]['revenue_proxy']:,}

Business interpretation:
- Top-product revenue can reflect either broad demand or a high-ticket item with fewer purchases.
- Always pair revenue ranking with buyer count or purchase count before making assortment decisions.

Potential issue:
- Missing brand/category values are filled as 'Unknown' to preserve rows, so metadata-based product analysis remains partially incomplete.

6. Basket size
- Average items per purchase session: {basket_summary.loc[0, 'avg_items_per_purchase_session']}
- Median items per purchase session: {basket_summary.loc[0, 'median_items_per_purchase_session']}
- P90 items per purchase session: {basket_summary.loc[0, 'p90_items_per_purchase_session']}
- Average revenue proxy per purchase session: {basket_summary.loc[0, 'avg_revenue_per_purchase_session']}

Business interpretation:
- If most purchase sessions are single-item, cross-sell is underdeveloped or the catalog skews to considered purchases.
- If session value rises faster than item count, higher basket value may be driven more by premium price mix than bundling.

Potential issue:
- Basket size is approximated using purchase sessions because there is no order_id. A session can contain multiple separate purchases or an incomplete order journey.

Recommended next step:
- Move from descriptive EDA into a cleaned purchase table plus a funnel table, then analyze conversion by category and customer behavior before RFM.
""".strip()

    (OUTPUT_DIR / "eda_report.txt").write_text(report, encoding="utf-8")


def main() -> None:
    ensure_output_dir()
    con = connect()
    build_views(con)

    revenue_stats = plot_revenue_distribution(con)
    monthly, _daily = plot_monthly_trend(con)
    country_note = export_top_countries_note(con)
    top_customers = plot_top_customers(con)
    top_products = plot_top_products(con)
    basket_summary = plot_basket_size(con)

    write_report(
        revenue_stats=revenue_stats,
        monthly=monthly,
        country_note=country_note,
        top_customers=top_customers,
        top_products=top_products,
        basket_summary=basket_summary,
    )

    print(f"EDA outputs saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
