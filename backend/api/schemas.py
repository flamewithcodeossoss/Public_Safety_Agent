"""
Pydantic schemas for API request/response models.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any


# ── Request Models ──────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="Natural language question")


# ── Response Models ─────────────────────────────────────────────────

class AskResponse(BaseModel):
    answer: str
    resolved_tag: str | None = None
    confidence: float = 0.0
    query_sql: str = ""
    query_description: str = ""
    raw_result: list[dict[str, Any]] = []


class TagInfo(BaseModel):
    tag_name: str
    label: str
    domain: str


class MetricValue(BaseModel):
    tag_name: str
    label: str
    domain: str
    value: float | None = None
    timestamp: str | None = None


class HealthResponse(BaseModel):
    status: str
    db_loaded: bool
    db_rows: int = 0
    db_tags: int = 0
    ollama_reachable: bool = False
    ollama_model: str = ""


class HistoryPoint(BaseModel):
    timestamp: str
    value: float | None = None


class HistoryResponse(BaseModel):
    tag_name: str
    label: str
    data: list[HistoryPoint]


# ── WebSocket Message Models ────────────────────────────────────────

class WSMessage(BaseModel):
    type: str  # "question", "node_update", "answer", "error"
    data: dict[str, Any] = {}
