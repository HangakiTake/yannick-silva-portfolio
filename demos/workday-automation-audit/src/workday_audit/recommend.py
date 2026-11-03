"""Pick one tool for a task. First matching rule wins. The rules are the policy."""

from __future__ import annotations

import re

from .normalize import normalize

# Order matters. A later rule does not override an earlier one.
RULES: list[tuple[str, re.Pattern[str], str, str]] = [
    (
        "tax_or_filing",
        re.compile(r"sales tax|1099|sign off|tax return"),
        "dont_automate",
        "Filing or sign-off stays with a person. A wrong return is your name on it.",
    ),
    (
        "judgment_review",
        re.compile(r"look at each|uncleared|use my judgment"),
        "dont_automate",
        "Each item needs a human look. Automating the decision would hide exceptions.",
    ),
    (
        "relationship",
        re.compile(r"who i should call|i pick who|client calls"),
        "dont_automate",
        "Who to call, and how, depends on the relationship. A schedule bot would guess.",
    ),
    (
        "multi_step",
        re.compile(
            r"missing receipt|unpaid invoice|appointment reminder|did you get|proposal|"
            r"checklist email|client report|vendor bill|rename pdf|inquiry"
        ),
        "n8n",
        "Several steps, or a message a customer will see. n8n can redact, call Claude, write the sheet, and wait for approval before anything is sent.",
    ),
    (
        "simple_sync",
        re.compile(r"new leads|daily sales|pos email|back up|backup|whatsapp"),
        "make",
        "Two apps, no branch, and nothing is sent to a customer. Make is the smaller tool for that.",
    ),
    (
        "text_read",
        re.compile(r"receipt|voicemail|transcribe|from photos"),
        "claude_step",
        "The hard part is reading messy text. A Claude step can propose a category or a transcript. You still post it.",
    ),
    (
        "text_draft",
        re.compile(r"invoice wording|wording on the invoice|invoice description"),
        "claude_step",
        "The hard part is the wording. Claude drafts it. You paste it onto the invoice after you read it.",
    ),
    (
        "sheet_calc",
        re.compile(
            r"reconcil|mileage|cashflow|cash flow|payout|time sheet|log my hours|"
            r"duplicate client|pricing sheet|recurring invoice"
        ),
        "spreadsheet",
        "The work is matching or totalling inside a sheet. A formula or a template does it without another subscription.",
    ),
]
_DEFAULT = (
    "multi_step",
    "n8n",
    "This does not fit a formula or a two-app sync. An n8n workflow can hold the steps and stop for a person where it should.",
)


def recommend_task(task: dict) -> dict:
    blob = normalize(" ".join(task.get("evidence") or [task.get("summary", "")]))
    work_type, tool, reason = _DEFAULT
    for name, pattern, picked, why in RULES:
        if pattern.search(blob):
            work_type, tool, reason = name, picked, why
            break
    customer = bool(task.get("customer_facing"))
    needs_approval = customer and tool != "dont_automate"
    if needs_approval:
        reason = reason + " Anything the customer would see waits for approval. The runner never sends it."
    return {
        **task,
        "work_type": work_type,
        "tool": tool,
        "reason": reason,
        "requires_approval": needs_approval,
    }


def recommend(tasks: list[dict]) -> list[dict]:
    return [recommend_task(task) for task in tasks]
