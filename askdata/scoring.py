"""Execution accuracy: does the agent's result contain the gold answer?

A prediction passes when it has the same number of rows as the gold result and every gold
column lines up with a distinct predicted column, row by row, after sorting. Numbers match
within 0.5% (or 0.05 absolute, for rounded percentages); text ignores case and spaces; dates
compare by day. Extra predicted columns and different column names are fine.
"""
import datetime as dt
import math
import re
from decimal import Decimal
from itertools import permutations

import pandas as pd

REL_TOL, ABS_TOL = 0.005, 0.05


def _norm(v):
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT or v is pd.NA:
        return None
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float, Decimal)) or hasattr(v, "dtype"):
        try:
            return float(v)
        except (TypeError, ValueError):
            pass
    if isinstance(v, (pd.Timestamp, dt.datetime)):
        return v.date().isoformat() if (v.hour, v.minute, v.second) == (0, 0, 0) else v.isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    s = str(v).strip().lower()
    if re.fullmatch(r"\d{4}-\d{2}", s):  # a month written as 2011-11
        return s + "-01"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[ t]00:00:00", s):
        return s[:10]
    try:
        return float(s)
    except ValueError:
        return s


def _equal(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)
    return a == b


def _sort_key(v):
    # None first, then numbers, then strings; numbers rounded so near-equal values sort together.
    if v is None:
        return (0, 0, "")
    if isinstance(v, float):
        return (1, round(v, 1), "")
    return (2, 0, v)


def _column(df: pd.DataFrame, i: int) -> list:
    return [_norm(v) for v in df.iloc[:, i].tolist()]


def _same_values(a: list, b: list) -> bool:
    return all(_equal(x, y) for x, y in zip(sorted(a, key=_sort_key), sorted(b, key=_sort_key)))


def matches(gold: pd.DataFrame, pred: pd.DataFrame) -> bool:
    if len(gold) != len(pred) or pred.shape[1] < gold.shape[1]:
        return False
    gold_cols = [_column(gold, i) for i in range(gold.shape[1])]
    pred_cols = [_column(pred, j) for j in range(pred.shape[1])]
    # Candidate predicted columns for each gold column, by their values alone.
    candidates = [[j for j, p in enumerate(pred_cols) if _same_values(g, p)] for g in gold_cols]
    if any(not c for c in candidates):
        return False
    gold_rows = sorted(zip(*gold_cols), key=lambda r: tuple(map(_sort_key, r)))
    # Try each distinct assignment (tiny in practice) and check the rows line up too.
    for assignment in permutations(range(len(pred_cols)), len(gold_cols)):
        if not all(j in c for j, c in zip(assignment, candidates)):
            continue
        pred_rows = sorted(zip(*(pred_cols[j] for j in assignment)), key=lambda r: tuple(map(_sort_key, r)))
        if all(all(_equal(a, b) for a, b in zip(g, p)) for g, p in zip(gold_rows, pred_rows)):
            return True
    return False
