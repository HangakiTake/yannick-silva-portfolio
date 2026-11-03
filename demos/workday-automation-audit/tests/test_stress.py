"""Inputs that are not in the three labelled weeks."""

import json
import re

from workday_audit.audit import run_audit
from workday_audit.extract import extract
from workday_audit.llm import MockLLM
from workday_audit.recommend import recommend
from workday_audit.redact import redact
from workday_audit.runner import process_inquiry

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"\(\d{3}\)\s*\d{3}-\d{4}")


def _accounted(text: str, anchor: str) -> bool:
    result = extract(text)
    blob = "\n".join(e for t in result.tasks for e in t["evidence"])
    blob += "\n" + "\n".join(q.quote for q in result.questions)
    return anchor in blob


def test_novel_two_task_sentence_is_not_dropped():
    text = (
        "EVERY WEDNESDAY I export the Shopify payout csv into the sheet, 15 min, "
        "and I also text the landlord about the rent, 5 min, weekly."
    )
    assert _accounted(text, "Shopify payout csv")
    assert _accounted(text, "text the landlord")
    result = extract(text)
    assert len(result.tasks) == 2
    assert all(t["provisional"] for t in result.tasks)


def test_contradictory_duration_is_a_question():
    text = "The bank thing takes 10 min or maybe 2 hours, whenever I get to it."
    result = extract(text)
    assert result.tasks == []
    assert any("10 min" in q.quote for q in result.questions)


def test_en_dash_and_decimal_hours():
    text = "every monday I file papers, 15–20 min.\napprox. 1.5 hours every month on the inventory cross-check in the sheet."
    result = extract(text)
    minutes = sorted(t["minutes_per_run"] for t in result.tasks)
    assert 17.5 in minutes
    assert 90 in minutes


def test_repeating_a_sentence_does_not_double_the_frequency():
    line = "Every morning I go through the new inquiry emails and draft replies, which takes 25-30 min."
    result = extract(line + "\n" + line)
    assert len(result.tasks) == 1
    assert result.tasks[0]["frequency_per_month"] < 30
    assert len(result.tasks[0]["evidence"]) == 2


def test_empty_notes():
    result = extract("")
    assert result.tasks == []
    assert result.questions == []


def test_pii_in_a_messy_note_does_not_reach_the_model():
    text = "Please email jane.doe@secret.example or call (503) 555-0101. I do this daily, 15 min."
    red = redact(text)
    assert "jane.doe@secret.example" not in red.text
    assert "(503) 555-0101" not in red.text
    llm = MockLLM()
    run_audit(text, llm=llm)
    payload = json.dumps(llm.payloads)
    assert EMAIL.findall(payload) == []
    assert PHONE.findall(payload) == []


def test_paraphrased_inquiries():
    cases = [
        ("circling back on the quote I asked about", "new_lead", "normal", "general"),
        ("Could you resend the P&L when you have a minute?", "document_request", "normal", "general"),
        ("The ACH didn't land even though we transferred on Tuesday", "payment_notice", "normal", "general"),
        ("Please unsubscribe me", "spam", "normal", "general"),
        ("Would Thursday work to meet?", "scheduling", "normal", "general"),
        ("Any update on the overdue invoice?", "invoice_status", "normal", "general"),
        ("Just saying hello, hope the cafe is well", "other", "normal", "general"),
        ("We need payroll catch-up, how much, asap", "new_lead", "high", "payroll"),
    ]
    llm = MockLLM()
    for i, (body, cat, urg, svc) in enumerate(cases):
        out = process_inquiry({"id": f"s{i}", "from_name": "Sam", "from_email": "sam@example.com", "subject": "Hi", "body": body}, llm)
        assert (out["category"], out["urgency"], out["service"]) == (cat, urg, svc)
        assert out["sent"] is False


def test_hours_abbreviation_and_takes_follow_on():
    hours = extract("once a week I do the filing, 2 hrs.")
    assert hours.tasks and hours.tasks[0]["minutes_per_run"] == 120
    follow = extract("every morning I read email. takes 20mins.")
    assert follow.tasks and follow.tasks[0]["minutes_per_run"] == 20
    assert follow.tasks[0]["frequency_per_month"] > 20


def test_wide_range_is_not_averaged():
    result = extract("I spend somewhere between 10 minutes and 3 hours on email, hard to say.")
    assert result.tasks == []
    assert result.questions


def test_every_other_week_is_not_guessed_as_weekly():
    result = extract("every other friday I archive the old folders, 15 min.")
    assert result.tasks == []
    assert result.questions


def test_negated_weekly_is_not_a_weekly_task():
    result = extract("One-off fact, not a weekly task.")
    assert result.tasks == []
    kept = extract("I do not file this weekly, I do it every morning, 10 min.")
    assert kept.tasks
    assert kept.tasks[0]["frequency_per_month"] > 20


def test_mon_fri_counts_as_a_weekday():
    result = extract("Mon-Fri I update the log, 10 min.")
    assert result.tasks
    assert 21 <= result.tasks[0]["frequency_per_month"] <= 22
    assert result.tasks[0]["minutes_per_run"] == 10


def test_customer_facing_automation_keeps_approval():
    tasks = recommend(extract(
        "Every morning I draft replies to new inquiry emails, 20 min, and I never send them myself."
    ).tasks)
    assert tasks[0]["tool"] == "n8n"
    assert tasks[0]["requires_approval"] is True
