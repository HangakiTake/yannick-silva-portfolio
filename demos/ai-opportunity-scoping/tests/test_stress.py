"""Messy inputs that the sample generator does not already cover."""

from __future__ import annotations

from pathlib import Path

from src.inventory import load_inventory
from src.units import parse_volume


def test_semicolon_and_latin1_and_blank_line(tmp_path: Path):
    semicolon = tmp_path / "semi.csv"
    semicolon.write_text(
        "process name;department;monthly volume;handling time;error rate;data sources;comments\n"
        "Checkout address validation;Ops;10;1;1%;Shopify;Deterministic validate step\n",
        encoding="utf-8",
    )
    inventory = load_inventory(semicolon)
    assert len(inventory.parsed) == 1
    assert inventory.exceptions == []

    latin = tmp_path / "latin.csv"
    latin.write_bytes(
        "process,team,volume,minutes,error,sources,notes\n"
        "Pick list,Opérations,10,5,1%,WMS,Checklist always the same\n".encode("latin-1")
    )
    parsed = load_inventory(latin)
    assert parsed.parsed[0].team == "Opérations"

    blank = tmp_path / "blank.csv"
    blank.write_text(
        "process,team,volume,minutes,error,sources,notes\n"
        "One,Ops,10,5,1%,WMS,Checklist always the same\n"
        "\n"
        "Two,Ops,10,5,1%,WMS,Checklist always the same\n",
        encoding="utf-8",
    )
    held = load_inventory(blank)
    assert held.rows_seen == 3
    assert held.accounted == 3
    assert any("blank_row" in row.reasons for row in held.exceptions)
    assert {row.process for row in held.parsed} == {"One", "Two"}


def test_same_name_different_team_is_kept_and_duration_is_not_a_count(tmp_path: Path):
    path = tmp_path / "teams.csv"
    path.write_text(
        "process,team,volume,minutes,error,sources,notes\n"
        "Weekly social captions,Marketing,12,40,0%,Brand,Brand creative captions\n"
        "Weekly social captions,Sales,12,40,0%,Brand,Brand creative captions\n"
        "Swapped,Ops,2h,10,1%,WMS,Checklist always the same\n",
        encoding="utf-8",
    )
    inventory = load_inventory(path)
    assert len(inventory.parsed) == 2
    assert {row.team for row in inventory.parsed} == {"Marketing", "Sales"}
    swapped = inventory.exceptions[0]
    assert "bad_volume" in swapped.reasons
    assert parse_volume("2h")[1] == "bad_volume"


def test_alias_headers(tmp_path: Path):
    path = tmp_path / "alias.csv"
    path.write_text(
        "process name,department,monthly volume,handling time,error rate,data sources,free text\n"
        "Merge duplicate customer records,Support,20,4,1%,Shopify,Exact email match is automatic. Always the same rule.\n",
        encoding="utf-8",
    )
    inventory = load_inventory(path)
    assert inventory.parsed[0].process.startswith("Merge duplicate")
    assert inventory.parsed[0].sources == ["Shopify"]
