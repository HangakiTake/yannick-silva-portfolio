"""Thresholds from the plan. Labels in data/labels.json were written against the week notes."""

import json
import os
import re
import subprocess
from pathlib import Path

from workday_audit.audit import run_audit
from workday_audit.cost import monthly_cost
from workday_audit.extract import extract
from workday_audit.guide import render_guide
from workday_audit.llm import make_llm
from workday_audit.paths import CONFIG, DATA, ROOT
from workday_audit.recommend import recommend
from workday_audit.redact import javascript_redactor, redact, restore
from workday_audit.report import render_shortlist
from workday_audit.runner import run_inquiries
from workday_audit.score import rank, score_components
from workday_audit.workflow import ancestors, build_workflow, send_nodes

WEEKS = DATA / "weeks"
LABELS = json.loads((DATA / "labels.json").read_text(encoding="utf-8"))
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?:\(\d{3}\)\s*\d{3}[\s.\-]\d{4}|\b\d{3}[\s.\-]\d{3}[\s.\-]\d{4}|\+\d[\d\s().\-]{8,}\d)")


def week_text() -> str:
    return "\n".join((WEEKS / f"{name}.txt").read_text(encoding="utf-8") for name in ("week_a", "week_b", "week_c"))


def test_corpus_shape():
    mentions = LABELS["mentions"]
    assert len({m["week"] for m in mentions}) >= 3
    assert len(mentions) >= 45
    assert sum(1 for m in mentions if m["messy"]) >= 15
    assert len(LABELS["tasks"]) >= 30
    for mention in mentions:
        assert mention["anchor"] in (WEEKS / f"{mention['week']}.txt").read_text(encoding="utf-8")


def test_extraction_thresholds():
    extracted = extract(week_text())
    found = freq_ok = 0
    drops = []
    task_mentions = [m for m in LABELS["mentions"] if m["expect"] == "task"]
    by_id = {task["id"]: task for task in extracted.tasks}
    question_blob = "\n".join(q.quote for q in extracted.questions)
    ranges = {t["id"]: t for t in LABELS["tasks"]}
    for mention in task_mentions:
        task = by_id.get(mention["task_id"])
        evidence = "\n".join(task["evidence"]) if task else ""
        if mention["anchor"] in evidence:
            found += 1
            window = ranges[mention["task_id"]]
            flo, fhi = window["frequency_per_month"]
            mlo, mhi = window["minutes_per_run"]
            if flo <= task["frequency_per_month"] <= fhi and mlo <= task["minutes_per_run"] <= mhi:
                freq_ok += 1
        elif mention["anchor"] in question_blob:
            pass
        else:
            drops.append(mention["anchor"])
    for mention in LABELS["mentions"]:
        if mention["expect"] != "question":
            continue
        assert mention["anchor"] in question_blob
        assert mention["anchor"] not in "\n".join(e for t in extracted.tasks for e in t["evidence"])
    assert not drops, drops
    assert found / len(task_mentions) >= 0.90
    assert freq_ok / found >= 0.90
    # Mentioning a task four times must not multiply the monthly rate.
    inquiry = by_id["inquiry_replies"]
    assert inquiry["frequency_per_month"] < 30
    assert len(inquiry["evidence"]) >= 2


def test_redaction_thresholds():
    items = json.loads((DATA / "pii_items.json").read_text(encoding="utf-8"))
    corpus = (DATA / "pii_corpus.txt").read_text(encoding="utf-8")
    assert len(items) >= 60
    for item in items:
        assert item["text"] in corpus
    result = redact(corpus)
    missed = [item for item in items if item["text"] in result.text]
    assert len(items) - len(missed) >= 0.98 * len(items)
    assert restore(result.text, result.mapping) == corpus
    emails = [i["text"] for i in items if i["kind"] == "email"]
    phones = [i["text"] for i in items if i["kind"] == "phone"]
    for raw in emails + phones:
        assert raw not in result.text
    assert EMAIL.findall(result.text) == []
    assert PHONE.findall(result.text) == []


def test_javascript_redactor_matches_python():
    corpus = (DATA / "pii_corpus.txt").read_text(encoding="utf-8")
    script = javascript_redactor() + "\nprocess.stdout.write(JSON.stringify(redact(require('fs').readFileSync(0,'utf8'))));"
    proc = subprocess.run(["node", "-e", script], input=corpus.encode(), capture_output=True, check=True)
    out = json.loads(proc.stdout)
    py = redact(corpus)
    assert out["text"] == py.text
    assert out["mapping"] == py.mapping


def test_tool_recommendations():
    extracted = {t["id"]: t for t in recommend(extract(week_text()).tasks)}
    misses = []
    for label in LABELS["tasks"]:
        got = extracted[label["id"]]["tool"]
        if got != label["tool"]:
            misses.append(f"{label['id']}: expected {label['tool']}, got {got}")
    assert len(LABELS["tasks"]) >= 30
    assert 1 - len(misses) / len(LABELS["tasks"]) >= 0.80
    assert misses == []
    for task in extracted.values():
        if task["customer_facing"] and task["tool"] != "dont_automate":
            assert task["requires_approval"]
            assert "approval" in task["reason"].lower()


def test_scoring_is_reproducible_and_weights_reorder():
    frame = rank(recommend(extract(week_text()).tasks))
    again = rank(recommend(extract(week_text()).tasks))
    assert frame["id"].tolist() == again["id"].tolist()
    assert frame.iloc[0]["id"] == "inquiry_replies"
    # Every score is the documented formula on that row's own fields.
    for row in frame.to_dict(orient="records"):
        expect = round(score_components(row["hours_saved"], row["effort"], row["risk"], {"hours": row["w_hours"], "effort": row["w_effort"], "risk": row["w_risk"]}), 6)
        assert row["score"] == expect
    cfg = json.loads((CONFIG / "scoring.json").read_text(encoding="utf-8"))
    example = cfg["reorder_example"]
    weights = cfg["weights"]
    high = score_components(**example["high_hours"], weights=weights)
    low = score_components(**example["low_effort"], weights=weights)
    assert high > low
    heavy = {**weights, "effort": example["high_effort_weight"]}
    assert score_components(**example["low_effort"], weights=heavy) > score_components(**example["high_hours"], weights=heavy)


def test_workflow_structure():
    workflow = build_workflow()
    names = [n["name"] for n in workflow["nodes"]]
    assert len(names) == len(set(names))
    for source, conn in workflow["connections"].items():
        assert source in names
        for output in conn["main"]:
            for link in output:
                assert link["node"] in names
    blob = json.dumps(workflow)
    assert "sk-ant" not in blob
    assert "sk-" not in blob
    for node in workflow["nodes"]:
        for cred in (node.get("credentials") or {}).values():
            assert set(cred) <= {"id", "name"}
            assert cred["name"]
            assert cred["id"] == ""
    sends = send_nodes(workflow)
    assert sends
    for node in sends:
        assert node["disabled"] is True
        assert "Human approval" in ancestors(workflow, node["name"])
    assert workflow["active"] is False
    draft = next(n for n in workflow["nodes"] if n["name"] == "Save draft reply")
    send = next(n for n in workflow["nodes"] if n["name"] == "Send reply")
    assert "$('Map fields')" in json.dumps(draft["parameters"])
    assert "$('Map fields')" in json.dumps(send["parameters"])
    assert "Add lead row" not in ancestors(workflow, "Save draft reply")
    prompt = json.loads((CONFIG / "prompts.json").read_text(encoding="utf-8"))["inquiry_system"]
    assert prompt[:40] in blob


def test_runner_drafts_and_accuracy():
    emails = json.loads((DATA / "inquiries.json").read_text(encoding="utf-8"))
    assert len(emails) >= 30
    llm, status = make_llm("mock")
    assert status == "mock"
    result = run_inquiries(emails, llm)
    assert result["sent"] == []
    correct = 0
    for email, out in zip(emails, result["results"]):
        assert out["status"] == "draft_awaiting_approval"
        assert out["sent"] is False
        assert "not sent" in out["draft_body"].lower()
        expect = email["expect"]
        if (out["category"], out["urgency"], out["service"]) == (expect["category"], expect["urgency"], expect["service"]):
            correct += 1
    assert correct / len(emails) >= 0.95
    payload = json.dumps(llm.payloads)
    assert EMAIL.findall(payload) == []
    assert PHONE.findall(payload) == []
    for row in result["sheet"].rows:
        assert row["sent"] is False
        assert EMAIL.findall(json.dumps(row)) == []


def test_guide_covers_nodes_prompt_and_cost():
    audit = run_audit(week_text())
    top = audit["ranked"].iloc[0].to_dict()
    html = render_guide(top, "html")
    markdown = render_guide(top, "md")
    cost = monthly_cost()
    for node in build_workflow()["nodes"]:
        assert node["name"] in html
        assert node["notes"][:40] in html
    assert "Where to edit the prompt" in html
    assert "config/prompts.json" in html
    assert "Human approval" in html
    assert "€24" in html or "€" + str(cost["n8n_eur"]) in html
    assert cost["as_of"] in html
    assert f"{cost['claude_usd']:.4f}" in html
    assert "2026-11-03" in markdown
    assert "not sent" in html.lower() or "never sends" in html.lower()
    page = render_shortlist(audit["ranked"], audit["extraction"].questions, audit["redaction"].counts)
    assert "priya.raman@northwind-cafe.example" not in page
    assert "(503) 555-0148" not in page


def test_live_mode_not_run_without_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    llm, status = make_llm("live")
    assert llm is None
    assert status == "not_run"


def test_cost_comes_from_config():
    cfg = json.loads((CONFIG / "costs.json").read_text(encoding="utf-8"))
    cost = monthly_cost(cfg)
    inquiries = cfg["assumptions"]["inquiries_per_month"]
    expect = inquiries * (
        cfg["assumptions"]["avg_input_tokens"] * cfg["prices"]["claude_input_usd_per_mtok"]
        + cfg["assumptions"]["avg_output_tokens"] * cfg["prices"]["claude_output_usd_per_mtok"]
    ) / 1_000_000
    assert cost["claude_usd"] == round(expect, 4)
    assert cost["n8n_eur"] == cfg["prices"]["n8n_cloud_starter_eur_billed_monthly"]
    assert cost["as_of"] == cfg["as_of"]


def test_repo_has_no_secrets_and_no_banned_name():
    banned = "Global" + " Fund"
    key_prefix = "sk-" + "ant-"
    access_key = re.compile("AKIA" + r"[0-9A-Z]{16}")
    checked = 0
    for path in ROOT.rglob("*"):
        if path.suffix.lower() not in {".py", ".json", ".md", ".html", ".txt", ".yml", ".yaml", ".j2"}:
            continue
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert banned.lower() not in text.lower()
        assert key_prefix not in text
        assert access_key.search(text) is None
        checked += 1
    assert checked > 10
    # The public pages added beside the demo are scanned too.
    for rel in ("../../projects/workday-automation-audit.html", "../../index.html"):
        path = (ROOT / rel).resolve()
        if path.exists():
            text = path.read_text(encoding="utf-8")
            assert banned.lower() not in text.lower()
