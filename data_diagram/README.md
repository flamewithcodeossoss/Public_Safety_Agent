# Smart City LangGraph Agent

Natural-language interface over AVEVA Historian CSV exports.

## Setup

```bash
pip install -r requirements.txt

# If using Ollama (recommended for local Qwen 3.5)
ollama pull RogerBen/qwen3.5-35b-opus-distill:latest
```

## Data

Copy your 8 CSV files into the `data/` folder:
```
data/
  MRS_Access_Control_AccessChannels_QR.csv
  MRS_Access_Control_Beaches_Vip.csv
  MRS_Access_Control_MainGate_Vip.csv
  MRS_CCTV_cameras_total_number.csv
  MRS_CCTV_Total_disabled_cameras.csv
  MRS_CCTV_Total_enabled_cameras.csv
  MRS_Gate_APIs_Gates_Fail.csv
  MRS_Gate_APIs_Gates_Success.csv
```

Or set `DATA_DIR` environment variable to point to your folder.

## Usage

### Python API
```python
from agent.graph import ask

answer = ask("What is the current count at the Beaches VIP access point?")
print(answer)

answer = ask("How many CCTV cameras are disabled right now?")
print(answer)

answer = ask("What is the average gate failure rate over the last 24 hours?")
print(answer)
```

### Test data layer only (no LLM needed)
```bash
cd smart_city_agent
python -m agent.graph --no-llm --data-dir /path/to/csv/files
```

## Architecture

```
User question
     ↓
Node 1 — NL Understanding   [Qwen 2.5]   extract intent + location + time
     ↓
Node 2 — Tag Resolver       [Python]     fuzzy match → exact TagName
     ↓
Node 3 — Query Builder      [Python]     build DuckDB SQL deterministically
     ↓
Node 4 — Executor           [Python]     run query on in-memory DuckDB
     ↓
Node 5 — Answer Formatter   [Qwen 2.5]   format result as natural language
```

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DATA_DIR` | `./data` | Path to CSV files |
| `OLLAMA_MODEL` | `RogerBen/qwen3.5-35b-opus-distill:latest` | Ollama model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `VLLM_BASE_URL` | `http://localhost:8000/v1` | vLLM endpoint (if using vLLM) |
| `VLLM_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | Model name for vLLM |

## Supported query intents

| Intent | Example question |
|---|---|
| `latest` | "What is the current count at Beaches VIP?" |
| `average` | "What is the average gate failure count?" |
| `max` | "What was the peak traffic at Main Gate?" |
| `min` | "What is the lowest CCTV enabled count?" |
| `trend` | "Show me the recent trend for disabled cameras" |
| `count_records` | "How many readings do we have for QR channels?" |

## Adding new tags (when real-time API is ready)

1. Add the TagName + aliases to `config/tag_registry.py`
2. The rest of the agent requires zero changes
