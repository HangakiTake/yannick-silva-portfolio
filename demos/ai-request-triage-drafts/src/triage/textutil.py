"""Turn messy mail into the customer's own words, then find dates, phones and amounts."""

import re
from html.parser import HTMLParser

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12, "décembre": 12,
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "mayo": 5, "junio": 6, "julio": 7,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))
_MONTH_DATE = re.compile(
    rf"\b(\d{{1,2}})\s+(?:de\s+)?({_MONTH_ALT})\s+(?:de\s+)?(20\d{{2}})\b",
    re.IGNORECASE,
)
_MONTH_DATE_US = re.compile(
    rf"\b({_MONTH_ALT})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")
_PHONE = re.compile(r"(?:\+?\d[\d\s().-]{8,20}\d)")
_AMOUNT = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*|\d+)(\.\d{2})?\b")
_DOLLARS = re.compile(r"\b(\d+(?:\.\d{2})?)\s+dollars\b", re.IGNORECASE)
_USD_BEFORE = re.compile(r"\bUSD\s*\$?\s*(\d{1,3}(?:,\d{3})*|\d+)(\.\d{2})?\b", re.IGNORECASE)
_USD_AFTER = re.compile(r"\b(\d{1,3}(?:,\d{3})*|\d+)(\.\d{2})?\s*USD\b", re.IGNORECASE)
_ADDRESS = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_FORWARD = (
    "---------- forwarded message ---------",
    "-----original message-----",
    "begin forwarded message",
)
_WROTE = re.compile(
    r"(?im)^on .+ wrote:\s*$|^le .+ a [eé]crit\s*:?\s*$|^em .+ escreveu\s*:?\s*$|^el .+ escribi[oó]\s*:?\s*$"
)
_HEADER = re.compile(r"(?i)^(from|to|cc|date|sent|subject|reply-to)\s*:")
_KEYWORD = re.compile(
    r"(?i)(?<!\w)(quote|book|invoice|help|devis|reserva|estimate|receipt|facture|schedule|"
    r"presupuesto|orçamento|orcamento|agendar|appointment|urgent)(?!\w)"
)
_CONFIDENTIAL = re.compile(r"(?i)this message and any attachments are confidential")
_NAME_WORD = r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÿ'’-]*"
_INTRO = re.compile(
    rf"(?i:(?:i am|i'm|this is|je m'appelle|meu nome é|me llamo|soy))\s+"
    rf"({_NAME_WORD}(?:\s+{_NAME_WORD})+)"
)
_AT_COMPANY = re.compile(rf"\bat\s+({_NAME_WORD}(?:\s+{_NAME_WORD}){{0,3}})")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_EXPLICIT_EMAIL = re.compile(
    r"(?i)\b(?:send it to|my email is|e-mail|email)\s+(?:me\s+at\s+)?([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)

GENERIC_NAME_WORDS = {
    "office", "team", "info", "admin", "sales", "noreply", "no-reply", "accounts",
    "support", "desk", "prize", "seo", "notification",
}
ROLE_WORDS = {"manager", "director", "directrice", "directeur", "owner", "coordinator"}
GREETINGS = {
    "thanks", "thank you", "merci", "obrigado", "obrigada", "gracias", "regards",
    "cheers", "sincerely", "hello", "hi", "olá", "ola", "bonjour",
}


class _HTMLText(HTMLParser):
    def __init__(self, hidden_classes: set[str] | None = None):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip: list[str] = []
        self._hide_tag = ""
        self._hide_depth = 0
        self.unclosed_hide = False
        self._hidden_classes = hidden_classes or set()

    def handle_starttag(self, tag, attrs):
        attr = {key.lower(): (value or "") for key, value in attrs}
        style = attr.get("style", "")
        classes = set(attr.get("class", "").split())
        hidden = bool(re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", style, re.I))
        hidden = hidden or bool(classes & self._hidden_classes)
        if self._hide_depth:
            if tag == self._hide_tag:
                self._hide_depth += 1
            return
        if tag in {"script", "style"} or hidden:
            self._skip.append(tag)
            if hidden:
                self._hide_tag = tag
                self._hide_depth = 1
        if tag in {"p", "div", "br", "tr", "li", "h1", "h2"} and not self._hide_depth:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self._hide_depth:
            if tag == self._hide_tag:
                self._hide_depth -= 1
                if self._hide_depth == 0:
                    self._hide_tag = ""
                    if self._skip and self._skip[-1] == tag:
                        self._skip.pop()
            return
        if self._skip and self._skip[-1] == tag:
            self._skip.pop()
        if tag in {"p", "div", "tr", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip and not self._hide_depth:
            self.parts.append(data)

    def close(self):
        super().close()
        if self._hide_depth:
            self.unclosed_hide = True


def normalize_text(raw: str) -> str:
    return (
        (raw or "")
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\xa0", " ")
    )


def hidden_css_classes(raw: str) -> set[str]:
    classes = set()
    for block in re.findall(r"<style[^>]*>(.*?)</style>", raw or "", flags=re.I | re.S):
        for match in re.finditer(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", block):
            if re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", match.group(2), re.I):
                classes.add(match.group(1))
    return classes


def html_to_text(raw: str) -> tuple[str, bool]:
    parser = _HTMLText(hidden_css_classes(raw or ""))
    parser.feed(raw or "")
    parser.close()
    return "".join(parser.parts), parser.unclosed_hide


def alias_mentioned(text: str, alias: str) -> bool:
    """True when the service is named and not in a short negation ('not a deep clean')."""
    folded = (text or "").casefold()
    pattern = r"(?<!\w)" + re.escape(alias.casefold()).replace(r"\ ", r"\s+") + r"(?!\w)"
    for match in re.finditer(pattern, folded):
        prefix = folded[max(0, match.start() - 16) : match.start()]
        if re.search(r"(?:\bnot\b|\bno\b|n't|\bwithout\b)\s+(?:a\s+|an\s+|the\s+)?$", prefix):
            continue
        return True
    return False


def _alnum_count(text: str) -> int:
    return sum(character.isalnum() for character in text)


def _cut_signature(text: str) -> str:
    kept = []
    for line in text.splitlines():
        if line.strip() in {"--", "-- "}:
            break
        kept.append(line)
    return "\n".join(kept)


def _cut_disclaimer(text: str) -> str:
    match = _CONFIDENTIAL.search(text)
    if match:
        return text[: match.start()]
    return text


def _strip_forward_headers(tail: str) -> str:
    lines = tail.splitlines()
    skipping = True
    started = False
    kept = []
    for line in lines:
        stripped = line.strip()
        if skipping:
            if not stripped:
                if started:
                    skipping = False
                continue
            if stripped.startswith("-") or "forwarded message" in stripped.casefold() or "original message" in stripped.casefold():
                continue
            if _HEADER.match(stripped):
                started = True
                continue
            skipping = False
        kept.append(line)
    return "\n".join(kept)


def customer_text(raw: str, own_addresses: tuple[str, ...] | list[str] = ()) -> str:
    """Text the customer wrote, without quoted history, forwarded staff mail, or a disclaimer."""
    text = normalize_text(raw).replace("\r\n", "\n").replace("\r", "\n")
    own = {address.casefold() for address in own_addresses if address}
    lowered = text.casefold()
    cut_at = len(text)
    for marker in _FORWARD:
        index = lowered.find(marker)
        if index != -1:
            cut_at = min(cut_at, index)
    wrote = _WROTE.search(text)
    if wrote:
        cut_at = min(cut_at, wrote.start())
    head = "\n".join(line for line in text[:cut_at].splitlines() if not line.strip().startswith(">"))
    head = _cut_disclaimer(_cut_signature(head))
    if _alnum_count(head) < 20 and not _KEYWORD.search(head):
        tail_raw = text[cut_at:]
        from_line = next((line for line in tail_raw.splitlines() if re.match(r"(?i)^\s*from\s*:", line)), "")
        from_emails = {address.casefold() for address in _ADDRESS.findall(from_line)}
        # A short "FYI" in front of our own sent mail is not a new customer request.
        if from_emails & own:
            return head.strip()
        tail = _strip_forward_headers(tail_raw)
        tail = "\n".join(line for line in tail.splitlines() if not line.strip().startswith(">"))
        tail = _cut_disclaimer(_cut_signature(tail))
        if _alnum_count(tail) > _alnum_count(head):
            return tail.strip()
    return head.strip()


def _valid(year: int, month: int, day: int) -> str | None:
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        from datetime import date

        date(year, month, day)
    except ValueError:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def find_dates(text: str) -> list[dict]:
    found: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(iso: str | None, phrase: str, ambiguous: bool) -> None:
        if not iso:
            return
        key = (iso, phrase)
        if key in seen:
            return
        seen.add(key)
        found.append({"iso": iso, "phrase": phrase, "ambiguous": ambiguous})

    for match in _ISO_DATE.finditer(text or ""):
        year, month, day = (int(part) for part in match.groups())
        add(_valid(year, month, day), match.group(0), False)
    for match in _SLASH_DATE.finditer(text or ""):
        first, second, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        month_first = _valid(year, first, second)
        day_first = _valid(year, second, first)
        if month_first and day_first and first != second:
            add(month_first, match.group(0), True)
        elif month_first:
            add(month_first, match.group(0), False)
        elif day_first:
            add(day_first, match.group(0), False)
    for match in _MONTH_DATE.finditer(text or ""):
        day, month_name, year = int(match.group(1)), match.group(2).casefold(), int(match.group(3))
        add(_valid(year, MONTHS[month_name], day), match.group(0), False)
    for match in _MONTH_DATE_US.finditer(text or ""):
        month_name, day, year = match.group(1).casefold(), int(match.group(2)), int(match.group(3))
        add(_valid(year, MONTHS[month_name], day), match.group(0), False)
    return found


def canonical_amount(number: str, cents: str | None) -> str:
    whole = str(int(number.replace(",", "")))
    if cents:
        return f"${whole}{cents}"
    return f"${whole}"


def find_amounts(text: str) -> list[str]:
    found: list[str] = []
    for match in _AMOUNT.finditer(text or ""):
        found.append(canonical_amount(match.group(1), match.group(2)))
    for match in _DOLLARS.finditer(text or ""):
        raw = match.group(1)
        if "." in raw:
            whole, cents = raw.split(".")
            found.append(canonical_amount(whole, "." + cents))
        else:
            found.append(canonical_amount(raw, None))
    for pattern in (_USD_BEFORE, _USD_AFTER):
        for match in pattern.finditer(text or ""):
            found.append(canonical_amount(match.group(1), match.group(2)))
    deduped = []
    for amount in found:
        if amount not in deduped:
            deduped.append(amount)
    return deduped


def phone_grounded(phone: str, text: str) -> bool:
    """The digits must sit together in the message, not across unrelated numbers."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 10:
        return False
    pattern = r"(?<!\d)" + r"\D{0,3}".join(re.escape(digit) for digit in digits) + r"(?!\d)"
    return re.search(pattern, text or "") is not None


def find_phones(text: str, business_digits: str) -> list[str]:
    found = []
    blocked = {business_digits, "1" + business_digits} if business_digits else set()
    for match in _PHONE.finditer(text or ""):
        raw = match.group(0).strip()
        number = re.sub(r"\D", "", raw)
        if len(number) not in {10, 11}:
            continue
        if number in blocked or (len(number) >= 10 and number[-10:] == business_digits):
            continue
        if raw not in found:
            found.append(raw)
    return found


def explicit_email(text: str) -> str:
    match = _EXPLICIT_EMAIL.search(text or "")
    if not match:
        return ""
    return match.group(1).rstrip(".,;:").casefold()


def intro_name(text: str) -> str:
    match = _INTRO.search(text or "")
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def at_company(text: str) -> str:
    match = _AT_COMPANY.search(text or "")
    if not match:
        return ""
    return match.group(1).strip(" .")


def person_like(name: str) -> bool:
    words = [word for word in (name or "").split() if word]
    if len(words) < 2:
        return False
    if not re.match(r"[A-ZÀ-ÖØ-Þ]", words[0]):
        return False
    return not all(word.casefold().strip(".") in GENERIC_NAME_WORDS for word in words)


def company_after_name(text: str, person_name: str) -> str:
    if not person_name:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    start = None
    for index, line in enumerate(lines):
        if line.casefold().rstrip(".") == person_name.casefold():
            start = index + 1
    if start is None:
        return ""
    for line in lines[start:]:
        lowered = line.casefold().strip(",.")
        if lowered in GREETINGS or line.endswith((",", ".")):
            continue
        if any(word in ROLE_WORDS for word in lowered.split()):
            continue
        if "@" in line or find_phones(line, ""):
            continue
        words = line.split()
        if 1 <= len(words) <= 4 and words[0][:1].isupper():
            return line.strip(" .")
    return ""
