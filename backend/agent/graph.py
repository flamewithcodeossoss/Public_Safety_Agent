"""
Smart City LangGraph Agent
==========================
5-node graph:

  [user_question]
       ↓
  Node 1: nl_understanding   ← Qwen 2.5  (extract intent + entities)
       ↓
  Node 2: tag_resolver       ← Deterministic (fuzzy match → TagName)
       ↓
  Node 3: query_builder      ← Deterministic (build DuckDB SQL)
       ↓
  Node 4: executor           ← Deterministic (run query → raw result)
       ↓
  Node 5: answer_formatter   ← Qwen 2.5  (format result → natural language)

The LLM is only used in Node 1 (extraction) and Node 5 (formatting).
All data logic is deterministic Python — safe with local models.
"""

from __future__ import annotations
import json
import os
from typing import TypedDict, AsyncIterator
from pathlib import Path

from langgraph.graph import StateGraph, END

# ── Internal modules ────────────────────────────────────────────────
from agent.tag_resolver   import resolve_tag, resolve_domain_tags, tag_label
from agent.query_builder  import build_query, build_comparison_query
from agent.data_loader    import get_connection
from config.tag_registry  import TAG_LABELS


# ════════════════════════════════════════════════════════════════════
# STATE
# ════════════════════════════════════════════════════════════════════

class AgentState(TypedDict):
    # Input
    user_question: str

    # Node 1 output
    extracted_intent: dict          # {"intent": "...", "location": "...", "time_filter": {...}}

    # Node 2 output
    resolved_tag: str | None        # exact TagName or None
    resolver_confidence: float
    resolver_error: str | None

    # Node 3 output
    query_sql: str
    query_params: list
    query_description: str

    # Node 4 output
    raw_result: list[dict]          # list of row dicts from DuckDB
    executor_error: str | None

    # Node 5 output
    final_answer: str


# ════════════════════════════════════════════════════════════════════
# LLM SETUP  — Qwen 2.5:14b via Ollama (Docker service)
# ════════════════════════════════════════════════════════════════════

def _get_llm():
    """
    Returns a LangChain-compatible chat LLM.
    Configured for Ollama (Qwen 2.5:14b) by default.

    Environment variables:
        OLLAMA_MODEL    = "qwen2.5:14b"  (default)
        OLLAMA_BASE_URL = "http://ollama:11434"  (Docker service name)
    """
    # ── Option A: Ollama (default — Docker or local) ────────────
    try:
        from langchain_ollama import ChatOllama
        model = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://192.168.1.145:11434")
        return ChatOllama(model=model, base_url=base_url, temperature=0)
    except ImportError:
        pass

    # ── Option B: vLLM / OpenAI-compatible endpoint ─────────────
    try:
        from langchain_openai import ChatOpenAI
        base_url = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
        model    = os.getenv("VLLM_MODEL",    "Qwen/Qwen2.5-14B-Instruct")
        return ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key="EMPTY",           # vLLM doesn't need a real key
            temperature=0,
        )
    except ImportError:
        pass

    raise RuntimeError(
        "No LLM backend found. Install langchain-ollama or langchain-openai.\n"
        "  pip install langchain-ollama   # for Ollama\n"
        "  pip install langchain-openai   # for vLLM"
    )


# ════════════════════════════════════════════════════════════════════
# NODE 1 — NL UNDERSTANDING
# ════════════════════════════════════════════════════════════════════

_EXTRACT_SYSTEM = """You are a data extraction assistant for a Smart City monitoring system.
Extract structured information from the user's question and return ONLY valid JSON.

Available data domains:
- Access Control: AccessChannels_QR, Beaches_Vip, MainGate_Vip
- CCTV: cameras_total_number, Total_disabled_cameras, Total_enabled_cameras
- Gate APIs: Gates_Fail, Gates_Success

Return this exact JSON structure:
{
  "intent": "<latest|average|sum|min|max|trend|count_records>",
  "location": "<extracted location or asset name, e.g. 'Beaches VIP', 'disabled cameras'>",
  "time_filter": {
    "type": "<latest|last_n|date_range|all>",
    "n": <number of hours if last_n, else null>,
    "start": "<YYYY-MM-DD if date_range, else null>",
    "end": "<YYYY-MM-DD if date_range, else null>"
  }
}

Rules:
- intent=latest when user says "current", "now", "today", "what is", "count at"
- intent=average when user says "average", "mean", "typical"
- intent=trend when user says "trend", "history", "over time", "last readings"
- intent=max when user says "peak", "highest", "maximum"
- intent=min when user says "lowest", "minimum"
- time_filter.type=latest for most "current" questions
- time_filter.type=last_n + n=24 for "last 24 hours", "today"
- Return ONLY the JSON object. No explanation. No markdown.
"""

def node_nl_understanding(state: AgentState) -> dict:
    """Node 1: Use Qwen to extract structured intent from the user question."""
    llm = _get_llm()
    from langchain_core.messages import SystemMessage, HumanMessage

    response = llm.invoke([
        SystemMessage(content=_EXTRACT_SYSTEM),
        HumanMessage(content=state["user_question"]),
    ])

    text = response.content.strip()
    # Strip markdown fences if model wraps in ```json
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    try:
        extracted = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: treat as a "latest" query with raw location
        extracted = {
            "intent": "latest",
            "location": state["user_question"],
            "time_filter": {"type": "latest", "n": None, "start": None, "end": None},
        }

    return {"extracted_intent": extracted}


# ════════════════════════════════════════════════════════════════════
# NODE 2 — TAG RESOLVER
# ════════════════════════════════════════════════════════════════════

def node_tag_resolver(state: AgentState) -> dict:
    """Node 2: Deterministic fuzzy match from location string → TagName."""
    location = state["extracted_intent"].get("location", "")
    tag, confidence = resolve_tag(location)

    if tag is None:
        return {
            "resolved_tag": None,
            "resolver_confidence": 0.0,
            "resolver_error": (
                f"Could not resolve '{location}' to a known tag. "
                f"Available: {', '.join(TAG_LABELS.values())}"
            ),
        }

    return {
        "resolved_tag": tag,
        "resolver_confidence": confidence,
        "resolver_error": None,
    }


# ════════════════════════════════════════════════════════════════════
# NODE 3 — QUERY BUILDER
# ════════════════════════════════════════════════════════════════════

def node_query_builder(state: AgentState) -> dict:
    """Node 3: Build DuckDB SQL from resolved tag + intent. No LLM."""
    if state.get("resolver_error"):
        return {
            "query_sql": "",
            "query_params": [],
            "query_description": "No query — tag resolution failed.",
        }

    intent_dict = {
        **state["extracted_intent"],
        "tag_name": state["resolved_tag"],
    }
    qr = build_query(intent_dict)

    return {
        "query_sql": qr.sql,
        "query_params": qr.params,
        "query_description": qr.description,
    }


# ════════════════════════════════════════════════════════════════════
# NODE 4 — EXECUTOR
# ════════════════════════════════════════════════════════════════════

def node_executor(state: AgentState) -> dict:
    """Node 4: Run the SQL against DuckDB. No LLM."""
    if not state.get("query_sql"):
        return {"raw_result": [], "executor_error": "No SQL to execute."}

    try:
        conn = get_connection()
        rel  = conn.execute(state["query_sql"], state["query_params"])
        cols = [d[0] for d in rel.description]
        rows = rel.fetchall()
        result = [dict(zip(cols, row)) for row in rows]
        return {"raw_result": result, "executor_error": None}

    except Exception as e:
        return {"raw_result": [], "executor_error": str(e)}


# ════════════════════════════════════════════════════════════════════
# NODE 5 — ANSWER FORMATTER
# ════════════════════════════════════════════════════════════════════

_FORMAT_SYSTEM = """You are a smart city monitoring assistant for Marassi city.
Convert the raw query result into a clear, concise natural-language answer.
Be direct and factual. Include the value, the tag label, and the timestamp.
If the result is empty, say the data is not available.
Keep answers under 3 sentences unless a trend is requested.
For trend data, summarize the direction (increasing/decreasing/stable) and key values.
"""

def node_answer_formatter(state: AgentState) -> dict:
    """Node 5: Use Qwen to render raw DB result as a natural-language answer."""

    # Short-circuit on errors
    if state.get("resolver_error"):
        return {"final_answer": f"Sorry, I couldn't find that sensor. {state['resolver_error']}"}

    if state.get("executor_error"):
        return {"final_answer": f"Query failed: {state['executor_error']}"}

    if not state["raw_result"]:
        return {"final_answer": "No data found for that query in the available dataset."}

    llm = _get_llm()
    from langchain_core.messages import SystemMessage, HumanMessage

    # Serialize result for the LLM
    tag_label_str = tag_label(state.get("resolved_tag", ""))
    context = (
        f"User question: {state['user_question']}\n"
        f"Sensor: {tag_label_str} ({state.get('resolved_tag', '')})\n"
        f"Query type: {state['query_description']}\n"
        f"Result: {json.dumps(state['raw_result'], default=str, indent=2)}"
    )

    response = llm.invoke([
        SystemMessage(content=_FORMAT_SYSTEM),
        HumanMessage(content=context),
    ])

    return {"final_answer": response.content.strip()}


# ════════════════════════════════════════════════════════════════════
# ROUTING — skip to error answer if tag resolution failed
# ════════════════════════════════════════════════════════════════════

def route_after_resolver(state: AgentState) -> str:
    if state.get("resolver_error"):
        return "answer_formatter"   # skip query builder + executor
    return "query_builder"


# ════════════════════════════════════════════════════════════════════
# GRAPH ASSEMBLY
# ════════════════════════════════════════════════════════════════════

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("nl_understanding",  node_nl_understanding)
    graph.add_node("tag_resolver",      node_tag_resolver)
    graph.add_node("query_builder",     node_query_builder)
    graph.add_node("executor",          node_executor)
    graph.add_node("answer_formatter",  node_answer_formatter)

    graph.set_entry_point("nl_understanding")
    graph.add_edge("nl_understanding", "tag_resolver")
    graph.add_conditional_edges("tag_resolver", route_after_resolver)
    graph.add_edge("query_builder", "executor")
    graph.add_edge("executor",      "answer_formatter")
    graph.add_edge("answer_formatter", END)

    return graph.compile()


# ════════════════════════════════════════════════════════════════════
# PUBLIC API
# ════════════════════════════════════════════════════════════════════

_app = None

def get_graph():
    """Get or build the compiled LangGraph (singleton)."""
    global _app
    if _app is None:
        _app = build_graph()
    return _app


def ask(question: str, data_dir: Path | None = None) -> str:
    """
    Main entry point for synchronous question answering.

    Usage:
        from agent.graph import ask
        answer = ask("What is the current count at the Beaches VIP access point?")
        print(answer)
    """
    if data_dir:
        from agent.data_loader import build_connection
        import agent.data_loader as dl
        dl._conn = build_connection(data_dir)

    app = get_graph()

    initial_state: AgentState = {
        "user_question":      question,
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
    return result["final_answer"]


async def ask_streaming(question: str) -> AsyncIterator[dict]:
    """
    Streaming entry point — yields intermediate states after each node.
    Used by the WebSocket endpoint to show agent thinking steps.
    """
    app = get_graph()

    initial_state: AgentState = {
        "user_question":      question,
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

    # Stream node-by-node using LangGraph's stream interface
    node_labels = {
        "nl_understanding": "Understanding your question...",
        "tag_resolver":     "Resolving sensor tag...",
        "query_builder":    "Building query...",
        "executor":         "Querying database...",
        "answer_formatter": "Formatting answer...",
    }

    async for event in app.astream(initial_state, stream_mode="updates"):
        for node_name, state_update in event.items():
            yield {
                "node": node_name,
                "label": node_labels.get(node_name, node_name),
                "data": {k: _serialize(v) for k, v in state_update.items()},
            }


def _serialize(obj):
    """Make objects JSON-serializable."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, (list, dict, str, int, float, bool, type(None))):
        return obj
    return str(obj)


# ════════════════════════════════════════════════════════════════════
# DEV: run directly for testing (bypasses LLM, tests data layer only)
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--no-llm",   action="store_true",
                        help="Test data layer only (skips LLM nodes)")
    args = parser.parse_args()

    dd = Path(args.data_dir) if args.data_dir else None

    if args.no_llm:
        # Quick data-layer smoke test
        from agent.data_loader import get_connection
        from agent.tag_resolver import resolve_tag
        from agent.query_builder import build_query

        conn = get_connection(dd or Path(__file__).parent.parent / "data")
        tests = [
            ("beaches vip", "latest"),
            ("main gate",   "latest"),
            ("disabled cameras", "average"),
            ("gates fail",  "trend"),
        ]
        for loc, intent in tests:
            tag, conf = resolve_tag(loc)
            print(f"\n[{loc}] → {tag}  (conf={conf})")
            if tag:
                qr = build_query({"intent": intent, "tag_name": tag,
                                   "time_filter": {"type": "latest"}})
                rows = conn.execute(qr.sql, qr.params).fetchall()
                print(f"  SQL: {qr.sql[:80]}...")
                print(f"  Result: {rows}")
    else:
        q = "What is the current traffic or count at the Beaches VIP access point?"
        print(f"Q: {q}")
        print(f"A: {ask(q, data_dir=dd)}")
