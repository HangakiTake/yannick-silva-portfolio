"""Thresholds from PLAN_AND_SPECS.md. Oracles were written before the implementation."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.agent import make_agent
from src.api import app, reset_store
from src.build_inventory import build, load_catalog
from src.decision import write_decision
from src.inventory import InventoryError, ParsedRow, load_inventory
from src.paths import ROOT
from src.pipeline import scope_path
from src.policy import as_of_date, assess
from src.paths import scoring_config
from src.scoring import net_of, rank_rows, score_row
from src.units import parse_error_rate, parse_minutes, parse_volume
from src.live import live_step
from src.tools import MODELS, ToolRunner, openai_tools, tool_schema, validate_call

DATA = ROOT / "data"
FIXTURES = Path(__file__).parent / "fixtures"


def _row(process, volume, minutes, error, sources, notes, team="Ops"):
    return ParsedRow(
        source_row=1,
        process=process,
        team=team,
        monthly_volume=Decimal(str(volume)),
        minutes_per_item=Decimal(str(minutes)),
        error_rate=None if error is None else Decimal(str(error)),
        error_missing=error is None,
        sources=sources,
        sources_raw=", ".join(sources),
        notes=notes,
        raw={},
    )


@pytest.fixture(scope="session", autouse=True)
def inventory_files():
    build()


def test_unit_gold_meets_95_percent():
    gold = json.loads((DATA / "gold_units.json").read_text(encoding="utf-8"))
    parsers = {"minutes": parse_minutes, "volume_monthly": parse_volume, "error_rate": parse_error_rate}
    checked = 0
    matched = 0
    for name, parser in parsers.items():
        for case in gold[name]:
            value, error = parser(case["raw"])
            if "expect" in case:
                checked += 1
                if value is not None and format(value, "f") == case["expect"]:
                    matched += 1
                else:
                    pytest.fail(f"{name} {case['raw']!r} -> {value}, expected {case['expect']}")
            else:
                assert error == case["error"], (name, case, error)
    assert checked >= 20
    assert matched / checked >= 0.95


def test_inventory_accounts_for_every_row():
    catalog = load_catalog()
    messy = 0
    for path in (DATA / "pebblecart_inventory.xlsx", DATA / "pebblecart_inventory.csv"):
        inventory = load_inventory(path)
        assert inventory.rows_seen >= 40
        assert inventory.accounted == inventory.rows_seen
        assert len(inventory.parsed) + len(inventory.exceptions) == inventory.rows_seen
        seen = [row.source_row for row in inventory.parsed] + [row.source_row for row in inventory.exceptions]
        assert len(seen) == len(set(seen))
        assert len(inventory.parsed) == sum(1 for row in catalog["rows"] if row["expect"] == "parse")
        parsed_names = [row.process for row in inventory.parsed]
        by_name = {row.process: row for row in inventory.parsed}
        assert by_name["Expense policy questions"].monthly_volume == Decimal("780.0000")
        assert by_name["Reconcile Stripe payouts to the bank"].monthly_volume == Decimal("1200.0000")
        assert by_name["Reconcile Stripe payouts to the bank"].minutes_per_item == Decimal("90.0000")
        assert by_name["Billing email triage and correction"].monthly_volume == Decimal("6000.0000")
        assert by_name["Billing email triage and correction"].minutes_per_item == Decimal("75.0000")
        assert by_name["Weekend warehouse cycle count"].monthly_volume == Decimal("1216.6667")
        assert by_name["Weekend warehouse cycle count"].error_missing is True
        assert by_name["Security questionnaire first draft"].minutes_per_item == Decimal("120.0000")
        ordered = sorted(
            [*inventory.parsed, *inventory.exceptions],
            key=lambda row: row.source_row,
        )
        assert len(ordered) == len(catalog["rows"])
        for raw, got in zip(catalog["rows"], ordered):
            if raw["expect"] == "parse":
                assert got.process == " ".join(raw["process"].split())
            else:
                assert raw["reason"] in got.reasons
        messy = sum(1 for row in catalog["rows"] if row.get("messy"))
    assert messy >= 10
    assert "Customer support queue: order status, refunds and tickets" in parsed_names


def test_missing_header_fails_loudly(tmp_path: Path):
    path = tmp_path / "nope.csv"
    path.write_text("hello,world\n1,2\n", encoding="utf-8")
    with pytest.raises(InventoryError):
        load_inventory(path)


def test_scoring_is_reproducible_and_weights_flip():
    scoped = scope_path(DATA / "pebblecart_inventory.xlsx")
    again = scope_path(DATA / "pebblecart_inventory.xlsx")
    assert [row.process for row in scoped.ranked] == [row.process for row in again.ranked]
    assert [row.net for row in scoped.ranked] == [row.net for row in again.ranked]
    assert scoped.ranked[0].process == "Customer support queue: order status, refunds and tickets"

    cfg = json.loads(json.dumps(scoring_config()))
    high_hours = _row("HighHours", "2000", "10", "0.01", ["Sheets"], "checklist, always the same, no language")
    high_error = _row("HighError", "400", "6", "0.10", ["Sheets"], "checklist, always the same, no language")
    default_rank = rank_rows([score_row(high_hours, cfg), score_row(high_error, cfg)])
    assert [row.process for row in default_rank] == ["HighHours", "HighError"]
    assert default_rank[0].net == Decimal("55.0833")
    assert default_rank[1].net == Decimal("30.7500")
    flipped = dict(cfg)
    flipped["w_hours"] = 0.20
    flipped["w_error"] = 0.80
    flipped_rank = rank_rows([score_row(high_hours, flipped), score_row(high_error, flipped)])
    assert [row.process for row in flipped_rank] == ["HighError", "HighHours"]
    assert flipped_rank[0].net == Decimal("75.7500")
    assert flipped_rank[1].net == Decimal("18.4167")

    assert net_of(Decimal("70"), Decimal("20"), "0.25") == Decimal("65.0000")
    assert net_of(Decimal("80"), Decimal("90"), "0.25") == Decimal("57.5000")
    assert net_of(Decimal("70"), Decimal("20"), "0.05") == Decimal("69.0000")
    assert net_of(Decimal("80"), Decimal("90"), "0.05") == Decimal("75.5000")
    # Lowering the effort weight lets the harder, higher-payoff row through.
    assert net_of(Decimal("70"), Decimal("20"), "0.25") > net_of(Decimal("80"), Decimal("90"), "0.25")
    assert net_of(Decimal("80"), Decimal("90"), "0.05") > net_of(Decimal("70"), Decimal("20"), "0.05")
    # The trace keeps the inputs.
    traced = score_row(high_hours, cfg)
    assert traced.monthly_volume == Decimal("2000")
    assert traced.minutes_per_item == Decimal("10")
    assert traced.weights["w_hours"] == cfg["w_hours"]
    assert traced.effort_reason.startswith("structured:")


def test_architecture_matches_hand_labels():
    gold = json.loads((DATA / "gold_architecture.json").read_text(encoding="utf-8"))
    assert len(gold["labels"]) >= 25
    scoped = scope_path(DATA / "pebblecart_inventory.xlsx")
    by_name = {row.process: row for row in scoped.ranked}
    matches = 0
    mismatches = []
    for label in gold["labels"]:
        assert label["process"] in by_name, label["process"]
        got = scoped.recommendations[label["process"]]
        if label["agreement"] == "match":
            assert got.pattern == label["pattern"], (label["process"], got.pattern, got.reason)
            matches += 1
        else:
            assert got.pattern != label["pattern"]
            assert got.pattern == label["rubric_will_say"]
            assert label["why_it_differs"]
            mismatches.append(label)
            matches += 0
    rate = matches / len(gold["labels"])
    assert rate >= 0.80
    assert len(mismatches) == 1
    assert mismatches[0]["process"] == "Tag blog posts from past tags"


def test_refund_policy_boundaries():
    reset_store()
    from datetime import datetime

    clock = as_of_date()
    orders = json.loads((DATA / "orders.json").read_text(encoding="utf-8"))["orders"]
    by_id = {order["order_id"]: order for order in orders}

    def days(order):
        if not order["delivered_on"]:
            return None
        delivered = datetime.strptime(order["delivered_on"], "%Y-%m-%d").date()
        return (clock - delivered).days

    assert days(by_id["PBL-1006"]) == 14
    assert days(by_id["PBL-1007"]) == 15
    assert days(by_id["PBL-1015"]) == 30
    assert days(by_id["PBL-1016"]) == 31
    assert days(by_id["PBL-1003"]) > 30

    cases = [
        ("PBL-1001", "damaged", True, "40"),
        ("PBL-1002", "damaged", True, "75"),
        ("PBL-1003", "damaged", False, "refund window"),
        ("PBL-1004", "damaged", False, "cannot be refunded"),
        ("PBL-1005", "damaged", False, "not delivered"),
        ("PBL-1006", "changed_mind", True, "20"),
        ("PBL-1007", "changed_mind", False, "changed-mind"),
        ("PBL-1008", "damaged", False, "already refunded"),
        ("PBL-1009", "damaged", True, "75"),
        ("PBL-1010", "damaged", True, "75"),
        ("PBL-1012", "damaged", False, "cannot be refunded"),
        ("PBL-1014", "damaged", False, "cancelled"),
        ("PBL-1015", "damaged", True, "30"),
        ("PBL-1016", "damaged", False, "refund window"),
        ("PBL-1001", "late_delivery", True, "40"),
    ]
    for order_id, reason, eligible, expect in cases:
        result = assess(by_id[order_id], reason)
        assert result["eligible"] is eligible, (order_id, reason, result)
        if eligible:
            assert format(result["max_auto_refund_usd"], "f") == expect
        else:
            assert expect in result["detail"]
    missing = assess(None, "damaged")
    assert missing["eligible"] is False
    assert "not found" in missing["detail"].lower()


def test_agent_scripted_conversations(tmp_path: Path):
    conversations = json.loads((FIXTURES / "conversations.json").read_text(encoding="utf-8"))
    assert len(conversations) >= 30
    log_path = tmp_path / "tools.jsonl"
    correct = 0
    out_of_policy = [item for item in conversations if item["out_of_policy"]]
    assert out_of_policy
    for item in conversations:
        reset_store()
        agent = make_agent(log_path, mode="mock")
        result = agent.run(item["id"], item["turns"])
        expected = item["tools"]
        if _calls_match(result["calls"], expected) and _policy_ok(item, result):
            correct += 1
        else:
            pytest.fail(f"{item['id']}: got {result['calls']} reply={result['reply']!r}")
        if "tools_per_turn" in item:
            for got, want in zip(result["per_turn"], item["tools_per_turn"], strict=True):
                assert _calls_match(got, want), (item["id"], got, want)
        if item["out_of_policy"]:
            assert not any(call["name"] == "issue_refund" and call["status"] == "ok" for call in result["calls"])
            assert any(call["name"] == "escalate_to_human" and call["status"] == "ok" for call in result["calls"])
            assert "I issued the refund" not in result["reply"]
        from src.api import _STORE

        if item["out_of_policy"]:
            assert _STORE["refunds"] == []
        if item.get("reply_contains"):
            assert item["reply_contains"] in result["reply"]
    assert correct / len(conversations) >= 0.95
    text = log_path.read_text(encoding="utf-8")
    assert "@" not in text
    assert "example.com" not in text
    logged = [json.loads(line) for line in text.splitlines() if line.strip()]
    assert logged
    assert all(entry["tool"] and entry["status"] and "arguments" in entry for entry in logged)


def _calls_match(got: list[dict], expected: list[dict]) -> bool:
    if len(got) != len(expected):
        return False
    for actual, want in zip(got, expected):
        if actual["name"] != want["name"] or actual["status"] != "ok":
            return False
        for key, value in want.get("args", {}).items():
            if key == "amount_usd" or key == "requested_amount_usd":
                if Decimal(str(actual["arguments"][key])) != Decimal(str(value)):
                    return False
            elif actual["arguments"].get(key) != value:
                return False
        if "summary_contains" in want and want["summary_contains"].lower() not in actual["arguments"]["summary"].lower():
            return False
        if "reason_contains" in want and want["reason_contains"].lower() not in actual["arguments"]["reason"].lower():
            return False
    return True


def _policy_ok(item: dict, result: dict) -> bool:
    if not item["out_of_policy"]:
        return True
    return not any(call["name"] == "issue_refund" for call in result["calls"])


def test_malformed_tool_args_are_rejected(tmp_path: Path):
    cases = [
        ("lookup_order", {}, "order_id"),
        ("lookup_order", {"order_id": 123}, "order_id"),
        ("lookup_order", {"order_id": ""}, "order_id"),
        ("lookup_order", {"order_id": "1001"}, "order_id"),
        ("lookup_order", {"order_id": "PBL-12"}, "order_id"),
        ("lookup_order", {"order_id": "ORDER-1001"}, "order_id"),
        ("lookup_order", {"order_id": "PBL-1001", "admin": True}, "admin"),
        ("lookup_order", {"order_id": None}, "order_id"),
        ("lookup_order", {"order_id": ["PBL-1001"]}, "order_id"),
        ("lookup_order", {"order_id": "PBL-1001; drop"}, "order_id"),
        ("check_refund_policy", {"order_id": "PBL-1001", "reason": "because"}, "reason"),
        ("check_refund_policy", {"order_id": "PBL-1001"}, "reason"),
        ("issue_refund", {"order_id": "PBL-1001", "amount_usd": "40", "reason": "damaged"}, "amount_usd"),
        ("issue_refund", {"order_id": "PBL-1001", "amount_usd": True, "reason": "damaged"}, "amount_usd"),
        ("issue_refund", {"order_id": "PBL-1001", "amount_usd": 0, "reason": "damaged"}, "amount_usd"),
        ("issue_refund", {"order_id": "PBL-1001", "amount_usd": -5, "reason": "damaged"}, "amount_usd"),
        ("issue_refund", {"order_id": "PBL-1001", "amount_usd": 40.001, "reason": "damaged"}, "amount_usd"),
        ("issue_refund", {"order_id": "PBL-1001", "reason": "damaged"}, "amount_usd"),
        ("open_ticket", {"order_id": "PBL-1001", "summary": "", "priority": "normal"}, "summary"),
        ("open_ticket", {"order_id": "PBL-1001", "summary": "   ", "priority": "normal"}, "summary"),
        ("open_ticket", {"order_id": "PBL-1001", "summary": "x" * 501, "priority": "normal"}, "summary"),
        ("open_ticket", {"order_id": "PBL-1001", "summary": "late parcel", "priority": "urgent"}, "priority"),
        ("open_ticket", {"order_id": "PBL-1001", "summary": "late parcel", "priority": "HIGH!!"}, "priority"),
        ("escalate_to_human", {"order_id": "PBL-1001", "reason": ""}, "reason"),
        ("escalate_to_human", {"order_id": "PBL-1001", "reason": "nope", "requested_amount_usd": "lots"}, "requested_amount_usd"),
        ("issue_refund", {"order_id": "PBL-1001", "amount_usd": None, "reason": "damaged"}, "amount_usd"),
        ("open_ticket", {"order_id": "PBL-1001", "summary": "late", "priority": 1}, "priority"),
        ("nope", {"order_id": "PBL-1001"}, "unknown tool"),
    ]
    runner = ToolRunner(BoomClient(), tmp_path / "rejected.jsonl", "malformed")
    for name, args, needle in cases:
        result = runner.call(name, args, "malformed")
        assert result["status"] == "rejected", (name, args, result)
        assert needle in result["error"], (name, args, result["error"])
    assert runner.http_calls == 0
    # Accepted shapes.
    assert validate_call("lookup_order", {"order_id": "pbl 1001"}).order_id == "PBL-1001"
    assert validate_call("lookup_order", {"order_id": "PBL1001"}).order_id == "PBL-1001"
    assert validate_call("open_ticket", {"order_id": "PBL-1001", "summary": "x", "priority": "High"}).priority == "high"
    assert validate_call("check_refund_policy", {"order_id": "PBL-1001", "reason": "Damaged"}).reason == "damaged"
    assert len(validate_call("open_ticket", {"order_id": "PBL-1001", "summary": "x" * 500, "priority": "low"}).summary) == 500


def test_out_of_policy_refund_is_not_executed(tmp_path: Path):
    reset_store()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    runner = ToolRunner(client, tmp_path / "guard.jsonl", "guard")
    forced = runner.call(
        "issue_refund",
        {"order_id": "PBL-1002", "amount_usd": Decimal("120"), "reason": "damaged"},
        "guard",
    )
    assert forced["status"] == "not_executed"
    assert "not executed" in forced["error"]
    assert client.get("/refunds").json()["refunds"] == []
    # A cent over the cap is refused. The cap itself is allowed.
    allowed = runner.call(
        "issue_refund",
        {"order_id": "PBL-1002", "amount_usd": Decimal("75"), "reason": "damaged"},
        "guard",
    )
    assert allowed["status"] == "ok"
    again = runner.call(
        "issue_refund",
        {"order_id": "PBL-1002", "amount_usd": Decimal("1"), "reason": "damaged"},
        "guard",
    )
    assert again["status"] == "not_executed"
    assert len(client.get("/refunds").json()["refunds"]) == 1
    text = (tmp_path / "guard.jsonl").read_text(encoding="utf-8")
    assert text.count("\n") == 3


def test_tool_schema_matches_models():
    names = [tool["name"] for tool in tool_schema()["tools"]]
    assert names == list(MODELS)
    for tool in tool_schema()["tools"]:
        model = MODELS[tool["name"]]
        required = {name for name, field in model.model_fields.items() if field.is_required()}
        assert set(tool["parameters"]["required"]) == required
    wrapped = openai_tools()
    assert wrapped[0]["type"] == "function"
    assert wrapped[0]["function"]["name"] == "lookup_order"


def test_decision_doc_has_the_required_sections(tmp_path: Path):
    gold = json.loads((DATA / "gold_architecture.json").read_text(encoding="utf-8"))
    gaps = [label for label in gold["labels"] if label["agreement"] == "mismatch"]
    md_path, html_path = write_decision(DATA / "pebblecart_inventory.xlsx", tmp_path, gaps)
    for path in (md_path, html_path):
        text = path.read_text(encoding="utf-8")
        for heading in (
            "Ranked shortlist",
            "Recommended architecture",
            "Integration plan",
            "Cost and risk",
            "Phased plan",
            "Phase 1",
            "Phase 2",
            "Phase 3",
            "Phase 4",
        ):
            assert heading in text
        assert "gpt-5-mini" in text
        assert "0.25" in text
        assert "2026-11-03" in text
        assert "Tag blog posts from past tags" in text
        assert "Customer support queue" in text
        assert "counted as 0" in text
    # No employer name, no key.
    blob = "\n".join(path.read_text(encoding="utf-8") for path in (md_path, html_path))
    employer = "global " + "fund"
    assert employer not in blob.lower()


def test_support_queue_cost_is_the_published_arithmetic():
    scoped = scope_path(DATA / "pebblecart_inventory.xlsx")
    # 5000 items * (7000 * $0.25 + 400 * $2.00) / 1_000_000 = $12.75
    assert scoped.costs["Customer support queue: order status, refunds and tickets"]["usd"] == Decimal("12.7500")


def test_live_mode_is_not_called_without_a_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        live_step([])


def test_repo_has_no_secrets_or_employer_name():
    banned = ("global " + "fund", "sk" + "-")
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".pytest_cache", "__pycache__", "node_modules"} for part in path.parts):
            continue
        if path.suffix.lower() in {".xlsx", ".png", ".zip"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for needle in banned:
            assert needle not in text, (path, needle)


class BoomClient:
    def get(self, *args, **kwargs):
        raise AssertionError("HTTP was called for a rejected tool")

    def post(self, *args, **kwargs):
        raise AssertionError("HTTP was called for a rejected tool")
