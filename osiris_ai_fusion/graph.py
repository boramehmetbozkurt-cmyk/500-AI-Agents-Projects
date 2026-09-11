from __future__ import annotations

import asyncio
import json
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from llm import LocalLLM
from osiris_client import OsirisClient, READ_ONLY_TOOLS
from seal import seal_intent, sign_receipt


class AgentState(TypedDict, total=False):
    query: str
    planned_tools: list[str]
    evidence: dict[str, Any]
    analysis: str
    receipt: dict[str, Any]


KEYWORD_TOOL_MAP = {
    "deprem": "earthquakes",
    "earthquake": "earthquakes",
    "yangın": "fires",
    "fire": "fires",
    "uçuş": "aircraft",
    "uçak": "aircraft",
    "flight": "aircraft",
    "hava kalitesi": "air_quality",
    "air quality": "air_quality",
    "çatışma": "conflicts",
    "conflict": "conflicts",
    "ülke riski": "country_risk",
    "country risk": "country_risk",
    "siber": "cyber_threats",
    "cyber": "cyber_threats",
    "kripto": "crypto",
    "crypto": "crypto",
    "kamera": "cctv",
    "cctv": "cctv",
}


def _plan_tools(query: str) -> list[str]:
    q = query.lower()
    selected = {tool for keyword, tool in KEYWORD_TOOL_MAP.items() if keyword in q}
    if not selected:
        selected = {"earthquakes", "fires", "aircraft", "conflicts", "country_risk"}
    return sorted(selected)


async def planner_node(state: AgentState) -> AgentState:
    tools = _plan_tools(state["query"])
    return {**state, "planned_tools": tools}


async def collector_node(state: AgentState) -> AgentState:
    intent = seal_intent(state["query"], state["planned_tools"])
    client = OsirisClient()

    async def one(tool: str) -> tuple[str, Any]:
        try:
            return tool, await client.fetch_tool(tool)
        except Exception as exc:
            return tool, {"error": str(exc)}

    results = await asyncio.gather(*(one(tool) for tool in state["planned_tools"]))
    evidence = {tool: data for tool, data in results}
    return {
        **state,
        "evidence": evidence,
        "_sealed_intent": intent,  # internal graph state
    }


async def analyst_node(state: AgentState) -> AgentState:
    llm = LocalLLM()
    compact = json.dumps(state.get("evidence", {}), ensure_ascii=False)[:50000]
    system = (
        "You are the OSIRIS Fusion Analyst. Use only the supplied read-only OSINT evidence. "
        "Never invent facts. Separate observed evidence from inference. State uncertainty. "
        "Do not recommend intrusive surveillance or unauthorized access."
    )
    prompt = (
        f"USER QUERY:\n{state['query']}\n\n"
        f"TOOLS USED: {', '.join(state.get('planned_tools', []))}\n\n"
        f"EVIDENCE:\n{compact}\n\n"
        "Return a concise Turkish intelligence-style assessment with: BLUF, findings, correlations, confidence, and data gaps."
    )
    try:
        analysis = await llm.generate(system, prompt)
    except Exception as exc:
        analysis = f"Local LLM unavailable: {exc}. Evidence was collected successfully."
    return {**state, "analysis": analysis}


async def verifier_node(state: AgentState) -> AgentState:
    intent = state.get("_sealed_intent")
    if intent is None:
        raise RuntimeError("Missing sealed intent")
    receipt = sign_receipt(intent, state.get("planned_tools", []), state.get("analysis", ""))
    return {**state, "receipt": receipt}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("collector", collector_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("verifier", verifier_node)
    graph.set_entry_point("planner")
    graph.add_edge("planner", "collector")
    graph.add_edge("collector", "analyst")
    graph.add_edge("analyst", "verifier")
    graph.add_edge("verifier", END)
    return graph.compile()


AGENT_GRAPH = build_graph()


async def investigate(query: str) -> dict[str, Any]:
    result = await AGENT_GRAPH.ainvoke({"query": query})
    result.pop("_sealed_intent", None)
    return result
