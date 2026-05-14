# Online Retail Analytics Project

An e-commerce analytics portfolio project based on a large event-level online retail dataset covering October and November 2019.

## Project Goal

This project demonstrates a full analytics workflow on large-scale e-commerce data:

- data quality review
- exploratory data analysis
- funnel and assortment analysis
- cart abandonment analysis
- customer segmentation
- statistical validation of key findings
- business recommendations

## What This Repository Includes

- reproducible Python scripts for each analysis stage
- visualizations and summary charts
- business-focused conclusions for every analysis block
- RFM customer segmentation
- cart abandonment measurement at the session-product level
- statistical testing for key hypotheses
- a single HTML dashboard with the final visuals and conclusions

## How To Review The Project

The best reading order is:

1. `README.md` for the project story and main findings
2. `analysis/output/*.png` for the visual results
3. `analysis/dashboard.html` for a single-page summary of the analysis
4. `analysis/*.py` for the reproducible code

For local review, the easiest file to open is:

- [analysis/dashboard.html](analysis/dashboard.html)

## Scope Completed

The project includes:

1. Data overview and data quality checks
2. Cleaning logic and dataset limitation review
3. Core EDA for revenue, trends, customers, products, and basket size
4. Category funnel analysis
5. Cart abandonment analysis
6. Category and brand mix analysis
7. Category opportunity matrix
8. RFM segmentation
9. Statistical analysis of key hypotheses
10. Retention and cohort analysis
11. Impact vs effort prioritization
12. Experiment roadmap and final decision memo
13. Visual packaging into a single HTML dashboard

## Important Dataset Limitation

This is an **event-level** dataset, not an order-level dataset.

The data contains:

- `view`
- `cart`
- `purchase`

The data does not contain:

- `order_id`
- product quantity
- country or geography

Because of that:

- revenue is treated as a **purchase-value proxy**, not audited financial revenue
- basket size is measured at the **purchase-session proxy** level
- country analysis is **not possible** without an external geography field

## Data Source

This project uses the Online Retail event dataset from Kaggle. The raw CSV files are not stored in this repository because of their size.

Source:
[ECommerce behavior data from multi-category store](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store)

## Tools Used

- `Python`
- `DuckDB`
- `Pandas`
- `Matplotlib`
- `Seaborn`
- `SciPy`

## Executive Summary

- November growth was driven mainly by **more purchasing users and more purchase events**, not by a higher ticket size.
- The portfolio is **highly concentrated**: `electronics.smartphone` accounts for `66.29%` of category revenue proxy.
- Brand concentration is also high: `Apple + Samsung = 67.31%` of brand revenue proxy.
- Most purchase sessions are **single-item**: average purchase session size is `1.18`, median is `1`.
- Observed cart abandonment is `62.02%` at the `session + product` cart level, with November rising to `65.25%`.
- Repeat customers are only `36.84%` of customers, but they generate `73.77%` of revenue proxy.
- The October cohort shows `26.3%` month-1 retention, and the eligible 30-day repeat rate is `40.52%`.
- From a retention perspective, a large share of customer value sits in **Champions** and **Loyal Customers**, while **Cannot Lose Them** already requires dedicated retention action.
- Statistical tests confirm that:
  - smartphones convert materially better than the rest of the catalog
  - November has a different price mix than October
  - Apple operates in a significantly more premium price tier than Samsung
- The best next business moves are not more traffic first, but conversion repair, retention, and protection of the concentrated revenue engine.

## Main Findings

### 1. Revenue Distribution

- purchase events analyzed: `1,659,788`
- revenue proxy: `505.2M`
- average purchase price: `304.35`
- median purchase price: `174.02`

Interpretation:

- the distribution is strongly right-skewed
- a meaningful share of value comes from higher-priced items
- the business is not driven by a flat mix of low-value orders; premium products materially shape performance

![Revenue Distribution](analysis/output/revenue_distribution.png)

### 2. Monthly Trend

- October revenue proxy: `229.96M`
- November revenue proxy: `275.19M`
- month-over-month growth: about `19.7%`

Interpretation:

- November growth came mainly from a broader buyer base and more purchase activity
- average purchase price declined slightly, so the uplift was volume-driven rather than ticket-driven

![Monthly and Daily Trend](analysis/output/monthly_daily_trend.png)

### 3. Top Customers

Interpretation:

- a relatively small group of customers appears to generate very high value
- this strongly supports the use of RFM and customer-value segmentation
- some of the top customers may reflect reseller or business-like behavior

![Top Customers](analysis/output/top_customers.png)

### 4. Top Products

Interpretation:

- the top products are dominated by Apple and Samsung smartphones
- revenue is concentrated around a narrow set of hero SKUs
- this is commercially powerful, but risky from an assortment dependency perspective

![Top Products](analysis/output/top_products.png)

### 5. Basket Size

- average items per purchase session: `1.18`
- median items per purchase session: `1`

Interpretation:

- most purchase sessions are single-item
- cross-sell and bundling appear underdeveloped
- this may reflect either a high-consideration catalog or missed merchandising opportunities

![Basket Size](analysis/output/basket_size.png)

### 6. Category Conversion Funnel

Interpretation:

- some categories combine high traffic with strong conversion
- `electronics.smartphone` is especially important because it combines large traffic volume with strong purchase intent
- high-traffic, low-conversion categories represent the biggest short-term optimization opportunity

![Category Conversion](analysis/output/category_conversion.png)

### 7. Cart Abandonment

- cart session-product pairs observed: `2,681,975`
- cart abandonment rate: `62.02%`
- cart-to-purchase rate: `37.98%`
- October cart abandonment: `51.46%`
- November cart abandonment: `65.25%`

Interpretation:

- cart-stage loss is too large to treat as normal leakage; it is a meaningful commercial problem on its own
- the largest abandoned-cart volume sits in `electronics.smartphone`, `electronics.audio.headphone`, and `electronics.video.tv`, so fixing cart friction there can matter at scale
- lower-priced items abandon the most (`69.20%` under 50), which suggests hesitation is not only about financing or high-ticket affordability

Important note:

- this is measured at the `user_session + product_id` level and requires an explicit observed cart event, so it is a conservative proxy rather than true checkout abandonment

![Cart Abandonment](analysis/output/cart_abandonment.png)

### 8. Category Revenue Mix

- `electronics.smartphone` contributes `66.29%` of category revenue proxy

Interpretation:

- the portfolio depends heavily on the smartphone category
- this is the main commercial engine, but also a major concentration risk

![Category Revenue Mix](analysis/output/category_revenue_mix.png)

### 9. Brand Revenue Mix

- `Apple`: `47.26%`
- `Samsung`: `20.05%`
- combined: `67.31%`

Interpretation:

- brand concentration is very high
- supplier dependency and brand concentration are important strategic risks

![Brand Revenue Mix](analysis/output/brand_revenue_mix.png)

### 10. Category Opportunity Matrix

Interpretation:

- the core portfolio sits in the **High Traffic / High Conversion** quadrant
- categories such as `computers.desktop`, `furniture.living_room.sofa`, and `apparel.shoes` stand out as optimization targets
- categories such as `appliances.environment.air_conditioner` and `electronics.camera.photo` look like underexposed niche opportunities

![Category Opportunity Matrix](analysis/output/category_opportunity_matrix.png)

### 11. RFM Segmentation

- `Champions`: `96,004` customers, `42.39%` revenue share
- `Loyal Customers`: `67,963` customers, `14.74%` revenue share
- `Cannot Lose Them`: `48,511` customers, `16.03%` revenue share
- `Potential Loyalists`: `128,038` customers, `8.08%` revenue share

Interpretation:

- nearly half of total value is concentrated in `Champions`
- `Cannot Lose Them` already represents too much value to ignore from a retention standpoint
- `Potential Loyalists` are the best audience for CRM, personalization, and repeat-purchase growth

![RFM Segment Revenue](analysis/output/rfm_segment_revenue.png)
![RFM Heatmap](analysis/output/rfm_heatmap.png)

### 12. Statistical Analysis

Tested hypotheses:

- November vs October purchase price distribution
- smartphone conversion vs the rest of the catalog
- Apple vs Samsung purchase price distribution

Results:

- median November purchase price is about `5.49%` lower than October
- `electronics.smartphone` converts to purchase about `132.59%` better than the rest of the catalog
- Apple median purchase price is about `231.94%` higher than Samsung

Interpretation:

- smartphone strength is not just a visual pattern; it is statistically stronger than the rest of the catalog
- November growth came with a cheaper price mix
- Apple functions as a premium price engine in the portfolio

Important note:

- with a dataset this large, even small differences can become statistically significant
- business meaning should therefore be judged with **uplift, median differences, and concentration**, not p-values alone

![Monthly Price Boxplot](analysis/output/stats_monthly_price_boxplot.png)
![Conversion Comparison](analysis/output/stats_conversion_comparison.png)
![Brand Price Boxplot](analysis/output/stats_brand_price_boxplot.png)

### 13. Retention and Cohort Analysis

- repeat customer share: `36.84%`
- repeat revenue share: `73.77%`
- average days to second purchase: `8.13`
- median days to second purchase: `3`
- repeat within 7 days: `25.17%`
- repeat within 30 days: `40.52%`
- October cohort month-1 retention: `26.3%`

Interpretation:

- repeat customers are not the majority of the customer base, but they drive most of the value
- second purchases happen quickly for many customers, which suggests CRM timing should focus on the first week and first month
- retention analysis makes the case stronger than RFM alone because it shows real behavioral continuation over time

![Cohort Retention Heatmap](analysis/output/cohort_retention_heatmap.png)
![Repeat Mix](analysis/output/retention_repeat_mix.png)
![Days to Second Purchase](analysis/output/days_to_second_purchase.png)

### 14. Decision Prioritization

Top strategic priorities:

1. Protect smartphone category economics
2. Improve high-traffic / low-conversion categories
3. Launch a retention play for `Cannot Lose Them`
4. Convert `Potential Loyalists` into repeat buyers
5. Improve cross-sell and bundling

Interpretation:

- this layer moves the project from descriptive analytics into business decision support
- the most important senior-level shift is prioritization: not everything should be done at once
- the project now identifies what should be protected, what should be optimized, and what should be tested next

![Impact vs Effort Matrix](analysis/output/impact_effort_matrix.png)

### 15. Experiment Roadmap

Recommended tests:

- desktop category PDP redesign
- bundle recommendations on single-item flows
- repeat-purchase CRM flow for `Potential Loyalists`
- win-back campaign for `Cannot Lose Them`
- traffic reallocation to niche high-conversion categories

Interpretation:

- each experiment is tied to a concrete analytical finding
- the roadmap focuses on measurable business outcomes rather than generic “optimization”
- this creates a bridge from analysis to product, CRM, and merchandising execution

![Experiment Roadmap](analysis/output/ab_test_roadmap.png)

## Final Business Recommendations

1. Protect the smartphone category as the main revenue engine through stock, pricing, product page quality, and promotional priority.
2. Reduce concentration risk over time by developing additional growth pockets outside smartphones and outside Apple/Samsung.
3. Prioritize high-traffic, low-conversion categories as the main source of near-term performance uplift.
4. Improve cross-sell and bundling because the current basket pattern is heavily single-item.
5. Build retention strategies by RFM segment:
   - protect `Champions` and `Loyal Customers`
   - convert `Potential Loyalists` into repeat purchasers
   - win back `Cannot Lose Them` and `At Risk` customers with targeted campaigns
6. Add geography and order-level data in the next phase if the goal is true market expansion analysis or real basket economics.
7. Use experiment sequencing rather than broad changes:
   - fix high-traffic low-conversion categories first
   - test retention flows second
   - expand traffic to efficient niche categories third

## Project Limitations

- the dataset covers only `October–November 2019`
- there is no `country`
- there is no `order_id`
- there is no `quantity`
- revenue in this project is an analytical proxy, not financial reporting

These limitations do not invalidate the project, but they are essential for correct interpretation.

## Project Structure

```text
analysis/
  step01_data_audit.py
  02_eda.py
  03_funnel_mix_eda.py
  04_category_opportunity_matrix.py
  05_rfm_segmentation.py
  06_statistical_analysis.py
  07_retention_cohort_analysis.py
  09_cart_abandonment_analysis.py
  08_decision_memo.py
  dashboard.html
  output/
README.md
requirements.txt
```

## How To Reproduce

1. Create a virtual environment
2. Install the dependencies
3. Place the source CSV files in the project root with these names:
   - `2019-Oct.csv`
   - `2019-Nov.csv`
4. Run the scripts stage by stage from the `analysis` folder

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python analysis/step01_data_audit.py
python analysis/02_eda.py
python analysis/03_funnel_mix_eda.py
python analysis/04_category_opportunity_matrix.py
python analysis/05_rfm_segmentation.py
python analysis/06_statistical_analysis.py
python analysis/07_retention_cohort_analysis.py
python analysis/09_cart_abandonment_analysis.py
python analysis/08_decision_memo.py
```

## HTML Dashboard

All key visuals and concise business conclusions are collected in:

- [analysis/dashboard.html](analysis/dashboard.html)

Additional strategic outputs:

- [analysis/output/final_business_decision_memo.md](analysis/output/final_business_decision_memo.md)
- [analysis/output/decision_priority_matrix.csv](analysis/output/decision_priority_matrix.csv)
- [analysis/output/ab_test_roadmap.csv](analysis/output/ab_test_roadmap.csv)

## Not Included In The Repository

Because of file size, the repository does not include:

- `2019-Oct.csv`
- `2019-Nov.csv`
- `online_retail.duckdb`
- `.venv`
