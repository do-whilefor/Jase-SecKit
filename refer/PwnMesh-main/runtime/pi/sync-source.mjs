import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// Maintenance command only. Production never reads the ignored refer tree.
const root = fileURLToPath(new URL("../../", import.meta.url));
const source = resolve(root, "refer/pi-main");
const target = fileURLToPath(new URL("./upstream", import.meta.url));
if (process.argv.includes("--check")) {
  const manifest = JSON.parse(readFileSync(resolve(target, "provenance.json"), "utf8"));
  const checked = new Set();
  for (const file of manifest.files) {
    if (checked.has(file.path)) throw new Error(`Duplicate Pi source manifest entry: ${file.path}`);
    checked.add(file.path);
    const actual = createHash("sha256").update(readFileSync(resolve(target, file.path))).digest("hex");
    if (actual !== file.sha256) throw new Error(`Pi source hash mismatch: ${file.path}`);
  }
  process.stdout.write(`Verified ${checked.size} unmodified Pi ${manifest.version} source files.\n`);
  process.exit(0);
}
const entries = [
  "packages/agent/src/agent.ts",
  "packages/coding-agent/src/core/session-manager.ts",
  "packages/coding-agent/src/core/compaction/compaction.ts",
  ...["transcript", "event-stream", "text", "retry", "uuid", "validation"].map((name) => `packages/ai/src/utils/${name}.ts`),
];
const seen = new Set();
const files = [];
function copy(path) {
  path = path.replaceAll("\\", "/");
  if (seen.has(path)) return;
  seen.add(path);
  const absolute = resolve(source, path);
  const bytes = readFileSync(absolute);
  const destination = resolve(target, path);
  mkdirSync(dirname(destination), { recursive: true });
  copyFileSync(absolute, destination);
  files.push({ path: path.replaceAll("\\", "/"), sha256: createHash("sha256").update(bytes).digest("hex") });
  if (!path.endsWith(".ts")) return;
  const code = stripTypeScriptTypes(bytes.toString("utf8"), { mode: "strip" });
  for (const match of code.matchAll(/(?:from\s*|import\s*)["']([^"']+)["']/g)) {
    if (match[1].startsWith(".")) copy(relative(source, resolve(dirname(absolute), match[1])));
  }
}
for (const entry of entries) copy(entry);
copy("packages/coding-agent/package.json");
copy("LICENSE");
writeFileSync(resolve(target, "provenance.json"), `${JSON.stringify({
  repository: "https://github.com/earendil-works/pi",
  version: "1.3.0",
  source: "refer/pi-main",
  unmodified: true,
  entries,
  files: files.sort((a, b) => a.path.localeCompare(b.path)),
}, null, 2)}\n`);
process.stdout.write(`Vendored ${files.length} unmodified Pi source files.\n`);
