"""Behaviour of the Brightfield Solar lead workflow. Offline mocks only."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from src.auditlog import AuditLog
from src.mailer import ApprovalRequired, deliver
from src.normalize import canonicalize, idempotency_key, normalize_email, usable_address, usable_kwh
from src.pipeline import OWNER, run
from src.store import Store

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "data" / "leads.json"


def _open(tmp_path: Path, name: str = "state"):
    folder = tmp_path / name
    folder.mkdir(parents=True, exist_ok=True)
    store = Store(folder / "orchestrator.sqlite")
    audit = AuditLog(folder / "audit.jsonl", run_id=f"test-{name}")
    return store, audit


def _run(store, audit, **kwargs):
    kwargs.setdefault("sleep", lambda _seconds: None)
    kwargs.setdefault("base_delay", 0.05)
    return run(INBOX, store, audit, **kwargs)


def _snapshot(store: Store) -> dict:
    def rows(items, fields):
        return sorted(({k: item[k] for k in fields} for item in items), key=lambda r: r.get("email") or r.get("entity_id"))

    return {
        "crm": rows(store.list_crm(), ["email", "name", "phone", "site_address", "monthly_kwh"]),
        "tasks": rows(store.list_tasks(), ["email", "missing"]),
        "events": rows(store.list_events(), ["email", "slot"]),
        "drafts": rows(store.list_drafts(), ["email", "body", "status"]),
        "exceptions": rows(store.list_exceptions(), ["step", "entity_id", "owner", "reason"]),
        "outbox": rows(store.list_outbox(), ["email", "body", "draft_id"]),
    }


def test_inbox_merges_exact_and_case_duplicates(tmp_path):
    raw = json.loads(INBOX.read_text(encoding="utf-8"))
    assert len(raw) == 12
    canonical = [json.dumps(canonicalize(row), sort_keys=True) for row in raw]
    assert sum(n - 1 for n in Counter(canonical).values()) == 3
    raw_keys = [json.dumps(row, sort_keys=True) for row in raw]
    assert sum(n - 1 for n in Counter(raw_keys).values()) == 2

    store, audit = _open(tmp_path)
    stats = _run(store, audit)
    assert stats["crm_writes"] == 9
    assert len(store.list_crm()) == 9
    assert {row["email"] for row in store.list_crm()} == {normalize_email(row["email"]) for row in raw}
    ben = store.get_crm("ben.okoye@example.com")
    assert ben["name"] == "Ben Okoye"
    assert ben["phone"] == "4155550177"
    grace = store.get_crm("grace.lee@example.com")
    assert grace["monthly_kwh"] == "1150"


def test_placeholders_become_one_internal_task_each(tmp_path):
    assert usable_address("TBD") is False
    assert usable_address("see attached") is False
    assert usable_address("") is False
    assert usable_kwh("about 900") is None
    assert usable_kwh("n/a") is None
    assert usable_kwh("0") is None
    assert usable_kwh("1,150") == "1150"

    store, audit = _open(tmp_path)
    stats = _run(store, audit)
    tasks = {row["email"]: json.loads(row["missing"]) for row in store.list_tasks()}
    assert stats["task_writes"] == 4
    assert tasks == {
        "chiara.vogel@example.com": ["site_address"],
        "diego.santos@example.com": ["monthly_kwh"],
        "elena.novak@example.com": ["site_address", "monthly_kwh"],
        "hiro.tanaka@example.com": ["site_address"],
    }
    assert all(row["email"] not in {item["draft_id"] for item in store.list_outbox()} for row in store.list_tasks())
    assert store.list_outbox() == []


def test_blank_follow_up_does_not_wipe_a_usable_value(tmp_path):
    inbox = tmp_path / "inbox.json"
    inbox.write_text(
        json.dumps(
            [
                {
                    "name": "Ben Okoye",
                    "email": "ben.okoye@example.com",
                    "phone": "4155550177",
                    "site_address": "902 Market Street, San Francisco, CA 94103",
                    "monthly_kwh": "410",
                },
                {
                    "name": "Ben Okoye",
                    "email": "BEN.OKOYE@example.com",
                    "phone": "",
                    "site_address": "TBD",
                    "monthly_kwh": "n/a",
                },
            ]
        ),
        encoding="utf-8",
    )
    store, audit = _open(tmp_path)
    run(inbox, store, audit, sleep=lambda _s: None)
    ben = store.get_crm("ben.okoye@example.com")
    assert ben["site_address"] == "902 Market Street, San Francisco, CA 94103"
    assert ben["monthly_kwh"] == "410"
    assert ben["phone"] == "4155550177"
    assert len(store.list_crm()) == 1


def test_second_and_third_runs_add_no_crm_events_or_emails(tmp_path):
    store, audit = _open(tmp_path)
    first = _run(store, audit)
    assert first["event_writes"] == 8
    assert first["email_writes"] == 0
    assert len(store.list_events()) == 8
    assert len({row["slot"] for row in store.list_events()}) == 8

    again = _run(store, AuditLog(tmp_path / "state" / "audit.jsonl", run_id="second"))
    assert again["crm_writes"] == 0
    assert again["task_writes"] == 0
    assert again["event_writes"] == 0
    assert again["email_writes"] == 0

    for draft in store.list_drafts():
        if draft["email"] == "farid.malik@example.net":
            continue
        store.save_approval(draft["id"], "Sam Okonkwo", draft["body_sha256"])
    sent = _run(store, AuditLog(tmp_path / "state" / "audit.jsonl", run_id="send"))
    assert sent["crm_writes"] == 0
    assert sent["event_writes"] == 0
    assert sent["email_writes"] == 8
    assert len(store.list_outbox()) == 8

    quiet = _run(store, AuditLog(tmp_path / "state" / "audit.jsonl", run_id="third"))
    assert quiet["crm_writes"] == 0
    assert quiet["event_writes"] == 0
    assert quiet["email_writes"] == 0
    assert len(store.list_outbox()) == 8
    queued = [row for row in store.list_drafts() if row["status"] == "queued"]
    assert [row["email"] for row in queued] == ["farid.malik@example.net"]


def test_crash_at_step_4_resumes_to_the_same_state(tmp_path):
    clean_store, clean_audit = _open(tmp_path, "clean")
    _run(clean_store, clean_audit)
    expected = _snapshot(clean_store)
    clean_store.close()

    store, audit = _open(tmp_path, "crash")
    with pytest.raises(SystemExit) as caught:
        _run(store, audit, crash_after=4)
    assert caught.value.code == 2
    assert len(store.list_events()) == 1
    assert store.list_drafts() == []
    store.close()

    resumed, resumed_audit = _open(tmp_path, "crash")
    _run(resumed, resumed_audit)
    assert _snapshot(resumed) == expected


def test_crash_after_calendar_write_does_not_double_book(tmp_path):
    store, audit = _open(tmp_path)
    with pytest.raises(SystemExit):
        _run(store, audit, halt_after_write="schedule")
    first = store.list_events()
    assert len(first) == 1
    email = first[0]["email"]
    assert store.ledger_status(idempotency_key("schedule", email, {"intent": "discovery"})) is None
    store.close()

    resumed, resumed_audit = _open(tmp_path)
    stats = _run(resumed, resumed_audit)
    booked = [row for row in resumed.list_events() if row["email"] == email]
    assert len(booked) == 1
    assert booked[0]["slot"] == first[0]["slot"]
    assert stats["event_writes"] == 7


def test_transient_failure_retries_with_backoff_and_books_once(tmp_path):
    sleeps = []
    store, audit = _open(tmp_path)
    stats = _run(
        store,
        audit,
        sleep=sleeps.append,
        base_delay=0.05,
        failures={"grace.lee@example.com": 2},
    )
    grace = "grace.lee@example.com"
    assert stats["attempts"][grace] == 3
    assert sleeps == [0.05, 0.1]
    events = [row for row in store.list_events() if row["email"] == grace]
    assert len(events) == 1
    lines = [line for line in audit.read() if line["input"] == grace and line["step"] == "schedule"]
    assert sum(1 for line in lines if line["result"].startswith("attempt 1") or line["result"].startswith("attempt 2")) == 2


def test_permanent_failure_escalates_once_to_the_named_owner(tmp_path):
    store, audit = _open(tmp_path)
    _run(store, audit)
    rows = store.list_exceptions()
    assert len(rows) == 1
    assert rows[0]["owner"] == OWNER == "Priya Shah"
    assert rows[0]["entity_id"] == "farid.malik@example.net"
    assert rows[0]["step"] == "schedule"
    assert "3 attempts" in rows[0]["reason"]
    assert store.get_event("farid.malik@example.net") is None

    _run(store, AuditLog(tmp_path / "state" / "audit.jsonl", run_id="rerun"))
    assert len(store.list_exceptions()) == 1
    rerun_lines = [
        line
        for line in AuditLog(tmp_path / "state" / "audit.jsonl", run_id="read").read()
        if line["run_id"] == "rerun" and line["input"] == "farid.malik@example.net" and line["step"] == "schedule"
    ]
    assert rerun_lines
    assert all(line["result"] == "skipped: escalated" for line in rerun_lines)


def test_send_refuses_without_a_matching_approval(tmp_path):
    store, audit = _open(tmp_path)
    _run(store, audit)
    draft = store.get_draft_by_email("amira.hassan@example.com")
    assert draft["status"] == "queued"
    assert "[template draft — not a language model]" in draft["body"]
    with pytest.raises(ApprovalRequired):
        deliver(store, draft["id"])
    assert store.list_outbox() == []

    other = store.get_draft_by_email("ben.okoye@example.com")
    store.save_approval(other["id"], "Sam Okonkwo", other["body_sha256"])
    with pytest.raises(ApprovalRequired):
        deliver(store, draft["id"])

    store.save_approval(draft["id"], "Sam Okonkwo", "0" * 64)
    with pytest.raises(ApprovalRequired):
        deliver(store, draft["id"])
    assert store.list_outbox() == []
    assert store.get_draft(draft["id"])["status"] == "queued"

    with pytest.raises(ValueError):
        store.save_approval(draft["id"], "   ", draft["body_sha256"])
    with pytest.raises(ApprovalRequired):
        deliver(store, draft["id"])


def test_approved_send_is_read_back_and_matches(tmp_path):
    store, audit = _open(tmp_path)
    _run(store, audit)
    draft = store.get_draft_by_email("ines.costa@example.com")
    saved = store.save_approval(draft["id"], "Sam O'Brien", draft["body_sha256"])
    assert saved["by_name"] == "Sam O'Brien"
    sent, new = deliver(store, draft["id"])
    assert new is True
    assert sent["body"] == draft["body"]
    assert sent["email"] == "ines.costa@example.com"
    read_back = store.get_outbox(sent["id"])
    assert read_back["body"] == draft["body"]
    assert read_back["email"] == draft["email"]
    again, newer = deliver(store, draft["id"])
    assert newer is False
    assert again["id"] == sent["id"]
    assert len(store.list_outbox()) == 1


def test_every_write_has_an_audit_line_and_a_verification(tmp_path):
    store, audit = _open(tmp_path)
    _run(store, audit)
    lines = audit.read()
    required = {"ts", "run_id", "step", "key", "input", "result", "actor"}
    assert lines
    assert all(required <= set(line) for line in lines)
    assert all(line["actor"] == "agent" for line in lines)

    def verified(step, email):
        hits = [
            line
            for line in lines
            if line["step"] == step and line["input"] == email and line.get("verified") is True
        ]
        assert hits, (step, email)

    for row in store.list_crm():
        verified("register", row["email"])
    for row in store.list_tasks():
        verified("request_missing", row["email"])
    for row in store.list_events():
        verified("schedule", row["email"])
    for row in store.list_drafts():
        verified("draft", row["email"])
        assert row["status"] == "queued"

    refused = [line for line in lines if line["step"] == "send"]
    assert refused
    assert all(line["result"] == "refused: no approval" for line in refused)
    assert all(line.get("verified") is False for line in refused)


def test_recovered_booking_refreshes_a_queued_draft(tmp_path):
    store, audit = _open(tmp_path, "farid")
    _run(store, audit)
    before = store.get_draft_by_email("farid.malik@example.net")
    assert "could not book" in before["body"]
    assert store.get_event("farid.malik@example.net") is None

    recovered, recovered_audit = _open(tmp_path, "farid")
    stats = run(
        INBOX,
        recovered,
        recovered_audit,
        sleep=lambda _s: None,
        failures={},
        retry_escalated=True,
    )
    event = recovered.get_event("farid.malik@example.net")
    after = recovered.get_draft_by_email("farid.malik@example.net")
    assert event is not None
    assert event["slot"] in after["body"]
    assert after["status"] == "queued"
    assert after["body_sha256"] != before["body_sha256"]
    assert stats["event_writes"] == 1
    assert recovered.list_exceptions() == []
    with pytest.raises(ApprovalRequired):
        deliver(recovered, after["id"])


def test_idempotency_key_hashes_step_normalised_id_and_payload():
    payload = {"email": "ben.okoye@example.com", "intent": "discovery"}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    material = f"schedule|ben.okoye@example.com|{digest}"
    expect = hashlib.sha256(material.encode()).hexdigest()
    assert idempotency_key("schedule", " BEN.OKOYE@Example.com ", payload) == expect


def test_later_usable_value_updates_the_same_crm_row(tmp_path):
    inbox = tmp_path / "inbox.json"
    inbox.write_text(
        json.dumps(
            [
                {
                    "name": "Diego Santos",
                    "email": "diego.santos@example.com",
                    "phone": "4085550160",
                    "site_address": "44 Palm Court, San Jose, CA 95112",
                    "monthly_kwh": "about 900",
                },
                {
                    "name": "Diego Santos",
                    "email": "Diego.Santos@example.com",
                    "phone": "4085550160",
                    "site_address": "44 Palm Court, San Jose, CA 95112",
                    "monthly_kwh": "900",
                },
            ]
        ),
        encoding="utf-8",
    )
    store, audit = _open(tmp_path)
    run(inbox, store, audit, sleep=lambda _s: None, failures={})
    row = store.get_crm("diego.santos@example.com")
    assert row["monthly_kwh"] == "900"
    assert len(store.list_crm()) == 1
    assert store.list_tasks() == []


def test_cli_crash_and_approve(tmp_path):
    state = tmp_path / "cli-state"
    crashed = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "run",
            "--inbox",
            str(INBOX),
            "--state",
            str(state),
            "--crash-after",
            "4",
            "--backoff",
            "0",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert crashed.returncode == 2, crashed.stderr

    finished = subprocess.run(
        [sys.executable, "-m", "src.cli", "run", "--inbox", str(INBOX), "--state", str(state), "--backoff", "0"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr
    summary = json.loads(finished.stdout)
    assert summary["crm"] == 9
    assert summary["events"] == 8
    assert summary["drafts_queued"] == 9
    assert summary["outbox"] == 0
    assert summary["exceptions"] == 1

    store = Store(state / "orchestrator.sqlite")
    draft = store.get_draft_by_email("amira.hassan@example.com")
    store.close()
    approved = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "approve",
            draft["id"],
            "--by",
            "Sam Okonkwo",
            "--state",
            str(state),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert approved.returncode == 0, approved.stderr
    audit_lines = [
        json.loads(line)
        for line in (state / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    human = [line for line in audit_lines if line["step"] == "approve"]
    assert human[-1]["actor"] == "Sam Okonkwo"
    assert human[-1]["result"] == "approved"
    sent = subprocess.run(
        [sys.executable, "-m", "src.cli", "run", "--inbox", str(INBOX), "--state", str(state), "--backoff", "0"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert sent.returncode == 0, sent.stderr
    after = json.loads(sent.stdout)
    assert after["outbox"] == 1
    assert after["drafts_queued"] == 8

    refused = subprocess.run(
        [sys.executable, "-m", "src.cli", "approve", draft["id"], "--by", "   ", "--state", str(state)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode == 1


def test_messy_row_is_kept_or_rejected_on_purpose(tmp_path):
    inbox = tmp_path / "inbox.json"
    inbox.write_text(
        json.dumps(
            [
                {
                    "name": "Robert'); DROP TABLE crm;--",
                    "email": "robert@example.com",
                    "phone": "(415) 555-0101",
                    "site_address": "10 Oak Street, Berkeley, CA 94704",
                    "monthly_kwh": 640,
                },
                {
                    "name": "Ada Lovelace",
                    "email": "Ada <ADA@example.com>",
                    "phone": "4155550199",
                    "site_address": "1 Loop Road, Alameda, CA 94501",
                    "monthly_kwh": "640 kWh",
                },
                {
                    "name": "No Email",
                    "email": "not-an-email",
                    "phone": "1",
                    "site_address": "1",
                    "monthly_kwh": "0",
                },
            ]
        ),
        encoding="utf-8",
    )
    store, audit = _open(tmp_path)
    run(inbox, store, audit, sleep=lambda _s: None, failures={})
    assert {row["email"] for row in store.list_crm()} == {"robert@example.com", "ada@example.com"}
    robert = store.get_crm("robert@example.com")
    assert robert["name"] == "Robert'); DROP TABLE crm;--"
    assert robert["monthly_kwh"] == "640"
    assert store.get_crm("ada@example.com")["monthly_kwh"] == "640"
    assert store.conn.execute("SELECT 1 FROM crm").fetchone() is not None
    assert [row["raw_email"] for row in store.list_rejections()] == ["not-an-email"]
    rejected = [line for line in audit.read() if line["input"] == "not-an-email"]
    assert rejected
    assert rejected[0]["verified"] is True
    assert rejected[0]["key"]
    run(inbox, store, AuditLog(tmp_path / "state" / "audit.jsonl", run_id="again"), sleep=lambda _s: None, failures={})
    assert len(store.list_rejections()) == 1
    assert len(store.list_crm()) == 2


def test_editing_a_draft_after_approval_blocks_the_send(tmp_path):
    store, audit = _open(tmp_path)
    _run(store, audit)
    draft = store.get_draft_by_email("amira.hassan@example.com")
    store.save_approval(draft["id"], "Sam Okonkwo", draft["body_sha256"])
    store.conn.execute(
        "UPDATE drafts SET body = ?, body_sha256 = ? WHERE id = ?",
        ("Please wire funds today.", "f" * 64, draft["id"]),
    )
    store.conn.commit()
    with pytest.raises(ApprovalRequired):
        deliver(store, draft["id"])
    assert store.list_outbox() == []
    assert store.get_draft(draft["id"])["status"] == "queued"


def test_sent_text_stays_put_when_the_lead_changes(tmp_path):
    inbox = tmp_path / "inbox.json"
    first = {
        "name": "Ana Ruiz",
        "email": "ana.ruiz@example.com",
        "phone": "4155550166",
        "site_address": "8 Hill Street, Oakland, CA 94607",
        "monthly_kwh": "500",
    }
    inbox.write_text(json.dumps([first]), encoding="utf-8")
    store, audit = _open(tmp_path)
    run(inbox, store, audit, sleep=lambda _s: None, failures={})
    draft = store.get_draft_by_email("ana.ruiz@example.com")
    store.save_approval(draft["id"], "Sam Okonkwo", draft["body_sha256"])
    deliver(store, draft["id"])
    sent_body = store.list_outbox()[0]["body"]

    changed = dict(first, name="Ana Maria Ruiz")
    inbox.write_text(json.dumps([changed]), encoding="utf-8")
    run(inbox, store, AuditLog(tmp_path / "state" / "audit.jsonl", run_id="edit"), sleep=lambda _s: None, failures={})
    assert store.list_outbox()[0]["body"] == sent_body
    assert len(store.list_outbox()) == 1
    assert store.get_crm("ana.ruiz@example.com")["name"] == "Ana Maria Ruiz"
    flagged = [row for row in store.list_exceptions() if row["step"] == "draft"]
    assert len(flagged) == 1
    assert flagged[0]["owner"] == OWNER
    run(inbox, store, AuditLog(tmp_path / "state" / "audit.jsonl", run_id="edit2"), sleep=lambda _s: None, failures={})
    assert len([row for row in store.list_exceptions() if row["step"] == "draft"]) == 1


def test_every_crash_point_resumes_to_the_clean_run(tmp_path):
    clean_store, clean_audit = _open(tmp_path, "clean")
    _run(clean_store, clean_audit)
    expected = _snapshot(clean_store)
    clean_store.close()
    for step in (1, 4, 7, 15, 30, 45, 80):
        store, audit = _open(tmp_path, f"crash-{step}")
        try:
            _run(store, audit, crash_after=step)
        except SystemExit as exc:
            assert exc.code == 2
            store.close()
            resumed, resumed_audit = _open(tmp_path, f"crash-{step}")
            _run(resumed, resumed_audit)
            assert _snapshot(resumed) == expected
        else:
            assert _snapshot(store) == expected


def test_run_cannot_grant_an_approval(tmp_path):
    import sqlite3

    store = Store(tmp_path / "state" / "orchestrator.sqlite", approvals_mode="ro")
    with pytest.raises(PermissionError):
        store.save_approval("dft_x", "Sam Okonkwo", "ab")
    with pytest.raises(sqlite3.OperationalError):
        store.approval_conn.execute(
            "INSERT INTO approvals (draft_id, by_name, body_sha256, approved_at) VALUES ('a','b','c','d')"
        )
    source = (ROOT / "src" / "pipeline.py").read_text(encoding="utf-8")
    cli = (ROOT / "src" / "cli.py").read_text(encoding="utf-8")
    assert "save_approval" not in source
    assert 'approvals_mode="ro"' in cli


def test_cli_retry_books_when_the_fault_is_cleared(tmp_path):
    state = tmp_path / "retry-state"
    first = subprocess.run(
        [sys.executable, "-m", "src.cli", "run", "--inbox", str(INBOX), "--state", str(state), "--backoff", "0"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["exceptions"] == 1
    assert json.loads(first.stdout)["events"] == 8
    second = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "run",
            "--inbox",
            str(INBOX),
            "--state",
            str(state),
            "--backoff",
            "0",
            "--retry-escalated",
            "--no-faults",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert second.returncode == 0, second.stderr
    after = json.loads(second.stdout)
    assert after["exceptions"] == 0
    assert after["events"] == 9
    assert after["outbox"] == 0


def test_sources_do_not_import_network_libraries():
    banned = ("urllib", "requests", "smtplib", "http.client", "imaplib", "socket")
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in banned:
            assert name not in text, f"{path.name} mentions {name}"
