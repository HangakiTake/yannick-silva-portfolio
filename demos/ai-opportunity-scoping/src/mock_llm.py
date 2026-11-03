"""Deterministic stand-in for the tool-calling model.

It is not a language model. It reads the user text, calls the same tools a
model would, and obeys the policy result from the API. Live mode is separate
and only runs when OPENAI_API_KEY is set.
"""

from __future__ import annotations

import re
from decimal import Decimal

_REASONS = (
    ("not as described", "not_as_described"),
    ("changed my mind", "changed_mind"),
    ("changed mind", "changed_mind"),
    ("wrong item", "wrong_item"),
    (r"\blate\b", "late_delivery"),
    ("damaged", "damaged"),
    ("broken", "damaged"),
)


def _users(messages: list[dict]) -> str:
    return "\n".join(message["content"] for message in messages if message["role"] == "user")


def _last_user(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message["role"] == "user":
            return message["content"]
    return ""


def _last_result(messages: list[dict], name: str) -> dict | None:
    found = None
    for message in messages:
        if message.get("role") == "tool" and message.get("name") == name:
            found = message["result"]
    return found


def _order_id(text: str) -> str | None:
    match = re.search(r"\bpbl[\s-]?\d{4,}\b", text, re.I)
    if not match:
        return None
    digits = re.search(r"\d{4,}", match.group(0)).group(0)
    return f"PBL-{digits}"


def _amount(text: str) -> Decimal | None:
    found = re.findall(r"\$\s*(\d+(?:\.\d+)?)", text)
    if not found:
        return None
    return Decimal(found[-1])


def _reason(text: str) -> str | None:
    lowered = text.lower()
    for needle, code in _REASONS:
        if needle.startswith("\\"):
            if re.search(needle, lowered):
                return code
        elif needle in lowered:
            return code
    return None


def _priority(text: str) -> str:
    lowered = text.lower()
    if re.search(r"priority\s+high|high priority", lowered):
        return "high"
    if re.search(r"priority\s+low|low priority", lowered):
        return "low"
    return "normal"


def _tool(name: str, arguments: dict) -> dict:
    return {"type": "tool", "name": name, "arguments": arguments}


def _say(content: str) -> dict:
    return {"type": "message", "content": content}


def step(messages: list[dict]) -> dict:
    text = _users(messages)
    lowered = text.lower()
    order_id = _order_id(text)
    refund = bool(re.search(r"\b(refund|money back)\b", lowered))
    ticket = "open a ticket" in lowered or "open a case" in lowered
    human = bool(re.search(r"\b(human|escalate)\b", lowered)) and not refund
    status = bool(re.search(r"\b(where|status|track)\b", lowered)) and not refund and not ticket

    if refund:
        return _refund(messages, text, order_id)
    if ticket:
        return _ticket(messages, text, order_id)
    if human:
        return _human(messages, order_id)
    if status:
        return _status(messages, order_id)
    return _say("I can look up an order, check a refund, or open a ticket. I need an order id like PBL-1001.")


def _refund(messages: list[dict], text: str, order_id: str | None) -> dict:
    if not order_id:
        return _say("I need the order id. It looks like PBL- and at least four digits.")
    lookup = _last_result(messages, "lookup_order")
    if lookup is None:
        return _tool("lookup_order", {"order_id": order_id})
    if lookup.get("status") != "ok":
        return _say("The order system did not answer. I did not change anything.")
    output = lookup.get("output") or {}
    if not output.get("found"):
        if _last_result(messages, "escalate_to_human"):
            return _say("I did not issue a refund. A person has this case.")
        return _tool(
            "escalate_to_human",
            {"order_id": order_id, "reason": "order not found"},
        )
    reason = _reason(text)
    if not reason:
        return _say("What is the reason: damaged, wrong item, not as described, late delivery, or changed mind?")
    policy = _last_result(messages, "check_refund_policy")
    if policy is None:
        return _tool("check_refund_policy", {"order_id": order_id, "reason": reason})
    if policy.get("status") != "ok":
        return _say("The order system did not answer. I did not change anything.")
    if _last_result(messages, "issue_refund") or _last_result(messages, "escalate_to_human"):
        issued = _last_result(messages, "issue_refund")
        if issued and issued.get("status") == "ok":
            return _say("I issued the refund.")
        return _say("I did not issue a refund. A person has this case.")
    body = policy.get("output") or {}
    total = Decimal(str(output.get("total_usd") or "0"))
    explicit = _amount(text)
    requested = explicit if explicit is not None else total
    cap = Decimal(str(body.get("max_auto_refund_usd") or "0"))
    if body.get("eligible") and requested <= cap:
        return _tool(
            "issue_refund",
            {"order_id": order_id, "amount_usd": requested, "reason": reason},
        )
    if body.get("eligible"):
        why = f"Above the automatic cap for this order ({cap} USD)."
    else:
        why = str(body.get("detail") or "Out of policy.")
    return _tool(
        "escalate_to_human",
        {"order_id": order_id, "reason": why, "requested_amount_usd": requested},
    )


def _status(messages: list[dict], order_id: str | None) -> dict:
    if not order_id:
        return _say("I need the order id. It looks like PBL- and at least four digits.")
    lookup = _last_result(messages, "lookup_order")
    if lookup is None:
        return _tool("lookup_order", {"order_id": order_id})
    if lookup.get("status") != "ok":
        return _say("The order system did not answer. I did not change anything.")
    output = lookup.get("output") or {}
    if not output.get("found"):
        return _say(f"I could not find order {order_id}.")
    return _say(f"Order {order_id} is {output.get('status')}.")


def _ticket(messages: list[dict], text: str, order_id: str | None) -> dict:
    if not order_id:
        return _say("I need the order id. It looks like PBL- and at least four digits.")
    opened = _last_result(messages, "open_ticket")
    if opened:
        if opened.get("status") == "ok":
            return _say("I opened a ticket.")
        return _say("I could not open the ticket.")
    return _tool(
        "open_ticket",
        {"order_id": order_id, "summary": text.strip()[:500], "priority": _priority(text)},
    )


def _human(messages: list[dict], order_id: str | None) -> dict:
    if not order_id:
        return _say("I need the order id. It looks like PBL- and at least four digits.")
    if _last_result(messages, "escalate_to_human"):
        return _say("I did not issue a refund. A person has this case.")
    return _tool(
        "escalate_to_human",
        {"order_id": order_id, "reason": _last_user(messages).strip()[:500]},
    )
