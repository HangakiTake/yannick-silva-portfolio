"""Follow-up text from a fixed template.

This is not a language model. The banner in the body says so.
"""

from __future__ import annotations

BANNER = "[template draft — not a language model]"

_LABELS = {
    "site_address": "the site address",
    "monthly_kwh": "your monthly kWh",
}


def render(lead: dict, event: dict | None, missing: list[str]) -> str:
    name = lead.get("name") or "there"
    lines = [BANNER, "", f"Hello {name},", ""]
    if event:
        lines.append(
            "Your discovery call with Brightfield Solar is booked for "
            f"{event['slot']} (Pacific wall time)."
        )
    else:
        lines.append(
            "We could not book a discovery call automatically. "
            "A person on our team still needs to confirm a time."
        )
    if missing:
        asked = " and ".join(_LABELS[field] for field in missing)
        lines.append(f"Please reply with {asked}.")
    lines.extend(
        [
            "",
            "This note was filled from a template. A person has to approve it before it is sent.",
        ]
    )
    return "\n".join(lines)
