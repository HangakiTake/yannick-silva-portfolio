"""Architecture recommender. The order and the phrases are docs/architecture_rubric.md."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.paths import scoring_config
from src.phrases import first_phrase, phrase_groups, scrub
from src.scoring import ScoredRow

RISKS = {
    "rules": "A case that was never written down falls through to a person. Rules do not invent facts. Someone has to own that queue.",
    "llm_agent": "The model can pick the wrong tool or invent a fact. Arguments are checked, and a refund the policy does not allow is not executed. A person takes the escalation. Order text would be sent to OpenAI.",
    "rag": "The right passage can be missing or out of date. A person should review anything that is sent out. The documents would be sent to the API.",
    "classic_ml": "Bad labels teach the wrong score, and scores drift. A person should review the first month. This is not a refund bot.",
    "dont_automate": "The hours stay with the team. That is the recommendation, not a blank.",
}

HISTORY = ("labelled", "labeled", "historical labels", "win/loss")


@dataclass
class Recommendation:
    process: str
    pattern: str
    reason: str
    rule: str
    risk: str
    human_in_the_loop: str


def _hitl(pattern: str) -> str:
    if pattern == "dont_automate":
        return "A person does the work."
    if pattern == "llm_agent":
        return "A person handles anything the policy or the tool check refuses."
    if pattern == "rag":
        return "A person reviews the answer before it is sent out."
    if pattern == "classic_ml":
        return "A person reviews the scores for the first month."
    return "A person handles the cases the rules do not cover."


def recommend(row: ScoredRow, cfg: dict | None = None) -> Recommendation:
    cfg = cfg or scoring_config()
    groups = phrase_groups()
    original = f"{row.process} {row.notes}".lower()
    cleaned = scrub(original)

    def make(pattern: str, reason: str, rule: str) -> Recommendation:
        return Recommendation(row.process, pattern, reason, rule, RISKS[pattern], _hitl(pattern))

    hit = first_phrase(original, groups["dont"])
    if hit:
        return make("dont_automate", f"The notes say this stays with a person ({hit}).", "dont_phrase")
    hit = first_phrase(original, groups["action"])
    if hit:
        return make(
            "llm_agent",
            f"The work includes a customer reply or a record change ({hit}).",
            "action",
        )
    if row.monthly_hours < Decimal(str(cfg["tiny_hours"])) and row.monthly_volume < Decimal(str(cfg["tiny_volume"])):
        return make(
            "dont_automate",
            "Under 5 hours a month and under 30 items. Not worth wiring up.",
            "tiny",
        )
    hit = first_phrase(original, groups["ml"])
    history = first_phrase(original, HISTORY)
    if hit and (row.monthly_volume >= Decimal(str(cfg["ml_min_volume"])) or history):
        return make(
            "classic_ml",
            f"This is a score or a class ({hit}), and there is history to learn from.",
            "ml",
        )
    hit = first_phrase(original, groups["rules"])
    if hit:
        return make("rules", f"The steps are fixed ({hit}). A workflow can do this without a model.", "rules")
    hit = first_phrase(original, groups["rag"])
    if hit:
        return make(
            "rag",
            f"The answer is already in a document ({hit}). Retrieve it, and let a person send it.",
            "rag",
        )
    channel = first_phrase(cleaned, groups["channel"])
    toolword = first_phrase(cleaned, groups["toolword"])
    if channel and toolword:
        return make(
            "llm_agent",
            f"People write in ({channel}) and the reply needs a system ({toolword}).",
            "agent_signal",
        )
    if channel:
        return make("llm_agent", f"People write in ({channel}) and the reply is not a fixed rule.", "agent_channel")
    if row.monthly_volume >= Decimal(str(cfg["fallback_rules_min_volume"])) and row.minutes_per_item <= Decimal(
        str(cfg["fallback_rules_max_minutes"])
    ):
        return make(
            "rules",
            "High volume and a short repeated step, with no judgment described.",
            "fallback_rules",
        )
    return make(
        "dont_automate",
        "The steps are not clear enough to automate. Leave it with the team until they are written down.",
        "fallback_dont",
    )
