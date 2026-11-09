"""Static checks on model-written SQL before it reaches the database.

The executor is already read-only with external access switched off, so this is the
first of two locks: it rejects anything that is not a single SELECT over the tables
the agent is allowed to see, and says why, so the model can fix its query.
"""
import re

import sqlglot
from sqlglot import exp

ALLOWED_TABLES = frozenset({
    "sales", "returns", "rfm", "rfm_segments", "monthly_kpis", "cohort_retention",
    "customer_first_month", "headline_kpis", "repeat_purchase", "retention_curve",
    "revenue_concentration", "top_countries", "top_products",
})

# Scalar functions that read files, the environment or settings.
BANNED_FUNCTIONS = re.compile(
    r"^(read_\w+|glob|getenv|current_setting|parquet_\w+|sniff_csv|query|query_table|duckdb_\w+|"
    r"pragma_\w+|load|install)$",
    re.IGNORECASE,
)


class GuardError(ValueError):
    """The SQL is not allowed to run."""


def check(sql: str) -> str:
    """Return the cleaned SQL if it is a single read-only SELECT, else raise GuardError."""
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise GuardError("The query is empty.")
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise GuardError(f"The query does not parse: {str(e).splitlines()[0]}") from e
    if len(statements) != 1:
        raise GuardError("Send exactly one statement.")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.SetOperation)):
        raise GuardError(f"Only SELECT queries are allowed, not {tree.key.upper()}.")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise GuardError("Table functions (read_csv, duckdb_settings() and the like) are not allowed.")
        if table.catalog or table.db.lower() not in ("", "main"):
            raise GuardError(f"Only tables in the main schema are allowed, not {table.sql('duckdb')}.")
        name = table.name.lower()
        if name not in ALLOWED_TABLES and name not in cte_names:
            raise GuardError(f"Unknown table '{table.name}'. Allowed tables: {', '.join(sorted(ALLOWED_TABLES))}.")

    for func in tree.find_all(exp.Func):
        name = func.name if isinstance(func, exp.Anonymous) else func.sql_name()
        if BANNED_FUNCTIONS.match(name or ""):
            raise GuardError(f"The function {name} is not allowed.")
    return sql
