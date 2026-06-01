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
from datetime import date, timedelta
import calendar


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

    elif tf_type == "last_month":
        # Resolve to the previous calendar month's full date range.
        today = date.today()
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        where_clauses.append(
            "CAST(DateTime AS DATE) >= CAST(? AS DATE) "
            "AND CAST(DateTime AS DATE) <= CAST(? AS DATE)"
        )
        params += [last_month_start.isoformat(), last_month_end.isoformat()]

    elif tf_type == "date_range":
        # Cast to DATE so a single-day query (start=end=2026-05-08)
        # captures all timestamps throughout that day (00:00 to 23:59).
        where_clauses.append(
            "CAST(DateTime AS DATE) >= CAST(? AS DATE) "
            "AND CAST(DateTime AS DATE) <= CAST(? AS DATE)"
        )
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
        # When a date_range filter is present, return ALL readings for that day/range.
        # Without a date_range, fall back to the last 50 readings.
        if tf_type == "date_range":
            sql = f"""
                SELECT TagName, DateTime, Value
                FROM hist
                WHERE {where_sql}
                ORDER BY DateTime ASC
            """.strip()
            desc = f"All readings for {tag} in selected date range"
        else:
            sql = f"""
                SELECT TagName, DateTime, Value
                FROM hist
                WHERE {where_sql}
                ORDER BY DateTime DESC
                LIMIT 50
            """.strip()
            desc = f"Recent trend (last 50 readings) for {tag}"

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
            SELECT TagName, DateTime, Value, l, StartDateTime
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


def build_domain_summary_query(tag_names: list[str], tf: dict) -> QueryResult:
    """
    Build a domain-level summary query: avg, min, max, count per tag,
    with an optional time filter (last_month, date_range, last_n, all).

    Used when the user says 'summarize CCTV status for last month' —
    queries ALL tags in the domain at once and returns statistics per tag.
    """
    from datetime import date, timedelta

    # Build time filter WHERE conditions
    time_where = "Value IS NOT NULL"
    time_params: list = []

    tf_type = tf.get("type", "all")

    if tf_type == "last_month":
        today = date.today()
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        time_where += (
            " AND CAST(DateTime AS DATE) >= CAST(? AS DATE)"
            " AND CAST(DateTime AS DATE) <= CAST(? AS DATE)"
        )
        time_params += [last_month_start.isoformat(), last_month_end.isoformat()]
        period_desc = f"{last_month_start.strftime('%B %Y')}"

    elif tf_type == "date_range":
        time_where += (
            " AND CAST(DateTime AS DATE) >= CAST(? AS DATE)"
            " AND CAST(DateTime AS DATE) <= CAST(? AS DATE)"
        )
        time_params += [tf["start"], tf["end"]]
        period_desc = f"{tf['start']} to {tf['end']}"

    elif tf_type == "last_n":
        n = int(tf.get("n", 24))
        time_where += (
            f" AND DateTime >= (SELECT MAX(DateTime) FROM hist) - INTERVAL '{n} hours'"
        )
        period_desc = f"last {n} hours"

    else:
        period_desc = "all time"

    placeholders = ", ".join(["?" for _ in tag_names])

    sql = f"""
        SELECT
            TagName,
            ROUND(AVG(Value), 2)   AS avg_value,
            MIN(Value)             AS min_value,
            MAX(Value)             AS max_value,
            COUNT(*)               AS sample_count,
            MIN(DateTime)          AS period_start,
            MAX(DateTime)          AS period_end
        FROM hist
        WHERE TagName IN ({placeholders})
          AND {time_where}
        GROUP BY TagName
        ORDER BY TagName
    """.strip()

    params = tag_names + time_params

    return QueryResult(
        sql=sql,
        params=params,
        description=f"Domain summary (avg/min/max) for {period_desc}: {', '.join(tag_names)}"
    )
