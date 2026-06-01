"""
Smart City LangGraph Agent
==========================
5-node graph:

  [user_question]
       ↓
  Node 1: nl_understanding   ← Qwen  (extract intent + entities)
       ↓
  Node 2: tag_resolver       ← Deterministic (fuzzy match → TagName)
       ↓
  Node 3: query_builder      ← Qwen  (resolved tag + schema → raw SQL)
       ↓
  Node 4: executor           ← DuckDB (run SQL; on error → reflect back to Qwen, retry up to 3×)
       ↓
  Node 5: answer_formatter   ← Qwen  (format result → natural language)

The LLM is used in Node 1 (extraction), Node 3 (SQL generation),
Node 4 (reflection on errors), and Node 5 (formatting).
"""

from __future__ import annotations
import json
import os
import re
from typing import TypedDict, AsyncIterator
from pathlib import Path

from langgraph.graph import StateGraph, END

# ── Internal modules ────────────────────────────────────────────────
from agent.tag_resolver   import resolve_tag, resolve_domain_tags, tag_label
from agent.data_loader    import get_connection
from config.tag_registry  import TAG_LABELS, DOMAIN_TAGS


# ════════════════════════════════════════════════════════════════════
# STATE
# ════════════════════════════════════════════════════════════════════

class AgentState(TypedDict):
    # Input
    user_question: str

    # Node 1 output
    extracted_intent: dict          # {"intent": "...", "location": "...", "time_filter": {...}}

    # Node 2 output
    resolved_tag: str | None        # exact TagName, "__domain__X", or None
    domain_tags: list[str]          # populated when resolved_tag is a domain
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
# LLM SETUP  — Qwen via Ollama (Docker service)
# ════════════════════════════════════════════════════════════════════

# Stop tokens for SQL generation — cuts output as soon as the SQL ends
_SQL_STOP = [";", "```", "\n\n"]


def _get_llm(**kwargs):
    """
    Returns a LangChain-compatible chat LLM.
    Pass extra kwargs (e.g. stop=[...]) to override defaults.

    Environment variables:
        OLLAMA_MODEL    = "RogerBen/qwen3.5-35b-opus-distill:latest"  (default)
        OLLAMA_BASE_URL = "http://192.168.1.206:11434"  (default)
    """
    # ── Option A: Ollama (default — Docker or local) ────────────
    try:
        from langchain_ollama import ChatOllama
        model = os.getenv("OLLAMA_MODEL", "RogerBen/qwen3.5-35b-opus-distill:latest")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://192.168.1.206:11434")
        return ChatOllama(model=model, base_url=base_url, temperature=0, **kwargs)
    except ImportError:
        pass

    # ── Option B: vLLM / OpenAI-compatible endpoint ─────────────
    #    For best latency, launch vLLM with --enable-prefix-caching
    try:
        from langchain_openai import ChatOpenAI
        base_url = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
        model    = os.getenv("VLLM_MODEL",    "Qwen/Qwen3.5-35B-Instruct")
        return ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key="EMPTY",           # vLLM doesn't need a real key
            temperature=0,
            **kwargs,
        )
    except ImportError:
        pass

    raise RuntimeError(
        "No LLM backend found. Install langchain-ollama or langchain-openai.\n"
        "  pip install langchain-ollama   # for Ollama\n"
        "  pip install langchain-openai   # for vLLM"
    )


def _get_sql_llm():
    """LLM tuned for SQL generation — includes stop sequences to cut latency."""
    return _get_llm(stop=_SQL_STOP)


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
  "intent": "<latest|average|sum|min|max|trend|count_records|summary>",
  "location": "<extracted location, asset name, or domain name>",
  "time_filter": {
    "type": "<latest|last_n|last_month|date_range|all>",
    "n": <number of hours if last_n, else null>,
    "start": "<YYYY-MM-DD if date_range, else null>",
    "end": "<YYYY-MM-DD if date_range, else null>"
  }
}

Rules for intent:
- intent=latest        → user asks about current/now value of a specific sensor
- intent=summary       → user says "summarize", "overview", "status report", OR asks about a whole domain (CCTV, gates, access control)
- intent=trend         → user says "trend", "history", "over time", OR asks about a specific past date
- intent=average       → user says "average", "mean", "typical"
- intent=max           → user says "peak", "highest", "maximum"
- intent=min           → user says "lowest", "minimum"
- intent=count_records → user says "how many readings", "how many records", "how many updates"

Rules for location:
- For single-sensor questions: extract the specific sensor name (e.g. "Beaches VIP", "disabled cameras")
- For domain questions: extract the domain name only (e.g. "CCTV", "access control", "gates")

Rules for time_filter:
- type=latest     → no date mentioned, user wants the current value
- type=last_month → user says "last month", "previous month", "past month"
- type=last_n     → user says "last N hours", "past N hours" → set n=hours
- type=date_range → user mentions a specific date or range → set start and end in YYYY-MM-DD
- type=all        → user says "all time", "entire dataset", "overall"

Critical rules:
- If user mentions a SPECIFIC DATE: time_filter.type="date_range", intent="trend"
- If user asks to SUMMARIZE a whole domain: intent="summary", location=domain name only
- If user says "last month": time_filter.type="last_month" (NOT date_range)
- Return ONLY the JSON object. No explanation. No markdown."""

def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks emitted by Qwen 3.x thinking mode."""
    return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()


def _extract_sql(text: str) -> str:
    """Extract raw SQL from LLM response, stripping markdown fences and think blocks."""
    text = _strip_think(text)
    # Strip markdown fences if model wraps in ```sql or ```
    if "```" in text:
        parts = text.split("```")
        for part in parts[1::2]:  # odd-indexed parts are inside fences
            cleaned = part.strip()
            if cleaned.lower().startswith("sql"):
                cleaned = cleaned[3:].strip()
            if cleaned:
                return cleaned.strip()
    return text.strip()


def node_nl_understanding(state: AgentState) -> dict:
    """Node 1: Use Qwen to extract structured intent from the user question."""
    llm = _get_llm()
    from langchain_core.messages import SystemMessage, HumanMessage

    response = llm.invoke([
        SystemMessage(content=_EXTRACT_SYSTEM),
        HumanMessage(content=state["user_question"]),
    ])

    text = _strip_think(response.content)
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
    """Node 2: Detect domain vs single-tag and resolve accordingly."""
    location = state["extracted_intent"].get("location", "")
    tag, confidence = resolve_tag(location)

    # Check if it resolved to a domain sentinel
    if tag and tag.startswith("__domain__"):
        domain_name = tag.replace("__domain__", "")
        tags_in_domain = DOMAIN_TAGS.get(domain_name, [])
        if tags_in_domain:
            return {
                "resolved_tag": tag,          # keep sentinel for routing
                "domain_tags": tags_in_domain,
                "resolver_confidence": 100.0,
                "resolver_error": None,
            }

    if tag is None:
        return {
            "resolved_tag": None,
            "domain_tags": [],
            "resolver_confidence": 0.0,
            "resolver_error": (
                f"Could not resolve '{location}' to a known tag. "
                f"Available: {', '.join(TAG_LABELS.values())}"
            ),
        }

    return {
        "resolved_tag": tag,
        "domain_tags": [],
        "resolver_confidence": confidence,
        "resolver_error": None,
    }


# ════════════════════════════════════════════════════════════════════
# NODE 3 — QUERY BUILDER  (LLM-powered: Qwen generates DuckDB SQL)
# ════════════════════════════════════════════════════════════════════

_SQL_GEN_SYSTEM = """You are a DuckDB SQL expert. Write ONE query against table `hist`.

Schema: hist(TagName VARCHAR, DateTime TIMESTAMP, Value INTEGER, vValue INTEGER, StartDateTime TIMESTAMP)

DuckDB notes:
- Time offsets: INTERVAL '24 hours'. Date compare: CAST(x AS DATE). Last month: date_trunc('month', current_date) - INTERVAL '1 month'.
- Always include WHERE Value IS NOT NULL.
- Inline all values as literals (no ? placeholders).

Return ONLY raw SQL. No markdown. No explanation."""


def _build_sql_prompt(state: AgentState) -> str:
    """Build a minimal human message for SQL generation — only the relevant tag(s)."""
    intent_info = state["extracted_intent"]
    intent = intent_info.get("intent", "latest")
    tf = intent_info.get("time_filter", {"type": "latest"})
    domain_tags = state.get("domain_tags", [])

    if domain_tags:
        tag_str = ", ".join(f"'{t}'" for t in domain_tags)
        parts = [
            f"Tags: {tag_str}",
            f"Intent: {intent}",
            f"Time: {json.dumps(tf)}",
        ]
    else:
        tag = state["resolved_tag"]
        parts = [
            f"Tag: '{tag}'",
            f"Intent: {intent}",
            f"Time: {json.dumps(tf)}",
        ]

    return "\n".join(parts)


def node_query_builder(state: AgentState) -> dict:
    """Node 3: Use Qwen to generate DuckDB SQL from resolved tag + schema."""
    if state.get("resolver_error"):
        return {
            "query_sql": "",
            "query_params": [],
            "query_description": "No query — tag resolution failed.",
        }

    llm = _get_sql_llm()
    from langchain_core.messages import SystemMessage, HumanMessage

    human_msg = _build_sql_prompt(state)

    response = llm.invoke([
        SystemMessage(content=_SQL_GEN_SYSTEM),
        HumanMessage(content=human_msg),
    ])

    sql = _extract_sql(response.content)

    # Build a human-readable description
    intent = state["extracted_intent"].get("intent", "latest")
    domain_tags = state.get("domain_tags", [])
    if domain_tags:
        desc = f"LLM-generated {intent} query for domain ({len(domain_tags)} tags)"
    else:
        desc = f"LLM-generated {intent} query for {state.get('resolved_tag', 'unknown')}"

    return {
        "query_sql": sql,
        "query_params": [],       # LLM inlines all values, no params needed
        "query_description": desc,
    }


# ════════════════════════════════════════════════════════════════════
# NODE 4 — EXECUTOR  (with reflection loop: retry up to 3× on error)
# ════════════════════════════════════════════════════════════════════

_MAX_SQL_RETRIES = 3


def _execute_sql(sql: str, params: list) -> tuple[list[dict] | None, str | None]:
    """Run SQL against DuckDB. Returns (rows, None) on success or (None, error) on failure."""
    try:
        conn = get_connection()
        rel = conn.execute(sql, params)
        cols = [d[0] for d in rel.description]
        rows = rel.fetchall()
        return [dict(zip(cols, row)) for row in rows], None
    except Exception as e:
        return None, str(e)


def _ask_llm_to_fix_sql(state: AgentState, failed_sql: str, error_msg: str) -> str:
    """Ask Qwen to fix a failed SQL query given the error message."""
    llm = _get_sql_llm()
    from langchain_core.messages import SystemMessage, HumanMessage

    fix_prompt = (
        f"SQL:\n{failed_sql}\n"
        f"Error: {error_msg}\n"
        f"Context:\n{_build_sql_prompt(state)}\n"
        f"Fix the SQL. Return ONLY corrected raw SQL."
    )

    response = llm.invoke([
        SystemMessage(content=_SQL_GEN_SYSTEM),
        HumanMessage(content=fix_prompt),
    ])

    return _extract_sql(response.content)


def node_executor(state: AgentState) -> dict:
    """Node 4: Run SQL against DuckDB. On error, ask Qwen to fix it (up to 3 retries)."""
    sql = state.get("query_sql", "")
    params = state.get("query_params", [])

    if not sql:
        return {"raw_result": [], "executor_error": "No SQL to execute."}

    # First attempt
    result, error = _execute_sql(sql, params)
    if error is None:
        return {"raw_result": result, "executor_error": None}

    # ── Reflection loop: silently retry up to _MAX_SQL_RETRIES times ──
    current_sql = sql
    last_error = error

    for attempt in range(1, _MAX_SQL_RETRIES + 1):
        print(f"[executor] SQL failed (attempt {attempt}/{_MAX_SQL_RETRIES}): {last_error}")
        print(f"[executor] Asking Qwen to fix the query...")

        try:
            fixed_sql = _ask_llm_to_fix_sql(state, current_sql, last_error)
        except Exception as llm_err:
            print(f"[executor] LLM fix request failed: {llm_err}")
            break

        if not fixed_sql or fixed_sql == current_sql:
            print(f"[executor] LLM returned same/empty SQL, stopping retries.")
            break

        current_sql = fixed_sql
        result, error = _execute_sql(current_sql, [])

        if error is None:
            print(f"[executor] Retry {attempt} succeeded!")
            return {
                "raw_result": result,
                "executor_error": None,
                "query_sql": current_sql,  # update state with the fixed SQL
            }

        last_error = error

    # All retries exhausted
    print(f"[executor] All {_MAX_SQL_RETRIES} retries exhausted. Last error: {last_error}")
    return {"raw_result": [], "executor_error": last_error}


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

    return {"final_answer": _strip_think(response.content)}


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
        "domain_tags":        [],
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
        "domain_tags":        [],
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
        "query_builder":    "Generating SQL query...",
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
# DEV: run directly for testing
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()

    dd = Path(args.data_dir) if args.data_dir else None

    q = "What is the current traffic or count at the Beaches VIP access point?"
    print(f"Q: {q}")
    print(f"A: {ask(q, data_dir=dd)}")
