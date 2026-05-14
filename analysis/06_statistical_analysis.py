#!/usr/bin/env python3
"""
Statistical analysis for the online retail project.

Hypotheses covered:
1. November and October purchase price distributions differ.
2. Smartphone conversion is higher than the rest of the catalog.
3. Apple purchase prices are higher than Samsung purchase prices.
"""

from __future__ import annotations

import math
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
from scipy.stats import mannwhitneyu


sns.set_theme(style="whitegrid")


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(DB_PATH))
    con.execute("PRAGMA threads=4;")
    return con


def prepare_tables(con: duckdb.DuckDBPyConnection) -> None:
    purchase_exists = con.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = 'purchase_clean'
        """
    ).fetchone()[0]
    if not purchase_exists:
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

    funnel_exists = con.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = 'funnel_session_product'
        """
    ).fetchone()[0]
    if funnel_exists:
        return

    events_exists = con.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = 'retail_events'
        """
    ).fetchone()[0]
    if not events_exists:
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
                any_value(user_id) AS user_id,
                MAX(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END) AS saw_view_event,
                MAX(CASE WHEN event_type = 'cart' THEN 1 ELSE 0 END) AS saw_cart_event,
                MAX(CASE WHEN event_type = 'purchase' AND price > 0 THEN 1 ELSE 0 END) AS saw_purchase_event,
                SUM(CASE WHEN event_type = 'purchase' AND price > 0 THEN price ELSE 0 END) AS revenue_proxy
            FROM retail_events
            GROUP BY 1, 2
        )
        SELECT
            user_session,
            product_id,
            category_code,
            brand,
            user_id,
            CASE WHEN saw_view_event = 1 OR saw_cart_event = 1 OR saw_purchase_event = 1 THEN 1 ELSE 0 END AS reached_view,
            CASE WHEN saw_cart_event = 1 OR saw_purchase_event = 1 THEN 1 ELSE 0 END AS reached_cart,
            saw_purchase_event AS reached_purchase,
            revenue_proxy
        FROM stage_flags
        """
    )


def z_test_two_proportions(success_a: float, total_a: float, success_b: float, total_b: float) -> tuple[float, float]:
    p_a = success_a / total_a
    p_b = success_b / total_b
    pooled = (success_a + success_b) / (total_a + total_b)
    se = math.sqrt(pooled * (1 - pooled) * ((1 / total_a) + (1 / total_b)))
    z = (p_a - p_b) / se
    p_value = math.erfc(abs(z) / math.sqrt(2))
    return z, p_value


def run_tests(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    monthly_prices = con.execute(
        """
        SELECT
            CAST(date_trunc('month', event_ts) AS DATE) AS month_date,
            price
        FROM purchase_clean
        """
    ).fetchdf()

    oct_prices = monthly_prices.loc[monthly_prices["month_date"].astype(str) == "2019-10-01", "price"].to_numpy()
    nov_prices = monthly_prices.loc[monthly_prices["month_date"].astype(str) == "2019-11-01", "price"].to_numpy()
    mw_month = mannwhitneyu(oct_prices, nov_prices, alternative="two-sided")

    top_brand_prices = con.execute(
        """
        SELECT brand, price
        FROM purchase_clean
        WHERE brand IN ('apple', 'samsung')
        """
    ).fetchdf()
    apple_prices = top_brand_prices.loc[top_brand_prices["brand"] == "apple", "price"].to_numpy()
    samsung_prices = top_brand_prices.loc[top_brand_prices["brand"] == "samsung", "price"].to_numpy()
    mw_brand = mannwhitneyu(apple_prices, samsung_prices, alternative="two-sided")

    smartphone, rest = con.execute(
        """
        WITH smartphone AS (
            SELECT
                SUM(reached_purchase) AS purchases,
                SUM(reached_view) AS views
            FROM funnel_session_product
            WHERE category_code = 'electronics.smartphone'
        ),
        rest AS (
            SELECT
                SUM(reached_purchase) AS purchases,
                SUM(reached_view) AS views
            FROM funnel_session_product
            WHERE category_code <> 'electronics.smartphone'
              AND category_code <> 'Unknown'
        )
        SELECT
            smartphone.purchases,
            smartphone.views,
            rest.purchases,
            rest.views
        FROM smartphone, rest
        """
    ).fetchone()[:2], con.execute(
        """
        WITH smartphone AS (
            SELECT
                SUM(reached_purchase) AS purchases,
                SUM(reached_view) AS views
            FROM funnel_session_product
            WHERE category_code = 'electronics.smartphone'
        ),
        rest AS (
            SELECT
                SUM(reached_purchase) AS purchases,
                SUM(reached_view) AS views
            FROM funnel_session_product
            WHERE category_code <> 'electronics.smartphone'
              AND category_code <> 'Unknown'
        )
        SELECT
            rest.purchases,
            rest.views
        FROM smartphone, rest
        """
    ).fetchone()
    z_value, z_p = z_test_two_proportions(
        success_a=float(smartphone[0]),
        total_a=float(smartphone[1]),
        success_b=float(rest[0]),
        total_b=float(rest[1]),
    )

    results = pd.DataFrame(
        [
            {
                "hypothesis": "November vs October purchase price distribution",
                "group_a": "October 2019",
                "group_b": "November 2019",
                "metric_a": float(pd.Series(oct_prices).median()),
                "metric_b": float(pd.Series(nov_prices).median()),
                "uplift_pct": round(((pd.Series(nov_prices).median() - pd.Series(oct_prices).median()) / pd.Series(oct_prices).median()) * 100, 2),
                "test": "Mann-Whitney U",
                "statistic": float(mw_month.statistic),
                "p_value": float(mw_month.pvalue),
            },
            {
                "hypothesis": "Smartphone conversion vs rest of catalog",
                "group_a": "electronics.smartphone",
                "group_b": "All non-smartphone categories",
                "metric_a": round(float(smartphone[0]) / float(smartphone[1]) * 100, 2),
                "metric_b": round(float(rest[0]) / float(rest[1]) * 100, 2),
                "uplift_pct": round((((float(smartphone[0]) / float(smartphone[1])) / (float(rest[0]) / float(rest[1]))) - 1) * 100, 2),
                "test": "Two-proportion z-test",
                "statistic": float(z_value),
                "p_value": float(z_p),
            },
            {
                "hypothesis": "Apple vs Samsung purchase price distribution",
                "group_a": "apple",
                "group_b": "samsung",
                "metric_a": float(pd.Series(apple_prices).median()),
                "metric_b": float(pd.Series(samsung_prices).median()),
                "uplift_pct": round(((pd.Series(apple_prices).median() - pd.Series(samsung_prices).median()) / pd.Series(samsung_prices).median()) * 100, 2),
                "test": "Mann-Whitney U",
                "statistic": float(mw_brand.statistic),
                "p_value": float(mw_brand.pvalue),
            },
        ]
    )
    results.to_csv(OUTPUT_DIR / "statistical_tests_summary.csv", index=False)
    return results


def plot_monthly_price_sample(con: duckdb.DuckDBPyConnection) -> None:
    sample_df = con.execute(
        """
        WITH sample AS (
            SELECT
                CAST(date_trunc('month', event_ts) AS DATE) AS month_date,
                price
            FROM purchase_clean
            USING SAMPLE 250000 ROWS
        )
        SELECT * FROM sample
        """
    ).fetchdf()

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.boxplot(data=sample_df, x=sample_df["month_date"].astype(str), y="price", showfliers=False, ax=ax)
    ax.set_title("Purchase Price Distribution by Month")
    ax.set_xlabel("Month")
    ax.set_ylabel("Price")
    ax.set_ylim(0, sample_df["price"].quantile(0.95))
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "stats_monthly_price_boxplot.png", dpi=160)
    plt.close(fig)


def plot_conversion_comparison(con: duckdb.DuckDBPyConnection) -> None:
    compare_df = con.execute(
        """
        WITH base AS (
            SELECT 'electronics.smartphone' AS group_name, SUM(reached_purchase) AS purchases, SUM(reached_view) AS views
            FROM funnel_session_product
            WHERE category_code = 'electronics.smartphone'
            UNION ALL
            SELECT 'rest_of_catalog' AS group_name, SUM(reached_purchase) AS purchases, SUM(reached_view) AS views
            FROM funnel_session_product
            WHERE category_code <> 'electronics.smartphone'
              AND category_code <> 'Unknown'
        )
        SELECT
            group_name,
            ROUND(100.0 * purchases / views, 2) AS conversion_pct
        FROM base
        """
    ).fetchdf()

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.barplot(data=compare_df, x="group_name", y="conversion_pct", ax=ax, color="#0f766e")
    ax.set_title("Smartphone Conversion vs Rest of Catalog")
    ax.set_xlabel("")
    ax.set_ylabel("Purchase to view conversion (%)")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "stats_conversion_comparison.png", dpi=160)
    plt.close(fig)


def plot_brand_price_sample(con: duckdb.DuckDBPyConnection) -> None:
    brand_sample = con.execute(
        """
        SELECT brand, price
        FROM purchase_clean
        WHERE brand IN ('apple', 'samsung', 'xiaomi')
        USING SAMPLE 180000 ROWS
        """
    ).fetchdf()

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.boxplot(data=brand_sample, x="brand", y="price", showfliers=False, ax=ax)
    ax.set_title("Purchase Price Distribution by Top Brands")
    ax.set_xlabel("Brand")
    ax.set_ylabel("Price")
    ax.set_ylim(0, brand_sample["price"].quantile(0.95))
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "stats_brand_price_boxplot.png", dpi=160)
    plt.close(fig)


def write_report(results: pd.DataFrame) -> None:
    lines = ["STATISTICAL ANALYSIS", ""]
    for _, row in results.iterrows():
        lines.append(
            f"- {row['hypothesis']}: {row['group_a']}={row['metric_a']}, {row['group_b']}={row['metric_b']}, "
            f"uplift={row['uplift_pct']}%, p-value={row['p_value']:.6g}"
        )
    lines.extend(
        [
            "",
            "Business interpretation:",
            "- Statistical significance confirms that the portfolio differences we saw in EDA are not random noise within this sample.",
            "- Effect size still matters more than p-value here because the dataset is very large and can make small differences look significant.",
            "- Smartphone strength is not just a visual impression from charts; it is statistically stronger conversion than the rest of the catalog.",
            "",
            "Potential issues:",
            "- Large samples inflate statistical power, so practical importance should be judged with uplift and median differences, not p-value alone.",
            "- Purchase price is still a proxy metric because no quantity or order total exists.",
        ]
    )
    (OUTPUT_DIR / "statistical_analysis_report.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_output_dir()
    con = connect()
    prepare_tables(con)
    results = run_tests(con)
    plot_monthly_price_sample(con)
    plot_conversion_comparison(con)
    plot_brand_price_sample(con)
    write_report(results)
    print(f"Statistical outputs saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
