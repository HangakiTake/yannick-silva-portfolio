"""Tool-calling support agent. Mock mode is the default. Live mode needs a key."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from src.api import app as fastapi_app
from src.live import live_step
from src.mock_llm import step as mock_step
from src.tools import ToolRunner


class Agent:
    def __init__(self, runner: ToolRunner, mode: str = "mock"):
        self.runner = runner
        self.mode = mode

    def run(self, conversation_id: str, turns: list[str]) -> dict:
        messages: list[dict] = []
        per_turn: list[list[dict]] = []
        calls: list[dict] = []
        for turn in turns:
            messages.append({"role": "user", "content": turn})
            turn_calls: list[dict] = []
            for _ in range(8):
                if self.mode == "live":
                    nxt = live_step(messages)
                elif self.mode == "mock":
                    nxt = mock_step(messages)
                else:
                    raise RuntimeError(f"unknown mode: {self.mode}")
                if nxt["type"] == "message":
                    messages.append({"role": "assistant", "content": nxt["content"]})
                    break
                result = self.runner.call(nxt["name"], nxt["arguments"], conversation_id)
                record = {
                    "name": nxt["name"],
                    "arguments": result["arguments"],
                    "status": result["status"],
                    "error": result["error"],
                }
                calls.append(record)
                turn_calls.append(record)
                messages.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{"name": nxt["name"], "arguments": result["arguments"]}],
                    }
                )
                messages.append({"role": "tool", "name": nxt["name"], "result": result})
            else:
                raise RuntimeError(f"{conversation_id} did not finish within 8 tool rounds")
            per_turn.append(turn_calls)
        reply = ""
        for message in reversed(messages):
            if message["role"] == "assistant" and message.get("content"):
                reply = message["content"]
                break
        return {"calls": calls, "per_turn": per_turn, "reply": reply, "messages": messages}


def make_agent(log_path, mode: str | None = None, base_url: str | None = None) -> Agent:
    resolved = mode or ("live" if os.environ.get("OPENAI_API_KEY") else "mock")
    if base_url:
        import httpx

        client = httpx.Client(base_url=base_url)
    else:
        client = TestClient(fastapi_app)
    return Agent(ToolRunner(client, log_path), mode=resolved)
