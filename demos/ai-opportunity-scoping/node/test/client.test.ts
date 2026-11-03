import assert from "node:assert/strict";
import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { OpenAI, PebblecartClient, liveClient, loadTools, toOpenAITools, validateArgs } from "../src/client.ts";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const port = 8765;
const base = `http://127.0.0.1:${port}`;

let server: ChildProcess;

async function waitForHealth(): Promise<void> {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      const response = await fetch(`${base}/health`);
      if (response.ok) return;
    } catch {
      // The server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error("fake API did not start");
}

test.before(async () => {
  server = spawn("python3", ["-m", "uvicorn", "src.api:app", "--port", String(port), "--log-level", "warning"], {
    cwd: root,
    stdio: "ignore",
  });
  await waitForHealth();
});

test.after(() => {
  server.kill("SIGTERM");
});

test("openai package loads and live mode stays off without a key", () => {
  assert.equal(typeof OpenAI, "function");
  const previous = process.env.OPENAI_API_KEY;
  delete process.env.OPENAI_API_KEY;
  assert.equal(liveClient(), null);
  if (previous) process.env.OPENAI_API_KEY = previous;
  const tools = toOpenAITools(loadTools());
  assert.deepEqual(tools.map((tool) => tool.function.name), [
    "lookup_order",
    "check_refund_policy",
    "issue_refund",
    "open_ticket",
    "escalate_to_human",
  ]);
});

test("malformed tool arguments are rejected before any HTTP call", async () => {
  const checked = validateArgs("lookup_order", { order_id: "nope" });
  assert.ok("error" in checked);
  assert.match(checked.error, /order_id/);
  let called = false;
  const original = globalThis.fetch;
  globalThis.fetch = async () => {
    called = true;
    throw new Error("fetch should not run");
  };
  try {
    const client = new PebblecartClient(base);
    const result = await client.execute("lookup_order", { order_id: "nope" });
    assert.equal(result.status, "rejected");
    assert.equal(called, false);
  } finally {
    globalThis.fetch = original;
  }
});

test("mock client looks up an order and refunds only inside the policy", async () => {
  const client = new PebblecartClient(base);
  const lookup = await client.run(["Where is order PBL-1001?"]);
  assert.deepEqual(lookup.calls.map((call) => call.tool), ["lookup_order"]);
  assert.equal(lookup.calls[0].arguments.order_id, "PBL-1001");
  assert.equal(lookup.calls[0].status, "ok");
  assert.equal(lookup.calls[0].output?.status, "delivered");
  assert.equal(lookup.calls[0].output?.item_name, "Kettle");

  const refund = await client.run(["Please refund PBL-1001. It arrived damaged."]);
  assert.deepEqual(refund.calls.map((call) => call.tool), ["lookup_order", "check_refund_policy", "issue_refund"]);
  assert.equal(refund.calls.every((call) => call.status === "ok"), true);
  assert.equal(refund.reply, "I issued the refund.");

  const over = await client.run(["Refund the full $120 on PBL-1002. It arrived damaged."]);
  assert.deepEqual(over.calls.map((call) => call.tool), ["lookup_order", "check_refund_policy", "escalate_to_human"]);
  assert.equal(over.calls.some((call) => call.tool === "issue_refund"), false);
  assert.equal(over.reply, "I did not issue a refund. A person has this case.");
  const refunds = await (await fetch(`${base}/refunds`)).json();
  const ids = refunds.refunds.map((row: { order_id: string }) => row.order_id);
  assert.ok(ids.includes("PBL-1001"));
  assert.equal(ids.includes("PBL-1002"), false);
});
