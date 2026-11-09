-- 01_clean.sql
-- Raw Online Retail II → clean fact tables.
--   sales   : product purchase lines (one row per invoice line)
--   returns : cancelled lines (invoice starts with 'C'), quantities made positive
-- Written in PostgreSQL-compatible SQL; runs on DuckDB via `python -m retail.run`.

CREATE OR REPLACE TABLE raw AS
SELECT DISTINCT *                       -- ~34k exact duplicate rows, partly from the overlapping Dec-2010 sheets
FROM read_parquet('data/online_retail_ii.parquet');

-- Product lines only: 5-digit stock codes (optionally with a letter suffix, e.g. 85123A).
-- Excludes postage, manual adjustments, bank charges, Amazon fees, samples and gift vouchers.
CREATE OR REPLACE MACRO is_product(code) AS regexp_matches(code, '^[0-9]{5}[A-Za-z]*$');

-- Order-entry mistakes: a line cancelled in full by the same customer on the same day
-- (e.g. 80,995 paper birds, £168k, invoiced and cancelled on 9 Dec 2011). These are not
-- real sales or real returns, so both sides are dropped.
CREATE OR REPLACE TABLE reversed_lines AS
SELECT DISTINCT
    s.invoice AS sale_invoice, c.invoice AS cancel_invoice,
    s.stock_code, s.quantity, s.price, s.customer_id
FROM raw s
JOIN raw c
  ON  c.invoice LIKE 'C%'
  AND s.invoice NOT LIKE 'C%'
  AND c.customer_id = s.customer_id
  AND c.stock_code  = s.stock_code
  AND c.quantity    = -s.quantity
  AND c.price       = s.price
  AND CAST(c.invoice_date AS DATE) = CAST(s.invoice_date AS DATE)
  AND c.invoice_date >= s.invoice_date;

CREATE OR REPLACE TABLE sales AS
SELECT
    invoice,
    stock_code,
    trim(description)                   AS description,
    quantity,
    price,
    quantity * price                    AS revenue,
    invoice_date,
    CAST(date_trunc('month', invoice_date) AS DATE) AS invoice_month,
    customer_id,
    country
FROM raw
WHERE invoice NOT LIKE 'C%'             -- cancellations go to `returns`
  AND invoice NOT LIKE 'A%'             -- 6 bad-debt adjustment rows
  AND quantity > 0
  AND price > 0
  AND is_product(stock_code)
  AND (invoice, stock_code, quantity, price) NOT IN (
      SELECT (sale_invoice, stock_code, quantity, price) FROM reversed_lines);

CREATE OR REPLACE TABLE returns AS
SELECT
    invoice,
    stock_code,
    -quantity                           AS quantity,
    price,
    -quantity * price                   AS revenue,
    invoice_date,
    CAST(date_trunc('month', invoice_date) AS DATE) AS invoice_month,
    customer_id,
    country
FROM raw
WHERE invoice LIKE 'C%'
  AND quantity < 0
  AND price > 0
  AND is_product(stock_code)
  AND (invoice, stock_code, -quantity, price) NOT IN (
      SELECT (cancel_invoice, stock_code, quantity, price) FROM reversed_lines);

-- Row counts at each step, for the README's data-cleaning table.
CREATE OR REPLACE TABLE cleaning_log AS
SELECT 'raw rows'                         AS step, (SELECT count(*) FROM read_parquet('data/online_retail_ii.parquet')) AS n_rows
UNION ALL SELECT 'after removing exact duplicates', (SELECT count(*) FROM raw)
UNION ALL SELECT 'same-day reversed order lines removed', (SELECT count(*) FROM reversed_lines)
UNION ALL SELECT 'sales lines (products, qty > 0, price > 0)', (SELECT count(*) FROM sales)
UNION ALL SELECT 'sales lines with a customer id', (SELECT count(*) FROM sales WHERE customer_id IS NOT NULL)
UNION ALL SELECT 'return lines', (SELECT count(*) FROM returns);
