const ZERO_COST = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 };
export const MODEL = {
  id: "pwnmesh-host", name: "PwnMesh host transport", api: "pwnmesh-host",
  provider: "pwnmesh", baseUrl: "", reasoning: false, input: ["text"],
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  contextWindow: 0, maxTokens: 16384,
};

export function modelForHost(descriptor) {
  if (!descriptor?.id || !descriptor.api || !descriptor.provider) return { ...MODEL };
  return { ...MODEL, id: descriptor.id, name: descriptor.id, api: descriptor.api,
    provider: descriptor.provider, reasoning: descriptor.reasoning === true,
    input: descriptor.input?.length ? [...descriptor.input] : ["text"],
    maxTokens: descriptor.maxTokens > 0 ? descriptor.maxTokens : MODEL.maxTokens };
}

export function toUsage(usage = {}) {
  const input = usage.input_tokens ?? 0, output = usage.output_tokens ?? 0;
  const cacheRead = usage.cache_read_input_tokens ?? 0, cacheWrite = usage.cache_creation_input_tokens ?? 0;
  return { input, output, cacheRead, cacheWrite, totalTokens: input + output + cacheRead + cacheWrite, cost: { ...ZERO_COST } };
}

export function fromUsage(usage) {
  if (!usage) return undefined;
  return { input_tokens: usage.input, output_tokens: usage.output,
    cache_read_input_tokens: usage.cacheRead, cache_creation_input_tokens: usage.cacheWrite };
}

export function toAssistant(message, model = MODEL) {
  if (message.role !== "assistant" || !Array.isArray(message.content)) throw new Error("Invalid host assistant message");
  const ids = new Set();
  const source = message.model_source;
  if (source) model = modelForHost(source);
  return {
    role: "assistant", api: model.api, provider: model.provider, model: model.id,
    timestamp: Date.now(), usage: toUsage(message.usage),
    stopReason: ({ end_turn: "stop", stop: "stop", max_tokens: "length", length: "length", tool_use: "toolUse" })[message.stop_reason]
      ?? (message.content.some((block) => block.type === "tool_use") ? "toolUse" : "stop"),
    _pwnmeshSequence: message.sequence ?? 0,
    _pwnmeshTiming: message.model_timing,
    _pwnmeshModelSource: source ? { ...source, input: source.input ? [...source.input] : undefined } : undefined,
    content: message.content.map((block) => {
      if (block.type === "text") return { type: "text", text: block.text ?? "" };
      if (block.type === "thinking") return { type: "thinking", thinking: block.thinking ?? "", thinkingSignature: block.signature ?? "" };
      if (block.type === "redacted_thinking") return { type: "thinking", thinking: "", thinkingSignature: block.data, redacted: true };
      if (block.type !== "tool_use" || !block.id || ids.has(block.id) || !block.name ||
        !block.input || typeof block.input !== "object" || Array.isArray(block.input)) {
        throw new Error("Invalid or duplicate host tool call");
      }
      ids.add(block.id);
      return { type: "toolCall", id: block.id, name: block.name, arguments: block.input };
    }),
  };
}

function contentBlocks(content) {
  if (typeof content === "string") return [{ type: "text", text: content }];
  return (content ?? []).map((block) => {
    if (block.type === "text") return { type: "text", text: block.text };
    if (block.type === "thinking") return block.redacted
      ? { type: "redacted_thinking", data: block.thinkingSignature ?? "" }
      : { type: "thinking", thinking: block.thinking ?? "", signature: block.thinkingSignature ?? "" };
    if (block.type === "toolCall") return { type: "tool_use", id: block.id, name: block.name, input: block.arguments };
    throw new Error(`Unsupported Pi content: ${block.type}`);
  });
}

export function fromMessage(message) {
  if (message.role === "toolResult") return { role: "user",
    content: [{ type: "tool_result", tool_use_id: message.toolCallId, content: textOf(message), is_error: message.isError }],
    sequence: message._pwnmeshSequence ?? 0 };
  if (!["user", "assistant", "system"].includes(message.role)) throw new Error(`Unprojected Pi role: ${message.role}`);
  const result = { role: message.role, content: contentBlocks(message.content), sequence: message._pwnmeshSequence ?? 0 };
  if (message.role === "assistant") {
    result.stop_reason = ({ stop: "end_turn", length: "max_tokens", toolUse: "tool_use" })[message.stopReason] ?? "end_turn";
    result.usage = fromUsage(message.usage);
    if (message._pwnmeshTiming) result.model_timing = message._pwnmeshTiming;
    if (message._pwnmeshModelSource) result.model_source = { ...message._pwnmeshModelSource,
      input: message._pwnmeshModelSource.input ? [...message._pwnmeshModelSource.input] : undefined };
  }
  return result;
}

export function fromMessages(messages, includeSystem = false) {
  const result = [];
  let previousTool = false;
  for (const message of messages) {
    if (message.role === "system" && !includeSystem) continue;
    const converted = fromMessage(message);
    const previous = result.at(-1);
    if (message.role === "toolResult" && previousTool) {
      previous.content.push(...converted.content);
      previous.sequence = Math.max(previous.sequence, converted.sequence);
    }
    else result.push(converted);
    previousTool = message.role === "toolResult";
  }
  return result;
}

export function textOf(message) {
  return typeof message?.content === "string" ? message.content
    : (message?.content ?? []).filter((block) => block.type === "text").map((block) => block.text).join("\n");
}
