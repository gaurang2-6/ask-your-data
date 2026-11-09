"""Build data/retail.duckdb, the database the agent queries.

    python scripts/build_db.py                   download Online Retail II and run sql/01-04
    python scripts/build_db.py --from PATH       copy an existing retail.duckdb instead

The SQL in sql/ comes from the retail-customer-analytics project
(https://github.com/gaurang2-6/retail-customer-analytics), which explains each cleaning step.
"""
import argparse
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB = DATA / "retail.duckdb"
URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
# Working tables the SQL needs along the way but the agent never sees.
SCRATCH_TABLES = ["raw", "reversed_lines", "cleaning_log"]


def download() -> Path:
    parquet = DATA / "online_retail_ii.parquet"
    if parquet.exists():
        return parquet
    xlsx = DATA / "online_retail_II.xlsx"
    if not xlsx.exists():
        zip_path = DATA / "online_retail_ii.zip"
        print("Downloading Online Retail II (45 MB)...")
        urllib.request.urlretrieve(URL, zip_path)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(DATA)
    print("Reading both Excel sheets (takes ~2 minutes)...")
    sheets = pd.read_excel(xlsx, sheet_name=None, dtype={"Invoice": str, "StockCode": str, "Description": str})
    df = pd.concat(sheets.values(), ignore_index=True)
    df.columns = ["invoice", "stock_code", "description", "quantity", "invoice_date",
                  "price", "customer_id", "country"]
    df["customer_id"] = df["customer_id"].astype("Int64")
    df.to_parquet(parquet, index=False)
    return parquet


def build():
    download()
    DB.unlink(missing_ok=True)
    os.chdir(ROOT)  # the SQL reads data/online_retail_ii.parquet relative to the repo root
    with duckdb.connect(str(DB)) as con:
        for path in sorted((ROOT / "sql").glob("*.sql")):
            print(f"Running {path.name}")
            con.execute(path.read_text(encoding="utf-8"))
        for table in SCRATCH_TABLES:
            con.execute(f"DROP TABLE IF EXISTS {table}")
        con.execute("DROP MACRO IF EXISTS is_product")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="source", type=Path, help="copy this retail.duckdb instead of building")
    args = parser.parse_args()
    DATA.mkdir(exist_ok=True)
    if args.source:
        DB.unlink(missing_ok=True)
        shutil.copy(args.source, DB)
        with duckdb.connect(str(DB)) as con:
            for table in SCRATCH_TABLES:
                con.execute(f"DROP TABLE IF EXISTS {table}")
            con.execute("CHECKPOINT")
    else:
        build()
    with duckdb.connect(str(DB), read_only=True) as con:
        n = con.execute("SELECT count(*) FROM sales").fetchall()[0][0]
    print(f"Wrote {DB} ({n:,} sales lines)")


if __name__ == "__main__":
    main()
