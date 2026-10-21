import { createHash } from "node:crypto";
import { appendFileSync, closeSync, existsSync, fsyncSync, lstatSync, mkdirSync, openSync, readSync, statSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { StringDecoder } from "node:string_decoder";

function readRange(path, start, end, consume) {
  const fd = openSync(path, "r");
  try {
    const buffer = Buffer.allocUnsafe(64 * 1024);
    let offset = start;
    while (offset < end) {
      const count = readSync(fd, buffer, 0, Math.min(buffer.length, end - offset), offset);
      if (!count) throw new Error("Pi session ended before its committed checkpoint");
      consume(buffer.subarray(0, count));
      offset += count;
    }
  } finally { closeSync(fd); }
}

function verifyPrefix(path, reference, collect = false) {
  if (!Number.isSafeInteger(reference.offset) || reference.offset <= 0 ||
    !/^[0-9a-f]{64}$/.test(reference.sha256) || !(reference.leafId === null || typeof reference.leafId === "string")) {
    throw new Error("Invalid Pi session file checkpoint");
  }
  if (!existsSync(path) || statSync(path).size < reference.offset) throw new Error("Pi session file is missing committed bytes");
  const digest = createHash("sha256"), decoder = new StringDecoder("utf8"), ids = new Set();
  let header, pending = "", finalByte = -1;
  const entries = [];
  readRange(path, 0, reference.offset, (bytes) => {
    digest.update(bytes);
    finalByte = bytes.at(-1);
    pending += decoder.write(bytes);
    let end;
    while ((end = pending.indexOf("\n")) !== -1) {
      const line = pending.slice(0, end);
      pending = pending.slice(end + 1);
      let entry;
      try { entry = JSON.parse(line); } catch { continue; } // Pi preserves malformed orphan tails.
      if (!header) {
        header = entry;
        if (collect) entries.push(entry);
        continue;
      }
      if (typeof entry.id !== "string" || ids.has(entry.id) || (entry.parentId !== null && !ids.has(entry.parentId))) {
        throw new Error("Invalid committed Pi session tree");
      }
      ids.add(entry.id);
      if (collect) entries.push(entry);
    }
  });
  if (finalByte !== 10 || pending || decoder.end()) throw new Error("Pi checkpoint is not at a JSONL record boundary");
  if (digest.copy().digest("hex") !== reference.sha256) throw new Error("Pi session committed prefix hash mismatch");
  if (JSON.stringify(header) !== JSON.stringify(reference.header) || header?.type !== "session" || header.version !== 3 ||
    (reference.leafId !== null && !ids.has(reference.leafId))) throw new Error("Pi session checkpoint identity or leaf mismatch");
  return { digest, entries };
}

function terminateOrphanTail(path) {
  const size = statSync(path).size;
  if (!size) return;
  let final;
  readRange(path, size - 1, size, (bytes) => { final = bytes[0]; });
  if (final !== 10) appendFileSync(path, "\n");
}

// SessionManager remains the writer and tree/projection owner. This module binds
// its native append-only JSONL file to the host's atomic policy checkpoint.
export function openNativeSession(input, SessionManager) {
  if (!input.sessionPath) throw new Error("Pi requires the host's bound sessionPath");
  const path = resolve(input.sessionPath);
  if (existsSync(path) && lstatSync(path).isSymbolicLink()) throw new Error("Pi session file cannot be a symbolic link");
  const reference = input.session;
  if (reference && (typeof reference.file !== "string" || !reference.file || Object.hasOwn(reference, "entries"))) {
    throw new Error("Pi requires a native session file checkpoint");
  }
  if (reference && resolve(reference.file) !== path) throw new Error("Pi session path does not match this run");
  if (input.type !== "inspect") mkdirSync(dirname(path), { recursive: true });
  let digest = createHash("sha256"), offset = 0, manager;
  if (reference) {
    const verified = verifyPrefix(path, reference, input.type === "inspect");
    digest = verified.digest;
    offset = reference.offset;
    if (input.type === "inspect") {
      manager = SessionManager.inMemory(reference.header.cwd, undefined, verified.entries);
    } else {
      terminateOrphanTail(path);
      manager = SessionManager.open(path, undefined, reference.header.cwd);
    }
    if (reference.leafId === null) manager.resetLeaf();
    else manager.branch(reference.leafId);
  } else {
    if (existsSync(path)) terminateOrphanTail(path);
    manager = SessionManager.open(path, undefined, input.cwd ?? process.cwd());
    // No policy checkpoint authorizes an old file's conversation.
    manager.resetLeaf();
  }
  const known = new Set();
  for (const entry of manager.getEntries()) {
    if (typeof entry.id !== "string" || known.has(entry.id) || (entry.parentId !== null && !known.has(entry.parentId))) {
      throw new Error("Invalid or duplicate Pi session entry in the file tail");
    }
    known.add(entry.id);
  }
  return {
    manager,
    snapshot() {
      if (input.type === "inspect" && reference) return reference;
      if (!existsSync(path)) {
        // Pi delays setup-only files until the first conversation message.
        // A setup-only edit must nevertheless retain every buffered entry.
        const entries = [manager.getHeader(), ...manager.getEntries()];
        writeFileSync(path, entries.map((entry) => JSON.stringify(entry)).join("\n") + "\n", { flag: "wx", mode: 0o600 });
        manager = SessionManager.open(path, undefined, manager.getCwd());
        this.manager = manager;
      }
      const fd = openSync(path, "r+");
      try { fsyncSync(fd); } finally { closeSync(fd); }
      const size = statSync(path).size;
      if (size < offset) throw new Error("Pi session file was truncated");
      readRange(path, offset, size, (bytes) => digest.update(bytes));
      offset = size;
      return { header: manager.getHeader(), file: path, offset, leafId: manager.getLeafId(), sha256: digest.copy().digest("hex") };
    },
  };
}
