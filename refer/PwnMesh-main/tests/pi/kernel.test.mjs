import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { appendFileSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { runKernel as kernel } from "../../runtime/pi/kernel.mjs";
import { nativeSession, sessionEntries, temporarySessionPath } from "./session-fixture.mjs";

const runKernel = (input, host) => kernel({
  ...input, sessionPath: input.sessionPath ?? input.session?.file ?? temporarySessionPath(),
}, host);

const assistant = (text, calls = []) => ({
  role: "assistant", content: [...(text ? [{ type: "text", text }] : []),
    ...calls.map((id) => ({ type: "tool_use", id, name: "echo", input: { value: id } }))],
  stop_reason: calls.length ? "tool_use" : "end_turn",
});
const echo = { name: "echo", description: "Echo a value", input_schema: {
  type: "object", properties: { value: { type: "string" } }, required: ["value"], additionalProperties: false,
} };
const clone = (value) => structuredClone(value);
function harness(model, hooks = {}) {
  const events = [], saves = [], tools = [], requests = [];
  const host = async (method, params) => {
    if (hooks[method]) return hooks[method](params);
    if (method === "event") { events.push(clone(params)); return {}; }
    if (method === "save") { saves.push(clone(params)); return {}; }
    if (method === "input_size") return { bytes: Buffer.byteLength(JSON.stringify(params)) };
    if (method === "model") { requests.push(clone(params)); return model(params, requests.length); }
    if (method === "tool") { tools.push(params); return { text: params.input.value }; }
    return {};
  };
  return { host, events, saves, tools, requests };
}

test("executes the actual Pi loop, persists the assistant before effects, and groups Go tool receipts", async () => {
  const h = harness((_request, call) => call === 1 ? assistant("", ["one", "two"]) : assistant("done"));
  const original = h.host;
  h.host = async (method, params) => {
    if (method === "tool") {
      assert.ok(sessionEntries(h.saves.at(-1).session).some((entry) =>
        entry.message?.role === "assistant" && entry.message.content.some((block) => block.id === params.id)));
    }
    return original(method, params);
  };
  const result = await runKernel({ type: "run", prompt: "Use two tools.", tools: [echo] }, h.host);
  assert.equal(result.error, undefined);
  assert.equal(result.text, "done");
  assert.equal(h.tools.length, 2);
  assert.equal(h.requests.length, 2);
  const receipts = result.history.filter((message) => message.content.some((block) => block.type === "tool_result"));
  assert.equal(receipts.length, 1);
  assert.deepEqual(receipts[0].content.map((block) => block.tool_use_id), ["one", "two"]);
  assert.deepEqual(receipts[0].content.map((block) => block.content), ["one", "two"]);
  assert.equal(result.session.header.version, 3);
  assert.equal(sessionEntries(result.session).filter((entry) => entry.message?.role === "toolResult").length, 2);
  const emitted = h.events.filter((event) => event.type === "message_end").map((event) => event.message.sequence);
  assert.deepEqual(emitted, [1, 2, 3, 4, 5]);
  assert.equal(result.lastSequence, 5);
  assert.equal(receipts[0].sequence, 4);
});

test("structured tool metadata survives error receipts without entering model context", async () => {
  const details = { complete: false, fullOutputPath: "/retained/diagnostic.txt", truncated: true };
  const h = harness((_request, call) => call === 1 ? assistant("", ["partial-tool"]) : assistant("handled"), {
    tool: () => ({ text: "partial command output", details, isError: true, error: "command canceled" }),
  });
  const result = await runKernel({ type: "run", prompt: "Inspect.", tools: [echo] }, h.host);
  assert.equal(result.error, undefined);
  const receipt = sessionEntries(result.session).find((entry) => entry.message?.role === "toolResult").message;
  assert.equal(receipt.isError, true);
  assert.deepEqual(receipt.details, details);
  assert.match(receipt.content.map((block) => block.text ?? "").join("\n"), /partial command output\ncommand canceled/);
  assert.ok(!JSON.stringify(h.requests.at(-1)).includes("/retained/diagnostic.txt"));
  const restored = await runKernel({ type: "inspect", session: result.session }, () => {});
  assert.deepEqual(sessionEntries(restored.session).find((entry) => entry.message?.role === "toolResult").message.details, details);
});

test("restores canonical Pi entries and settles interrupted calls without repeating tools", async () => {
  const h = harness(() => assistant("", ["already-sent"]));
  let interrupted;
  const original = h.host;
  h.host = async (method, params) => {
    if (method === "save" && params.history.at(-1)?.role === "assistant") {
      interrupted ??= clone(params);
      throw new Error("simulated transport loss after durable assistant");
    }
    return original(method, params);
  };
  await runKernel({ type: "run", prompt: "Run the tool.", tools: [echo] }, h.host);
  assert.ok(interrupted);
  const resumed = harness((request) => {
    assert.ok(request.messages.some((message) => message.content.some((block) =>
      block.type === "tool_result" && block.tool_use_id === "already-sent" && block.is_error)));
    return assistant("recovered");
  });
  const result = await runKernel({ type: "run", ...interrupted,
    history: [{ role: "user", content: [{ type: "text", text: "POISONED CACHE" }] }], tools: [echo] }, resumed.host);
  assert.equal(result.error, undefined);
  assert.equal(result.text, "recovered");
  assert.equal(resumed.tools.length, 0);
  assert.ok(!JSON.stringify(resumed.requests).includes("POISONED CACHE"));
});

test("inspect is read-only and edit saves native Pi session instructions", async () => {
  const h = harness(() => assistant("complete"));
  const original = await runKernel({ type: "run", prompt: "Task." }, h.host);
  const inspect = await runKernel({ type: "inspect", session: original.session },
    () => { throw new Error("inspect must not call host"); });
  assert.deepEqual(inspect.session, original.session);
  const edit = harness(() => { throw new Error("edit must not call model"); });
  const edited = await runKernel({ ...inspect, type: "edit", instructions: ["Follow-up instruction."] }, edit.host);
  assert.equal(edited.history.at(-1).content[0].text, "Follow-up instruction.");
  assert.equal(sessionEntries(edited.session).at(-1).message.role, "user");
  assert.equal(edited.lastSequence, original.lastSequence + 1);
});

test("failed model attempts remain in native history but are omitted from recovery context", async () => {
  for (const canceled of [false, true]) {
    const failed = harness(() => {
      throw Object.assign(new Error("provider interrupted"), {
        kind: "transport", canceled,
        response: assistant("unfinished answer", ["never-execute"]),
      });
    });
    const result = await runKernel({ type: "run", prompt: "Keep investigating.", tools: [echo] }, failed.host);
    assert.equal(result.error, "provider interrupted");
    const entry = sessionEntries(result.session).find((entry) => entry.message?.stopReason === (canceled ? "aborted" : "error"));
    assert.ok(entry, "the original failed response must be retained");
    assert.equal(entry.message.errorMessage, "provider interrupted");
    assert.ok(entry.message.content.some((block) => block.text === "unfinished answer"));
    assert.ok(sessionEntries(result.session).some((edit) => edit.type === "context_edit" && edit.targetId === entry.id && edit.replacement === null));
    assert.equal(failed.tools.length, 0);
    assert.ok(!JSON.stringify(result.history).includes("unfinished answer"));
    assert.ok(failed.events.some((event) => event.type === "model_attempt_failed"));
    assert.ok(!failed.events.some((event) => event.type === "message_end" && event.message?.role === "assistant"));
    const recovered = harness((request) => {
      assert.ok(!JSON.stringify(request).includes("unfinished answer"));
      assert.ok(!JSON.stringify(request).includes("never-execute"));
      return assistant("recovered");
    });
    const resumed = await runKernel({ type: "run", session: result.session, tools: [echo] }, recovered.host);
    assert.equal(resumed.text, "recovered");
    assert.equal(resumed.error, undefined);
    assert.equal(recovered.tools.length, 0);
    assert.ok(sessionEntries(resumed.session).some((entry) => entry.message?.errorMessage === "provider interrupted"));
  }
});

test("an interrupted partial tool response retains raw bytes and usage without enabling the tool", async () => {
  const response = { ...assistant("partial text"), usage: { input_tokens: 12, output_tokens: 3 } };
  response.content.push({ type: "tool_use", id: "incomplete-call", name: "echo" });
  const h = harness(() => { throw Object.assign(new Error("stream interrupted"), { kind: "transport", response }); });
  const result = await runKernel({ type: "run", prompt: "Task", tools: [echo] }, h.host);
  assert.equal(result.errorKind, "transport");
  assert.equal(result.error, "stream interrupted");
  const failures = sessionEntries(result.session).filter((entry) => entry.message?.stopReason === "error");
  assert.equal(failures.length, 1);
  assert.deepEqual(failures[0].message._pwnmeshRawResponse, response);
  assert.equal(failures[0].message.usage.input, 12);
  assert.equal(failures[0].message.usage.output, 3);
  assert.ok(!JSON.stringify(result.history).includes("partial text"));
  assert.equal(h.tools.length, 0);
});

test("each tool receipt is durable before the next effect and survives an interrupted batch", async () => {
  const h = harness((_request, call) => call === 1 ? assistant("", ["first", "second"]) : assistant("done"));
  let partial;
  const original = h.host;
  h.host = async (method, params) => {
    if (method === "tool" && params.id === "second") {
      partial = clone(h.saves.at(-1));
      assert.equal(sessionEntries(partial.session).at(-1).message.toolCallId, "first");
      throw new Error("crash before second effect");
    }
    return original(method, params);
  };
  await runKernel({ type: "run", prompt: "Two tools", tools: [echo] }, h.host);
  assert.ok(partial);
  const resumed = harness((request) => {
    const receipts = request.messages.flatMap((message) => message.content).filter((block) => block.type === "tool_result");
    assert.equal(receipts.length, 2);
    assert.equal(receipts[0].tool_use_id, "first");
    assert.equal(receipts[0].content, "first");
    assert.equal(receipts[0].is_error, false);
    assert.equal(receipts[1].tool_use_id, "second");
    assert.equal(receipts[1].is_error, true);
    return assistant("resumed");
  });
  const result = await runKernel({ ...partial, type: "run", tools: [echo] }, resumed.host);
  assert.equal(result.error, undefined);
  assert.equal(resumed.tools.length, 0);
  assert.equal(result.history.filter((message) => message.content[0]?.type === "tool_result").length, 1);
});

test("repair distinguishes a reused call ID in a later interrupted turn", async () => {
  const h = harness(() => { throw new Error("edit cannot request a model"); });
  const history = [
    { role: "user", content: [{ type: "text", text: "Task" }], sequence: 1 },
    { ...assistant("", ["same-id"]), sequence: 2 },
    { role: "user", content: [{ type: "tool_result", tool_use_id: "same-id", content: "old receipt" }], sequence: 3 },
    { ...assistant("", ["same-id"]), sequence: 4 },
  ];
  const result = await runKernel({ type: "edit", session: nativeSession(history) }, h.host);
  const receipt = result.history.at(-1);
  assert.equal(receipt.sequence, 5);
  assert.equal(receipt.content[0].tool_use_id, "same-id");
  assert.equal(receipt.content[0].is_error, true);
  assert.match(receipt.content[0].content, /not replayed/);
});

test("Pi compaction retains canonical entries, projects summaries, and resumes without Go history", async () => {
  const old = [];
  for (let i = 0; i < 8; ++i) {
    old.push({ role: "user", content: [{ type: "text", text: `Question ${i} ` + "context ".repeat(100) }], sequence: i * 2 + 1 });
    old.push({ ...assistant(`Answer ${i} ` + "evidence ".repeat(100)), sequence: i * 2 + 2,
      usage: { input_tokens: 5000, output_tokens: 10 } });
  }
  const h = harness((request) => assistant(request.maxTokens ? "Retained task and confirmed evidence." : "compacted result"));
  const result = await runKernel({ type: "run", session: nativeSession(old), prompt: "Continue.",
    context: { tokens: 3000, targetTokens: 1000 } }, h.host);
  assert.equal(result.error, undefined);
  assert.equal(result.compactionCount, 1);
  assert.ok(sessionEntries(result.session).some((entry) => entry.type === "compaction"));
  assert.ok(sessionEntries(result.session).length > old.length);
  assert.ok(result.history.length < old.length);
  assert.ok(h.requests.some((request) => request.maxTokens > 0));
  assert.deepEqual(h.events.filter((event) => event.type.startsWith("context_")).map((event) => event.type),
    ["context_compaction_prepared", "context_compacted"]);
  const restored = await runKernel({ type: "inspect", session: result.session }, () => {});
  assert.equal(restored.compactionCount, 1);
  assert.deepEqual(restored.history, result.history);
  assert.equal(restored.taskPrompt, old[0].content[0].text);
});

test("the kernel requires a bound file checkpoint and rejects inline session migration", async () => {
  const host = () => { throw new Error("invalid session must fail before callbacks"); };
  await assert.rejects(kernel({ type: "run", prompt: "Task" }, host), /bound sessionPath/);
  const session = nativeSession([{ role: "user", content: [{ type: "text", text: "Task" }] }]);
  for (const invalid of [{ header: session.header, entries: sessionEntries(session) }, { ...session, entries: [] }]) {
    await assert.rejects(kernel({ type: "run", sessionPath: session.file, session: invalid }, host), /native session file checkpoint/);
  }
});

test("malformed host request sizing cannot fall back to a guessed budget", async () => {
  const h = harness(() => { throw new Error("invalid sizing must not reach model"); }, { input_size: () => ({}) });
  const result = await runKernel({ type: "run", prompt: "Task", context: { bytes: 1000 } }, h.host);
  assert.equal(result.error, "Invalid host request size");
  assert.equal(h.requests.length, 0);
});

test("a history projection cannot bootstrap a conversation without a Pi session", async () => {
  await assert.rejects(runKernel({ type: "run", history: [assistant("untrusted cache")] },
    () => { throw new Error("must reject before calling host"); }), /requires a canonical Pi session/);
});

test("a provider overflow uses Pi compaction once and persists the retry allowance", async () => {
  const old = [];
  for (let i = 0; i < 8; ++i) {
    old.push({ role: "user", content: [{ type: "text", text: `Question ${i} ` + "context ".repeat(50) }] });
    old.push(assistant(`Answer ${i} ` + "evidence ".repeat(50)));
  }
  let normal = 0, summaries = 0;
  const h = harness((request) => {
    if (request.maxTokens) { ++summaries; return assistant("Short factual checkpoint."); }
    if (++normal === 1) throw Object.assign(new Error("provider context limit"), { kind: "context_overflow" });
    return assistant("Recovered from overflow.");
  });
  const result = await runKernel({ type: "run", session: nativeSession(old), prompt: "Continue.", context: { targetTokens: 700 } }, h.host);
  assert.equal(result.error, undefined);
  assert.equal(normal, 2);
  assert.ok(summaries >= 1 && summaries <= 2); // Pi may separately summarize a split turn.
  assert.equal(result.compactionCount, 1);
  assert.ok(h.saves.some((saved) => sessionEntries(saved.session).some((entry) =>
    entry.customType === "pwnmesh.context_overflow" && entry.data.pending === true)));
  const latest = sessionEntries(result.session).filter((entry) => entry.customType === "pwnmesh.context_overflow").at(-1);
  assert.equal(latest.data.pending, false);
});

test("restarting after failed overflow compaction cannot grant another forced retry", async () => {
  const history = [];
  for (let i = 0; i < 8; ++i) {
    history.push({ role: "user", content: [{ type: "text", text: "context ".repeat(60) }] });
    history.push(assistant("evidence ".repeat(60)));
  }
  const failed = harness((request) => {
    throw Object.assign(new Error(request.maxTokens ? "summary unavailable" : "context too large"),
      { kind: request.maxTokens ? "transport" : "context_overflow",
        response: { ...assistant(request.maxTokens ? "partial summary" : "overflow response"), usage: { output_tokens: 7 } } });
  });
  const first = await runKernel({ type: "run", session: nativeSession(history), prompt: "Continue.", context: { targetTokens: 700 } }, failed.host);
  assert.equal(first.errorKind, "transport");
  const failures = sessionEntries(first.session).filter((entry) => entry.message?.stopReason === "error");
  assert.equal(failures.length, 2);
  assert.deepEqual(failures.map((entry) => entry.message._pwnmeshRequestKind), ["turn", "summary"]);
  assert.ok(failures.every((entry) => entry.message.usage.output === 7));
  assert.ok(!JSON.stringify(first.history).includes("partial summary"));
  const saved = failed.saves.at(-1);
  assert.ok(sessionEntries(saved.session).some((entry) => entry.customType === "pwnmesh.context_overflow" && entry.data.pending));
  const resumed = harness((request) => {
    assert.equal(request.maxTokens, 0);
    throw Object.assign(new Error("still too large"), { kind: "context_overflow" });
  });
  const second = await runKernel({ ...saved, type: "run", context: { targetTokens: 700 } }, resumed.host);
  assert.equal(second.errorKind, "context_overflow");
  assert.equal(resumed.requests.length, 1);
});

test("proactive summary failure records one attempt and retains a later independent failure", async () => {
  const history = [];
  for (let i = 0; i < 8; ++i) {
    history.push({ role: "user", content: [{ type: "text", text: "context ".repeat(100) }] });
    history.push({ ...assistant("evidence ".repeat(100)), usage: { input_tokens: 5000, output_tokens: 10 } });
  }
  const failed = harness((request) => {
    assert.ok(request.maxTokens > 0);
    throw Object.assign(new Error("summary interrupted"), { kind: "transport",
      response: { ...assistant("partial proactive summary"), usage: { output_tokens: 7 } } });
  });
  const first = await runKernel({ type: "run", session: nativeSession(history), prompt: "Continue.",
    context: { tokens: 3000, targetTokens: 1000 } }, failed.host);
  assert.equal(first.errorKind, "transport");
  assert.equal(failed.requests.length, 1);
  const attempts = sessionEntries(first.session).filter((entry) => entry.message?.stopReason === "error");
  assert.equal(attempts.length, 1);
  assert.equal(attempts[0].message._pwnmeshRequestKind, "summary");
  assert.equal(attempts[0].message.usage.output, 7);
  assert.equal(failed.events.filter((event) => event.type === "model_attempt_failed").length, 1);
  assert.ok(!JSON.stringify(first.history).includes("partial proactive summary"));

  const resumed = harness((request) => {
    assert.equal(request.maxTokens, 0);
    assert.ok(!JSON.stringify(request).includes("partial proactive summary"));
    throw Object.assign(new Error("later turn interrupted"), { kind: "transport",
      response: { ...assistant("independent partial turn"), usage: { output_tokens: 3 } } });
  });
  const second = await runKernel({ type: "run", session: first.session }, resumed.host);
  const allAttempts = sessionEntries(second.session).filter((entry) => entry.message?.stopReason === "error");
  assert.equal(second.error, "later turn interrupted");
  assert.equal(allAttempts.length, 2);
  assert.deepEqual(allAttempts.map((entry) => entry.message._pwnmeshRequestKind), ["summary", "turn"]);
  assert.equal(allAttempts[1].message.usage.output, 3);
  assert.equal(resumed.events.filter((event) => event.type === "model_attempt_failed").length, 1);
});

test("phase tool restrictions and hook replacement snapshots govern the next Pi request", async () => {
  const h = harness((request) => { assert.deepEqual(request.tools, []); return assistant("finished"); }, {
    before_request: () => ({ toolsDisabledReason: "Concluding", instructions: ["Return final output."] }),
  });
  const result = await runKernel({ type: "run", prompt: "Task", tools: [echo] }, h.host);
  assert.equal(result.error, undefined);
  assert.ok(h.requests[0].messages.some((message) => message.content.some((block) => block.text === "Return final output.")));
});

test("Pi refuses every truncated tool call even when the partial arguments form valid JSON", async () => {
  const h = harness((_request, call) => call === 1
    ? { ...assistant("", ["truncated"]), stop_reason: "max_tokens" }
    : assistant("explained without replay"));
  const result = await runKernel({ type: "run", prompt: "Task", tools: [echo] }, h.host);
  assert.equal(result.error, undefined);
  assert.equal(h.tools.length, 0);
  const receipt = result.history.flatMap((message) => message.content).find((block) => block.type === "tool_result");
  assert.equal(receipt.tool_use_id, "truncated");
  assert.equal(receipt.is_error, true);
  assert.match(receipt.content, /truncated/);
});

test("hard context size measures the actual host request including tools and system text", async () => {
  const huge = { ...echo, description: "large schema metadata ".repeat(1000) };
  let checked = false;
  const h = harness(() => { throw new Error("oversized request must not reach the model"); }, {
    input_size: (request) => {
      assert.equal(request.tools[0].description, huge.description);
      assert.equal(request.messages[0].role, "system");
      checked = true;
      return { bytes: 50000 };
    },
  });
  const result = await runKernel({ type: "run", prompt: "Task", tools: [huge], context: { bytes: 1000 } }, h.host);
  assert.ok(checked);
  assert.equal(result.errorKind, "context_budget");
  assert.equal(h.requests.length, 0);
});

test("an oversized Pi summary is rejected before reaching the host model", async () => {
  const history = [];
  for (let i = 0; i < 8; ++i) {
    history.push({ role: "user", content: [{ type: "text", text: "large context ".repeat(200) }] });
    history.push(assistant("evidence ".repeat(200)));
  }
  const h = harness(() => { throw new Error("oversized summary must not be sent"); });
  const result = await runKernel({ type: "run", session: nativeSession(history), prompt: "Continue.",
    context: { bytes: 3000, targetTokens: 400 } }, h.host);
  assert.equal(result.errorKind, "context_budget");
  assert.equal(h.requests.length, 0);
});

test("native Pi JSONL stores full history while policy snapshots stay small", async () => {
  const directory = mkdtempSync(join(tmpdir(), "pwnmesh-pi-native-"));
  try {
    const sessionPath = join(directory, "pi-session.jsonl");
    const history = [];
    for (let i = 0; i < 8; ++i) {
      history.push({ role: "user", content: [{ type: "text", text: `Question ${i} ` + "context ".repeat(9000) }] });
      history.push(assistant(i === 7 ? "Recent short result." : `Answer ${i} ` + "evidence ".repeat(9000)));
    }
    for (let i = 0; i < 4; ++i) {
      history.push({ role: "user", content: [{ type: "text", text: "recent ".repeat(60) }] });
      history.push(assistant("brief ".repeat(60)));
    }
    const h = harness((request) => assistant(request.maxTokens ? "Short summary." : "done"));
    const result = await runKernel({ type: "run", sessionPath, session: nativeSession(history, directory, sessionPath), prompt: "Continue.",
      context: { tokens: 3000, targetTokens: 1000 } }, h.host);
    assert.equal(result.error, undefined);
    assert.equal(result.session.file, sessionPath);
    assert.ok(JSON.stringify(result.session).length < 2000);
    assert.ok(statSync(sessionPath).size > 1024 * 1024);
    assert.ok(!Object.hasOwn(result.session, "entries"));
    const inspected = await runKernel({ type: "inspect", sessionPath, session: result.session },
      () => { throw new Error("inspect must not invoke callbacks"); });
    assert.deepEqual(inspected.history, result.history);
    assert.deepEqual(inspected.session, result.session);
  } finally { rmSync(directory, { recursive: true, force: true }); }
});

test("native checkpoints ignore crash tails, preserve branches, and reject altered committed bytes", async () => {
  const directory = mkdtempSync(join(tmpdir(), "pwnmesh-pi-crash-"));
  try {
    const sessionPath = join(directory, "pi-session.jsonl");
    const h = harness(() => assistant("committed"));
    const first = await runKernel({ type: "run", sessionPath, prompt: "Task." }, h.host);
    assert.equal(first.error, undefined);
    appendFileSync(sessionPath, JSON.stringify({
      type: "message", id: "deadbeef", parentId: first.session.leafId, timestamp: new Date().toISOString(),
      message: { role: "user", content: [{ type: "text", text: "UNCOMMITTED ORPHAN" }], timestamp: 0, _pwnmeshSequence: 100 },
    }) + "\n" + '{"type":');
    const rawBeforeInspect = readFileSync(sessionPath);
    const unchanged = await runKernel({ type: "inspect", sessionPath, session: first.session }, () => {});
    assert.deepEqual(unchanged.history, first.history);
    assert.deepEqual(readFileSync(sessionPath), rawBeforeInspect);
    const resumed = harness((request) => {
      assert.ok(!JSON.stringify(request).includes("UNCOMMITTED ORPHAN"));
      return assistant("new branch");
    });
    const result = await runKernel({ type: "run", sessionPath, session: first.session, prompt: "Continue." }, resumed.host);
    assert.equal(result.error, undefined);
    assert.ok(readFileSync(sessionPath, "utf8").includes("UNCOMMITTED ORPHAN"));
    const original = await runKernel({ type: "inspect", sessionPath, session: first.session }, () => {});
    assert.deepEqual(original.history, first.history);
    await assert.rejects(runKernel({ type: "inspect", sessionPath: join(directory, "other.jsonl"), session: first.session }, () => {}),
      /path does not match/);
    appendFileSync(sessionPath, JSON.stringify({
      type: "message", id: first.session.leafId, parentId: null, timestamp: new Date().toISOString(),
      message: { role: "user", content: [{ type: "text", text: "forged duplicate leaf" }], timestamp: 0 },
    }) + "\n");
    await assert.rejects(runKernel({ type: "edit", sessionPath, session: first.session }, () => {}),
      /duplicate Pi session/);
    const changed = readFileSync(sessionPath, "utf8").replace("Task.", "Tusk.");
    writeFileSync(sessionPath, changed);
    await assert.rejects(runKernel({ type: "inspect", sessionPath, session: first.session }, () => {}), /hash mismatch/);
  } finally { rmSync(directory, { recursive: true, force: true }); }
});

test("a summary must meet the configured target as well as the larger trigger budget", async () => {
  const history = [];
  for (let i = 0; i < 8; ++i) {
    history.push({ role: "user", content: [{ type: "text", text: "old context ".repeat(150) }] });
    history.push(assistant("result"));
  }
  const h = harness((request) => {
    assert.ok(request.maxTokens);
    return assistant("summary ".repeat(600));
  });
  const result = await runKernel({ type: "run", session: nativeSession(history), prompt: "Continue.",
    context: { tokens: 3000, targetTokens: 600 } }, h.host);
  assert.equal(result.errorKind, "context_budget");
  assert.match(result.error, /compacted context/);
  assert.ok(h.requests.every((request) => request.maxTokens > 0));
});

test("vendored kernel algorithms exactly match the recorded upstream source hashes", () => {
  const base = new URL("../../runtime/pi/upstream/", import.meta.url);
  const manifest = JSON.parse(readFileSync(new URL("provenance.json", base), "utf8"));
  assert.equal(manifest.version, "1.3.0");
  for (const file of manifest.files) {
    assert.equal(createHash("sha256").update(readFileSync(new URL(file.path, base))).digest("hex"), file.sha256, file.path);
  }
  assert.ok(manifest.files.some((file) => file.path.endsWith("agent-loop.ts")));
  assert.ok(manifest.files.some((file) => file.path.endsWith("session-manager.ts")));
  assert.ok(manifest.files.some((file) => file.path.endsWith("compaction.ts")));
});
