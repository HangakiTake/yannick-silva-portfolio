"""Checks the hand-labelled set. Does not import the extractor."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD = json.loads((ROOT / "gold" / "labels.json").read_text(encoding="utf-8"))
ITEMS = GOLD["items"]


def source_text(item):
    return (ROOT / item["source"]).read_text(encoding="utf-8", errors="replace")


def test_gold_was_labelled_before_the_extractor_and_is_large_enough():
    assert GOLD["labelled_before_extractor"] is True
    assert GOLD["count"] == len(ITEMS) >= 40
    assert GOLD["messy_count"] == sum(1 for item in ITEMS if item["messy"]) >= 15
    assert len({item["id"] for item in ITEMS}) == len(ITEMS)


def test_every_label_points_at_a_real_file_and_every_sample_is_labelled():
    labelled = {item["source"] for item in ITEMS}
    for item in ITEMS:
        assert (ROOT / item["source"]).is_file(), item["id"]
    on_disk = set()
    for path in (ROOT / "samples").rglob("*"):
        if path.is_file():
            on_disk.add(str(path.relative_to(ROOT)))
    # The form file is one source for many rows.
    assert on_disk <= labelled | {"samples/forms/web_form.csv"}
    assert "samples/forms/web_form.csv" in on_disk


def test_needs_human_follows_the_written_rule():
    force = {"legal", "payment_dispute", "angry", "spam", "empty", "low_confidence"}
    for item in ITEMS:
        expected = (
            item["request_type"] in {"complaint", "other"}
            or item["urgency"] == "high"
            or bool(set(item["flags"]) & force)
        )
        assert item["expect_needs_human"] is expected, item["id"]


def test_gold_values_appear_in_the_source():
    for item in ITEMS:
        text = source_text(item)
        folded = text.casefold()
        digits = re.sub(r"\D", "", text)
        for part in item["customer_name"].split():
            assert part.casefold() in folded, (item["id"], part)
        if item["contact_email"]:
            assert item["contact_email"].casefold() in folded, item["id"]
        if item["company"]:
            assert item["company"].casefold() in folded, item["id"]
        phone = re.sub(r"\D", "", item["contact_phone"])
        if phone:
            assert phone in digits, item["id"]
        for amount in item["amounts"]:
            number = amount.replace("$", "").replace(",", "")
            assert number in text, (item["id"], amount)
        for iso in item["key_dates"]:
            year, month, day = iso.split("-")
            assert year in text, (item["id"], iso)
            assert str(int(day)) in text, (item["id"], iso)


def test_no_forbidden_names_in_the_demo_tree():
    banned = ("global" + " fund", "global" + "fund")
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".json", ".py", ".csv", ".eml", ".html", ".txt", ".yml"}:
            continue
        folded = path.read_text(encoding="utf-8", errors="ignore").casefold()
        for phrase in banned:
            assert phrase not in folded, path
