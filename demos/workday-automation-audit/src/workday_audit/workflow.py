"""Build the importable n8n workflow for the top pick: inquiry replies.

Credentials are names only. The send node exists so the approval gate is real,
and it ships disabled. The Python runner never calls it.
"""

from __future__ import annotations

import json

from .cost import load_costs
from .paths import CONFIG
from .redact import javascript_redactor

_PROMPT = json.loads((CONFIG / "prompts.json").read_text(encoding="utf-8"))["inquiry_system"]


def _node(node_id: str, name: str, ntype: str, version: float, x: int, y: int, parameters: dict, notes: str, credentials: dict | None = None, disabled: bool = False) -> dict:
    node = {
        "id": node_id,
        "name": name,
        "type": ntype,
        "typeVersion": version,
        "position": [x, y],
        "parameters": parameters,
        "notes": notes,
    }
    if credentials:
        node["credentials"] = credentials
    if disabled:
        node["disabled"] = True
    return node


def _cred(name: str) -> dict:
    return {"id": "", "name": name}


def build_workflow() -> dict:
    model = load_costs()["prices"]["claude_model"]
    # An n8n expression, so the redacted body is inserted when the node runs.
    json_body = (
        "={{ JSON.stringify({ model: "
        + json.dumps(model)
        + ", max_tokens: 800, system: "
        + json.dumps(_PROMPT)
        + ", messages: [{ role: 'user', content: $json.redacted_body }] }) }}"
    )
    redact_js = javascript_redactor() + (
        "\nconst item = $input.first().json;\n"
        "const raw = [item.subject, item.text, item.body, item.snippet].filter(Boolean).join('\\n');\n"
        "const result = redact(raw);\n"
        "if (/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}/.test(result.text)) {\n"
        "  throw new Error('Redaction left an email address. Refusing to call Claude.');\n"
        "}\n"
        "return [{ json: { ...item, redacted_body: result.text, redaction_counts: result.counts } }];\n"
    )
    nodes = [
        _node("manual", "Run one email now", "n8n-nodes-base.manualTrigger", 1, 0, 80, {},
              "Start here while you are testing. Paste one email in the next node with the pin data, or use the Gmail trigger."),
        _node("gmail-in", "New inquiry email", "n8n-nodes-base.gmailTrigger", 1.2, 0, 280,
              {"event": "messageReceived", "simple": False},
              "Fires when a new email arrives. The raw email is in this node's output. Turn off saving execution data if the inbox is sensitive.",
              {"gmailOAuth2": _cred("Gmail account")}),
        _node("redact", "Redact personal data", "n8n-nodes-base.code", 2, 280, 180,
              {"jsCode": redact_js},
              "Replaces names, emails, phones, amounts and street addresses with placeholders before Claude sees the text. Same rules as config/redaction.json."),
        _node("claude", "Claude classify and draft", "n8n-nodes-base.httpRequest", 4.2, 560, 180,
              {
                  "method": "POST",
                  "url": "https://api.anthropic.com/v1/messages",
                  "authentication": "genericCredentialType",
                  "genericAuthType": "httpHeaderAuth",
                  "sendHeaders": True,
                  "headerParameters": {"parameters": [
                      {"name": "anthropic-version", "value": "2023-06-01"},
                      {"name": "content-type", "value": "application/json"},
                  ]},
                  "sendBody": True,
                  "specifyBody": "json",
                  "jsonBody": json_body,
              },
              "Calls Claude with the redacted email and the system prompt. The API key lives in the n8n credential named 'Anthropic API' (header x-api-key). It is not in this file. Edit the prompt in the JSON body, or rebuild this file after editing config/prompts.json.",
              {"httpHeaderAuth": _cred("Anthropic API")}),
        _node("map", "Map fields", "n8n-nodes-base.code", 2, 840, 180,
              {"jsCode": "const raw = $json.body ?? $json.data ?? $json.content ?? $json;\nconst text = typeof raw === 'string' ? raw : JSON.stringify(raw);\nconst start = text.indexOf('{'); const end = text.lastIndexOf('}');\nif (start < 0) throw new Error('Claude did not return JSON. Check the HTTP node response path.');\nconst fields = JSON.parse(text.slice(start, end + 1));\nconst draft = String(fields.draft_body || '');\nif (!/not sent/i.test(draft)) throw new Error('Draft is missing the not-sent line.');\nreturn [{ json: { ...fields, sent: false, draft_status: 'draft_awaiting_approval' } }];"},
              "Reads the JSON fields Claude returned: category, urgency, service, draft subject and draft body. Stops if the draft does not say it has not been sent. Later nodes read these fields by name, so a sheet response cannot wipe them."),
        _node("sheet", "Add lead row", "n8n-nodes-base.googleSheets", 4.5, 1120, 40,
              {
                  "operation": "append",
                  "documentId": "={{ $env.LEADS_SHEET_ID }}",
                  "sheetName": "Leads",
                  "columns": {
                      "mappingMode": "defineBelow",
                      "value": {
                          "category": "={{ $('Map fields').item.json.category }}",
                          "urgency": "={{ $('Map fields').item.json.urgency }}",
                          "service": "={{ $('Map fields').item.json.service }}",
                          "draft_status": "={{ $('Map fields').item.json.draft_status }}",
                          "sent": "={{ $('Map fields').item.json.sent }}",
                      },
                  },
              },
              "Appends one row to the Leads tab: category, urgency, service, draft status, sent=false. Set LEADS_SHEET_ID in the n8n environment. Create those five column headers in row 1 before the first run.",
              {"googleSheetsOAuth2Api": _cred("Google Sheets account")}),
        _node("draft", "Save draft reply", "n8n-nodes-base.gmail", 2.1, 1120, 280,
              {
                  "resource": "draft",
                  "operation": "create",
                  "subject": "={{ $('Map fields').item.json.draft_subject }}",
                  "message": "={{ $('Map fields').item.json.draft_body }}",
              },
              "Saves a Gmail draft with the subject and body from Map fields. It does not send.",
              {"gmailOAuth2": _cred("Gmail account")}),
        _node("approval", "Human approval", "n8n-nodes-base.wait", 1.1, 1680, 180,
              {"resume": "webhook", "httpMethod": "GET", "options": {}},
              "Pauses until a person opens the approval link. Leave this node in the path. That is the approval switch, on."),
        _node("approved", "Approved?", "n8n-nodes-base.if", 2, 1960, 180,
              {"conditions": {"options": {"caseSensitive": True, "typeValidation": "strict"}, "combinator": "and", "conditions": [
                  {"id": "approved", "leftValue": "={{ $json.approved }}", "rightValue": True, "operator": {"type": "boolean", "operation": "true"}}
              ]}},
              "True only when the approval link was confirmed. The false branch stops at 'Leave as draft'."),
        _node("hold", "Leave as draft", "n8n-nodes-base.noOp", 1, 2240, 320, {},
              "Approval was not given. The draft stays in Gmail. Nothing is sent."),
        _node("send", "Send reply", "n8n-nodes-base.gmail", 2.1, 2240, 40,
              {
                  "resource": "message",
                  "operation": "send",
                  "subject": "={{ $('Map fields').item.json.draft_subject }}",
                  "message": "={{ $('Map fields').item.json.draft_body }}",
              },
              "Sends the reply. This node ships disabled. It is only reachable after Human approval and only on the true branch of Approved?. Enable it only after you have used the draft path for a while.",
              {"gmailOAuth2": _cred("Gmail account")}, disabled=True),
    ]
    def link(target: str) -> list:
        return [[{"node": target, "type": "main", "index": 0}]]

    connections = {
        "Run one email now": {"main": link("Redact personal data")},
        "New inquiry email": {"main": link("Redact personal data")},
        "Redact personal data": {"main": link("Claude classify and draft")},
        "Claude classify and draft": {"main": link("Map fields")},
        "Map fields": {"main": [[
            {"node": "Add lead row", "type": "main", "index": 0},
            {"node": "Save draft reply", "type": "main", "index": 0},
        ]]},
        "Save draft reply": {"main": link("Human approval")},
        "Human approval": {"main": link("Approved?")},
        "Approved?": {"main": [
            [{"node": "Send reply", "type": "main", "index": 0}],
            [{"node": "Leave as draft", "type": "main", "index": 0}],
        ]},
    }
    return {
        "name": "Inquiry draft reply (demo, fictional bookkeeper)",
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": {"executionOrder": "v1"},
        "pinData": {},
        "meta": {"templateCredsSetupCompleted": False, "demo": "synthetic inbox, send node disabled"},
    }


def send_nodes(workflow: dict) -> list[dict]:
    found = []
    for node in workflow["nodes"]:
        params = node.get("parameters") or {}
        operation = str(params.get("operation", "")).lower()
        if operation == "send" or node["type"] == "n8n-nodes-base.emailSend":
            found.append(node)
    return found


def ancestors(workflow: dict, name: str) -> set[str]:
    reverse: dict[str, set[str]] = {}
    for source, conn in workflow["connections"].items():
        for output in conn.get("main", []):
            for link in output:
                reverse.setdefault(link["node"], set()).add(source)
    seen, stack = set(), [name]
    while stack:
        current = stack.pop()
        for parent in reverse.get(current, ()):
            if parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return seen
