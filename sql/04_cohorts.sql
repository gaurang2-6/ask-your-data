-- 04_cohorts.sql
-- Monthly acquisition cohorts: of the customers whose first purchase was in month M,
-- what share bought again k months later?

CREATE OR REPLACE TABLE cohort_retention AS
WITH activity AS (
    SELECT DISTINCT s.customer_id, f.first_month AS cohort_month, s.invoice_month
    FROM sales s
    JOIN customer_first_month f USING (customer_id)
),
counts AS (
    SELECT
        cohort_month,
        date_diff('month', cohort_month, invoice_month) AS months_since_first,
        count(*)                                        AS customers
    FROM activity
    GROUP BY ALL
)
SELECT
    cohort_month,
    months_since_first,
    customers,
    first_value(customers) OVER (PARTITION BY cohort_month ORDER BY months_since_first) AS cohort_size,
    round(100.0 * customers / first_value(customers) OVER (PARTITION BY cohort_month ORDER BY months_since_first), 1) AS retention_pct
FROM counts
ORDER BY cohort_month, months_since_first;

-- Average retention curve, weighted by cohort size. Only cohorts that are observable for
-- the full k months count towards month k, so late cohorts don't drag the curve down.
CREATE OR REPLACE TABLE retention_curve AS
WITH cohorts AS (
    -- The data starts in Dec 2009, so that "cohort" is every existing customer, not new ones.
    SELECT DISTINCT cohort_month, cohort_size FROM cohort_retention
    WHERE cohort_month > DATE '2009-12-01'
),
grid AS (   -- every (cohort, k) pair that is fully observable, including months with 0 returners
    SELECT c.cohort_month, c.cohort_size, k.months_since_first
    FROM cohorts c
    CROSS JOIN range(0, 24) k(months_since_first)
    WHERE c.cohort_month + to_months(CAST(k.months_since_first AS INTEGER)) <= DATE '2011-11-01'  -- last complete month
)
SELECT
    g.months_since_first,
    count(*)                                                          AS cohorts,
    round(100.0 * sum(coalesce(r.customers, 0)) / sum(g.cohort_size), 1) AS retention_pct
FROM grid g
LEFT JOIN cohort_retention r USING (cohort_month, months_since_first)
GROUP BY g.months_since_first
ORDER BY g.months_since_first;

-- Second-purchase conversion: share of customers who ever place a second order,
-- and the median days between first and second order.
CREATE OR REPLACE TABLE repeat_purchase AS
WITH orders AS (
    SELECT customer_id, invoice, min(invoice_date) AS order_date
    FROM sales
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id, invoice
),
numbered AS (
    SELECT *, row_number() OVER (PARTITION BY customer_id ORDER BY order_date) AS order_number
    FROM orders
),
first_two AS (
    SELECT
        customer_id,
        max(order_date) FILTER (WHERE order_number = 1) AS first_order,
        max(order_date) FILTER (WHERE order_number = 2) AS second_order
    FROM numbered
    GROUP BY customer_id
)
SELECT
    count(*)                                                              AS customers,
    round(100.0 * count(second_order) / count(*), 1)                      AS repeat_pct,
    median(date_diff('day', first_order, second_order))                   AS median_days_to_second_order,
    round(100.0 * count(*) FILTER (WHERE date_diff('day', first_order, second_order) <= 90)
          / count(*), 1)                                                  AS repeat_within_90d_pct
FROM first_two;
