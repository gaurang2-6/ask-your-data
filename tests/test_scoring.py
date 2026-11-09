import datetime as dt

import pandas as pd

from askdata.scoring import matches


def df(**cols):
    return pd.DataFrame(cols)


def test_identical():
    g = df(country=["France", "Germany"], revenue=[10.0, 20.0])
    assert matches(g, g.copy())


def test_ignores_column_names_order_and_row_order():
    g = df(country=["France", "Germany"], revenue=[10.0, 20.0])
    p = df(total=[20.0, 10.0], name=["germany", "France "])
    assert matches(g, p)


def test_extra_columns_are_fine():
    g = df(revenue=[10.0])
    assert matches(g, df(country=["France"], revenue=[10.0], orders=[3]))


def test_rounding_within_tolerance():
    assert matches(df(pct=[31.234]), df(pct=[31.2]))
    assert matches(df(revenue=[19294869.0]), df(revenue=[19300000.0]))
    assert not matches(df(revenue=[100.0]), df(revenue=[102.0]))


def test_wrong_row_count_fails():
    assert not matches(df(x=[1, 2]), df(x=[1]))


def test_values_must_line_up_row_by_row():
    g = df(country=["France", "Germany"], revenue=[10.0, 20.0])
    p = df(country=["France", "Germany"], revenue=[20.0, 10.0])
    assert not matches(g, p)


def test_dates_compare_by_day_and_month_strings_match():
    g = df(month=[dt.date(2011, 11, 1)], revenue=[5.0])
    assert matches(g, df(month=[pd.Timestamp("2011-11-01")], revenue=[5.0]))
    assert matches(g, df(month=["2011-11"], revenue=[5.0]))


def test_numbers_as_text():
    assert matches(df(year=[2011]), df(year=["2011"]))


def test_nulls():
    assert matches(df(c=[None, 1.0]), df(c=[float("nan"), 1.0]))
