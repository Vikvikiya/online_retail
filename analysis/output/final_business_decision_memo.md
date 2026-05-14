# Final Business Decision Memo

## Context

This portfolio is commercially strong but structurally concentrated. Smartphones, Apple, and Samsung account for a disproportionate share of value. At the same time, there are clear conversion gaps, retention opportunities, and measurement limits.

## Top Priorities

### Protect smartphone category economics
- Focus area: Merchandising and pricing
- Evidence: Smartphones contribute 66.29% of category revenue proxy and convert 132.59% better than the rest of the catalog.
- Expected outcome: Preserve the portfolio’s largest commercial engine.
- Primary metric: Revenue proxy, conversion, stockout rate

### Improve high-traffic / low-conversion categories
- Focus area: Conversion optimization
- Evidence: 21 categories sit in the high-traffic/low-conversion bucket with 13.96M revenue proxy at risk.
- Expected outcome: Lift monetization of existing traffic without buying more demand.
- Primary metric: Purchase-to-view conversion

### Retention play for Cannot Lose Them
- Focus area: CRM and lifecycle marketing
- Evidence: Cannot Lose Them drive 16.03% of revenue proxy with high historical value and weaker recency.
- Expected outcome: Recover high-value customers before value decays further.
- Primary metric: 30-day repeat rate, win-back rate

## Recommended Experiment Roadmap

### Desktop category PDP redesign
- Hypothesis: Improving trust, specifications, and comparison clarity on high-traffic low-conversion desktop pages will increase purchase conversion.
- Target group: computers.desktop visitors
- Primary metric: Purchase-to-view conversion
- Guardrails: Bounce rate, add-to-cart rate, average order value proxy

### Bundle recommendations on single-item flows
- Hypothesis: Adding accessory bundles and cart recommendations will increase items per purchase session.
- Target group: Single-item purchase journeys
- Primary metric: Items per purchase session
- Guardrails: Conversion rate, session value proxy, cart abandonment

### Potential Loyalists repeat-purchase CRM flow
- Hypothesis: A lifecycle email or push sequence within 7 to 30 days of first purchase will increase repeat rate among Potential Loyalists.
- Target group: Potential Loyalists
- Primary metric: 30-day repeat rate
- Guardrails: Unsubscribe rate, promo dependency, margin proxy

### Win-back campaign for Cannot Lose Them
- Hypothesis: A targeted win-back offer or reminder for high-value dormant customers will recover revenue more efficiently than broad retention campaigns.
- Target group: Cannot Lose Them
- Primary metric: Reactivation rate
- Guardrails: Discount cost, net revenue proxy, unsubscribes

### Traffic reallocation to niche converters
- Hypothesis: Increasing exposure for low-traffic high-conversion categories will generate more efficient revenue than adding traffic to weak categories.
- Target group: High-conversion niche categories
- Primary metric: Incremental revenue proxy per 1,000 views
- Guardrails: Overall conversion mix, traffic quality

## Missing Data That Blocks Better Decisions

- order_id: blocks True order-level basket and checkout analysis because Purchase sessions are only a proxy for real orders.
- quantity: blocks True revenue and basket economics because A single purchase event may represent different unit counts.
- country / geography: blocks Geo expansion and localization decisions because Country-level analysis cannot be done honestly without geography.
- margin / cost: blocks Profitability prioritization because Revenue concentration does not necessarily mean profit concentration.
- traffic source: blocks Acquisition efficiency analysis because Low conversion may come from lower-intent traffic rather than poor onsite experience.

## Final Recommendation

The best senior-level recommendation from this analysis is not to chase more top-line traffic first. The better move is to protect the concentrated revenue engine, improve conversion in wasted-traffic categories, and build a CRM retention layer around high-value and high-potential segments.