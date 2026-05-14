#!/usr/bin/env python3
"""
Cart abandonment analysis for the online retail dataset.

Important:
- The dataset has no order_id, so cart abandonment is approximated at the
  `user_session + product_id` level.
- A cart is considered "abandoned" only when an explicit cart event exists
  and no purchase event for the same session-product pair is observed.
- Purchases without an observed cart event are excluded from abandonment
  because they may reflect direct-buy behavior or missing tracking.
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


def prepare_cart_table(con: duckdb.DuckDBPyConnection) -> None:
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
            CAST(date_trunc('month', CAST(event_time AS TIMESTAMP)) AS DATE) AS event_month,
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
          AND CAST(event_time AS TIMESTAMP) IS NOT NULL
        """
    )

    con.execute(
        """
        CREATE OR REPLACE TABLE cart_session_product AS
        WITH session_product AS (
            SELECT
                user_session,
                product_id,
                any_value(category_code) AS category_code,
                any_value(brand) AS brand,
                MIN(event_month) AS first_month,
                MAX(CASE WHEN event_type = 'cart' THEN 1 ELSE 0 END) AS saw_cart_event,
                MAX(CASE WHEN event_type = 'purchase' AND price > 0 THEN 1 ELSE 0 END) AS saw_purchase_event,
                MAX(CASE WHEN price > 0 THEN price END) AS product_price
            FROM retail_events
            GROUP BY 1, 2
        )
        SELECT
            user_session,
            product_id,
            category_code,
            brand,
            first_month,
            saw_cart_event,
            saw_purchase_event,
            product_price,
            CASE
                WHEN product_price < 50 THEN 'Under 50'
                WHEN product_price < 150 THEN '50-149'
                WHEN product_price < 300 THEN '150-299'
                WHEN product_price < 600 THEN '300-599'
                WHEN product_price < 1000 THEN '600-999'
                ELSE '1000+'
            END AS price_band,
            CASE
                WHEN saw_cart_event = 1 AND saw_purchase_event = 0 THEN 1
                ELSE 0
            END AS cart_abandoned
        FROM session_product
        WHERE saw_cart_event = 1
        """
    )


def export_query(con: duckdb.DuckDBPyConnection, query: str, file_name: str) -> pd.DataFrame:
    df = con.execute(query).fetchdf()
    df.to_csv(OUTPUT_DIR / file_name, index=False)
    return df


def export_overview(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return export_query(
        con,
        """
        SELECT
            COUNT(*) AS cart_session_products,
            COUNT(DISTINCT user_session) AS cart_sessions,
            SUM(saw_purchase_event) AS purchased_after_cart,
            SUM(cart_abandoned) AS abandoned_after_cart,
            ROUND(100.0 * SUM(cart_abandoned) / COUNT(*), 2) AS cart_abandonment_rate_pct,
            ROUND(100.0 * SUM(saw_purchase_event) / COUNT(*), 2) AS cart_to_purchase_rate_pct,
            ROUND(AVG(CASE WHEN cart_abandoned = 1 THEN product_price END), 2) AS avg_abandoned_cart_price,
            ROUND(AVG(CASE WHEN saw_purchase_event = 1 THEN product_price END), 2) AS avg_converted_cart_price
        FROM cart_session_product
        """
        ,
        "cart_abandonment_overview.csv",
    )


def export_monthly(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return export_query(
        con,
        """
        SELECT
            first_month AS month_date,
            COUNT(*) AS cart_session_products,
            SUM(cart_abandoned) AS abandoned_after_cart,
            ROUND(100.0 * SUM(cart_abandoned) / COUNT(*), 2) AS cart_abandonment_rate_pct,
            ROUND(100.0 * SUM(saw_purchase_event) / COUNT(*), 2) AS cart_to_purchase_rate_pct
        FROM cart_session_product
        GROUP BY 1
        ORDER BY 1
        """,
        "cart_abandonment_monthly.csv",
    )


def export_by_category(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return export_query(
        con,
        """
        SELECT
            category_code,
            COUNT(*) AS cart_session_products,
            SUM(cart_abandoned) AS abandoned_after_cart,
            SUM(saw_purchase_event) AS purchased_after_cart,
            ROUND(100.0 * SUM(cart_abandoned) / COUNT(*), 2) AS cart_abandonment_rate_pct,
            ROUND(AVG(product_price), 2) AS avg_cart_price
        FROM cart_session_product
        GROUP BY 1
        ORDER BY abandoned_after_cart DESC
        """,
        "cart_abandonment_by_category.csv",
    )


def export_by_price_band(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return export_query(
        con,
        """
        SELECT
            price_band,
            COUNT(*) AS cart_session_products,
            SUM(cart_abandoned) AS abandoned_after_cart,
            SUM(saw_purchase_event) AS purchased_after_cart,
            ROUND(100.0 * SUM(cart_abandoned) / COUNT(*), 2) AS cart_abandonment_rate_pct
        FROM cart_session_product
        GROUP BY 1
        ORDER BY
            CASE price_band
                WHEN 'Under 50' THEN 1
                WHEN '50-149' THEN 2
                WHEN '150-299' THEN 3
                WHEN '300-599' THEN 4
                WHEN '600-999' THEN 5
                WHEN '1000+' THEN 6
                ELSE 7
            END
        """,
        "cart_abandonment_by_price_band.csv",
    )


def plot_cart_abandonment(
    category_df: pd.DataFrame,
    price_band_df: pd.DataFrame,
    monthly_df: pd.DataFrame,
) -> None:
    category_chart_df = category_df[
        (category_df["cart_session_products"] >= 5000)
        & (category_df["category_code"] != "Unknown")
    ].copy()
    category_chart_df = category_chart_df.nlargest(10, "abandoned_after_cart")
    category_chart_df = category_chart_df.sort_values("cart_abandonment_rate_pct")

    fig, axes = plt.subplots(1, 3, figsize=(20, 6.5))

    sns.barplot(
        data=category_chart_df,
        x="cart_abandonment_rate_pct",
        y="category_code",
        color="#d97706",
        ax=axes[0],
    )
    axes[0].set_title("High-Volume Categories by Cart Abandonment")
    axes[0].set_xlabel("Cart abandonment rate (%)")
    axes[0].set_ylabel("Category")

    sns.barplot(
        data=price_band_df,
        x="price_band",
        y="cart_abandonment_rate_pct",
        color="#2563eb",
        ax=axes[1],
    )
    axes[1].set_title("Cart Abandonment by Price Band")
    axes[1].set_xlabel("Price band")
    axes[1].set_ylabel("Cart abandonment rate (%)")
    axes[1].tick_params(axis="x", rotation=25)

    sns.lineplot(
        data=monthly_df,
        x="month_date",
        y="cart_abandonment_rate_pct",
        marker="o",
        linewidth=2.5,
        color="#0f766e",
        ax=axes[2],
    )
    axes[2].set_title("Monthly Cart Abandonment Rate")
    axes[2].set_xlabel("Month")
    axes[2].set_ylabel("Cart abandonment rate (%)")

    fig.suptitle("Cart Abandonment Analysis", fontsize=16, y=1.02)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "cart_abandonment.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def write_report(
    overview_df: pd.DataFrame,
    category_df: pd.DataFrame,
    price_band_df: pd.DataFrame,
    monthly_df: pd.DataFrame,
) -> None:
    overview = overview_df.iloc[0]
    top_categories = category_df[
        (category_df["cart_session_products"] >= 5000)
        & (category_df["category_code"] != "Unknown")
    ].nlargest(3, "abandoned_after_cart")
    high_price_band = price_band_df.sort_values("cart_abandonment_rate_pct", ascending=False).iloc[0]
    latest_month = monthly_df.sort_values("month_date").iloc[-1]

    lines = [
        "Cart Abandonment Analysis",
        "=========================",
        "",
        f"Observed cart session-product pairs: {int(overview['cart_session_products']):,}",
        f"Observed cart sessions: {int(overview['cart_sessions']):,}",
        f"Cart abandonment rate: {overview['cart_abandonment_rate_pct']:.2f}%",
        f"Cart-to-purchase rate: {overview['cart_to_purchase_rate_pct']:.2f}%",
        f"Average abandoned cart price: {overview['avg_abandoned_cart_price']:.2f}",
        f"Average converted cart price: {overview['avg_converted_cart_price']:.2f}",
        "",
        "Top high-volume categories by abandoned cart volume:",
    ]

    for _, row in top_categories.iterrows():
        lines.append(
            f"- {row['category_code']}: {int(row['abandoned_after_cart']):,} abandoned cart session-products, "
            f"{row['cart_abandonment_rate_pct']:.2f}% abandonment"
        )

    lines.extend(
        [
            "",
            f"Highest price-band abandonment: {high_price_band['price_band']} at "
            f"{high_price_band['cart_abandonment_rate_pct']:.2f}%",
            f"Latest month observed ({latest_month['month_date']}): "
            f"{latest_month['cart_abandonment_rate_pct']:.2f}% cart abandonment",
            "",
            "Interpretation:",
            "- Cart-stage loss is material and should be treated as a distinct conversion problem, not just weak traffic quality.",
            "- High-volume abandoned categories are the best candidates for product page, checkout-friction, or trust-signal experiments.",
            "- If more expensive price bands abandon more often, financing, reassurance, and offer framing should be tested before discounting.",
            "",
            "Important limitation:",
            "- This is not true order-level cart abandonment because the dataset does not include order_id or checkout-step tracking.",
        ]
    )

    (OUTPUT_DIR / "cart_abandonment_report.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_output_dir()
    con = connect()
    prepare_cart_table(con)

    overview_df = export_overview(con)
    monthly_df = export_monthly(con)
    category_df = export_by_category(con)
    price_band_df = export_by_price_band(con)

    plot_cart_abandonment(category_df, price_band_df, monthly_df)
    write_report(overview_df, category_df, price_band_df, monthly_df)

    print("Saved cart abandonment outputs to analysis/output")


if __name__ == "__main__":
    main()
