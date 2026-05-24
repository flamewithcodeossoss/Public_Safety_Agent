"""
Tag Resolver — Node 2 in the LangGraph pipeline.

Converts a fuzzy location/asset string extracted by the LLM
into an exact AVEVA TagName using:
  1. Direct dict lookup (fast, exact)
  2. rapidfuzz partial_ratio (handles typos, partial phrases)
  3. Token-set ratio fallback (handles word-order variations)

Returns None if confidence is below threshold — agent will ask for clarification.
"""

from __future__ import annotations
from config.tag_registry import TAG_REGISTRY, TAG_LABELS, ALL_TAG_NAMES

try:
    from rapidfuzz import fuzz, process
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False
    print("[resolver] WARNING: rapidfuzz not installed. Install with: pip install rapidfuzz")


FUZZY_THRESHOLD = 65   # minimum score (0–100) to accept a match


def resolve_tag(query: str) -> tuple[str | None, float]:
    """
    Resolve a human query string to an exact TagName.

    Returns:
        (tag_name, confidence_score) — tag_name is None if no match found.
    """
    if not query:
        return None, 0.0

    normalized = query.strip().lower()

    # 1. Exact lookup in registry
    if normalized in TAG_REGISTRY:
        return TAG_REGISTRY[normalized], 100.0

    # 2. Partial string match in registry keys
    for key, tag in TAG_REGISTRY.items():
        if normalized in key or key in normalized:
            return tag, 90.0

    # 3. rapidfuzz fuzzy match against registry keys
    if _HAS_RAPIDFUZZ:
        # Match against human aliases
        result = process.extractOne(
            normalized,
            TAG_REGISTRY.keys(),
            scorer=fuzz.token_set_ratio,
        )
        if result and result[1] >= FUZZY_THRESHOLD:
            return TAG_REGISTRY[result[0]], float(result[1])

        # Also try matching directly against TagName strings
        result2 = process.extractOne(
            normalized,
            ALL_TAG_NAMES,
            scorer=fuzz.partial_ratio,
        )
        if result2 and result2[1] >= FUZZY_THRESHOLD:
            return result2[0], float(result2[1])

    return None, 0.0


def resolve_domain_tags(domain: str) -> list[str]:
    """
    Return all TagNames belonging to a domain.
    domain: 'access_control' | 'cctv' | 'gate_apis'
    """
    from config.tag_registry import TAG_DOMAIN
    return [t for t, d in TAG_DOMAIN.items() if d == domain]


def tag_label(tag_name: str) -> str:
    """Human-readable label for a TagName."""
    return TAG_LABELS.get(tag_name, tag_name)
