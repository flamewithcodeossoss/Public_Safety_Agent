# Marassi Smart City — Public Safety Agent

AI-powered natural-language interface over AVEVA Historian data for smart city public safety monitoring.

## Architecture

```
┌──────────────┐    ┌──────────────────┐    ┌───────────────┐
│   Frontend   │    │     Backend      │    │    Ollama      │
│  React+Vite  │───▶│  FastAPI+DuckDB  │───▶│  Qwen 2.5:14b │
│  Port 5173   │    │  LangGraph Agent │    │  Port 11434   │
└──────────────┘    └──────────────────┘    └───────────────┘
```

### Agent Pipeline (5 Nodes, Only 2 LLM Calls)

1. **NL Understanding** (Qwen 2.5) — Extract intent, location, time filter
2. **Tag Resolver** (Python) — Fuzzy match → exact AVEVA TagName
3. **Query Builder** (Python) — Build DuckDB SQL deterministically
4. **Executor** (Python) — Run query on in-memory DuckDB
5. **Answer Formatter** (Qwen 2.5) — Format result as natural language

## Quick Start

```bash
# 1. Clone and enter project
cd Public_Safety_Agent

# 2. Start all services (GPU-accelerated)
docker compose up --build

# 3. First run will pull Qwen 2.5:14b model (~9GB)
# Wait for "Model pull complete!" in logs

# 4. Open dashboard
open http://localhost:5173
```

## Data

8 CSV files from AVEVA Historian (~41,000 rows, Feb–May 2026):

| Domain | Tags | Description |
|--------|------|-------------|
| Access Control | AccessChannels_QR, Beaches_Vip, MainGate_Vip | Visitor counts at access points |
| CCTV | cameras_total_number, Total_disabled_cameras, Total_enabled_cameras | Camera fleet status |
| Gate APIs | Gates.Fail, Gates.Success | Gate API transaction counts |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/ask` | Ask a natural language question |
| `WS` | `/api/ws/chat` | WebSocket streaming chat |
| `GET` | `/api/tags` | List all available tags |
| `GET` | `/api/metrics/latest` | Latest values for all tags |
| `GET` | `/api/metrics/{tag}/history` | Time-series data for a tag |
| `GET` | `/api/health` | System health check |

## Example Questions

- "What is the current count at the Beaches VIP access point?"
- "How many CCTV cameras are disabled right now?"
- "Show me the gate failure trend"
- "What was the peak traffic at Main Gate?"
- "Average gate failures over the last 24 hours?"

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_MODEL` | `qwen2.5:14b` | Ollama model name |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama server URL |
| `DATA_DIR` | `/app/data` | Path to CSV files |

## Development

```bash
# Backend only (no Docker)
cd backend
pip install -r requirements.txt
DATA_DIR=../data OLLAMA_BASE_URL=http://localhost:11434 uvicorn main:app --reload

# Frontend only
cd frontend
npm install
npm run dev

# Test data layer (no LLM needed)
cd backend
python -m agent.graph --no-llm --data-dir ../data
```
