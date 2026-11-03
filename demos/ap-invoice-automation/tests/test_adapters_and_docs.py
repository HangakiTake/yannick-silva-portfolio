"""Live adapters stay untested. Docs must not invent an LLM score."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ap_pipeline.adapters.extract_llm import LIVE_API_TESTED as LLM_TESTED
from ap_pipeline.adapters.extract_llm import UNTESTED_NOTICE as LLM_NOTICE
from ap_pipeline.adapters.extract_llm import LlmExtractor
from ap_pipeline.adapters.mail_graph import LIVE_API_TESTED as GRAPH_TESTED
from ap_pipeline.adapters.mail_graph import UNTESTED_NOTICE as GRAPH_NOTICE
from ap_pipeline.adapters.mail_graph import GraphMailSource, reply_action
from ap_pipeline.adapters.qbo_rest import LIVE_API_TESTED as QBO_TESTED
from ap_pipeline.adapters.qbo_rest import UNTESTED_NOTICE as QBO_NOTICE
from ap_pipeline.adapters.qbo_rest import (
    QboRestClient,
    assert_sandbox_or_explicit_production,
    build_bill_payload,
    build_upload_parts,
    dumps_qbo,
)
from ap_pipeline.cli import main
from ap_pipeline.errors import CredentialsNotConfigured, PipelineError, ProductionGuardError
from ap_pipeline.eval_accuracy import LLM_NOT_MEASURED, score_rules, write_reports
from ap_pipeline.models import BillDraft, EmailMessage
from tests.conftest import FIXTURES, ROOT


class _Response:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.content = json.dumps(payload).encode()

    def json(self):
        return self._payload


class _Session:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def post(self, url, data=None, json=None, headers=None, auth=None, timeout=None):
        self.calls.append(("POST", url, data if data is not None else json))
        return self.handler("POST", url, data if data is not None else json)

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append(("GET", url, params))
        return self.handler("GET", url, params)

    def request(self, method, url, params=None, json=None, data=None, headers=None, timeout=None):
        body = json if json is not None else data
        self.calls.append((method, url, body))
        return self.handler(method, url, body)


def test_live_adapters_are_marked_untested_and_refuse_missing_credentials():
    assert LLM_TESTED is False and QBO_TESTED is False and GRAPH_TESTED is False
    assert "UNTESTED" in LLM_NOTICE and "UNTESTED" in QBO_NOTICE and "UNTESTED" in GRAPH_NOTICE
    with pytest.raises(CredentialsNotConfigured):
        LlmExtractor(provider="openai", api_key="", model="gpt-4o-mini")
    with pytest.raises(CredentialsNotConfigured):
        GraphMailSource(tenant_id="", client_id="", client_secret="", mailbox="")
    with pytest.raises(CredentialsNotConfigured):
        QboRestClient(
            client_id="",
            client_secret="",
            refresh_token="",
            realm_id="",
            expense_account_id="",
            session=object(),
        )


def test_qbo_payload_uses_two_decimal_amounts_and_refuses_production():
    draft = BillDraft(
        vendor_name="Cedarline Supply Co.",
        vendor_id="v-cedarline",
        invoice_number="INV-1002",
        txn_date="2026-03-03",
        total=Decimal("887.78"),
        po_number="PO-2402",
        memo="PO-2402 Oak Avenue repair",
        line_description="Subtotal 845.50 tax 42.28. PO-2402 Oak Avenue repair",
        qbo_customer_id="88",
        expense_account_id="80",
    )
    body = dumps_qbo(build_bill_payload(draft, "56"))
    assert '"Amount":887.78' in body
    assert '"value":"56"' in body
    assert "PO-2402 Oak Avenue repair" in body
    assert '"CustomerRef":{"value":"88"}' in body
    with pytest.raises(ProductionGuardError):
        assert_sandbox_or_explicit_production("https://quickbooks.api.intuit.com")
    for blocked in (
        "https://quickbooks.api.intuit.com:443",
        "https://quickbooks.api.intuit.com.",
        "https://user:pass@quickbooks.api.intuit.com",
        "https://sandbox-quickbooks.api.intuit.com@quickbooks.api.intuit.com",
        "https://evil.example",
    ):
        with pytest.raises(ProductionGuardError):
            assert_sandbox_or_explicit_production(blocked)
    assert (
        assert_sandbox_or_explicit_production("https://sandbox-quickbooks.api.intuit.com")
        == "https://sandbox-quickbooks.api.intuit.com"
    )
    upload, content_type = build_upload_parts("100", "invoice.pdf", b"%PDF-1.4")
    assert "file_metadata_0" in upload.decode("latin1")
    assert b"%PDF-1.4" in upload
    assert "multipart/form-data" in content_type
    quoted, _ = build_upload_parts("100", "../weird name.pdf", b"%PDF-1.4")
    assert b'filename="weird_name.pdf"' in quoted
    assert b"../" not in quoted


def test_qbo_token_error_does_not_echo_the_refresh_token():
    def handler(method, url, body):
        return _Response(401, {"error": "invalid_grant", "refresh_token": "SUPERSECRET"})

    client = QboRestClient(
        client_id="id",
        client_secret="secret",
        refresh_token="SUPERSECRET",
        realm_id="123",
        expense_account_id="80",
        session=_Session(handler),
    )
    with pytest.raises(PipelineError) as caught:
        client.create_bill(
            BillDraft(
                vendor_name="Cedarline Supply Co.",
                vendor_id="local",
                invoice_number="INV-1",
                txn_date="2026-03-01",
                total=Decimal("10.00"),
                po_number="PO-2401",
                memo="PO-2401 job",
                line_description="line",
            )
        )
    assert "SUPERSECRET" not in str(caught.value)


def test_qbo_create_uses_the_sandbox_vendor_id(monkeypatch):
    def handler(method, url, body):
        if method == "GET" and "Vendor" in url:
            return _Response(200, {"QueryResponse": {"Vendor": [{"Id": "56", "DisplayName": "Cedarline Supply Co."}]}})
        if method == "POST" and url.endswith("/bill") or "/bill?" in url:
            return _Response(200, {"Bill": {"Id": "100"}})
        raise AssertionError((method, url))

    session = _Session(handler)
    client = QboRestClient(
        client_id="id",
        client_secret="secret",
        refresh_token="refresh",
        realm_id="123",
        expense_account_id="80",
        session=session,
    )
    client._access_token = "access-token"
    client._token_deadline = 10**12
    bill = client.create_bill(
        BillDraft(
            vendor_name="Cedarline Supply Co.",
            vendor_id="v-cedarline",
            invoice_number="INV-1001",
            txn_date="2026-03-01",
            total=Decimal("1050.00"),
            po_number="PO-2401",
            memo="PO-2401 Maple Street re-roof",
            line_description="materials",
        )
    )
    assert bill.id == "100"
    assert bill.vendor_id == "56"
    posted = next(call for call in session.calls if call[0] == "POST")
    assert '"value":"56"' in posted[2]
    assert "v-cedarline" not in posted[2]


def test_qbo_vendor_lookup_allows_periods_and_refuses_quotes():
    def handler(method, url, body):
        return _Response(200, {"QueryResponse": {"Vendor": [{"Id": "56"}]}})

    client = QboRestClient(
        client_id="id",
        client_secret="secret",
        refresh_token="refresh",
        realm_id="123",
        expense_account_id="80",
        session=_Session(handler),
    )
    client._access_token = "token"
    client._token_deadline = 10**12
    assert client._vendor_id("Prairie Fastener Ltd.") == "56"
    with pytest.raises(PipelineError):
        client._vendor_id("O'Brien Roofing")


def test_cli_live_adapters_fail_before_touching_mail(tmp_path, monkeypatch, capsys):
    for name in ("GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET", "GRAPH_MAILBOX"):
        monkeypatch.delenv(name, raising=False)
    code = main(["run", "--mail", "graph", "--state", str(tmp_path / "state.json"), "--log-dir", str(tmp_path / "logs")])
    assert code == 1
    assert "UNTESTED" in capsys.readouterr().err

    for name, value in {
        "QBO_CLIENT_ID": "id",
        "QBO_CLIENT_SECRET": "secret",
        "QBO_REFRESH_TOKEN": "refresh",
        "QBO_REALM_ID": "123",
        "QBO_EXPENSE_ACCOUNT_ID": "80",
    }.items():
        monkeypatch.setenv(name, value)
    mail_root = tmp_path / "empty"
    (mail_root / "inbox").mkdir(parents=True)
    code = main(
        [
            "run",
            "--qbo",
            "rest",
            "--dry-run",
            "--mail-root",
            str(mail_root),
            "--state",
            str(tmp_path / "state.json"),
            "--log-dir",
            str(tmp_path / "logs"),
        ]
    )
    assert code == 0
    err = capsys.readouterr().err
    assert "UNTESTED" in err
    assert "does not create bills" in err


def test_qbo_prefers_the_rotated_refresh_token_in_the_cache(tmp_path):
    cache = tmp_path / "qbo-refresh"
    cache.write_text("rotated-token", encoding="utf-8")
    client = QboRestClient(
        client_id="id",
        client_secret="secret",
        refresh_token="old-token",
        realm_id="123",
        expense_account_id="80",
        token_cache=cache,
        session=_Session(lambda *args: _Response(500, {})),
    )
    assert client.refresh_token == "rotated-token"


def test_graph_follows_the_next_page_and_fetches_attachment_bytes():
    pages = {
        "first": _Response(
            200,
            {
                "value": [{"id": "m1", "subject": "Invoice", "receivedDateTime": "2026-03-02T15:00:00Z", "from": {"emailAddress": {"address": "ap@cedarline-supply.example", "name": "A"}}}],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/next-page",
            },
        ),
        "next": _Response(200, {"value": []}),
    }

    def handler(method, url, body):
        if url.endswith("/next-page"):
            return pages["next"]
        if url.endswith("/attachments"):
            return _Response(200, {"value": [{"id": "att1", "name": "invoice.pdf", "contentType": "application/pdf"}]})
        if url.endswith("/attachments/att1"):
            return _Response(200, {"contentBytes": base64.b64encode(b"%PDF").decode("ascii")})
        if "messages" in url:
            return pages["first"]
        return _Response(200, {"value": []})

    source = GraphMailSource(
        tenant_id="tenant",
        client_id="id",
        client_secret="secret",
        mailbox="ap@northline.example",
        session=_Session(handler),
    )
    source._access_token = "token"
    messages = source.list_messages()
    assert [message.id for message in messages] == ["m1"]
    assert messages[0].attachments[0].content == b"%PDF"


def test_graph_dry_run_creates_a_draft_and_live_send_uses_reply():
    assert reply_action(True) == "createReply"
    assert reply_action(False) == "reply"

    def handler(method, url, body):
        return _Response(202, {})

    session = _Session(handler)
    source = GraphMailSource(
        tenant_id="tenant",
        client_id="id",
        client_secret="secret",
        mailbox="ap@northline.example",
        session=session,
    )
    source._access_token = "token"
    message = EmailMessage(
        id="graph-message-1",
        from_name="Vendor",
        from_email="ap@vendor.example",
        subject="Invoice",
        received_at=datetime(2026, 3, 2, tzinfo=UTC),
        body="",
    )
    source.deliver_reply(message, "Invoice INV-1 needs a correction", "Hello", dry_run=True)
    draft_urls = [call[1] for call in session.calls]
    assert draft_urls[-1].endswith("/createReply")
    assert not any(url.endswith("/reply") for url in draft_urls)
    source.deliver_reply(message, "Invoice INV-1 needs a correction", "Hello", dry_run=False)
    send_urls = [call[1] for call in session.calls]
    assert send_urls[-1].endswith("/reply")
    assert sum(url.endswith("/createReply") for url in send_urls) == 1


def test_llm_rejects_bool_and_amounts_that_are_not_in_the_text():
    from ap_pipeline.adapters.extract_llm import _money, ground_amounts
    from ap_pipeline.models import InvoiceFields

    assert _money(True) is None
    assert _money(1.005) is None
    assert _money(1050) == Decimal("1050.00")
    fields = ground_amounts(
        InvoiceFields(subtotal=Decimal("100.00"), tax=Decimal("5.00"), total=Decimal("999.00")),
        "Subtotal: 100.00\nTax: 5.00\n",
    )
    assert fields.total is None
    assert fields.subtotal == Decimal("100.00")


def test_llm_extractor_parses_a_fake_response_and_skips_blank_scans():
    pdf = (FIXTURES / "mail" / "inbox" / "msg-01" / "invoice.pdf").read_bytes()
    image = (FIXTURES / "mail" / "inbox" / "msg-27" / "invoice.pdf").read_bytes()

    def handler(method, url, body):
        payload = {
            "vendor_name": "Cedarline Supply Co.",
            "invoice_number": "INV-1001",
            "po_number": "PO-2401",
            "invoice_date": "2026-03-01",
            "subtotal": "1000.00",
            "tax": "50.00",
            "total": "1050.00",
            "currency": "CAD",
        }
        return _Response(200, {"choices": [{"message": {"content": json.dumps(payload)}}]})

    session = _Session(handler)
    extractor = LlmExtractor(provider="openai", api_key="test-key", model="gpt-4o-mini", session=session)
    fields = extractor.extract(pdf)
    assert fields.total == Decimal("1050.00")
    assert extractor.calls == 1
    blank = extractor.extract(image)
    assert blank.no_text_layer is True
    assert extractor.calls == 1


def test_rules_accuracy_is_measured_and_llm_accuracy_is_not(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rules, llm = write_reports(FIXTURES / "manifest.json", tmp_path)
    assert rules["status"] == "measured"
    assert rules["total"] == 150
    assert rules["correct"] == 145
    assert {miss["id"] for miss in rules["misses"]} == {"inv-27"}
    assert llm["status"] == "not_measured"
    assert llm["accuracy"] is None
    assert llm["reason"] == LLM_NOT_MEASURED
    assert "not measured" in llm["reason"].lower()


def test_readme_and_make_blueprint_do_not_invent_a_live_result():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    scenario = (ROOT / "make" / "MAKE_SCENARIO.md").read_text(encoding="utf-8")
    blueprint = json.loads((ROOT / "make" / "ap-invoice-automation.blueprint.json").read_text(encoding="utf-8"))
    rules = score_rules(json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8")), FIXTURES)
    fraction = f"{rules['correct']}/{rules['total']}"
    assert fraction in readme
    assert "not measured" in readme.lower()
    assert "UNTESTED" in readme
    assert "mock" in readme.lower()
    for phrase in ("Intuit", "Make.com", "sandbox"):
        assert phrase in readme
    assert "llm accuracy is 9" not in readme.lower()
    assert "UNTESTED" in scenario
    assert "not measured" in scenario.lower()
    assert "UNTESTED" in blueprint["name"]
    assert blueprint["metadata"]["untested"] is True
    assert "UNTESTED" in blueprint["metadata"]["untested_notice"]
    assert isinstance(blueprint["flow"], list) and blueprint["flow"]
    routers = _modules(blueprint["flow"])
    assert "builtin:BasicRouter" in routers
    assert "quickbooks:createBill" in routers


def _modules(flow) -> set[str]:
    found = set()
    for module in flow:
        found.add(module["module"])
        for route in module.get("routes", []):
            found |= _modules(route["flow"])
    return found
