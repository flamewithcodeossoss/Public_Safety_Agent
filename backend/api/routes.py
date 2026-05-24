"""
API Routes — REST endpoints + WebSocket for the Smart City Agent.
"""

from __future__ import annotations
import json
import os
import traceback
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
import httpx

from api.schemas import (
    AskRequest, AskResponse,
    TagInfo, MetricValue, HealthResponse,
    HistoryResponse, HistoryPoint,
)
from config.tag_registry import TAG_LABELS, TAG_DOMAIN, ALL_TAG_NAMES
from agent.data_loader import get_connection
from agent.graph import ask, ask_streaming

router = APIRouter()


# ════════════════════════════════════════════════════════════════════
# POST /api/ask — Synchronous question → answer
# ════════════════════════════════════════════════════════════════════

@router.post("/api/ask", response_model=AskResponse)
async def ask_question(req: AskRequest):
    """Process a natural language question through the agent pipeline."""
    try:
        # Run the full pipeline (synchronous — blocks until done)
        from agent.graph import get_graph

        app = get_graph()
        initial_state = {
            "user_question":      req.question,
            "extracted_intent":   {},
            "resolved_tag":       None,
            "resolver_confidence": 0.0,
            "resolver_error":     None,
            "query_sql":          "",
            "query_params":       [],
            "query_description":  "",
            "raw_result":         [],
            "executor_error":     None,
            "final_answer":       "",
        }

        result = app.invoke(initial_state)

        # Serialize raw_result for JSON response
        raw = result.get("raw_result", [])
        serialized_raw = json.loads(json.dumps(raw, default=str))

        return AskResponse(
            answer=result["final_answer"],
            resolved_tag=result.get("resolved_tag"),
            confidence=result.get("resolver_confidence", 0.0),
            query_sql=result.get("query_sql", ""),
            query_description=result.get("query_description", ""),
            raw_result=serialized_raw,
        )

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════════════
# WebSocket /api/ws/chat — Streaming chat with intermediate steps
# ════════════════════════════════════════════════════════════════════

@router.websocket("/api/ws/chat")
async def websocket_chat(ws: WebSocket):
    """WebSocket endpoint for streaming agent responses with intermediate node states."""
    await ws.accept()

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            question = msg.get("question", "").strip()

            if not question:
                await ws.send_json({"type": "error", "data": {"message": "Empty question"}})
                continue

            try:
                # Stream intermediate node updates
                async for update in ask_streaming(question):
                    await ws.send_json({
                        "type": "node_update",
                        "data": {
                            "node": update["node"],
                            "label": update["label"],
                            "details": _safe_serialize(update["data"]),
                        }
                    })

                    # If this is the final node, also send the answer
                    if update["node"] == "answer_formatter":
                        answer = update["data"].get("final_answer", "")
                        await ws.send_json({
                            "type": "answer",
                            "data": {"answer": answer}
                        })

            except Exception as e:
                traceback.print_exc()
                await ws.send_json({
                    "type": "error",
                    "data": {"message": str(e)}
                })

    except WebSocketDisconnect:
        pass


# ════════════════════════════════════════════════════════════════════
# GET /api/tags — List all available tags
# ════════════════════════════════════════════════════════════════════

@router.get("/api/tags", response_model=list[TagInfo])
async def list_tags():
    """Return all available tags with their labels and domains."""
    return [
        TagInfo(
            tag_name=tag,
            label=TAG_LABELS[tag],
            domain=TAG_DOMAIN[tag],
        )
        for tag in ALL_TAG_NAMES
    ]


# ════════════════════════════════════════════════════════════════════
# GET /api/metrics/latest — Latest values for all tags (dashboard cards)
# ════════════════════════════════════════════════════════════════════

@router.get("/api/metrics/latest", response_model=list[MetricValue])
async def latest_metrics():
    """Get the most recent value for each of the 8 tags."""
    conn = get_connection()
    sql = """
        SELECT TagName, Value, DateTime
        FROM hist
        WHERE Value IS NOT NULL
        QUALIFY ROW_NUMBER() OVER (PARTITION BY TagName ORDER BY DateTime DESC) = 1
        ORDER BY TagName
    """
    rows = conn.execute(sql).fetchall()

    metrics = []
    for tag_name, value, dt in rows:
        metrics.append(MetricValue(
            tag_name=tag_name,
            label=TAG_LABELS.get(tag_name, tag_name),
            domain=TAG_DOMAIN.get(tag_name, "unknown"),
            value=float(value) if value is not None else None,
            timestamp=str(dt) if dt else None,
        ))

    return metrics


# ════════════════════════════════════════════════════════════════════
# GET /api/metrics/{tag_name}/history — Time-series data for charts
# ════════════════════════════════════════════════════════════════════

@router.get("/api/metrics/{tag_name:path}/history", response_model=HistoryResponse)
async def tag_history(tag_name: str, limit: int = 100):
    """Get historical data points for a specific tag."""
    if tag_name not in TAG_LABELS:
        raise HTTPException(status_code=404, detail=f"Unknown tag: {tag_name}")

    conn = get_connection()
    sql = """
        SELECT DateTime, Value
        FROM hist
        WHERE TagName = ? AND Value IS NOT NULL
        ORDER BY DateTime DESC
        LIMIT ?
    """
    rows = conn.execute(sql, [tag_name, limit]).fetchall()

    # Reverse to chronological order
    data = [
        HistoryPoint(timestamp=str(dt), value=float(val) if val is not None else None)
        for dt, val in reversed(rows)
    ]

    return HistoryResponse(
        tag_name=tag_name,
        label=TAG_LABELS[tag_name],
        data=data,
    )


# ════════════════════════════════════════════════════════════════════
# GET /api/health — Health check
# ════════════════════════════════════════════════════════════════════

@router.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Check if DuckDB is loaded and Ollama is reachable."""
    # Check DuckDB
    db_ok = False
    db_rows = 0
    db_tags = 0
    try:
        conn = get_connection()
        db_rows = conn.execute("SELECT COUNT(*) FROM hist").fetchone()[0]
        db_tags = conn.execute("SELECT COUNT(DISTINCT TagName) FROM hist").fetchone()[0]
        db_ok = True
    except Exception:
        pass

    # Check Ollama
    ollama_ok = False
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://192.168.1.145:11434")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{ollama_url}/api/tags")
            ollama_ok = resp.status_code == 200
    except Exception:
        pass

    status = "healthy" if (db_ok and ollama_ok) else "degraded" if db_ok else "unhealthy"

    return HealthResponse(
        status=status,
        db_loaded=db_ok,
        db_rows=db_rows,
        db_tags=db_tags,
        ollama_reachable=ollama_ok,
        ollama_model=ollama_model,
    )


# ════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════

def _safe_serialize(obj: Any) -> Any:
    """Make objects JSON-safe."""
    try:
        json.dumps(obj, default=str)
        return json.loads(json.dumps(obj, default=str))
    except (TypeError, ValueError):
        return str(obj)
