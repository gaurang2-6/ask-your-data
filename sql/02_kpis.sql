-- 02_kpis.sql
-- Monthly business KPIs: revenue, orders, average order value, active / new customers,
-- month-over-month growth and the share of revenue from returning customers.

CREATE OR REPLACE TABLE customer_first_month AS
SELECT customer_id, min(invoice_month) AS first_month
FROM sales
WHERE customer_id IS NOT NULL
GROUP BY customer_id;

CREATE OR REPLACE TABLE monthly_kpis AS
WITH monthly AS (
    SELECT
        s.invoice_month,
        sum(s.revenue)                                         AS revenue,
        count(DISTINCT s.invoice)                              AS orders,
        count(DISTINCT s.customer_id)                          AS active_customers,
        count(DISTINCT s.customer_id) FILTER (WHERE f.first_month = s.invoice_month) AS new_customers,
        sum(s.revenue) FILTER (WHERE f.first_month < s.invoice_month)               AS returning_revenue,
        sum(s.revenue) FILTER (WHERE s.customer_id IS NOT NULL)                     AS identified_revenue
    FROM sales s
    LEFT JOIN customer_first_month f USING (customer_id)
    GROUP BY s.invoice_month
),
monthly_returns AS (
    SELECT invoice_month, sum(revenue) AS returned_revenue
    FROM returns
    GROUP BY invoice_month
)
SELECT
    m.invoice_month,
    round(m.revenue, 2)                                              AS revenue,
    m.orders,
    round(m.revenue / m.orders, 2)                                   AS avg_order_value,
    m.active_customers,
    m.new_customers,
    round(100.0 * m.returning_revenue / m.identified_revenue, 1)     AS returning_revenue_pct,
    round(100.0 * coalesce(r.returned_revenue, 0) / m.revenue, 1)    AS return_rate_pct,
    round(100.0 * (m.revenue / lag(m.revenue) OVER w - 1), 1)        AS revenue_mom_pct,
    round(100.0 * (m.revenue / lag(m.revenue, 12) OVER w - 1), 1)    AS revenue_yoy_pct,
    m.invoice_month = (SELECT max(invoice_month) FROM sales)         AS is_partial_month   -- data ends 9 Dec 2011
FROM monthly m
LEFT JOIN monthly_returns r USING (invoice_month)
WINDOW w AS (ORDER BY m.invoice_month)
ORDER BY m.invoice_month;

-- Headline numbers for the KPI page (full period).
CREATE OR REPLACE TABLE headline_kpis AS
SELECT
    round(sum(revenue), 0)                                    AS total_revenue,
    count(DISTINCT invoice)                                   AS orders,
    count(DISTINCT customer_id)                               AS customers,
    round(sum(revenue) / count(DISTINCT invoice), 2)          AS avg_order_value,
    round(100.0 * sum(revenue) FILTER (WHERE customer_id IS NULL) / sum(revenue), 1) AS guest_revenue_pct,
    round(100.0 * sum(revenue) FILTER (WHERE country = 'United Kingdom') / sum(revenue), 1) AS uk_revenue_pct,
    round(100.0 * (SELECT sum(revenue) FROM returns) / sum(revenue), 1) AS return_rate_pct
FROM sales;

CREATE OR REPLACE TABLE top_countries AS
SELECT
    country,
    round(sum(revenue), 0)                                    AS revenue,
    count(DISTINCT customer_id)                               AS customers,
    round(100.0 * sum(revenue) / sum(sum(revenue)) OVER (), 1) AS revenue_share_pct,
    rank() OVER (ORDER BY sum(revenue) DESC)                  AS revenue_rank
FROM sales
GROUP BY country
QUALIFY revenue_rank <= 10
ORDER BY revenue_rank;

CREATE OR REPLACE TABLE top_products AS
SELECT
    stock_code,
    any_value(description)                                    AS description,
    sum(quantity)                                             AS units,
    round(sum(revenue), 0)                                    AS revenue,
    round(100.0 * sum(revenue) / sum(sum(revenue)) OVER (), 2) AS revenue_share_pct
FROM sales
GROUP BY stock_code
ORDER BY revenue DESC
LIMIT 15;
