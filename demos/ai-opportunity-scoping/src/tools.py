"""Tool argument checks (Pydantic) and the HTTP calls those tools make."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from src.paths import refund_policy, tool_schema

REASONS = tuple(refund_policy()["allowed_reasons"])
PRIORITIES = ("low", "normal", "high")
_ORDER = re.compile(r"PBL-?(\d{4,})\Z")


def normalize_order_id(value: str) -> str | None:
    compact = re.sub(r"\s+", "", value.strip().upper())
    match = _ORDER.fullmatch(compact)
    if not match:
        return None
    return f"PBL-{match.group(1)}"


def _amount(value: object, allow_zero: bool = False) -> Decimal:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        raise ValueError("must be a number greater than 0, with at most 2 decimal places")
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, float):
        amount = Decimal(str(value))
    else:
        raise ValueError("must be a number greater than 0, with at most 2 decimal places")
    exponent = amount.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ValueError("must be a number greater than 0, with at most 2 decimal places")
    if amount < 0 or (amount == 0 and not allow_zero):
        raise ValueError("must be a number greater than 0, with at most 2 decimal places")
    ceiling = Decimal(str(refund_policy()["hard_ceiling_usd"]))
    if amount > ceiling:
        raise ValueError(f"is above {ceiling} and was not executed")
    return amount


def _order(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("is required and must be a string like PBL-1001")
    canonical = normalize_order_id(value)
    if not canonical:
        raise ValueError("is required and must be a string like PBL-1001")
    return canonical


def _enum(value: object, allowed: tuple[str, ...], label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"must be one of: {', '.join(allowed)}")
    canonical = value.strip().lower()
    if canonical not in allowed:
        raise ValueError(f"must be one of: {', '.join(allowed)}")
    return canonical


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError("is required")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("is required")
    if len(cleaned) > 500:
        raise ValueError("must be 500 characters or fewer")
    return cleaned


class LookupOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str

    @field_validator("order_id", mode="before")
    @classmethod
    def check(cls, value: object) -> str:
        return _order(value)


class CheckRefund(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str
    reason: str

    @field_validator("order_id", mode="before")
    @classmethod
    def check_order(cls, value: object) -> str:
        return _order(value)

    @field_validator("reason", mode="before")
    @classmethod
    def check_reason(cls, value: object) -> str:
        return _enum(value, REASONS, "reason")


class IssueRefund(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str
    amount_usd: Decimal
    reason: str

    @field_validator("order_id", mode="before")
    @classmethod
    def check_order(cls, value: object) -> str:
        return _order(value)

    @field_validator("amount_usd", mode="before")
    @classmethod
    def check_amount(cls, value: object) -> Decimal:
        return _amount(value)

    @field_validator("reason", mode="before")
    @classmethod
    def check_reason(cls, value: object) -> str:
        return _enum(value, REASONS, "reason")


class OpenTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str
    summary: str
    priority: str

    @field_validator("order_id", mode="before")
    @classmethod
    def check_order(cls, value: object) -> str:
        return _order(value)

    @field_validator("summary", mode="before")
    @classmethod
    def check_summary(cls, value: object) -> str:
        return _text(value, "summary")

    @field_validator("priority", mode="before")
    @classmethod
    def check_priority(cls, value: object) -> str:
        return _enum(value, PRIORITIES, "priority")


class Escalate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str
    reason: str
    requested_amount_usd: Decimal | None = None

    @field_validator("order_id", mode="before")
    @classmethod
    def check_order(cls, value: object) -> str:
        return _order(value)

    @field_validator("reason", mode="before")
    @classmethod
    def check_reason(cls, value: object) -> str:
        return _text(value, "reason")

    @field_validator("requested_amount_usd", mode="before")
    @classmethod
    def check_amount(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return _amount(value, allow_zero=True)


MODELS = {
    "lookup_order": LookupOrder,
    "check_refund_policy": CheckRefund,
    "issue_refund": IssueRefund,
    "open_ticket": OpenTicket,
    "escalate_to_human": Escalate,
}


def openai_tools() -> list[dict]:
    tools = []
    for tool in tool_schema()["tools"]:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
        )
    return tools


def format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(item) for item in err["loc"]) or "arguments"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)


def validate_call(name: str, arguments: object) -> BaseModel:
    if name not in MODELS:
        raise ValueError(f"unknown tool: {name}")
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    try:
        return MODELS[name].model_validate(arguments)
    except ValidationError as exc:
        raise ValueError(format_validation_error(exc)) from exc


def _json_ready(value: object) -> object:
    if isinstance(value, Decimal):
        rendered = format(value, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return json.loads(rendered)
    return value


class ToolRunner:
    def __init__(self, client, log_path: Path | None, conversation_id: str = ""):
        self.client = client
        self.log_path = log_path
        self.conversation_id = conversation_id
        self.http_calls = 0

    def call(self, name: str, arguments: object, conversation_id: str | None = None) -> dict:
        cid = conversation_id or self.conversation_id
        try:
            model = validate_call(name, arguments)
        except ValueError as exc:
            result = {
                "status": "rejected",
                "arguments": arguments if isinstance(arguments, dict) else {},
                "output": None,
                "error": str(exc),
            }
            self._log(cid, name, result["arguments"], "rejected", str(exc))
            return result
        dumped = model.model_dump()
        try:
            output, status = self._dispatch(name, dumped)
        except Exception as exc:  # the HTTP client raises for 409
            detail = _http_detail(exc)
            status = "not_executed" if isinstance(exc, _Conflict) or _status_code(exc) == 409 else "error"
            result = {"status": status, "arguments": _plain(dumped), "output": None, "error": detail}
            self._log(cid, name, result["arguments"], status, detail)
            return result
        result = {"status": status, "arguments": _plain(dumped), "output": output, "error": None}
        self._log(cid, name, result["arguments"], status, output.get("detail") if isinstance(output, dict) else "ok")
        return result

    def _dispatch(self, name: str, args: dict) -> tuple[dict, str]:
        self.http_calls += 1
        if name == "lookup_order":
            response = self.client.get(f"/orders/{args['order_id']}")
            response.raise_for_status()
            return response.json(), "ok"
        if name == "check_refund_policy":
            response = self.client.get(
                f"/orders/{args['order_id']}/refund-policy",
                params={"reason": args["reason"]},
            )
            response.raise_for_status()
            return response.json(), "ok"
        if name == "issue_refund":
            response = self.client.post("/refunds", content=_body(args), headers={"content-type": "application/json"})
            if response.status_code == 409:
                detail = response.json().get("detail", "not executed")
                raise _Conflict(detail)
            response.raise_for_status()
            return response.json(), "ok"
        if name == "open_ticket":
            response = self.client.post("/tickets", json=args)
            response.raise_for_status()
            return response.json(), "ok"
        if name == "escalate_to_human":
            response = self.client.post(
                "/escalations", content=_body(args), headers={"content-type": "application/json"}
            )
            response.raise_for_status()
            return response.json(), "ok"
        raise ValueError(f"unknown tool: {name}")

    def _log(self, conversation_id: str, name: str, arguments: dict, status: str, detail: object) -> None:
        if self.log_path is None:
            return
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "conversation_id": conversation_id,
            "tool": name,
            "arguments": arguments,
            "status": status,
            "detail": _scrub(detail),
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")


class _Conflict(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def _body(args: dict) -> bytes:
    payload = {key: _json_ready(value) for key, value in args.items() if value is not None}
    return json.dumps(payload).encode("utf-8")


def _plain(args: dict) -> dict:
    return {key: _json_ready(value) for key, value in args.items() if value is not None}


def _scrub(detail: object) -> object:
    if isinstance(detail, dict):
        return {key: value for key, value in detail.items() if key not in {"email", "customer_name"} and "@" not in str(value)}
    text = str(detail)
    if "@" in text:
        return "[redacted]"
    return detail


def _status_code(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def _http_detail(exc: Exception) -> str:
    if isinstance(exc, _Conflict):
        return str(exc.detail)
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            body = response.json()
        except Exception:
            body = {}
        if isinstance(body, dict) and body.get("detail"):
            return str(body["detail"])
    return str(exc)
