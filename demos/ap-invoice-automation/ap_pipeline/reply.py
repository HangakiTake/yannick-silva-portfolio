"""Templated vendor replies. Wording lives here so it can be reviewed without reading the pipeline."""

from __future__ import annotations

from ap_pipeline.reasons import REASON_TEXT


def render_reply(
    reasons: list[str],
    *,
    invoice_number: str | None,
    company_name: str,
) -> tuple[str, str]:
    if not reasons:
        raise ValueError("A vendor reply requires at least one reason.")
    label = invoice_number or "received"
    subject = f"Invoice {label} needs a correction"
    bullets = "\n".join(f"- {REASON_TEXT[code]}" for code in reasons)
    body = (
        "Hello,\n\n"
        "Thank you for your invoice. We could not enter it for payment because:\n\n"
        f"{bullets}\n\n"
        "Please send a corrected PDF invoice. We will process it once these items are resolved.\n\n"
        "Accounts Payable\n"
        f"{company_name}\n"
    )
    return subject, body
