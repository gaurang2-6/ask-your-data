import pytest

from askdata.guard import GuardError, check


@pytest.mark.parametrize("sql", [
    "SELECT * FROM sales",
    "select count(*) from sales;",
    "WITH m AS (SELECT * FROM monthly_kpis) SELECT * FROM m",
    "SELECT country FROM sales UNION SELECT country FROM rfm",
    "SELECT s.country, r.segment FROM sales s JOIN rfm r USING (customer_id)",
    "SELECT * FROM main.sales",
    "SELECT dayname(invoice_date), sum(revenue) FROM sales GROUP BY 1",
])
def test_accepts_plain_selects(sql):
    assert check(sql) == sql.strip().rstrip(";")


@pytest.mark.parametrize("sql, reason", [
    ("DROP TABLE sales", "Only SELECT"),
    ("DELETE FROM sales", "Only SELECT"),
    ("INSERT INTO sales VALUES (1)", "Only SELECT"),
    ("UPDATE sales SET price = 0", "Only SELECT"),
    ("CREATE TABLE x AS SELECT 1", "Only SELECT"),
    ("ATTACH 'other.db'", "Only SELECT"),
    ("COPY sales TO 'out.csv'", "Only SELECT"),
    ("PRAGMA database_list", "Only SELECT"),
    ("SET threads = 1", "Only SELECT"),
    ("INSTALL httpfs", "Only SELECT"),
    ("SELECT 1; DROP TABLE sales", "exactly one"),
    ("SELECT * FROM secrets", "Unknown table"),
    ("SELECT * FROM information_schema.tables", "main schema"),
    ("SELECT * FROM other.main.sales", "main schema"),
    ("SELECT * FROM read_csv('/etc/passwd')", "Table functions"),
    ("SELECT * FROM duckdb_settings()", "Table functions"),
    ("SELECT getenv('HOME')", "not allowed"),
    ("SELECT current_setting('threads')", "not allowed"),
    ("SELECT * FROM sales WHERE country = (SELECT read_text('x'))", "not allowed"),
    ("", "empty"),
    ("SELEC * FRM sales", None),
])
def test_rejects_everything_else(sql, reason):
    with pytest.raises(GuardError, match=reason):
        check(sql)
