"""Independent check: a draft may only use prices, dates and promises from the request or the policy."""

import re

from triage.textutil import alias_mentioned

_MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*|\d+)(\.\d{2})?\b")
_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december|"
    "janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre|"
    "janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro|"
    "enero|febrero|marzo|mayo|junio|julio|septiembre|octubre|noviembre|diciembre"
)
_DATE = re.compile(
    rf"\b(?:\d{{1,2}}\s+(?:de\s+)?(?:{_MONTHS})\s+(?:de\s+)?20\d{{2}}|"
    rf"(?:{_MONTHS})\s+\d{{1,2}},?\s+20\d{{2}}|"
    rf"20\d{{2}}-\d{{2}}-\d{{2}}|\d{{1,2}}/\d{{1,2}}/20\d{{2}})\b",
    re.IGNORECASE,
)
_FORBIDDEN = ("refund", "guarantee", "same-day", "same day", "compensation", "we promise")


def _canonical(number: str, cents: str | None) -> str:
    whole = str(int(number.replace(",", "")))
    if cents:
        return f"${whole}{cents}"
    return f"${whole}"


def draft_violations(body: str, request_text: str, policy, request_type: str) -> list[str]:
    problems = []
    request_folded = (request_text or "").casefold()
    policy_folded = policy.text_blob().casefold()
    for match in _MONEY.finditer(body or ""):
        price = _canonical(match.group(1), match.group(2))
        if request_type != "quote":
            problems.append(f"price on a {request_type} draft: {price}")
            continue
        service = policy.service_for_price(price)
        if service is None:
            problems.append(f"price not in the policy: {price}")
            continue
        if not any(alias_mentioned(request_text, alias) for alias in service["aliases"]):
            problems.append(f"{price} quoted without the matching service in the request")
    for match in _DATE.finditer(body or ""):
        phrase = match.group(0)
        folded = phrase.casefold()
        if folded not in request_folded and folded not in policy_folded:
            problems.append(f"date not in the request or the policy: {phrase}")
    lowered = (body or "").casefold()
    for word in _FORBIDDEN:
        if word in lowered:
            problems.append(f"commitment not allowed: {word}")
    return problems
