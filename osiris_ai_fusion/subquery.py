"""Recursive subquery planning for Universal Deep Search.

A single-shot planner answers "compare the earthquake risk in Izmir and Istanbul
and what the news said this week" with one query against one provider fan-out.
The parts that actually need separate research never get researched separately.

This module decomposes a question into bounded, self-contained subquestions and
recurses into those, under three rules that keep the feature from doing harm:

1. **Decomposition is refused more often than it is attempted.** A question that
   is already atomic stays atomic. A bad split produces fragments that lose their
   predicate ("Izmir" on its own), and researching a fragment is worse than not
   recursing at all, so the deterministic splitter only fires on strong boundaries.
2. **It never widens authority.** Subqueries reuse the tools the root plan already
   sealed; they cannot introduce a tool the intent did not authorize.
3. **It never widens the budget.** Subquery calls come out of the tool-call budget
   the root plan left unspent, so recursion redistributes work rather than adding it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from config import get_settings

# Boundaries in decreasing strength. Splitting every level of punctuation in one
# pass would flatten the question and leave recursion nothing to descend into, so
# each level takes the strongest boundary still present and leaves the rest for the
# next level down. A clause after a sentence end or a ";" can survive losing its
# neighbour; one after a bare "ve"/"and" usually cannot, which is why coordinating
# conjunctions are not boundaries at any level.
SENTENCE_BOUNDARY = re.compile(r"[?!\n]+|(?<=\.)\s+(?=[A-ZÇĞİÖŞÜ])")
CLAUSE_BOUNDARY = re.compile(r"[;]+")
BOUNDARIES = (SENTENCE_BOUNDARY, CLAUSE_BOUNDARY)

# An enumeration is safe to split only when every side stands on its own.
MIN_FRAGMENT_WORDS = 3
MIN_FRAGMENT_CHARS = 12

MAX_SUBQUERY_CHARS = 300


@dataclass(frozen=True)
class SubQuery:
    """One derived question and how deep in the recursion it was produced."""

    query: str
    depth: int
    origin: str


def _clean(fragment: str) -> str:
    return " ".join(fragment.split()).strip(" ,;:-–—").strip()


def _is_researchable(fragment: str) -> bool:
    """Reject fragments that lost too much of the question to stand alone."""
    cleaned = _clean(fragment)
    return (
        len(cleaned) >= MIN_FRAGMENT_CHARS
        and len(cleaned.split()) >= MIN_FRAGMENT_WORDS
    )


def split_deterministic(query: str) -> list[str]:
    """Split on the strongest boundary present, if every piece survives alone.

    Returns an empty list rather than a partial split: half a question researched
    on its own is worse evidence than the whole question researched once.
    """
    for boundary in BOUNDARIES:
        parts = [_clean(part) for part in boundary.split(query) if _clean(part)]
        if len(parts) < 2:
            continue
        if all(_is_researchable(part) for part in parts):
            return parts
    return []


def _accept(
    candidates: list[str],
    *,
    root: str,
    max_count: int,
    seen: set[str],
) -> list[str]:
    """Keep distinct, researchable candidates that are not the root question again."""
    accepted: list[str] = []
    root_key = _clean(root).casefold()
    for candidate in candidates:
        cleaned = _clean(candidate)[:MAX_SUBQUERY_CHARS]
        key = cleaned.casefold()
        if not cleaned or key == root_key or key in seen:
            continue
        if not _is_researchable(cleaned):
            continue
        seen.add(key)
        accepted.append(cleaned)
        if len(accepted) >= max_count:
            break
    return accepted


async def _split_with_model(query: str, max_count: int) -> list[str]:
    """Ask the planner model to decompose. Turkish conjunctions defeat regexes."""
    # Imported here so the module itself stays free of the HTTP/model stack: the
    # deterministic path and the budget arithmetic must remain cheap to test.
    from llm import ModelRouter

    system = (
        "You decompose a research question into independent subquestions for "
        "ORBYTHRA Universal Deep Search. Return only JSON matching the schema. "
        "Each subquestion must be self-contained: restate the entity, place and "
        "time period it needs, because it will be researched on its own with no "
        "memory of the original question. Preserve the language of the input. "
        "If the question is already a single research target, return an empty "
        "list — never invent subquestions to fill the quota, and never answer "
        "the question yourself."
    )
    prompt = (
        f"QUESTION: {query}\n"
        f"MAX_SUBQUESTIONS: {max_count}\n"
        "Return {\"subqueries\": [...]}."
    )
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "subqueries": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": max_count,
            }
        },
        "required": ["subqueries"],
    }
    payload, _ = await ModelRouter().generate_json(system, prompt, schema)
    rows = payload.get("subqueries") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, str)]


async def plan_subqueries(
    query: str,
    *,
    max_count: int | None = None,
    max_depth: int | None = None,
) -> list[SubQuery]:
    """Decompose ``query`` recursively, breadth-first, within count and depth caps.

    Breadth-first ordering matters: when the budget runs out mid-plan, the caller
    keeps the shallowest — and therefore most directly relevant — subquestions.
    """
    settings = get_settings()
    if not settings.subquery_planning_enabled:
        return []
    max_count = settings.subquery_max_count if max_count is None else max_count
    max_depth = settings.subquery_max_depth if max_depth is None else max_depth
    if max_count < 1 or max_depth < 1:
        return []

    planned: list[SubQuery] = []
    seen: set[str] = {_clean(query).casefold()}
    frontier: list[tuple[str, int]] = [(query, 0)]

    while frontier and len(planned) < max_count:
        parent, depth = frontier.pop(0)
        if depth >= max_depth:
            continue

        remaining = max_count - len(planned)
        candidates = split_deterministic(parent)
        origin = "deterministic"
        if not candidates and settings.ai_planner_enabled:
            try:
                candidates = await _split_with_model(parent, remaining)
                origin = "model"
            except Exception:
                # Decomposition is an optimization. A planner outage must leave the
                # root investigation exactly as it would have been without it.
                candidates = []

        for accepted in _accept(candidates, root=parent, max_count=remaining, seen=seen):
            planned.append(SubQuery(query=accepted, depth=depth + 1, origin=origin))
            frontier.append((accepted, depth + 1))

    return planned[:max_count]


def allocate_subquery_calls(
    *,
    planned_tools: list[str],
    research_tools: list[str],
    subqueries: list[str],
    max_tool_calls: int,
) -> list[tuple[str, str]]:
    """Pair subqueries with authorized research tools inside the unspent budget.

    Two invariants hold by construction, and both are load-bearing:

    * every returned tool is one the root plan already sealed, so recursion cannot
      reach a capability the sealed intent did not authorize;
    * the root plan's own calls plus these never exceed ``max_tool_calls``, so
      enabling recursion redistributes the existing budget instead of raising it.

    Subqueries are consumed in order, which is breadth-first out of
    :func:`plan_subqueries`, so a budget that runs out keeps the shallowest and
    most directly relevant questions.
    """
    authorized = [tool for tool in research_tools if tool in planned_tools]
    remaining = max(0, max_tool_calls - len(planned_tools))
    calls: list[tuple[str, str]] = []
    if not authorized or remaining <= 0:
        return calls
    for question in subqueries:
        for tool in authorized:
            if len(calls) >= remaining:
                return calls
            calls.append((tool, question))
    return calls
