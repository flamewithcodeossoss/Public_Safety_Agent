"""
Data loader — reads all 8 CSV files into a single DuckDB in-memory table.

Key decisions:
  - All files share the same 5-column schema → union into one table `historian`
  - "(null)" string values → coerced to NULL
  - DateTime / StartDateTime parsed to TIMESTAMP
  - Value / vValue cast to INTEGER (NULL-safe)
  - Thread-safe: uses connection per-request pattern for FastAPI
"""

import os
import threading
import duckdb
import pandas as pd
from pathlib import Path

# ── Default data directory (override via env DATA_DIR) ──────────────
_DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR = Path(os.getenv("DATA_DIR", _DEFAULT_DATA_DIR))

# CSV filenames — using dots, matching actual TagName values in data
CSV_FILES = [
    "MRS_Access_Control.AccessChannels_QR.csv",
    "MRS_Access_Control.Beaches_Vip.csv",
    "MRS_Access_Control.MainGate_Vip.csv",
    "MRS_CCTV.cameras_total_number.csv",
    "MRS_CCTV.Total_disabled_cameras.csv",
    "MRS_CCTV.Total_enabled_cameras.csv",
    "MRS_Gate_APIs.Gates.Fail.csv",
    "MRS_Gate_APIs.Gates.Success.csv",
]


def _load_csv(path: Path) -> pd.DataFrame:
    """Load a single historian CSV and clean it."""
    df = pd.read_csv(path)
    # Coerce "(null)" strings → actual NaN/None
    df["Value"]   = pd.to_numeric(df["Value"].replace("(null)", None),   errors="coerce")
    df["vValue"]  = pd.to_numeric(df["vValue"].replace("(null)", None),  errors="coerce")
    # Parse timestamps (US format: M/d/yyyy h:mm:ss tt)
    df["DateTime"]      = pd.to_datetime(df["DateTime"],      format="mixed", errors="coerce")
    df["StartDateTime"] = pd.to_datetime(df["StartDateTime"], format="mixed", errors="coerce")
    return df


def build_connection(data_dir: Path = DATA_DIR) -> duckdb.DuckDBPyConnection:
    """
    Load all CSVs, union them, register as DuckDB table `hist`.
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


# ── Thread-safe singleton ──────────────────────────────────────────
_conn: duckdb.DuckDBPyConnection | None = None
_lock = threading.Lock()


def get_connection(data_dir: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Get or create the singleton DuckDB connection (thread-safe)."""
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:  # double-checked locking
                _conn = build_connection(data_dir or DATA_DIR)
    return _conn


def reset_connection():
    """Reset the singleton (useful for testing)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None
