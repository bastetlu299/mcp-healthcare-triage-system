"""
Router Agent
------------
Coordinates between specialist A2A agents (data, triage, insurance) using a
LangGraph workflow. The router interprets user intent, forwards the request to
the appropriate agent(s), and aggregates the returned information.
"""

import os
from typing import List, TypedDict

import httpx
from fastapi import FastAPI
from langgraph.graph import StateGraph, END

from sdk.types import (
    AgentCard,
    AgentCapabilities,
    AgentProvider,
    AgentSkill,
    Message,
    MessageSendParams,
    Role,
    Task,
)
from shared.a2a_handler import SimpleAgentRequestHandler, register_agent_routes
from shared.message_utils import build_text_message


# ---------------------------------------------------------------------------
# RPC configuration for each specialist agent
# ---------------------------------------------------------------------------

DATA_RPC = os.getenv("DATA_AGENT_RPC", "http://localhost:8011/rpc")
TRIAGE_RPC = os.getenv("TRIAGE_AGENT_RPC", "http://localhost:8012/rpc")
INSURANCE_RPC = os.getenv("INSURANCE_AGENT_RPC", "http://localhost:8013/rpc")


# ---------------------------------------------------------------------------
# Router state model for LangGraph
# ---------------------------------------------------------------------------

class RouterState(TypedDict):
    messages: List[str]
    route: str
    results: List[str]


# ---------------------------------------------------------------------------
# Utility: Send a JSON-RPC message to any A2A agent
# ---------------------------------------------------------------------------

async def call_agent_over_rpc(agent_url: str, text: str) -> str:
    """
    Send a single text message to an A2A agent via JSON-RPC and extract the reply.
    """
    msg_id = os.urandom(8).hex()
    payload = {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": "message/send",
        "params": MessageSendParams(
            message=Message(
                messageId=os.urandom(8).hex(),
                role=Role.user,
                parts=[build_text_message(text, role=Role.user).parts[0]],
            )
        ).model_dump(),
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(agent_url, json=payload)
        r.raise_for_status()
        response_body = r.json()

    if "result" not in response_body:
        return ""

    task = Task.model_validate(response_body["result"])
    if task.history and len(task.history) > 1:
        latest = task.history[-1]
        if latest.parts:
            return latest.parts[0].text

    return ""


# ---------------------------------------------------------------------------
# LangGraph workflow definition
# ---------------------------------------------------------------------------

def create_router_graph():
    graph = StateGraph(RouterState)

    # ---- Classification step ------------------------------------------------
    def classify_intent(state: RouterState) -> RouterState:
        query = state["messages"][-1].lower()

        if any(word in query for word in ["insurance", "coverage", "billing", "copay"]):
            state["route"] = "insurance"
        elif any(word in query for word in ["patient", "history", "chart"]):
            state["route"] = "data_then_triage"
        else:
            state["route"] = "triage"

        return state

    # ---- Specialist handoff -------------------------------------------------
    async def run_specialists(state: RouterState) -> RouterState:
        user_text = state["messages"][-1]
        collected: List[str] = []

        if state["route"] == "data_then_triage":
            data_reply = await call_agent_over_rpc(DATA_RPC, user_text)
            combined_prompt = f"Data context: {data_reply}. Provide guidance to the user."
            triage_reply = await call_agent_over_rpc(TRIAGE_RPC, combined_prompt)
            collected.extend([data_reply, triage_reply])

        elif state["route"] == "insurance":
            insurance_reply = await call_agent_over_rpc(INSURANCE_RPC, user_text)
            collected.append(insurance_reply)

        else:  # fallback to triage
            triage_reply = await call_agent_over_rpc(TRIAGE_RPC, user_text)
            collected.append(triage_reply)

        state["results"] = collected
        return state

    # ---- Summary generation -------------------------------------------------
    def summarize_outputs(state: RouterState) -> RouterState:
        text = "\n".join(state.get("results", []))
        state["messages"].append(f"Router summary:\n{text}")
        return state

    # assemble graph
    graph.add_node("classify", classify_intent)
    graph.add_node("dispatch", run_specialists)
    graph.add_node("summarize", summarize_outputs)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "dispatch")
    graph.add_edge("dispatch", "summarize")
    graph.add_edge("summarize", END)

    return graph.compile()


workflow = create_router_graph()


# ---------------------------------------------------------------------------
# Skill executed when router receives a message
# ---------------------------------------------------------------------------

async def router_skill(message: Message) -> Message:
    initial_text = message.parts[0].text if (message.parts and message.parts[0].text) else ""
    starting_state: RouterState = {
        "messages": [initial_text],
        "route": "triage",
        "results": [],
    }

    final = await workflow.ainvoke(starting_state)
    summary = final["messages"][-1]
    return build_text_message(summary)


# ---------------------------------------------------------------------------
# Router AgentCard
# ---------------------------------------------------------------------------

def create_agent_card() -> AgentCard:
    return AgentCard(
        name="Router Agent",
        description="Routes user intents across A2A agents using a LangGraph workflow.",
        url="http://localhost:8010",
        version="1.0.0",
        documentationUrl="https://example.com/docs/router",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        provider=AgentProvider(
            organization="Assignment 5",
            url="http://localhost:8010",
        ),
        skills=[
            AgentSkill(
                id="router",
                name="Request Routing",
                description="Dispatches tasks to data, triage, and insurance agents.",
                tags=["router", "workflow", "langgraph"],
                inputModes=["text"],
                outputModes=["text"],
                examples=[
                    "Get history and provide a final response",
                    "Handle an insurance coverage question",
                    "General triage request",
                ],
            )
        ],
        preferredTransport="JSONRPC",
    )


# ---------------------------------------------------------------------------
# FastAPI application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(title="Router Agent Service")
    handler = SimpleAgentRequestHandler(
        agent_id="router",
        skill_callback=router_skill,
    )
    register_agent_routes(app, create_agent_card(), handler)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8010)
