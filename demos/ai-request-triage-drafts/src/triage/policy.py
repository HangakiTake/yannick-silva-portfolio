"""Tone and the only prices a draft is allowed to mention."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Policy:
    raw: dict

    @property
    def business_name(self) -> str:
        return self.raw["business_name"]

    @property
    def opening_hours(self) -> str:
        return self.raw["opening_hours"]

    @property
    def prices(self) -> list[dict]:
        return self.raw["prices"]

    @property
    def allowed_commitments(self) -> list[str]:
        return self.raw["allowed_commitments"]

    @property
    def signature_lines(self) -> list[str]:
        return self.raw["signature_lines"]

    @property
    def business_phone_digits(self) -> str:
        return self.raw.get("business_phone_digits", "")

    def text_blob(self) -> str:
        return "\n".join(
            [self.opening_hours, *self.allowed_commitments, *self.signature_lines]
        )

    def service_for_price(self, price: str) -> dict | None:
        for service in self.prices:
            if service["price"] == price:
                return service
        return None


def load_policy(path: Path) -> Policy:
    return Policy(json.loads(Path(path).read_text(encoding="utf-8")))
