"""Rule-based reader used as the deterministic mock model."""

import re

from triage.schema import LOW_CONFIDENCE
from triage.textutil import (
    alias_mentioned,
    at_company,
    company_after_name,
    explicit_email,
    find_amounts,
    find_dates,
    find_phones,
    intro_name,
    person_like,
)

_SPAM = (
    "seo", "backlink", "crypto", "bitcoin", "lottery", "casino", "viagra",
    "unsubscribe", "click here to claim", "limited offer",
)
_LEGAL = ("attorney", "lawyer", "sue", "lawsuit", "court", "avocat", "abogado", "advogado")
_ANGRY = ("furious", "unacceptable", "inaceptable", "worst", "disgusted")
_COMPLAINT = (
    "complaint", "complain", "unhappy", "damaged", "damage", "broke", "broken",
    "disappointed", "queja", "reclama", "terrible", "worst", "furious",
    "unacceptable", "inaceptable", "rompieron",
)
_QUOTE = (
    "quote", "estimate", "pricing", "how much", "price", "devis", "tarif",
    "orçamento", "orcamento", "cotação", "cotacao", "precio", "presupuesto",
    "cotización", "cotizacion",
)
_BOOK = (
    "book", "booking", "schedule", "appointment", "reserve", "réserver", "reserver",
    "agendar", "reserva", "reservar",
)
_BILLING = ("invoice", "receipt", "facture", "fatura", "factura")
_SUPPORT_STRONG = (
    "reschedule", "lockbox", "lock box", "boîte à clé", "boite a cle",
    "could not get in", "não conseguiu", "nao conseguiu", "conseguiu entrar",
    "remarcar", "send someone back", "problème", "problema",
)
_SUPPORT_WEAK = (
    "help me", "can you help", "pouvez-vous m'aider", "m'aider", "me ajudar",
    "aider", "ajuda", "ayuda", "aide", "get in touch",
)
_NEW_WORK = (
    "handyman", "handy person", "home clean", "deep clean", "house clean",
    "limpieza", "nettoyage", "limpeza padrão", "limpeza padrao", "limpeza completa",
    "limpieza profunda", "nettoyage complet",
)
_ASKING = (
    "need", "want", "looking", "please", "can you", "could you", "send someone",
    "would like", "i'd like", "necesito", "preciso", "gostaria", "pourriez",
    "quote", "book", "schedule",
)
_JOB = ("job", "hiring", "my experience")
_HIGH = ("urgent", "asap", "emergency", "immediately", "right now", "as soon as possible")
_LOW = ("no rush", "whenever", "no hurry", "pas pressé", "sin prisa", "sem pressa")
_PAYMENT = (
    "charged twice", "charged me twice", "double charge", "chargeback",
    "dispute the charge", "unauthorized charge", "cobraron dos veces",
)
_CHARGED_TWICE = re.compile(r"(?i)charged\s+(?:\w+\s+){0,3}twice")


def contains(text: str, phrase: str) -> bool:
    pattern = re.escape(phrase).replace(r"\ ", r"\s+")
    return re.search(rf"(?i)(?<!\w){pattern}(?!\w)", text or "") is not None


def any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(contains(text, phrase) for phrase in phrases)


def mostly_capitals(text: str) -> bool:
    letters = [character for character in text if character.isalpha()]
    if len(letters) <= 20:
        return False
    return sum(character.isupper() for character in letters) / len(letters) > 0.7


def _without_name(text: str, name: str) -> str:
    if not name:
        return text
    return re.sub(re.escape(name), " ", text or "", flags=re.I)


def safety_flags(text: str) -> set[str]:
    flags = set()
    if any_phrase(text, _LEGAL):
        flags.add("legal")
    if any_phrase(text, _ANGRY) or mostly_capitals(text):
        flags.add("angry")
    if any_phrase(text, _PAYMENT) or _CHARGED_TWICE.search(text or ""):
        flags.add("payment_dispute")
    service_words = _QUOTE + _BOOK + _BILLING + _SUPPORT_STRONG + _SUPPORT_WEAK + _NEW_WORK
    if any_phrase(text, _SPAM) and not any_phrase(text, service_words):
        flags.add("spam")
    return flags


def _classify(text: str) -> tuple[str, set[str]]:
    flags = safety_flags(text)
    if "spam" in flags:
        return "other", flags
    if "legal" in flags or "angry" in flags or any_phrase(text, _COMPLAINT):
        return "complaint", flags
    if "payment_dispute" in flags:
        return "billing", flags
    if any_phrase(text, _JOB):
        return "other", flags
    if any_phrase(text, _QUOTE):
        return "quote", flags
    if any_phrase(text, _BOOK):
        return "booking", flags
    if any_phrase(text, _BILLING):
        return "billing", flags
    if any_phrase(text, _SUPPORT_STRONG):
        return "support", flags
    if any_phrase(text, _NEW_WORK) and any_phrase(text, _ASKING):
        return "quote", flags
    if any_phrase(text, _SUPPORT_WEAK):
        return "support", flags
    return "other", flags


def _urgency(text: str, flags: set[str]) -> str:
    if flags & {"legal", "payment_dispute", "angry"} or any_phrase(text, _HIGH):
        return "high"
    if any_phrase(text, _LOW):
        return "low"
    return "normal"


def _score(request_type: str, flags: set[str], name: str, email: str, phone: str, text: str) -> float:
    if "empty" in flags:
        return 0.10
    if "spam" in flags:
        return 0.22
    score = 45
    if request_type != "other":
        score += 27
    if name:
        score += 10
    if email or phone:
        score += 10
    if len(text) > 80:
        score += 5
    return min(score, 95) / 100


def _empty(subject: str, body: str) -> bool:
    return sum(character.isalnum() for character in f"{subject}{body}") < 3


def matched_services(text: str, policy) -> list[dict]:
    found = []
    for service in policy.prices:
        if any(alias_mentioned(text, alias) for alias in service["aliases"]):
            found.append(service)
    return found


def build_summary(name: str, request_type: str, dates: list[str], amounts: list[str], missing: list[str]) -> str:
    who = name or "The sender"
    first = f"{who}: {request_type}."
    second = "Dates mentioned: " + ", ".join(dates) + "." if dates else "No calendar date was mentioned."
    if amounts:
        third = "Amounts mentioned: " + ", ".join(amounts) + "."
    elif missing:
        third = "Still to ask: " + "; ".join(missing) + "."
    else:
        third = "No amount was mentioned."
    return "\n".join((first, second, third))


def analyse(request, policy) -> dict:
    """Read one request. Returns a dict that already matches the extraction schema."""
    body = request.body_text or ""
    subject = request.subject or ""
    text = f"{subject}\n{body}"
    if request.parse_error or _empty(subject, body):
        flags = {"empty", "low_confidence"}
        if person_like(request.sender_name):
            name = " ".join(request.sender_name.split())
        elif person_like(request.reply_name):
            name = " ".join(request.reply_name.split())
        else:
            name = ""
        email = explicit_email(body) or request.reply_email or request.sender_email
        return _result(
            request_type="other",
            urgency="normal",
            name=name,
            company=(request.supplied_company or "").strip(),
            email=(email or "").strip().casefold(),
            phone="",
            dates=[],
            phrases=[],
            amounts=[],
            missing=["what the sender needs"],
            confidence=0.10,
            flags=flags,
        )
    name = intro_name(body)
    if not person_like(name):
        if person_like(request.sender_name):
            name = " ".join(request.sender_name.split())
        elif person_like(request.reply_name):
            name = " ".join(request.reply_name.split())
        else:
            name = ""
    request_type, flags = _classify(_without_name(text, name))
    company = (request.supplied_company or "").strip()
    if not company:
        company = at_company(body) or company_after_name(body, name)
    email = explicit_email(body) or (request.reply_email or "") or (request.sender_email or "")
    email = email.strip().rstrip(".,;:").casefold()
    phones = find_phones(body, policy.business_phone_digits)
    if not phones and request.supplied_phone:
        phones = find_phones(request.supplied_phone, policy.business_phone_digits)
    phone = phones[0] if phones else ""
    date_hits = find_dates("\n".join((body, subject, request.preferred_date or "")))
    dates, phrases = [], []
    for hit in date_hits:
        if hit["iso"] not in dates:
            dates.append(hit["iso"])
            phrases.append(hit["phrase"])
    if any(hit["ambiguous"] for hit in date_hits):
        flags.add("ambiguous_date")
    amounts = [] if "spam" in flags else find_amounts(f"{subject}\n{body}")
    if "spam" in flags:
        request_type = "other"
    urgency = _urgency(text, flags)
    missing = []
    if not email and not phone:
        missing.append("a phone number or email")
    if request_type == "booking" and not dates:
        missing.append("a preferred date")
    if request_type == "booking" and "address" not in text.casefold():
        missing.append("the service address")
    if request_type == "quote" and not matched_services(text, policy):
        missing.append("which service to price")
    confidence = _score(request_type, flags, name, email, phone, text)
    if confidence < LOW_CONFIDENCE:
        flags.add("low_confidence")
    return _result(
        request_type=request_type,
        urgency=urgency,
        name=name,
        company=company,
        email=email,
        phone=phone,
        dates=dates,
        phrases=phrases,
        amounts=amounts,
        missing=missing,
        confidence=confidence,
        flags=flags,
    )


def refresh_copy(data: dict, request, policy) -> dict:
    """Rebuild the summary from the fields we kept, so a model cannot add a new fact."""
    text = f"{request.subject}\n{request.body_text}"
    missing = []
    if not data.get("contact_email") and not data.get("contact_phone"):
        missing.append("a phone number or email")
    if data.get("request_type") == "booking" and not data.get("key_dates"):
        missing.append("a preferred date")
    if data.get("request_type") == "booking" and "address" not in text.casefold():
        missing.append("the service address")
    if data.get("request_type") == "quote" and not matched_services(text, policy):
        missing.append("which service to price")
    data["missing_info"] = missing
    data["summary"] = build_summary(
        data.get("customer_name") or "",
        data.get("request_type") or "other",
        list(data.get("key_dates") or []),
        list(data.get("amounts") or []),
        missing,
    )
    return data


def _result(**kwargs) -> dict:
    flags = sorted(kwargs["flags"])
    summary = build_summary(
        kwargs["name"], kwargs["request_type"], kwargs["dates"], kwargs["amounts"], kwargs["missing"]
    )
    return {
        "request_type": kwargs["request_type"],
        "urgency": kwargs["urgency"],
        "customer_name": kwargs["name"],
        "company": kwargs["company"],
        "contact_email": kwargs["email"],
        "contact_phone": kwargs["phone"],
        "key_dates": kwargs["dates"],
        "date_phrases": kwargs["phrases"],
        "amounts": kwargs["amounts"],
        "summary": summary,
        "missing_info": kwargs["missing"],
        "confidence": kwargs["confidence"],
        "flags": flags,
    }
