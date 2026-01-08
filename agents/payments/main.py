"""
Insurance Agent
---------------
Handles queries related to coverage, copays, and benefits eligibility.
This agent does not call MCP tools directly; instead, it provides domain-
specific responses to upstream agents such as the router.
"""

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
# Skill implementation
# ---------------------------------------------------------------------------

async def insurance_skill(message: Message) -> Message:
    """
    Produce a text-based response summarizing insurance capabilities.
    """
    user_text = message.parts[0].text if (message.parts and message.parts[0].text) else ""
    reply = (
        "Insurance Agent Response:\n"
        "I handle coverage checks, copay explanations, and benefits questions.\n"
        f"Your request: {user_text}"
    )
    return build_text_message(reply)


# ---------------------------------------------------------------------------
# Agent metadata
# ---------------------------------------------------------------------------

def create_agent_card() -> AgentCard:
    return AgentCard(
        name="Insurance Agent",
        description="Provides assistance for insurance coverage and benefits inquiries.",
        version="1.0.0",
        url="http://localhost:8013",
        documentationUrl="https://example.com/docs/insurance",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        provider=AgentProvider(
            organization="Assignment 5",
            url="http://localhost:8013",
        ),
        skills=[
            AgentSkill(
                id="insurance",
                name="Insurance Services",
                description="Supports coverage questions and copay guidance.",
                tags=["insurance", "benefits"],
                inputModes=["text"],
                outputModes=["text"],
                examples=["Check coverage for labs", "What is my copay?", "Explain benefits"],
            )
        ],
        preferredTransport="JSONRPC",
    )


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(title="Insurance Agent Service")
    handler = SimpleAgentRequestHandler(
        agent_id="insurance",
        skill_callback=insurance_skill,
    )
    register_agent_routes(app, create_agent_card(), handler)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8013)
