-- 03_rfm.sql
-- RFM segmentation for identified customers.
--   Recency   : days since last purchase, measured from the day after the last invoice in the data
--   Frequency : number of distinct orders
--   Monetary  : net spend (purchases minus returns)
-- Each is scored 1–5 by quintile (5 = best), then mapped to named segments.

CREATE OR REPLACE TABLE rfm AS
WITH snapshot AS (
    SELECT CAST(max(invoice_date) AS DATE) + 1 AS snapshot_date FROM sales
),
purchases AS (
    SELECT
        customer_id,
        any_value(country)               AS country,
        max(invoice_date)                AS last_purchase,
        count(DISTINCT invoice)          AS frequency,
        sum(revenue)                     AS gross_spend
    FROM sales
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
),
customer_returns AS (
    SELECT customer_id, sum(revenue) AS returned
    FROM returns
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
),
base AS (
    SELECT
        p.customer_id,
        p.country,
        date_diff('day', CAST(p.last_purchase AS DATE), s.snapshot_date) AS recency_days,
        p.frequency,
        round(p.gross_spend - coalesce(r.returned, 0), 2)               AS monetary
    FROM purchases p
    CROSS JOIN snapshot s
    LEFT JOIN customer_returns r USING (customer_id)
),
scored AS (
    SELECT
        *,
        ntile(5) OVER (ORDER BY recency_days DESC)               AS r_score,  -- more recent → higher
        ntile(5) OVER (ORDER BY frequency, monetary)             AS f_score,  -- ties on frequency broken by spend
        ntile(5) OVER (ORDER BY monetary)                        AS m_score
    FROM base
)
SELECT
    *,
    CASE
        WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'
        WHEN r_score >= 3 AND f_score >= 3                  THEN 'Loyal'
        WHEN r_score >= 4 AND f_score <= 2                  THEN 'New / Promising'
        WHEN r_score  = 3 AND f_score <= 2                  THEN 'Need Attention'
        WHEN r_score <= 2 AND f_score >= 4                  THEN 'At Risk (high value)'
        WHEN r_score <= 2 AND f_score  = 3                  THEN 'At Risk'
        WHEN r_score  = 2                                   THEN 'Hibernating'
        ELSE 'Lost'
    END AS segment
FROM scored;

CREATE OR REPLACE TABLE rfm_segments AS
SELECT
    segment,
    count(*)                                                   AS customers,
    round(100.0 * count(*) / sum(count(*)) OVER (), 1)         AS customer_pct,
    round(sum(monetary), 0)                                    AS revenue,
    round(100.0 * sum(monetary) / sum(sum(monetary)) OVER (), 1) AS revenue_pct,
    round(median(recency_days), 0)                             AS median_recency_days,
    round(median(frequency), 1)                                AS median_orders,
    round(median(monetary), 0)                                 AS median_spend
FROM rfm
GROUP BY segment
ORDER BY revenue DESC;

-- Revenue concentration: what share of revenue comes from the top x% of customers.
CREATE OR REPLACE TABLE revenue_concentration AS
WITH ranked AS (
    SELECT
        monetary,
        percent_rank() OVER (ORDER BY monetary DESC)                     AS pct_rank,
        sum(monetary) OVER (ORDER BY monetary DESC ROWS UNBOUNDED PRECEDING) / sum(monetary) OVER () AS cum_share
    FROM rfm
)
SELECT
    top_pct,
    round(100.0 * max(cum_share) FILTER (WHERE pct_rank < top_pct / 100.0), 1) AS revenue_share_pct
FROM ranked, (VALUES (1), (5), (10), (20), (50)) t(top_pct)
GROUP BY top_pct
ORDER BY top_pct;
