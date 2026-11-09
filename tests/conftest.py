import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="session")
def tiny_db(tmp_path_factory) -> Path:
    """A few rows in two of the allowed tables, plus one table the agent must not see."""
    path = tmp_path_factory.mktemp("db") / "tiny.duckdb"
    con = duckdb.connect(str(path))
    con.execute("""
        CREATE TABLE sales AS SELECT * FROM (VALUES
            ('1001', '85123A', 6, 2.55, 15.30, 17850, 'United Kingdom', TIMESTAMP '2011-01-04 10:00:00'),
            ('1001', '71053',  6, 3.39, 20.34, 17850, 'United Kingdom', TIMESTAMP '2011-01-04 10:00:00'),
            ('1002', '85123A', 2, 2.55,  5.10, 12583, 'France',         TIMESTAMP '2011-02-11 14:30:00'),
            ('1003', '22423',  1, 12.75, 12.75, NULL, 'Germany',        TIMESTAMP '2011-02-20 09:15:00')
        ) t(invoice, stock_code, quantity, price, revenue, customer_id, country, invoice_date)
    """)
    con.execute("""
        CREATE TABLE monthly_kpis AS SELECT * FROM (VALUES
            (DATE '2011-01-01', 35.64, 1),
            (DATE '2011-02-01', 17.85, 2)
        ) t(invoice_month, revenue, orders)
    """)
    con.execute("CREATE TABLE secrets AS SELECT 'hunter2' AS password")
    con.close()
    return path


class ScriptedLLM:
    """Returns the queued SQL strings in order and records the feedback it was shown."""

    def __init__(self, *sqls: str):
        self.sqls = list(sqls)
        self.feedback_seen: list[list[str]] = []

    def generate_sql(self, question, schema, feedback):
        self.feedback_seen.append(list(feedback))
        return {"sql": self.sqls.pop(0), "chart": {"type": "none", "x": "", "y": ""}, "rationale": "stub"}

    def explain(self, question, sql, rows):
        return f"Explained {len(rows.splitlines()) - 1} rows."


@pytest.fixture
def scripted():
    return ScriptedLLM
