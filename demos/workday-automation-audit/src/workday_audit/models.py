"""Validated records. A bad tool name or a sent draft does not get through."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Tool = Literal["n8n", "make", "claude_step", "spreadsheet", "dont_automate"]


class TaskRecord(BaseModel):
    id: str
    summary: str
    frequency_per_month: float = Field(ge=0)
    minutes_per_run: float = Field(ge=0)
    tools: list[str]
    customer_facing: bool
    evidence: list[str]
    provisional: bool = False


class Recommendation(TaskRecord):
    work_type: str
    tool: Tool
    reason: str
    requires_approval: bool


class InquiryFields(BaseModel):
    category: str
    urgency: Literal["high", "normal"]
    service: str
    draft_subject: str
    draft_body: str

    def awaiting_approval(self) -> bool:
        return "not sent" in self.draft_body.lower()
