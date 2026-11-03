"""Real OpenAI tool calling. Not used unless OPENAI_API_KEY is set."""

from __future__ import annotations

import json
import os

from src.paths import price_config
from src.tools import openai_tools


def live_step(messages: list[dict]) -> dict:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    from openai import OpenAI

    client = OpenAI(api_key=key)
    response = client.chat.completions.create(
        model=price_config()["profiles"]["llm_agent"]["model"],
        messages=_to_openai(messages),
        tools=openai_tools(),
        temperature=0,
    )
    message = response.choices[0].message
    if message.tool_calls:
        call = message.tool_calls[0]
        return {
            "type": "tool",
            "name": call.function.name,
            "arguments": json.loads(call.function.arguments or "{}"),
        }
    return {"type": "message", "content": message.content or ""}


def _to_openai(messages: list[dict]) -> list[dict]:
    converted = [
        {
            "role": "system",
            "content": (
                "You are the Pebblecart support assistant. Use the tools. "
                "Never invent an order. If a refund is not eligible, or the amount is "
                "above the cap the policy returns, call escalate_to_human and do not call issue_refund."
            ),
        }
    ]
    for message in messages:
        if message["role"] == "user":
            converted.append({"role": "user", "content": message["content"]})
        elif message["role"] == "assistant" and message.get("tool_calls"):
            call = message["tool_calls"][0]
            converted.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call_{call['name']}",
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call["arguments"]),
                            },
                        }
                    ],
                }
            )
        elif message["role"] == "tool":
            converted.append(
                {
                    "role": "tool",
                    "tool_call_id": f"call_{message['name']}",
                    "content": json.dumps(message["result"].get("output") or {"error": message["result"].get("error")}),
                }
            )
        elif message["role"] == "assistant":
            converted.append({"role": "assistant", "content": message.get("content") or ""})
    return converted
