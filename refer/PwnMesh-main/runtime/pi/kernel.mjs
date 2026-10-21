import "./source-loader.mjs";
import { createInterface } from "node:readline";
import { pathToFileURL } from "node:url";
import { modelForHost, fromMessage, fromMessages, fromUsage, textOf, toAssistant } from "./kernel-wire.mjs";
import { openNativeSession } from "./session-file.mjs";

// Dynamic imports run after the source aliases have been installed. These are
// Pi's actual implementations, not a PwnMesh reimplementation of their APIs.
const { Agent } = await import("./upstream/packages/agent/src/agent.ts");
const { SessionManager } = await import("./upstream/packages/coding-agent/src/core/session-manager.ts");
const { convertToLlm } = await import("./upstream/packages/coding-agent/src/core/messages.ts");
const { compact, prepareCompaction, estimateProjectedContextTokens, estimateTokens } = await import("./upstream/packages/coding-agent/src/core/compaction/compaction.ts");
const { AssistantMessageEventStream, getCurrentTools, getCurrentSystemPrompt, getToolStateChanges, createInitialSystemMessage } = await import("./source-api.mjs");

const ENGINE = { engine: "pi", version: "1.3.0", agent: "Agent", session: "SessionManager", context: "prepareCompaction/compact/buildSessionContext" };
const SYSTEM = "Work toward the assigned task using available tools. Distinguish confirmed facts from guesses. Follow the current request's output contract.";
const copy = (value) => JSON.parse(JSON.stringify(value));
const failure = (value) => Object.assign(new Error(typeof value === "string" ? value : value?.message ?? "Host callback failed"), typeof value === "object" ? value : {});

export async function runKernel(input, host) {
  // The host may reserve larger event IDs from an excluded crash tail.
  // Conversation content and context still come only from the Pi snapshot.
  let manager, disk, lastSequence = input.lastSequence ?? 0, compactionCount = 0, agent;
  let lastError, terminalText, preparationFailure;
  const config = { ...input };
  const model = modelForHost(input.model);
  const callback = async (method, params = {}) => {
    try { return await host(method, params) ?? {}; }
    catch (error) { lastError = error instanceof Error ? error : failure(error); throw lastError; }
  };
  const load = (snapshot) => {
    disk = openNativeSession({ ...input, session: snapshot }, SessionManager);
    manager = disk.manager;
    compactionCount = manager.getEntries().filter((entry) => entry.type === "compaction").length;
    for (const entry of manager.getEntries()) lastSequence = Math.max(lastSequence, entry.message?._pwnmeshSequence ?? 0);
  };
  if (input.session) load(input.session);
  else {
    if (input.history?.length) throw new Error("Conversation history requires a canonical Pi session");
    disk = openNativeSession(input, SessionManager);
    manager = disk.manager;
  }
  const snapshot = () => {
    const reference = disk.snapshot();
    manager = disk.manager;
    return reference;
  };
  const projected = () => manager.buildSessionContext().messages;
  const history = () => fromMessages(convertToLlm(projected()));
  const state = () => ({ history: history(), session: snapshot(), lastSequence, compactionCount });
  const emit = (event) => callback("event", { ...event, at: event.at ?? new Date().toISOString() });
  const save = () => callback("save", state());
  const append = async (message, sequence = 0) => {
    if (message.role !== "system") message._pwnmeshSequence = sequence || ++lastSequence;
    manager.appendMessage(message);
    if (message.role !== "system") await emit({ type: "message_end", message: fromMessage(message) });
    await save();
  };
  const persistFailure = async (message) => {
    if (message._pwnmeshFailureRecorded) return;
    message._pwnmeshFailureRecorded = true;
    message._pwnmeshSequence = ++lastSequence;
    const entryID = manager.appendMessage(message);
    manager.appendContextEdit(entryID, null);
    await emit({ type: "model_attempt_failed", error: message.errorMessage, message: fromMessage(message) });
    await save();
  };
  const failedMessage = (error, response, kind) => {
    const empty = { role: "assistant", content: [{ type: "text", text: "" }] };
    let message;
    try { message = toAssistant(response?.role === "assistant" ? response : empty, model); }
    catch {
      // A failed stream may stop inside a tool call. Keep its raw response as
      // audit metadata; incomplete arguments never become executable calls.
      const content = (response?.content ?? []).filter((block) => ["text", "thinking", "redacted_thinking"].includes(block.type));
      message = toAssistant({ ...response, role: "assistant", content }, model);
      message._pwnmeshRawResponse = copy(response);
    }
    return { ...message, stopReason: error.canceled ? "aborted" : "error", errorMessage: error.message,
      _pwnmeshRequestKind: kind, _pwnmeshErrorKind: error.kind };
  };
  const instructions = async (texts) => {
    for (const text of texts ?? []) if (text) await append({ role: "user", content: [{ type: "text", text }], timestamp: Date.now() });
  };
  const apply = async (update) => {
    if (update?.session) {
      load(update.session);
      lastSequence = Math.max(lastSequence, update.lastSequence ?? 0);
    }
    for (const key of ["tools", "context", "toolsDisabledReason", "taskPrompt", "pinnedInstructions", "contextData", "contextDataPrefixes"]) {
      if (update && Object.hasOwn(update, key)) config[key] = update[key];
    }
    await instructions(update?.instructions);
  };
  const repair = async () => {
    const messages = projected();
    const calls = new Map();
    for (const message of messages) {
      if (message.role === "system") continue;
      if (message.role === "toolResult") {
        if (!calls.has(message.toolCallId)) throw new Error("Pi session contains an orphan or duplicate tool result");
        calls.delete(message.toolCallId);
        continue;
      }
      if (calls.size) throw new Error("Pi session has an interrupted tool group before a later message");
      if (message.role === "assistant") {
        for (const block of message.content) if (block.type === "toolCall") {
          if (calls.has(block.id)) throw new Error("Pi session contains duplicate tool calls");
          calls.set(block.id, block.name);
        }
      }
    }
    const missing = [...calls];
    if (!missing.length) return;
    const sequence = ++lastSequence;
    const settled = missing.map(([id, name]) => ({
      role: "toolResult", toolCallId: id, toolName: name, isError: true,
      content: [{ type: "text", text: "Interrupted before a durable tool receipt. This call was not replayed; verify any side effects before retrying." }],
      timestamp: Date.now(), _pwnmeshSequence: sequence,
    }));
    for (const message of settled) manager.appendMessage(message);
    await emit({ type: "message_end", message: fromMessages(settled)[0] });
    await save();
  };

  if (input.type === "inspect") return { type: "result", text: "", ...state(),
    taskPrompt: textOf(manager.getBranch().find((entry) => entry.message?.role === "user")?.message) };
  await repair();
  if (input.type === "edit") {
    await instructions(input.instructions);
    await save();
    return { type: "result", text: "", ...state() };
  }

  const definitions = input.tools ?? [];
  const makeTools = () => (config.tools ?? []).map((definition) => ({
    name: definition.name, label: definition.name, description: definition.description,
    parameters: definition.input_schema,
    async execute(id, args) {
      const result = await callback("tool", { id, name: definition.name, input: args });
      let text = result.text ?? "";
      if (result.error || result.isError) {
        const error = typeof result.error === "string" ? result.error : result.error?.message ?? "Tool failed";
        if (text !== error) text = text ? `${text}\n${error}` : error;
      }
      return { content: [{ type: "text", text }], details: result.details ?? undefined,
        isError: Boolean(result.error || result.isError) };
    },
  }));
  const activeTools = () => config.toolsDisabledReason ? [] : makeTools();
  if (!projected().some((message) => message.role === "system")) {
    manager.appendMessage(createInitialSystemMessage(input.systemPrompt ?? SYSTEM, definitions.map((tool) => ({
      name: tool.name, description: tool.description, parameters: tool.input_schema,
    }))));
  }
  const contextMessages = () => {
    let messages = projected();
    const pinned = [...new Set([config.taskPrompt, ...(config.pinnedInstructions ?? []), ...(config.contextData ?? [])].filter(Boolean))];
    if (config.contextDataPrefixes?.length) {
      messages = messages.filter((message) => message.role !== "user" || !config.contextDataPrefixes.some((prefix) => textOf(message).startsWith(prefix)));
    }
    const existing = new Set(messages.filter((message) => message.role === "user").map(textOf));
    const missing = pinned.filter((text) => !existing.has(text));
    if (missing.length) {
      const index = messages.findIndex((message) => message.role !== "system");
      messages = [...messages.slice(0, index < 0 ? messages.length : index),
        ...missing.map((text) => ({ role: "user", content: [{ type: "text", text }], timestamp: 0, _pwnmeshPinned: true })),
        ...messages.slice(index < 0 ? messages.length : index)];
    }
    return messages;
  };
  const contextTokens = (messages) => estimateProjectedContextTokens(manager.buildSessionProjection(), manager.getBranch()).tokens
    + messages.filter((message) => message._pwnmeshPinned).reduce((sum, message) => sum + estimateTokens(message), 0);
  const modelRequest = (messages) => {
    const wire = fromMessages(messages.filter((message) => message.role !== "system"));
    const system = getCurrentSystemPrompt(messages);
    if (system) wire.unshift({ role: "system", content: [{ type: "text", text: system }] });
    const tools = getCurrentTools(messages).map((tool) => ({
      name: tool.name, description: tool.description, input_schema: tool.parameters,
    }));
    return { messages: wire, tools };
  };
  const inputBytes = async (messages) => {
    const request = modelRequest(convertToLlm(messages));
    const result = await callback("input_size", request);
    if (!Number.isSafeInteger(result.bytes) || result.bytes < 0) throw new Error("Invalid host request size");
    return result.bytes;
  };
  const overflowPending = () => [...manager.getBranch()].reverse().find((entry) =>
    entry.type === "custom" && entry.customType === "pwnmesh.context_overflow")?.data?.pending === true;
  const streamFn = async (_model, context, options = {}) => {
    const stream = new AssistantMessageEventStream();
    let response;
    const requestModel = async (messages) => {
      try { return await callback("model", { ...modelRequest(messages), maxTokens: options.maxTokens ?? 0 }); }
      catch (error) {
        const message = failedMessage(error, error.response, options.maxTokens ? "summary" : "turn");
        await persistFailure(message);
        error._pwnmeshFailureMessage = message;
        throw error;
      }
    };
    try {
      if (options.maxTokens && config.context?.bytes > 0 && await inputBytes(context.messages) > config.context.bytes) {
        throw Object.assign(new Error("Pi summary request exceeds the configured byte budget"), { kind: "context_budget" });
      }
      let result;
      try {
        result = await requestModel(context.messages);
      } catch (error) {
        if (error.kind !== "context_overflow" || options.maxTokens || overflowPending()) throw error;
        // Consume the allowance before summarization or retry. Pi's custom
        // session entries make a restart retain the same allowance.
        manager.appendCustomEntry("pwnmesh.context_overflow", { pending: true });
        await save();
        await maybeCompact(true);
        result = await requestModel(convertToLlm(contextMessages()));
      }
      lastError = undefined;
      response = result;
      const message = toAssistant(response, model);
      stream.push({ type: "done", reason: message.stopReason, message });
    } catch (error) {
      lastError = error.kind || !lastError?.kind ? error : lastError;
      const message = lastError._pwnmeshFailureMessage ?? failedMessage(lastError, response, options.maxTokens ? "summary" : "turn");
      await persistFailure(message);
      stream.push({ type: "error", reason: message.stopReason, error: message });
    }
    return stream;
  };
  const maybeCompact = async (force = false) => {
    const before = contextMessages();
    const beforeBytes = await inputBytes(before);
    const tokens = contextTokens(before);
    const limits = config.context ?? {};
    if (!force && !(limits.bytes > 0 && beforeBytes > limits.bytes) && !(limits.tokens > 0 && tokens > limits.tokens)) return;
    const target = limits.targetTokens > 0 ? limits.targetTokens : Math.max(256, Math.floor((limits.tokens || tokens) / 2));
    const preparation = prepareCompaction(manager.getBranch(), {
      enabled: true, reserveTokens: 0, keepRecentTokens: Math.max(1, Math.floor(target / 2)),
    });
    if (!preparation) throw Object.assign(new Error("Pi context cannot be compacted within the configured budget"), { kind: "context_budget" });
    const result = await compact(preparation, model, undefined, undefined, undefined, undefined, undefined,
      (m, c, o) => streamFn(m, c, { ...o, maxTokens: limits.summaryMaxTokens || 16384 }), undefined,
      { maxRetries: 0 });
    manager.appendCompaction(result.summary, result.firstKeptEntryId, result.tokensBefore, result.details, false, result.usage);
    compactionCount++;
    const after = contextMessages(), afterBytes = await inputBytes(after);
    const view = history();
    const sourceSequences = [...preparation.messagesToSummarize, ...preparation.turnPrefixMessages]
      .map((message) => message._pwnmeshSequence ?? 0).filter((sequence) => sequence > 0);
    const record = {
      version: 1, id: compactionCount, previous_id: compactionCount - 1, at_sequence: lastSequence,
      source_start: sourceSequences.length ? Math.min(...sourceSequences) : 0,
      source_end: sourceSequences.length ? Math.max(...sourceSequences) : 0,
      first_kept_sequence: manager.getEntry(result.firstKeptEntryId)?.message?._pwnmeshSequence ?? 0,
      summary: result.summary, before_bytes: beforeBytes, after_bytes: afterBytes,
      before_tokens_estimate: tokens, after_tokens_estimate: contextTokens(after),
      token_basis: "pi_estimateProjectedContextTokens", usage: fromUsage(result.usage), reason: "budget", status: "committed", view,
    };
    await emit({ type: "context_compaction_prepared", compaction: record });
    await save();
    await emit({ type: "context_compacted", compaction: record });
    const afterTokens = contextTokens(after);
    if ((limits.bytes > 0 && afterBytes > limits.bytes) || (limits.tokens > 0 && afterTokens > limits.tokens) ||
      (limits.targetTokens > 0 && afterTokens > limits.targetTokens)) {
      throw Object.assign(new Error("Pi compacted context exceeds the configured budget"), { kind: "context_budget" });
    }
  };
  agent = new Agent({
    initialState: { model, messages: projected(), tools: activeTools() },
    convertToLlm, streamFn, toolExecution: "sequential",
    prepareRequest: async () => {
      preparationFailure = undefined;
      try {
        await apply(await callback("before_request"));
        const changes = getToolStateChanges(getCurrentTools(projected()), activeTools());
        if (changes.toolsAdded.length || changes.toolsRemoved.length) {
          await append({ role: "system", content: "", ...changes, timestamp: Date.now() });
        }
        await maybeCompact();
        return { context: { messages: contextMessages(), tools: activeTools() } };
      } catch (error) {
        lastError = error.kind || !lastError?.kind ? error : lastError;
        preparationFailure = lastError._pwnmeshFailureMessage;
        throw error;
      }
    },
    beforeToolCall: async () => {
      const stop = await callback("stop_result");
      if (stop.end) { terminalText = stop.text ?? ""; return { block: true, reason: "The task has already committed its result.", terminate: true }; }
      if (config.toolsDisabledReason) return { block: true, reason: config.toolsDisabledReason };
    },
    finishTurn: async (turn) => {
      if (["error", "aborted"].includes(turn.message.stopReason)) return { action: "end" };
      const stop = await callback("stop_result");
      if (stop.end) { terminalText = stop.text ?? ""; return { action: "end" }; }
      const update = await callback("turn_end", { message: fromMessage(turn.message) });
      await apply(update);
      if (update.end) { terminalText = update.text; return { action: "end" }; }
      if (update.instructions?.length) return { action: "continue" };
    },
    prepareNextTurnWithContext: async () => ({ context: { messages: contextMessages(), tools: activeTools() } }),
  });
  agent.subscribe(async (event) => {
    if (event.type === "message_end") {
      const message = event.message;
      if (message.role === "assistant" && ["error", "aborted"].includes(message.stopReason)) {
        // Retain the original attempt without accepting it as a completed turn.
        // Pi's native edit keeps partial calls out of recovery and compaction.
        // A failed preparation summary was already recorded by its stream.
        // Consume its reference only for Pi's synthetic preparation error.
        const original = preparationFailure;
        preparationFailure = undefined;
        await persistFailure(original ?? message);
        return;
      }
      if (message.role === "assistant" && message.stopReason !== "length" && overflowPending()) {
        manager.appendCustomEntry("pwnmesh.context_overflow", { pending: false });
      }
      await append(message);
    } else if (event.type === "tool_execution_start") {
      await emit({ type: "tool_start", tool_id: event.toolCallId, tool_name: event.toolName });
    } else if (event.type === "tool_execution_end") {
      await emit({ type: "tool_end", tool_id: event.toolCallId, tool_name: event.toolName,
        text: textOf(event.result), error: event.isError ? textOf(event.result) : undefined });
    } else if (["agent_start", "agent_end", "turn_start", "turn_end"].includes(event.type)) {
      await emit({ type: event.type });
    }
  });
  try {
    if (input.prompt) await agent.prompt(input.prompt);
    else await agent.continue();
  } catch (error) { lastError = error; }
  if (!lastError && agent.state.errorMessage) lastError = new Error(agent.state.errorMessage);
  const last = [...projected()].reverse().find((message) => message.role === "assistant");
  return { type: "result", text: terminalText ?? textOf(last), ...state(),
    ...(lastError ? { error: lastError.message, errorKind: lastError.kind, canceled: Boolean(lastError.canceled), deadline: Boolean(lastError.deadline) } : {}) };
}

async function main() {
  if (process.argv.includes("--check")) { process.stdout.write(`${JSON.stringify(ENGINE)}\n`); return; }
  const pending = new Map();
  let nextID = 0, started = false;
  const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
  const send = (message) => process.stdout.write(`${JSON.stringify(message)}\n`);
  const host = (method, params) => new Promise((resolve, reject) => {
    const id = String(++nextID);
    pending.set(id, { resolve, reject });
    send({ type: "call", id, method, params });
  });
  lines.on("line", (line) => {
    let message;
    try { message = JSON.parse(line); }
    catch { send({ type: "result", error: "Invalid Pi kernel protocol JSON" }); lines.close(); return; }
    if (message.type === "reply") {
      const call = pending.get(String(message.id));
      if (!call) return;
      pending.delete(String(message.id));
      if (message.error) call.reject(Object.assign(failure(message.error), { response: message.result }));
      else call.resolve(message.result);
    } else if (!started && ["run", "edit", "inspect"].includes(message.type)) {
      started = true;
      runKernel(message, host).then(send, (error) => send({ type: "result", error: error.message, errorKind: error.kind }))
        .finally(() => { lines.close(); process.stdin.pause(); });
    }
  });
  lines.on("close", () => {
    for (const call of pending.values()) call.reject(new Error("Host disconnected from Pi kernel"));
    pending.clear();
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
