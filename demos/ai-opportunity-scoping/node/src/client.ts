/**
 * Thin Node client for the same tool schema the Python agent uses.
 * Mock mode plans the tool calls locally and executes them against the fake API.
 * Live mode is only constructed when OPENAI_API_KEY is set. This file does not call it.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import OpenAI from "openai";

export { OpenAI };

type Tool = {
  name: string;
  description: string;
  parameters: {
    additionalProperties?: boolean;
    required?: string[];
    properties: Record<string, { type?: string; enum?: string[]; pattern?: string; minLength?: number; maxLength?: number }>;
  };
};

type Step =
  | { type: "message"; content: string }
  | { type: "tool"; name: string; arguments: Record<string, unknown> };

const here = path.dirname(fileURLToPath(import.meta.url));

export function loadTools(): Tool[] {
  const schemaPath = path.resolve(here, "../../shared/tools.schema.json");
  return JSON.parse(readFileSync(schemaPath, "utf8")).tools as Tool[];
}

export function toOpenAITools(tools: Tool[] = loadTools()) {
  return tools.map((tool) => ({
    type: "function" as const,
    function: {
      name: tool.name,
      description: tool.description,
      parameters: tool.parameters,
    },
  }));
}

export function liveClient(): OpenAI | null {
  const key = process.env.OPENAI_API_KEY;
  if (!key) return null;
  return new OpenAI({ apiKey: key });
}

export function normalizeOrderId(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const compact = value.trim().toUpperCase().replace(/\s+/g, "");
  const match = compact.match(/^PBL-?(\d{4,})$/);
  if (!match) return null;
  return `PBL-${match[1]}`;
}

export function validateArgs(name: string, args: unknown, tools: Tool[] = loadTools()): { args: Record<string, unknown> } | { error: string } {
  const tool = tools.find((item) => item.name === name);
  if (!tool) return { error: `unknown tool: ${name}` };
  if (args === null || typeof args !== "object" || Array.isArray(args)) return { error: "arguments must be an object" };
  const record = args as Record<string, unknown>;
  const properties = tool.parameters.properties;
  for (const key of Object.keys(record)) {
    if (!(key in properties)) return { error: `${key} is not a valid argument` };
  }
  const normalized: Record<string, unknown> = {};
  for (const key of tool.parameters.required ?? []) {
    if (record[key] === undefined || record[key] === null) return { error: `${key} is required` };
  }
  for (const [key, schema] of Object.entries(properties)) {
    if (record[key] === undefined) continue;
    const value = record[key];
    if (key === "order_id" || schema.pattern) {
      const orderId = normalizeOrderId(value);
      if (!orderId) return { error: "order_id is required and must be a string like PBL-1001" };
      normalized[key] = orderId;
      continue;
    }
    if (schema.enum) {
      if (typeof value !== "string" || !schema.enum.includes(value.trim().toLowerCase())) {
        return { error: `${key} must be one of: ${schema.enum.join(", ")}` };
      }
      normalized[key] = value.trim().toLowerCase();
      continue;
    }
    if (schema.type === "number") {
      if (typeof value !== "number" || Number.isNaN(value)) return { error: `${key} must be a number` };
      normalized[key] = value;
      continue;
    }
    if (schema.type === "string") {
      if (typeof value !== "string" || value.trim() === "") return { error: `${key} is required` };
      if (schema.maxLength && value.trim().length > schema.maxLength) return { error: `${key} must be ${schema.maxLength} characters or fewer` };
      normalized[key] = value.trim();
    }
  }
  return { args: normalized };
}

type ToolResult = { tool: string; status: string; arguments: Record<string, unknown>; output: Record<string, unknown> | null; error: string | null };

export class PebblecartClient {
  constructor(private baseUrl: string) {}

  async run(turns: string[]): Promise<{ calls: ToolResult[]; reply: string }> {
    const messages: Array<{ role: string; content?: string; name?: string; result?: ToolResult }> = [];
    const calls: ToolResult[] = [];
    let reply = "";
    for (const turn of turns) {
      messages.push({ role: "user", content: turn });
      for (let round = 0; round < 8; round += 1) {
        const next = plan(messages);
        if (next.type === "message") {
          reply = next.content;
          messages.push({ role: "assistant", content: next.content });
          break;
        }
        const result = await this.execute(next.name, next.arguments);
        calls.push(result);
        messages.push({ role: "tool", name: next.name, result });
      }
    }
    return { calls, reply };
  }

  async execute(name: string, args: Record<string, unknown>): Promise<ToolResult> {
    const checked = validateArgs(name, args);
    if ("error" in checked) {
      return { tool: name, status: "rejected", arguments: {}, output: null, error: checked.error };
    }
    const url = this.baseUrl.replace(/\/$/, "");
    const orderId = String(checked.args.order_id ?? "");
    let response: Response;
    if (name === "lookup_order") {
      response = await fetch(`${url}/orders/${orderId}`);
    } else if (name === "check_refund_policy") {
      response = await fetch(`${url}/orders/${orderId}/refund-policy?reason=${encodeURIComponent(String(checked.args.reason))}`);
    } else if (name === "issue_refund") {
      response = await fetch(`${url}/refunds`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(checked.args) });
    } else if (name === "open_ticket") {
      response = await fetch(`${url}/tickets`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(checked.args) });
    } else if (name === "escalate_to_human") {
      response = await fetch(`${url}/escalations`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(checked.args) });
    } else {
      return { tool: name, status: "rejected", arguments: checked.args, output: null, error: `unknown tool: ${name}` };
    }
    if (response.status === 409) {
      const body = await response.json();
      return { tool: name, status: "not_executed", arguments: checked.args, output: null, error: String(body.detail ?? "not executed") };
    }
    if (!response.ok) {
      return { tool: name, status: "error", arguments: checked.args, output: null, error: `HTTP ${response.status}` };
    }
    return { tool: name, status: "ok", arguments: checked.args, output: await response.json(), error: null };
  }
}

function textOf(messages: Array<{ role: string; content?: string }>): string {
  return messages.filter((message) => message.role === "user").map((message) => message.content ?? "").join("\n");
}

function lastResult(messages: Array<{ role: string; name?: string; result?: ToolResult }>, name: string): ToolResult | null {
  let found: ToolResult | null = null;
  for (const message of messages) {
    if (message.role === "tool" && message.name === name && message.result) found = message.result;
  }
  return found;
}

function orderId(text: string): string | null {
  const match = text.match(/\bpbl[\s-]?\d{4,}\b/i);
  if (!match) return null;
  const digits = match[0].match(/\d{4,}/);
  return digits ? `PBL-${digits[0]}` : null;
}

function amountOf(text: string): number | null {
  const found = [...text.matchAll(/\$\s*(\d+(?:\.\d+)?)/g)];
  if (!found.length) return null;
  return Number(found[found.length - 1][1]);
}

function reasonOf(text: string): string | null {
  const lowered = text.toLowerCase();
  if (lowered.includes("not as described")) return "not_as_described";
  if (lowered.includes("changed my mind") || lowered.includes("changed mind")) return "changed_mind";
  if (lowered.includes("wrong item")) return "wrong_item";
  if (/\blate\b/.test(lowered)) return "late_delivery";
  if (lowered.includes("damaged") || lowered.includes("broken")) return "damaged";
  return null;
}

function plan(messages: Array<{ role: string; content?: string; name?: string; result?: ToolResult }>): Step {
  const text = textOf(messages);
  const lowered = text.toLowerCase();
  const id = orderId(text);
  const refund = /\b(refund|money back)\b/.test(lowered);
  const status = /\b(where|status|track)\b/.test(lowered) && !refund;
  if (refund) return planRefund(messages, text, id);
  if (status) return planStatus(messages, id);
  return { type: "message", content: "I can look up an order, check a refund, or open a ticket. I need an order id like PBL-1001." };
}

function planStatus(messages: Array<{ role: string; name?: string; result?: ToolResult }>, id: string | null): Step {
  if (!id) return { type: "message", content: "I need the order id. It looks like PBL- and at least four digits." };
  const lookup = lastResult(messages, "lookup_order");
  if (!lookup) return { type: "tool", name: "lookup_order", arguments: { order_id: id } };
  if (lookup.status !== "ok") return { type: "message", content: "The order system did not answer. I did not change anything." };
  if (!lookup.output?.found) return { type: "message", content: `I could not find order ${id}.` };
  return { type: "message", content: `Order ${id} is ${String(lookup.output.status)}.` };
}

function planRefund(messages: Array<{ role: string; name?: string; result?: ToolResult }>, text: string, id: string | null): Step {
  if (!id) return { type: "message", content: "I need the order id. It looks like PBL- and at least four digits." };
  const lookup = lastResult(messages, "lookup_order");
  if (!lookup) return { type: "tool", name: "lookup_order", arguments: { order_id: id } };
  if (lookup.status !== "ok") return { type: "message", content: "The order system did not answer. I did not change anything." };
  if (!lookup.output?.found) {
    if (lastResult(messages, "escalate_to_human")) return { type: "message", content: "I did not issue a refund. A person has this case." };
    return { type: "tool", name: "escalate_to_human", arguments: { order_id: id, reason: "order not found" } };
  }
  const reason = reasonOf(text);
  if (!reason) return { type: "message", content: "What is the reason: damaged, wrong item, not as described, late delivery, or changed mind?" };
  const policy = lastResult(messages, "check_refund_policy");
  if (!policy) return { type: "tool", name: "check_refund_policy", arguments: { order_id: id, reason } };
  if (policy.status !== "ok") return { type: "message", content: "The order system did not answer. I did not change anything." };
  if (lastResult(messages, "issue_refund") || lastResult(messages, "escalate_to_human")) {
    const issued = lastResult(messages, "issue_refund");
    if (issued && issued.status === "ok") return { type: "message", content: "I issued the refund." };
    return { type: "message", content: "I did not issue a refund. A person has this case." };
  }
  const total = Number(lookup.output.total_usd ?? 0);
  const explicit = amountOf(text);
  const requested = explicit ?? total;
  const cap = Number(policy.output?.max_auto_refund_usd ?? 0);
  if (policy.output?.eligible && requested <= cap) {
    return { type: "tool", name: "issue_refund", arguments: { order_id: id, amount_usd: requested, reason } };
  }
  const why = policy.output?.eligible
    ? `Above the automatic cap for this order (${cap} USD).`
    : String(policy.output?.detail ?? "Out of policy.");
  return {
    type: "tool",
    name: "escalate_to_human",
    arguments: { order_id: id, reason: why, requested_amount_usd: requested },
  };
}
