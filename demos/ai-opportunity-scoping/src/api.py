"""Fake Pebblecart REST API. Orders, refund policy, tickets, escalations."""

from __future__ import annotations

import copy
import json
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Request

from src.paths import ROOT, refund_policy
from src.policy import assess, refund_allowed
from src.tools import normalize_order_id

app = FastAPI(title="Pebblecart demo API", version="0.1.0")
_STORE: dict = {}


def reset_store() -> None:
    global _STORE
    payload = json.loads((ROOT / "data" / "orders.json").read_text(encoding="utf-8"))
    _STORE = {
        "orders": {order["order_id"]: copy.deepcopy(order) for order in payload["orders"]},
        "refunds": [],
        "tickets": [],
        "escalations": [],
    }


def _as_decimal(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    return None


def _money(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _order_public(order: dict) -> dict:
    return {
        "found": True,
        "order_id": order["order_id"],
        "customer_name": order["customer_name"],
        "email": order["email"],
        "status": order["status"],
        "item_type": order["item_type"],
        "item_name": order["item_name"],
        "total_usd": _money(Decimal(str(order["total_usd"]))),
        "delivered_on": order["delivered_on"],
        "tracking": order["tracking"],
    }


@app.get("/health")
def health() -> dict:
    return {"ok": True, "company": "Pebblecart"}


@app.get("/orders/{order_id}")
def lookup_order(order_id: str) -> dict:
    canonical = normalize_order_id(order_id)
    if not canonical:
        raise HTTPException(status_code=400, detail="order_id is required and must be a string like PBL-1001")
    order = _STORE["orders"].get(canonical)
    if not order:
        return {"found": False, "order_id": canonical}
    return _order_public(order)


@app.get("/orders/{order_id}/refund-policy")
def check_policy(order_id: str, reason: str) -> dict:
    canonical = normalize_order_id(order_id)
    if not canonical:
        raise HTTPException(status_code=400, detail="order_id is required and must be a string like PBL-1001")
    if reason not in refund_policy()["allowed_reasons"]:
        raise HTTPException(status_code=400, detail=f"reason must be one of: {', '.join(refund_policy()['allowed_reasons'])}")
    result = assess(_STORE["orders"].get(canonical), reason)
    return {
        "order_id": canonical,
        "reason": reason,
        "eligible": result["eligible"],
        "max_auto_refund_usd": _money(result["max_auto_refund_usd"]),
        "order_total_usd": _money(result["order_total_usd"]),
        "days_since_delivery": result["days_since_delivery"],
        "detail": result["detail"],
    }


@app.post("/refunds")
async def issue_refund(request: Request) -> dict:
    payload = json.loads(await request.body(), parse_float=Decimal)
    order_id = payload.get("order_id")
    reason = payload.get("reason")
    amount = _as_decimal(payload.get("amount_usd"))
    canonical = normalize_order_id(order_id) if isinstance(order_id, str) else None
    if not canonical:
        raise HTTPException(status_code=400, detail="order_id is required and must be a string like PBL-1001")
    if reason not in refund_policy()["allowed_reasons"]:
        raise HTTPException(status_code=400, detail="reason must be one of the policy reasons")
    if amount is None or amount <= 0:
        raise HTTPException(status_code=400, detail="amount_usd must be a number greater than 0")
    order = _STORE["orders"].get(canonical)
    assessment = assess(order, reason)
    allowed, detail = refund_allowed(assessment, amount)
    if not allowed or order is None:
        raise HTTPException(status_code=409, detail=f"not executed: {detail}")
    order["status"] = "refunded"
    record = {
        "order_id": canonical,
        "amount_usd": _money(amount),
        "reason": reason,
        "executed": True,
    }
    _STORE["refunds"].append(record)
    return record


@app.post("/tickets")
async def open_ticket(request: Request) -> dict:
    payload = json.loads(await request.body())
    order_id = normalize_order_id(payload.get("order_id", "")) if isinstance(payload.get("order_id"), str) else None
    summary = str(payload.get("summary") or "").strip()
    priority = str(payload.get("priority") or "").lower()
    if not order_id:
        raise HTTPException(status_code=400, detail="order_id is required and must be a string like PBL-1001")
    if not summary or len(summary) > 500:
        raise HTTPException(status_code=400, detail="summary is required and must be 500 characters or fewer")
    if priority not in {"low", "normal", "high"}:
        raise HTTPException(status_code=400, detail="priority must be one of: low, normal, high")
    record = {"order_id": order_id, "summary": summary, "priority": priority}
    _STORE["tickets"].append(record)
    return record


@app.post("/escalations")
async def escalate(request: Request) -> dict:
    payload = json.loads(await request.body(), parse_float=Decimal)
    order_id = normalize_order_id(payload.get("order_id", "")) if isinstance(payload.get("order_id"), str) else None
    reason = str(payload.get("reason") or "").strip()
    if not order_id:
        raise HTTPException(status_code=400, detail="order_id is required and must be a string like PBL-1001")
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")
    record = {
        "order_id": order_id,
        "reason": reason,
        "requested_amount_usd": _money(_as_decimal(payload.get("requested_amount_usd"))),
        "executed_refund": False,
    }
    _STORE["escalations"].append(record)
    return record


@app.get("/refunds")
def list_refunds() -> dict:
    return {"refunds": list(_STORE["refunds"])}


@app.get("/tickets")
def list_tickets() -> dict:
    return {"tickets": list(_STORE["tickets"])}


@app.get("/escalations")
def list_escalations() -> dict:
    return {"escalations": list(_STORE["escalations"])}


reset_store()
