"""Draft a reply from grounded fields and the policy file. Never invents a price."""

from triage.extract import matched_services


def _sensitive(request_type: str, flags: set[str]) -> bool:
    return request_type in {"complaint", "other"} or bool(
        flags & {"legal", "payment_dispute", "angry", "spam", "empty", "schema_invalid"}
    )


_UNSAFE_NAME = ("refund", "guarantee", "compensation")


def _greeting(name: str) -> str:
    lowered = (name or "").casefold()
    if name and not any(word in lowered for word in _UNSAFE_NAME):
        return f"Hello {name},"
    return "Hello,"


def build_draft(request, extraction: dict, policy) -> str:
    name = extraction.get("customer_name") or ""
    request_type = extraction.get("request_type") or "other"
    flags = set(extraction.get("flags") or [])
    lines = [_greeting(name), "", f"Thank you for writing to {policy.business_name}."]
    text = f"{request.subject}\n{request.body_text}"
    if _sensitive(request_type, flags):
        if request_type == "complaint" or flags & {"legal", "payment_dispute", "angry"}:
            lines.append("You raised a concern.")
        else:
            lines.append("We could not tell what you need from this message.")
    elif request_type == "quote":
        lines.append("You asked for a price.")
        services = matched_services(text, policy)
        if services:
            for service in services:
                lines.append(f"{service['service'].capitalize()} is {service['price']} {service['unit']}.")
        else:
            lines.append("Which service should we price: standard home clean, deep clean, or hourly handyman?")
    elif request_type == "booking":
        lines.append("You asked to book a visit.")
        if not extraction.get("key_dates"):
            lines.append("What date should we use?")
        if "address" not in text.casefold():
            lines.append("What is the service address?")
    elif request_type == "support":
        lines.append("You asked for help with a visit.")
    elif request_type == "billing":
        lines.append("You asked about a bill or a receipt.")
    else:
        lines.append("We could not tell what you need from this message.")
    if not _sensitive(request_type, flags):
        for phrase in extraction.get("date_phrases") or []:
            if phrase and phrase in request.search_text:
                lines.append(f"You mentioned {phrase}.")
    lines.append("")
    lines.extend(policy.allowed_commitments)
    if policy.opening_hours and policy.opening_hours not in "\n".join(policy.allowed_commitments):
        lines.append(policy.opening_hours)
    lines.append("")
    lines.extend(policy.signature_lines)
    return "\n".join(lines)
