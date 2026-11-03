"""Full local audit. Extraction is rules. A model, if used, sees redacted text only."""

from __future__ import annotations

from .extract import extract
from .models import Recommendation
from .recommend import recommend
from .redact import Redaction, redact
from .score import rank


def run_audit(text: str, llm=None) -> dict:
    redaction: Redaction = redact(text)
    if llm is not None:
        llm.complete(
            {
                "system": "The week notes are already redacted. Do not ask for the originals.",
                "user": redaction.text,
            }
        )
    extracted = extract(text)
    recommended = [Recommendation.model_validate(item).model_dump() for item in recommend(extracted.tasks)]
    ranked = rank(recommended)
    return {
        "redaction": redaction,
        "extraction": extracted,
        "ranked": ranked,
    }
