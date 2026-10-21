import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("packaged Pi runs from an independent directory", () => {
  const root = fileURLToPath(new URL("../", import.meta.url));
  const directory = mkdtempSync(join(tmpdir(), "pwnmesh-pi-package-"));
  try {
    const runtime = join(directory, "runtime", "pi");
    mkdirSync(runtime, { recursive: true });
    for (const file of ["sync-source.mjs", "package-lock.json"]) {
      writeFileSync(join(runtime, file), "Old build maintenance file\n");
    }
    const packaged = spawnSync(process.execPath, [
      join(root, "scripts", "package-pi.mjs"), runtime,
    ], { cwd: directory, encoding: "utf8" });
    assert.equal(packaged.status, 0, packaged.stderr);
    assert.equal(existsSync(join(runtime, "sync-source.mjs")), false);
    assert.equal(existsSync(join(runtime, "package-lock.json")), false);
    assert.ok(existsSync(join(runtime, "upstream", "LICENSE")));
    assert.ok(existsSync(join(runtime, "upstream", "provenance.json")));
    const checked = spawnSync(process.execPath, [join(runtime, "kernel.mjs"), "--check"], {
      cwd: directory,
      encoding: "utf8",
    });
    assert.equal(checked.status, 0, checked.stderr);
    const identity = JSON.parse(checked.stdout);
    assert.equal(identity.engine, "pi");
    assert.equal(identity.agent, "Agent");
    assert.equal(identity.session, "SessionManager");
    assert.ok(identity.version);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("packaging in place retains source maintenance files", () => {
  const root = fileURLToPath(new URL("../", import.meta.url));
  const runtime = join(root, "runtime", "pi");
  const files = ["sync-source.mjs", "package-lock.json"].map((file) => join(runtime, file));
  const before = files.map((file) => readFileSync(file));
  const packaged = spawnSync(process.execPath, [join(root, "scripts", "package-pi.mjs"), runtime], {
    cwd: root, encoding: "utf8",
  });
  assert.equal(packaged.status, 0, packaged.stderr);
  files.forEach((file, index) => assert.deepEqual(readFileSync(file), before[index]));
});
