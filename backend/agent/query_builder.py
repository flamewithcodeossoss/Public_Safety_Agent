"""
Query Builder — Node 3 in the LangGraph pipeline.

Takes a structured intent dict (from LLM extraction) + resolved TagName
and builds a safe, parameterised DuckDB SQL query.

No LLM involved here — pure deterministic Python.
This is the key to reliability with a local model.

Intent structure (produced by Node 1):
{
    "intent":    "latest" | "average" | "sum" | "min" | "max" | "trend" | "count_records",
    "tag_name":  "MRS_Access_Control.Beaches_Vip",   # resolved by Node 2
    "time_filter": {
        "type":  "latest" | "last_n" | "date_range" | "all",
        "n":     24,          # used when type == "last_n" (hours)
        "start": "2026-02-01",  # used when type == "date_range"
        "end":   "2026-05-20",
    }
}
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class QueryResult:
    sql: str
    params: list
    description: str   # human-readable description of what this query does


def build_query(intent: dict) -> QueryResult:
    """
    Build a DuckDB SQL query from a structured intent dict.
    Returns QueryResult with .sql, .params, and .description.
    """
    tag      = intent["tag_name"]
    agg      = intent.get("intent", "latest")
    tf       = intent.get("time_filter", {"type": "latest"})
    tf_type  = tf.get("type", "latest")

    # ── Base WHERE clause ──────────────────────────────────────
    where_clauses = ["TagName = ?", "Value IS NOT NULL"]
    params: list = [tag]

    if tf_type == "last_n":
        n_hours = int(tf.get("n", 24))
        where_clauses.append(
            f"DateTime >= (SELECT MAX(DateTime) FROM hist WHERE TagName = ?) - INTERVAL '{n_hours} hours'"
        )
        params.append(tag)

    elif tf_type == "date_range":
        where_clauses.append("DateTime >= ? AND DateTime <= ?")
        params += [tf["start"], tf["end"]]

    # For "latest" tf_type, no extra filter — we ORDER + LIMIT below

    where_sql = " AND ".join(where_clauses)

    # ── Aggregation ─────────────────────────────────────────────
    if agg == "latest":
        sql = f"""
            SELECT TagName, DateTime, Value, vValue, StartDateTime
            FROM hist
            WHERE {where_sql}
            ORDER BY DateTime DESC
            LIMIT 1
        """.strip()
        desc = f"Most recent value for {tag}"

    elif agg == "average":
        sql = f"""
            SELECT TagName,
                   ROUND(AVG(Value), 2) AS avg_value,
                   COUNT(*) AS sample_count,
                   MIN(DateTime) AS period_start,
                   MAX(DateTime) AS period_end
            FROM hist
            WHERE {where_sql}
            GROUP BY TagName
        """.strip()
        desc = f"Average value for {tag} over selected period"

    elif agg == "sum":
        sql = f"""
            SELECT TagName,
                   SUM(Value) AS total_value,
                   COUNT(*) AS sample_count,
                   MIN(DateTime) AS period_start,
                   MAX(DateTime) AS period_end
            FROM hist
            WHERE {where_sql}
            GROUP BY TagName
        """.strip()
        desc = f"Sum of values for {tag}"

    elif agg == "min":
        sql = f"""
            SELECT TagName, MIN(Value) AS min_value,
                   MIN_BY(DateTime, Value) AS occurred_at
            FROM hist
            WHERE {where_sql}
            GROUP BY TagName
        """.strip()
        desc = f"Minimum value for {tag}"

    elif agg == "max":
        sql = f"""
            SELECT TagName, MAX(Value) AS max_value,
                   MAX_BY(DateTime, Value) AS occurred_at
            FROM hist
            WHERE {where_sql}
            GROUP BY TagName
        """.strip()
        desc = f"Maximum value for {tag}"

    elif agg == "trend":
        sql = f"""
            SELECT TagName, DateTime, Value
            FROM hist
            WHERE {where_sql}
            ORDER BY DateTime DESC
            LIMIT 20
        """.strip()
        desc = f"Recent trend (last 20 readings) for {tag}"

    elif agg == "count_records":
        sql = f"""
            SELECT TagName,
                   COUNT(*) AS record_count,
                   MIN(DateTime) AS first_seen,
                   MAX(DateTime) AS last_seen
            FROM hist
            WHERE {where_sql}
            GROUP BY TagName
        """.strip()
        desc = f"Record count for {tag}"

    else:
        # Default to latest
        sql = f"""
            SELECT TagName, DateTime, Value, vValue, StartDateTime
            FROM hist
            WHERE {where_sql}
            ORDER BY DateTime DESC
            LIMIT 1
        """.strip()
        desc = f"Most recent value for {tag} (default)"

    return QueryResult(sql=sql, params=params, description=desc)


def build_comparison_query(tag_names: list[str]) -> QueryResult:
    """
    Compare latest values across multiple tags (e.g. enabled vs disabled cameras).
    """
    placeholders = ", ".join(["?" for _ in tag_names])
    sql = f"""
        SELECT TagName, Value, DateTime
        FROM hist
        WHERE TagName IN ({placeholders})
          AND Value IS NOT NULL
        QUALIFY ROW_NUMBER() OVER (PARTITION BY TagName ORDER BY DateTime DESC) = 1
        ORDER BY TagName
    """.strip()
    return QueryResult(
        sql=sql,
        params=tag_names,
        description=f"Latest values for {len(tag_names)} tags: {', '.join(tag_names)}"
    )
