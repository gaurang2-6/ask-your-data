"""Read-only DuckDB access with a hard timeout and a row cap."""
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from .guard import ALLOWED_TABLES

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "retail.duckdb"
MAX_ROWS = 1000
TIMEOUT_S = 10.0


class QueryError(RuntimeError):
    """DuckDB rejected the query or it ran too long."""


@dataclass
class Result:
    df: pd.DataFrame
    truncated: bool


def db_path() -> Path:
    return Path(os.environ.get("ASK_DB", DEFAULT_DB))


def connect(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open the database read-only, with file and network access off and settings locked."""
    path = Path(path or db_path())
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `python scripts/build_db.py` first.")
    con = duckdb.connect(str(path), read_only=True, config={"enable_external_access": False})
    con.execute("SET lock_configuration = true")
    return con


def run_query(sql: str, path: Path | None = None, timeout_s: float = TIMEOUT_S,
              max_rows: int = MAX_ROWS) -> Result:
    """Run one SELECT. Interrupts it after `timeout_s` and keeps at most `max_rows` rows."""
    con = connect(path)
    timer = threading.Timer(timeout_s, con.interrupt)
    timer.start()
    try:
        cur = con.execute(sql)
        rows = cur.fetchmany(max_rows + 1)
        columns = [d[0] for d in cur.description]
    except duckdb.InterruptException as e:
        raise QueryError(f"The query took longer than {timeout_s:.0f} seconds and was stopped.") from e
    except duckdb.Error as e:
        raise QueryError(str(e).splitlines()[0]) from e
    finally:
        timer.cancel()
        con.close()
    truncated = len(rows) > max_rows
    return Result(pd.DataFrame(rows[:max_rows], columns=columns), truncated)


def schema_context(path: Path | None = None) -> str:
    """The table and column listing the model sees, plus notes on what the tables mean."""
    con = connect(path)
    try:
        cols = con.execute("""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'main'
            ORDER BY table_name, ordinal_position
        """).fetchall()
    finally:
        con.close()
    tables: dict[str, list[str]] = {}
    for table, column, dtype in cols:
        if table in ALLOWED_TABLES:
            tables.setdefault(table, []).append(f"{column} {dtype}")
    lines = []
    for table in sorted(tables):
        lines.append(f"- {table}: {TABLE_NOTES.get(table, '')}")
        lines.append(f"    columns: {', '.join(tables[table])}")
    return "\n".join(lines) + "\n\n" + GENERAL_NOTES


TABLE_NOTES = {
    "sales": "one row per product line on an invoice (cancellations, postage and fees removed). "
             "revenue = quantity * price in GBP. invoice is the order id. customer_id is NULL for guest checkouts.",
    "returns": "cancelled lines (invoice starts with 'C'); quantity and revenue are positive.",
    "rfm": "one row per known customer: recency_days (days since last order at the end of the data), "
           "frequency (distinct orders), monetary (total spend, GBP), 1-5 scores and segment name.",
    "rfm_segments": "one row per RFM segment with customer counts, revenue and medians. Percentages are 0-100.",
    "monthly_kpis": "one row per calendar month. Percentages are 0-100. is_partial_month marks Dec 2011, "
                    "which stops on the 9th.",
    "cohort_retention": "customers grouped by first-purchase month; retention_pct (0-100) of the cohort "
                        "still buying N months later.",
    "customer_first_month": "each known customer's first purchase month.",
    "headline_kpis": "a single row of whole-period totals. Percentages are 0-100.",
    "repeat_purchase": "a single row: share of customers with a second order, and how soon.",
    "retention_curve": "average retention_pct by months since first purchase, across cohorts.",
    "revenue_concentration": "share of revenue (0-100) earned from the top N percent of customers.",
    "top_countries": "the 10 countries with the most revenue.",
    "top_products": "the 15 products with the most revenue.",
}

GENERAL_NOTES = """Notes:
- Data: a UK online gift retailer, 1 Dec 2009 to 9 Dec 2011. Currency is GBP.
- An order is a distinct invoice. Average order value = revenue / distinct invoices.
- One stock_code can have slightly different descriptions; group products by stock_code.
- The SQL dialect is DuckDB. Use date_trunc, year(), month(), dayname(), hour(), strftime.
- Prefer the precomputed summary tables when they answer the question directly."""
