import assert from "node:assert/strict";
import { test } from "node:test";
import { fromMessage, modelForHost, toAssistant } from "../../runtime/pi/kernel-wire.mjs";

const source = { id: "configured-model", api: "openai-completions", provider: "endpoint:fixture",
  reasoning: true, maxTokens: 8192, input: ["text"] };
const message = { role: "assistant", content: [{ type: "thinking", thinking: "Retain reasoning", signature: "" },
  { type: "text", text: "Answer" }], stop_reason: "end_turn", model_source: source };

test("host model metadata survives Pi history projection without credentials or guessed context limits", () => {
  const model = modelForHost(source);
  assert.equal(model.id, source.id);
  assert.equal(model.api, source.api);
  assert.equal(model.reasoning, true);
  assert.equal(model.maxTokens, 8192);
  assert.equal(model.contextWindow, 0);
  assert.equal(model.baseUrl, "");
  const restored = toAssistant(message);
  assert.equal(restored.model, source.id);
  assert.equal(restored.provider, source.provider);
  assert.deepEqual(fromMessage(restored).model_source, source);
  assert.equal(fromMessage(restored).content[0].thinking, "Retain reasoning");
  restored._pwnmeshModelSource.input.push("image");
  assert.deepEqual(source.input, ["text"]);
});

test("restored source is retained when the active model changes and legacy source remains unknown", () => {
  const converted = toAssistant(message, modelForHost({ ...source, id: "different-model" }));
  assert.equal(converted.model, "configured-model");
  const legacy = { ...message };
  delete legacy.model_source;
  assert.equal(fromMessage(toAssistant(legacy)).model_source, undefined);
});
