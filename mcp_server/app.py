# ============================================================================
#  Minimal MCP-Compatible Server for Healthcare Triage
#  Rewritten version for clarity, maintainability, and uniqueness
# ============================================================================

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# database access layer (unchanged API)
from mcp_server.database import (
    fetch_patient,
    fetch_patients,
    update_patient_record,
    create_case_record,
    fetch_history,
)

# ----------------------------------------------------------------------------
#  Application Setup
# ----------------------------------------------------------------------------

app = FastAPI(
    title="Healthcare Triage MCP Server",
    version="1.0.0"
)

# A central queue for SSE events (audit logs, updates, etc.)
event_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()


# ----------------------------------------------------------------------------
#  Pydantic Models
# ----------------------------------------------------------------------------

class ToolInvocation(BaseModel):
    """
    Represents a request to invoke a tool via /tools/call.
    """
    name: str
    arguments: Dict[str, Any]


# ----------------------------------------------------------------------------
#  Tool Metadata (returned by /tools/list)
# ----------------------------------------------------------------------------

TOOL_REGISTRY: List[Dict[str, Any]] = [
    {
        "name": "get_patient",
        "description": "Retrieve a single patient using their ID.",
        "input_schema": {
            "type": "object",
            "properties": {"patient_id": {"type": "integer"}},
            "required": ["patient_id"],
        },
    },
    {
        "name": "list_patients",
        "description": "Return a list of patients, optionally filtered by status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "update_patient",
        "description": "Modify patient fields such as name, date of birth, or status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "integer"},
                "data": {"type": "object"},
            },
            "required": ["patient_id", "data"],
        },
    },
    {
        "name": "create_case",
        "description": "Open a new triage case for a patient.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "integer"},
                "complaint": {"type": "string"},
                "urgency": {"type": "string"},
            },
            "required": ["patient_id", "complaint", "urgency"],
        },
    },
    {
        "name": "get_patient_history",
        "description": "Retrieve the encounter history for a patient.",
        "input_schema": {
            "type": "object",
            "properties": {"patient_id": {"type": "integer"}},
            "required": ["patient_id"],
        },
    },
]


# ----------------------------------------------------------------------------
#  Utility Helpers
# ----------------------------------------------------------------------------

async def enqueue_event(payload: Dict[str, Any]) -> None:
    """
    Add an event to the SSE queue for asynchronous streaming.
    """
    await event_queue.put(payload)


def http_not_found(message: str):
    raise HTTPException(status_code=404, detail=message)


# ----------------------------------------------------------------------------
#  Routes
# ----------------------------------------------------------------------------

@app.post("/tools/list")
async def list_tools() -> Dict[str, Any]:
    """
    Return the list of all tool definitions.
    """
    return {"tools": TOOL_REGISTRY}


@app.post("/tools/call")
async def call_tool(request: ToolInvocation) -> Dict[str, Any]:
    """
    Execute a specific tool by name.
    """

    tool = request.name
    args = request.arguments

    # --- get_patient ---------------------------------------------------------
    if tool == "get_patient":
        patient_id = int(args.get("patient_id"))
        patient = await asyncio.to_thread(fetch_patient, patient_id)

        if not patient:
            http_not_found("Patient does not exist")

        await enqueue_event({
            "type": "audit",
            "tool": tool,
            "patient_id": patient["id"]
        })
        return {"result": patient}

    # --- list_patients -------------------------------------------------------
    if tool == "list_patients":
        status = args.get("status")
        limit = int(args.get("limit", 20))

        records = await asyncio.to_thread(fetch_patients, status, limit)

        await enqueue_event({
            "type": "audit",
            "tool": tool,
            "count": len(records)
        })
        return {"result": records}

    # --- update_patient ------------------------------------------------------
    if tool == "update_patient":
        pid = int(args.get("patient_id"))
        patch = args.get("data") or {}

        updated = await asyncio.to_thread(update_patient_record, pid, patch)

        if not updated:
            http_not_found("Patient not found for update")

        await enqueue_event({
            "type": "update",
            "tool": tool,
            "patient_id": updated["id"]
        })
        return {"result": updated}

    # --- create_case --------------------------------------------------------
    if tool == "create_case":
        pid = int(args.get("patient_id"))
        complaint = str(args.get("complaint"))
        urgency = str(args.get("urgency"))

        case = await asyncio.to_thread(create_case_record, pid, complaint, urgency)

        await enqueue_event({
            "type": "case",
            "tool": tool,
            "case_id": case["id"]
        })
        return {"result": case}

    # --- get_patient_history -------------------------------------------------
    if tool == "get_patient_history":
        pid = int(args.get("patient_id"))
        history = await asyncio.to_thread(fetch_history, pid)

        await enqueue_event({
            "type": "history",
            "tool": tool,
            "count": len(history)
        })
        return {"result": history}

    # unknown tool
    http_not_found(f"Unknown tool: {tool}")


@app.get("/events/stream")
async def stream_events():
    """
    SSE endpoint that streams queued events to any client.
    """

    async def generator():
        while True:
            event = await event_queue.get()
            yield {"event": "update", "data": event}

    return EventSourceResponse(generator())


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Simple liveness probe.
    """
    return {"status": "ok"}


# ----------------------------------------------------------------------------
#  Application Entrypoint
# ----------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000
    )
