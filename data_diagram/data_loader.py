"""
Data loader — reads all 8 CSV files into a single DuckDB in-memory table.

Key decisions:
  - All files share the same 5-column schema → union into one table `historian`
  - "(null)" string values → coerced to NULL
  - DateTime / StartDateTime parsed to TIMESTAMP
  - Value / vValue cast to INTEGER (NULL-safe)
"""

import os
import duckdb
import pandas as pd
from pathlib import Path

# ── Default data directory (override via env DATA_DIR) ──────────────
_DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR = Path(os.getenv("DATA_DIR", _DEFAULT_DATA_DIR))

# Map TagName → CSV filename  (auto-discovered if files are in DATA_DIR)
CSV_FILES = [
    "MRS_Access_Control_AccessChannels_QR.csv",
    "MRS_Access_Control_Beaches_Vip.csv",
    "MRS_Access_Control_MainGate_Vip.csv",
    "MRS_CCTV_cameras_total_number.csv",
    "MRS_CCTV_Total_disabled_cameras.csv",
    "MRS_CCTV_Total_enabled_cameras.csv",
    "MRS_Gate_APIs_Gates_Fail.csv",
    "MRS_Gate_APIs_Gates_Success.csv",
]


def _load_csv(path: Path) -> pd.DataFrame:
    """Load a single historian CSV and clean it."""
    df = pd.read_csv(path)
    # Coerce "(null)" strings → actual NaN/None
    df["Value"]   = pd.to_numeric(df["Value"].replace("(null)", None),   errors="coerce")
    df["vValue"]  = pd.to_numeric(df["vValue"].replace("(null)", None),  errors="coerce")
    # Parse timestamps
    df["DateTime"]      = pd.to_datetime(df["DateTime"],      format="mixed", errors="coerce")
    df["StartDateTime"] = pd.to_datetime(df["StartDateTime"], format="mixed", errors="coerce")
    return df


def build_connection(data_dir: Path = DATA_DIR) -> duckdb.DuckDBPyConnection:
    """
    Load all CSVs, union them, register as DuckDB table `historian`.
    Returns an in-memory DuckDB connection ready to query.
    """
    frames = []
    for fname in CSV_FILES:
        fpath = data_dir / fname
        if not fpath.exists():
            print(f"[loader] WARNING: {fpath} not found, skipping.")
            continue
        df = _load_csv(fpath)
        frames.append(df)

    if not frames:
        raise FileNotFoundError(f"No CSV files found in {data_dir}")

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("DateTime")

    conn = duckdb.connect(database=":memory:")
    conn.register("historian", combined)

    # Materialise as a proper table for performance
    conn.execute("""
        CREATE TABLE hist AS SELECT * FROM historian
    """)
    conn.execute("CREATE INDEX idx_tag ON hist(TagName)")
    conn.execute("CREATE INDEX idx_dt  ON hist(DateTime)")

    total = conn.execute("SELECT COUNT(*) FROM hist").fetchone()[0]
    tags  = conn.execute("SELECT COUNT(DISTINCT TagName) FROM hist").fetchone()[0]
    print(f"[loader] Loaded {total:,} rows, {tags} distinct tags into DuckDB.")
    return conn


# Singleton connection (module-level cache)
_conn: duckdb.DuckDBPyConnection | None = None


def get_connection(data_dir: Path = DATA_DIR) -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        _conn = build_connection(data_dir)
    return _conn
