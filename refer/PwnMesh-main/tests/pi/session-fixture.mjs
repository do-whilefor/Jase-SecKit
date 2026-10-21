import "../../runtime/pi/source-loader.mjs";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { toAssistant } from "../../runtime/pi/kernel-wire.mjs";
import { openNativeSession } from "../../runtime/pi/session-file.mjs";

const { SessionManager } = await import("../../runtime/pi/upstream/packages/coding-agent/src/core/session-manager.ts");

const temporaryDirectories = new Set();
export function temporarySessionPath() {
  const directory = mkdtempSync(join(tmpdir(), "pwnmesh-pi-test-"));
  temporaryDirectories.add(directory);
  return join(directory, "pi-session.jsonl");
}
process.once("exit", () => {
  for (const directory of temporaryDirectories) rmSync(directory, { recursive: true, force: true });
});

export function sessionEntries(reference) {
  return readFileSync(reference.file).subarray(0, reference.offset).toString("utf8").trimEnd()
    .split("\n").flatMap((line, index) => {
      if (!index) return [];
      try { return [JSON.parse(line)]; } catch { return []; }
    });
}

// Seed native Pi JSONL directly; the kernel only accepts file checkpoints.
export function nativeSession(messages, cwd = process.cwd(), sessionPath = temporarySessionPath()) {
  const disk = openNativeSession({ sessionPath, cwd }, SessionManager);
  const manager = disk.manager;
  let sequence = 0;
  for (const wire of messages) {
    let message;
    if (wire.role === "assistant") message = toAssistant(wire);
    else if (wire.content[0]?.type === "tool_result") {
      const result = wire.content[0];
      message = { role: "toolResult", toolCallId: result.tool_use_id, toolName: "echo",
        content: [{ type: "text", text: result.content }], isError: Boolean(result.is_error), timestamp: 0 };
    } else message = { role: wire.role, content: wire.content, timestamp: 0 };
    message._pwnmeshSequence = ++sequence;
    manager.appendMessage(message);
  }
  return disk.snapshot();
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  let input = "";
  for await (const piece of process.stdin) input += piece;
  const { messages, cwd, sessionPath } = JSON.parse(input);
  process.stdout.write(JSON.stringify(nativeSession(messages, cwd, sessionPath)));
}
