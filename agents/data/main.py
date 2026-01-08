"""
Patient Data Agent
------------------
This agent acts as a thin client over the MCP server. It exposes a single skill
that allows other agents (e.g., router or triage) to request patient records,
lists, and encounter history via A2A.
"""

import os
from typing import Any, Dict

import httpx
from fastapi import FastAPI

from sdk.types import (
    AgentCard,
    AgentCapabilities,
    AgentProvider,
    AgentSkill,
    Message,
)
from shared.a2a_handler import SimpleAgentRequestHandler, register_agent_routes
from shared.message_utils import build_text_message


# ---------------------------------------------------------------------------
# MCP configuration
# ---------------------------------------------------------------------------

MCP_ENDPOINT = os.getenv("MCP_SERVER_URL", "http://localhost:8000")


async def invoke_mcp(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Forward a tool call to the MCP server and return its result portion.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{MCP_ENDPOINT}/tools/call",
            json={"name": tool_name, "arguments": args},
        )
        response.raise_for_status()
        body = response.json()
        return body.get("result", {})


# ---------------------------------------------------------------------------
# Skill implementation
# ---------------------------------------------------------------------------

async def handle_data_request(message: Message) -> Message:
    """
    Interpret the incoming text query and choose the correct MCP tool.
    """
    text = message.parts[0].text if (message.parts and message.parts[0].text) else ""
    lowered = text.lower()

    # simple rule-based routing for demo purposes
    if "list" in lowered:
        data = await invoke_mcp("list_patients", {"limit": 5})
        reply = f"Patient list (limit 5): {data}"

    elif "history" in lowered:
        data = await invoke_mcp("get_patient_history", {"patient_id": 1})
        reply = f"Encounter history for patient 1: {data}"

    else:
        data = await invoke_mcp("get_patient", {"patient_id": 1})
        reply = f"Patient record: {data}"

    return build_text_message(reply)


# ---------------------------------------------------------------------------
# Agent metadata (A2A AgentCard)
# ---------------------------------------------------------------------------

def build_agent_card() -> AgentCard:
    return AgentCard(
        name="Patient Data Agent",
        description="Fetches patient records, lists, and history via MCP calls.",
        version="1.0.0",
        url="http://localhost:8011",
        documentationUrl="https://example.com/docs/patient-data",
        capabilities=AgentCapabilities(streaming=True),
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        provider=AgentProvider(
            organization="Assignment 5",
            url="http://localhost:8011",
        ),
        skills=[
            AgentSkill(
                id="patient-data",
                name="Patient Data Tools",
                description="Uses MCP to retrieve patient information.",
                tags=["mcp", "data"],
                inputModes=["text"],
                outputModes=["text"],
                examples=[
                    "List patients",
                    "Show me history for a patient",
                    "Get patient details",
                ],
            )
        ],
        preferredTransport="JSONRPC",
    )


# ---------------------------------------------------------------------------
# FastAPI application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(title="Patient Data Agent Service")
    handler = SimpleAgentRequestHandler(
        agent_id="patient-data",
        skill_callback=handle_data_request,
    )
    register_agent_routes(app, build_agent_card(), handler)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8011)
