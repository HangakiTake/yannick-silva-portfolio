"""Refund rules for the fictional shop. The API and the tests both call this."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from src.paths import refund_policy


def as_of_date(policy: dict | None = None) -> date:
    policy = policy or refund_policy()
    return datetime.strptime(policy["as_of"], "%Y-%m-%d").date()


def assess(order: dict | None, reason: str, policy: dict | None = None) -> dict:
    policy = policy or refund_policy()
    clock = as_of_date(policy)
    if order is None:
        return {
            "eligible": False,
            "max_auto_refund_usd": Decimal("0"),
            "order_total_usd": None,
            "days_since_delivery": None,
            "detail": "Order not found.",
        }
    total = Decimal(str(order["total_usd"]))
    status = order["status"]
    if status == "refunded":
        return _no(total, None, "The order is already refunded.")
    if status == "cancelled":
        return _no(total, None, "The order is cancelled.")
    if status != "delivered":
        return _no(total, None, f"The order is not delivered (status {status}).")
    if order["item_type"] in policy["blocked_item_types"]:
        return _no(total, None, f"This item cannot be refunded ({order['item_type']}).")
    delivered = datetime.strptime(order["delivered_on"], "%Y-%m-%d").date()
    days = (clock - delivered).days
    if days < 0:
        return _no(total, days, "The delivery date is after the demo clock.")
    if reason == "changed_mind" and days > int(policy["changed_mind_days"]):
        return _no(
            total,
            days,
            f"Outside the changed-mind window ({days} days, limit {policy['changed_mind_days']}).",
        )
    if days > int(policy["window_days"]):
        return _no(total, days, f"Outside the refund window ({days} days, limit {policy['window_days']}).")
    if reason not in policy["allowed_reasons"]:
        return _no(total, days, "That reason is not in the refund policy.")
    cap = min(Decimal(str(policy["max_auto_refund_usd"])), total)
    return {
        "eligible": True,
        "max_auto_refund_usd": cap,
        "order_total_usd": total,
        "days_since_delivery": days,
        "detail": f"Eligible up to {cap} USD.",
    }


def _no(total: Decimal, days: int | None, detail: str) -> dict:
    return {
        "eligible": False,
        "max_auto_refund_usd": Decimal("0"),
        "order_total_usd": total,
        "days_since_delivery": days,
        "detail": detail,
    }


def refund_allowed(assessment: dict, amount: Decimal) -> tuple[bool, str]:
    if not assessment["eligible"]:
        return False, assessment["detail"]
    cap = Decimal(assessment["max_auto_refund_usd"])
    total = Decimal(assessment["order_total_usd"])
    if amount > cap:
        return False, f"Above the automatic cap for this order ({cap} USD)."
    if amount > total:
        return False, "Above the amount the customer paid."
    if amount <= 0:
        return False, "Amount must be greater than 0."
    return True, assessment["detail"]
