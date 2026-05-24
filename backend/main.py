"""
Smart City Public Safety Agent — FastAPI Entry Point
=====================================================
Serves the LangGraph agent pipeline over REST + WebSocket.

Run locally:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Docker:
    See Dockerfile / docker-compose.yml
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.data_loader import get_connection
from api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load DuckDB on startup so first request is instant."""
    print("[startup] Loading CSV data into DuckDB...")
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM hist").fetchone()[0]
    print(f"[startup] DuckDB ready — {total:,} rows loaded.")
    yield
    print("[shutdown] Cleaning up...")


app = FastAPI(
    title="Marassi Smart City — Public Safety Agent",
    description=(
        "Natural-language interface over AVEVA Historian data. "
        "Ask questions about access control, CCTV cameras, and gate APIs."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS — allow frontend to connect ──────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",       # Vite dev server
        "http://localhost:3000",       # fallback
        "http://frontend:5173",        # Docker service name
        "*",                           # Allow all for development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount API routes ──────────────────────────────────────────────
app.include_router(router)


# ── Root redirect to docs ─────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "service": "Marassi Smart City — Public Safety Agent",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "ask": "POST /api/ask",
            "chat_ws": "WS /api/ws/chat",
            "tags": "GET /api/tags",
            "latest_metrics": "GET /api/metrics/latest",
            "tag_history": "GET /api/metrics/{tag_name}/history",
            "health": "GET /api/health",
        }
    }
