import time

import pytest

from askdata import db


def test_runs_a_select(tiny_db):
    r = db.run_query("SELECT country, sum(revenue) AS revenue FROM sales GROUP BY 1 ORDER BY 2 DESC", tiny_db)
    assert list(r.df.columns) == ["country", "revenue"]
    assert r.df.iloc[0].country == "United Kingdom"
    assert not r.truncated


def test_caps_rows(tiny_db):
    r = db.run_query("SELECT * FROM range(50)", tiny_db, max_rows=10)
    assert len(r.df) == 10 and r.truncated


@pytest.mark.parametrize("sql", [
    "DROP TABLE sales",
    "INSERT INTO sales SELECT * FROM sales",
    "CREATE TABLE x AS SELECT 1",
])
def test_connection_is_read_only(tiny_db, sql):
    with pytest.raises(db.QueryError):
        db.run_query(sql, tiny_db)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM read_csv('anything.csv')",
    "COPY sales TO 'leak.csv'",
    "SET enable_external_access = true",
])
def test_no_file_access_even_without_the_guard(tiny_db, sql):
    with pytest.raises(db.QueryError):
        db.run_query(sql, tiny_db)


def test_slow_query_is_stopped(tiny_db):
    start = time.perf_counter()
    with pytest.raises(db.QueryError, match="longer than"):
        db.run_query("SELECT count(*) FROM range(100000000) a, range(100000000) b", tiny_db, timeout_s=1)
    assert time.perf_counter() - start < 5


def test_schema_context_lists_only_allowed_tables(tiny_db):
    ctx = db.schema_context(tiny_db)
    assert "sales" in ctx and "monthly_kpis" in ctx
    assert "secrets" not in ctx and "hunter2" not in ctx
