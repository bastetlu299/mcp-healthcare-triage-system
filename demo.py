import asyncio
import os

import httpx

from sdk.types import Message, MessageSendParams, Role
from shared.message_utils import build_text_message

ROUTER_RPC = os.getenv("ROUTER_RPC", "http://localhost:8010/rpc")


def build_request(prompt: str) -> dict:
    base_message = build_text_message(prompt, role=Role.user)
    params = MessageSendParams(
        message=Message(messageId=base_message.messageId, role=Role.user, parts=base_message.parts)
    )
    return {"jsonrpc": "2.0", "id": "demo", "method": "message/send", "params": params.model_dump()}


def print_response(prompt: str, result: dict | None) -> None:
    print(f"=== Prompt: {prompt} ===")
    if not result:
        print("No result returned")
    else:
        print("Router task result:", result)
    print()


async def main():
    prompts = [
        "Patient 1 coverage summary and copay guidance",
        "Patient 2 has a fever and cough, what should triage do?",
        "Patient history then triage guidance",
        "Open a new urgent case for patient 3 about chest tightness",
        "List recent urgent patients and suggest a follow-up action",
    ]

    async with httpx.AsyncClient() as client:
        for prompt in prompts:
            request_body = build_request(prompt)
            response = await client.post(ROUTER_RPC, json=request_body)
            response.raise_for_status()
            result = response.json().get("result")
            print_response(prompt, result)


if __name__ == "__main__":
    asyncio.run(main())
