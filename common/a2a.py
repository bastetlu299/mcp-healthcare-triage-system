"""
A2A Runtime Utilities
---------------------
This module provides a minimal JSON-RPC execution layer for A2A agents.
It defines:

  - SimpleAgentRequestHandler: in-memory task + message management
  - register_agent_routes: attaches JSON-RPC endpoints to a FastAPI app

Every agent (router, data, triage, insurance) loads this file to expose
a standard RPC surface compliant with the A2A protocol used in Assignment 5.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sdk.types import (
    AgentCard,
    DeleteTaskPushNotificationConfigParams,
    Event,
    GetTaskPushNotificationConfigParams,
    ListTaskPushNotificationConfigParams,
    Message,
    MessageSendParams,
    Role,
    Task,
    TaskIdParams,
    TaskPushNotificationConfig,
    TaskQueryParams,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)


# -----------------------------------------------------------------------------
# JSON-RPC Payload Wrapper
# -----------------------------------------------------------------------------

class RPCRequest(BaseModel):
    """Basic structure of an inbound JSON-RPC request."""
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[str | int] = None


# -----------------------------------------------------------------------------
# Simple In-Memory Agent Runtime
# -----------------------------------------------------------------------------

class SimpleAgentRequestHandler:
    """
    A minimal runtime for A2A agents. Maintains tasks in memory and
    routes incoming RPC calls to the agent's skill callback.
    """

    def __init__(
        self,
        agent_name: str | None = None,
        skill_callback=None,
        *,
        agent_id: str | None = None,
    ):
        if skill_callback is None:
            raise ValueError("skill_callback is required")

        self.agent_name = agent_name or agent_id or "agent"
        self._tasks: Dict[str, Task] = {}
        self._skill = skill_callback

    # -- internal --------------------------------------------------------------

    def _make_ids(self) -> tuple[str, str]:
        """Create a (task_id, context_id) pair."""
        return uuid.uuid4().hex, uuid.uuid4().hex

    # -- RPC method handlers ---------------------------------------------------

    async def on_get_task(self, params: TaskQueryParams) -> Task | None:
        return self._tasks.get(params.id)

    async def on_cancel_task(self, params: TaskIdParams) -> Task | None:
        task = self._tasks.get(params.id)
        if not task:
            return None
        task.status = TaskStatus(state=TaskState.canceled)
        return task

    async def on_message_send(self, params: MessageSendParams) -> Task:
        """
        Synchronous send: receive a Message, run the skill, finalize the task.
        """
        task_id, ctx_id = self._make_ids()

        incoming = params.message
        incoming.taskId = task_id
        incoming.contextId = ctx_id

        reply = await self._skill(incoming)

        status = TaskStatus(state=TaskState.completed, message=reply)
        task = Task(
            id=task_id,
            contextId=ctx_id,
            history=[incoming, reply],
            status=status,
        )
        self._tasks[task_id] = task
        return task

    async def on_message_send_stream(
        self, params: MessageSendParams
    ) -> AsyncGenerator[Event, None]:
        """
        Streaming send: yields a running update and then a final update.
        """
        task_id, ctx_id = self._make_ids()

        incoming = params.message
        incoming.taskId = task_id
        incoming.contextId = ctx_id

        # Yield "running" event
        yield TaskStatusUpdateEvent(
            taskId=task_id,
            contextId=ctx_id,
            status=TaskStatus(state=TaskState.running),
            final=False,
        )

        reply = await self._skill(incoming)

        final_status = TaskStatus(state=TaskState.completed, message=reply)
        task = Task(
            id=task_id,
            contextId=ctx_id,
            history=[incoming, reply],
            status=final_status,
        )
        self._tasks[task_id] = task

        # Yield "completed" event
        yield TaskStatusUpdateEvent(
            taskId=task_id,
            contextId=ctx_id,
            status=final_status,
            final=True,
        )

    # -- Notification config stubs (not required in assignment) ---------------

    async def on_set_task_push_notification_config(
        self, params: TaskPushNotificationConfig
    ) -> TaskPushNotificationConfig:
        return params

    async def on_get_task_push_notification_config(
        self, params: TaskIdParams | GetTaskPushNotificationConfigParams
    ) -> TaskPushNotificationConfig:
        return TaskPushNotificationConfig(task_id=params.id, push_notification_config={})

    async def on_resubscribe_to_task(
        self, params: TaskIdParams
    ) -> AsyncGenerator[Event, None]:
        task = self._tasks.get(params.id)
        if task:
            yield TaskStatusUpdateEvent(
                taskId=task.id,
                contextId=task.contextId,
                status=task.status,
                final=True,
            )

    async def on_list_task_push_notification_config(
        self, params: ListTaskPushNotificationConfigParams
    ) -> List[TaskPushNotificationConfig]:
        return []

    async def on_delete_task_push_notification_config(
        self, params: DeleteTaskPushNotificationConfigParams
    ) -> None:
        return None


# -----------------------------------------------------------------------------
# FastAPI Route Registration
# -----------------------------------------------------------------------------

def register_agent_routes(
    app: FastAPI,
    agent_card: AgentCard,
    handler: SimpleAgentRequestHandler,
) -> None:
    """
    Register JSON-RPC endpoints + agent metadata routes for any A2A agent.
    """

    @app.get("/.well-known/agent-card.json")
    async def get_agent_card():
        return agent_card.model_dump()

    @app.post("/rpc")
    async def rpc_gateway(request: RPCRequest):
        params = request.params or {}

        if request.method == "message/send":
            result = await handler.on_message_send(
                MessageSendParams(**params)
            )

        elif request.method == "message/send_stream":
            send_params = MessageSendParams(**params)

            async def stream():
                async for event in handler.on_message_send_stream(send_params):
                    yield json.dumps(event.model_dump()) + "\n"

            return StreamingResponse(stream(), media_type="application/json")

        elif request.method == "task/get":
            result = await handler.on_get_task(TaskQueryParams(**params))
            if result is None:
                raise HTTPException(status_code=404, detail="Task not found")

        elif request.method == "task/cancel":
            result = await handler.on_cancel_task(TaskIdParams(**params))
            if result is None:
                raise HTTPException(status_code=404, detail="Task not found")

        else:
            raise HTTPException(status_code=404, detail="Unknown method")

        return {"jsonrpc": "2.0", "id": request.id, "result": result.model_dump()}

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}
