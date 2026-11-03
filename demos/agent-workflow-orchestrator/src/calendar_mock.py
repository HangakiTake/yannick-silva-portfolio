"""In-process calendar. Some addresses fail on purpose so retries can be seen.

Failures are seeded by email. They are not random. A real calendar is not contacted.
"""

from __future__ import annotations

from src.store import Store

# Fail this many times before a booking is allowed. Farid never gets there.
DEFAULT_FAILURES = {
    "grace.lee@example.com": 2,
    "farid.malik@example.net": 10**6,
}


class CalendarFailed(Exception):
    def __init__(self, email: str, attempts: int, detail: str):
        super().__init__(detail)
        self.email = email
        self.attempts = attempts
        self.detail = detail


def business_slots() -> list[str]:
    """Tuesday 10 Nov 2026, 09:00–15:30 Pacific wall time, lunch left empty."""
    slots = []
    for hour in range(9, 16):
        if hour == 12:
            continue
        for minute in (0, 30):
            slots.append(f"2026-11-10T{hour:02d}:{minute:02d}")
    return slots


class MockCalendar:
    def __init__(self, store: Store, failures: dict | None, sleep, base_delay: float, max_attempts: int = 3):
        self.store = store
        self.failures = dict(DEFAULT_FAILURES if failures is None else failures)
        self.sleep = sleep
        self.base_delay = base_delay
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.max_attempts = max_attempts
        self.attempts: dict[str, int] = {}
        self.sleeps: list[float] = []
        self.slots = business_slots()

    def book(self, email: str, on_attempt) -> tuple[dict, bool]:
        planned = self.failures.get(email, 0)
        for attempt in range(1, self.max_attempts + 1):
            self.attempts[email] = attempt
            if attempt <= planned:
                on_attempt(attempt, "failed: 503 calendar unavailable")
                if attempt == self.max_attempts:
                    raise CalendarFailed(email, attempt, "503 calendar unavailable")
                delay = self.base_delay * (2 ** (attempt - 1))
                self.sleeps.append(delay)
                self.sleep(delay)
                continue
            on_attempt(attempt, "booking")
            existing = self.store.get_event(email)
            if existing:
                return existing, False
            free = next((slot for slot in self.slots if slot not in self.store.used_slots()), None)
            if free is None:
                raise CalendarFailed(email, attempt, "no free slot")
            return self.store.insert_event(email, free)
