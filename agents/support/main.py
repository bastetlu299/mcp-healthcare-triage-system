"""
Triage Agent
------------
Provides compassionate, user-facing triage guidance. If the message includes
data context forwarded by the router (e.g., “Data context: ...”), the agent
incorporates it into a more informed response.
"""

from __future__ import annotations

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
# Internal helper functions
# ---------------------------------------------------------------------------

def parse_triage_prompt(text: str) -> tuple[str, str]:
    """
    Extract optional upstream "data context" and the actual patient request.
    Router sends messages formatted like:
        "Data context: ... Now craft guidance..."
    Returns:
        (context_text, user_request)
    """
    if "Data context:" in text:
        parts = text.split("Data context:", 1)
        lead = parts[0].strip()
        context = parts[1].strip()
        request = lead if lead else "your request"
        return context, request

    cleaned = text.strip()
    return "", cleaned or "your request"


def generate_suggestions(user_prompt: str) -> list[str]:
    """
    Produce 2–3 practical next steps based on keywords in the request.
    """
    lower = user_prompt.lower()
    out: list[str] = []

    if any(k in lower for k in ["chest pain", "shortness of breath", "fainting"]):
        out.append("If symptoms are severe or worsening, call emergency services immediately.")
        out.append("Do not drive yourself; ask someone to help or call for transport.")
    elif any(k in lower for k in ["fever", "cough", "sore throat"]):
        out.append("Track your temperature, stay hydrated, and rest.")
        out.append("If fever persists beyond 48 hours or you have breathing issues, seek urgent care.")
    elif any(k in lower for k in ["medication", "refill", "prescription"]):
        out.append("I can log a refill request and confirm the pharmacy details.")
        out.append("Please share the medication name, dose, and preferred pharmacy.")
    elif any(k in lower for k in ["history", "follow", "activity"]):
        out.append("I reviewed your recent encounters and will flag any changes for the clinician.")
        out.append("Let me know if your symptoms changed since the last check-in.")
    else:
        out.append("Share your symptoms, when they started, and any current medications.")
        out.append("We can arrange a follow-up or connect you to a clinician if needed.")

    out.append("If this is urgent, reply here and I’ll prioritize your case.")
    return out


# ---------------------------------------------------------------------------
# Skill implementation
# ---------------------------------------------------------------------------

async def triage_skill(message: Message) -> Message:
    """
    Generate a friendly, end-user-facing triage reply.
    This agent should never reveal internal routing or JSON structures.
    """
    text = message.parts[0].text if (message.parts and message.parts[0].text) else ""
    context_text, request_text = parse_triage_prompt(text)

    # Greeting
    if context_text:
        opening = "Hi there — I reviewed the latest notes in your chart."
    else:
        opening = "Hi there, thanks for reaching out."

    # Small contextual line
    prompt_lower = text.lower()
    if any(k in prompt_lower for k in ["chest pain", "shortness of breath"]):
        context_line = "Chest symptoms can be serious, so I want to make sure you're safe."
    elif any(k in prompt_lower for k in ["fever", "cough", "sore throat"]):
        context_line = "Respiratory symptoms can vary, so I’ll ask a few key questions."
    elif context_text:
        context_line = "I’ve reviewed the recent encounter notes you mentioned."
    else:
        context_line = ""

    # Build suggestions
    steps = generate_suggestions(text)

    response_lines = [
        opening,
        context_line,
        "",
        f"Here’s what I recommend based on {request_text}:",
    ]

    # Include top 3 suggestions
    for s in steps[:3]:
        response_lines.append(f"- {s}")

    response_lines.append(
        "If you'd like me to take action now, just reply to this message and I’ll coordinate next steps."
    )

    final_text = "\n".join(line for line in response_lines if line)
    return build_text_message(final_text)


# ---------------------------------------------------------------------------
# Agent metadata
# ---------------------------------------------------------------------------

def create_agent_card() -> AgentCard:
    return AgentCard(
        name="Triage Agent",
        description="Provides triage guidance and patient-friendly next steps.",
        url="http://localhost:8012",
        version="1.0.0",
        documentationUrl="https://example.com/docs/triage",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        provider=AgentProvider(
            organization="Assignment 5",
            url="http://localhost:8012",
        ),
        skills=[
            AgentSkill(
                id="triage-general",
                name="Triage Guidance",
                description="Handles intake questions and triage guidance for patient symptoms.",
                tags=["triage", "intake", "healthcare"],
                inputModes=["text"],
                outputModes=["text"],
                examples=[
                    "I have a fever and cough",
                    "My chest feels tight after exercise",
                    "Review my recent symptoms",
                ],
            )
        ],
        preferredTransport="JSONRPC",
    )


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(title="Triage Agent Service")
    handler = SimpleAgentRequestHandler(
        agent_id="triage",
        skill_callback=triage_skill,
    )
    register_agent_routes(app, create_agent_card(), handler)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8012)
