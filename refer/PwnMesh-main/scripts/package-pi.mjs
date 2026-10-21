import { cpSync, existsSync, mkdirSync, realpathSync, rmSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const source = fileURLToPath(new URL("../runtime/pi/", import.meta.url));
const destination = process.argv[2] && resolve(process.argv[2]);
if (!destination || process.argv.length !== 3) {
  throw new Error("Usage: node scripts/package-pi.mjs <destination>");
}
const check = spawnSync(process.execPath, [resolve(source, "kernel.mjs"), "--check"], {
  encoding: "utf8",
});
if (check.status !== 0) {
  process.stderr.write(check.stderr || "Pi runtime dependencies are missing. Run npm ci --prefix runtime/pi.\n");
  process.exit(check.status || 1);
}
if (!existsSync(destination) || realpathSync(source) !== realpathSync(destination)) {
  const maintenanceFiles = new Set(["sync-source.mjs", "package-lock.json"]);
  mkdirSync(dirname(destination), { recursive: true });
  cpSync(source, destination, { recursive: true, force: true,
    filter: (path) => !maintenanceFiles.has(relative(source, path)) });
  // Remove files left by an older build when reusing its output directory.
  for (const file of maintenanceFiles) rmSync(resolve(destination, file), { force: true });
}
