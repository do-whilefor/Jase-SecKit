#!/usr/bin/env node
/**
 * bundle-diff.js — Frontend bundle diff for patch-scope enumeration.
 * Downloads (or reads) two SPA bundles — pre/post patch, or two versions —
 * extracts the load-bearing literals (API paths, hostnames, semver markers)
 * and diffs them. The added/removed endpoint sets ARE the patch scope: what
 * the vendor touched, which adjacent endpoints to re-verify (Phase 3), and
 * whether any sink silently disappeared or appeared.
 *
 * Usage:
 *   node bundle-diff.js <old.js|URL> <new.js|URL> [--out report.md]
 *
 * Extracts:
 *   - API path literals   ( "/api/..." , '/rp/...' , `/cc/...` string literals )
 *   - absolute hostnames  ( https://host... literals )
 *   - semver-ish markers  ( v11.3.0 style build/version strings )
 *
 * Pure Node stdlib (https + fs).
 */
'use strict';
const fs = require('fs');
const https = require('https');
const http = require('http');

function load(src) {
  if (/^https?:\/\//.test(src)) {
    return new Promise((resolve, reject) => {
      const mod = src.startsWith('https:') ? https : http;
      const req = mod.get(src, { headers: { 'User-Agent': 'bundle-diff/1.0' }, timeout: 30000 }, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          load(new URL(res.headers.location, src).href).then(resolve, reject);
          res.resume();
          return;
        }
        if (res.statusCode !== 200) { res.resume(); return reject(new Error(`${src} → HTTP ${res.statusCode}`)); }
        let size = 0; const chunks = [];
        res.on('data', (c) => { size += c.length; chunks.push(c); if (size > 64 * 1024 * 1024) req.destroy(new Error('bundle > 64MB')); });
        res.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
      });
      req.on('timeout', () => req.destroy(new Error('timeout')));
      req.on('error', reject);
    });
  }
  return Promise.resolve(fs.readFileSync(src, 'utf8'));
}

function extract(code) {
  const apiPaths = new Set();
  const hosts = new Set();
  const versions = new Set();
  // Path literals: quoted strings starting with / and containing a letter + slash
  const pathRe = /["'`](\/(?:api|rp|cc|auth|fido|oauth|v[0-9]+)\/[A-Za-z0-9_\-./{}$]{2,120})["'`]/g;
  let m;
  while ((m = pathRe.exec(code))) apiPaths.add(m[1].replace(/\$\{[^}]*\}/g, '{param}'));
  const hostRe = /https?:\/\/[A-Za-z0-9._-]+\.[A-Za-z]{2,24}/g;
  while ((m = hostRe.exec(code))) hosts.add(m[0].replace(/[.,;)]+$/, ''));
  const verRe = /\bv?\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.]+)?\b/g;
  while ((m = verRe.exec(code))) versions.add(m[0]);
  return { apiPaths: [...apiPaths], hosts: [...hosts], versions: [...versions] };
}

function diffSets(a, b) {
  const A = new Set(a), B = new Set(b);
  return {
    removed: [...A].filter((x) => !B.has(x)),
    added: [...B].filter((x) => !A.has(x)),
  };
}

(async () => {
  const args = process.argv.slice(2);
  const pos = []; let out = null;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--out') out = args[++i]; else pos.push(args[i]);
  }
  if (pos.length < 2) { console.error('Usage: node bundle-diff.js <old.js|URL> <new.js|URL> [--out report.md]'); process.exit(1); }

  console.error(`Loading old: ${pos[0]}`);
  const oldCode = await load(pos[0]);
  console.error(`Loading new: ${pos[1]}`);
  const newCode = await load(pos[1]);
  const O = extract(oldCode), N = extract(newCode);
  const ep = diffSets(O.apiPaths, N.apiPaths);
  const hs = diffSets(O.hosts, N.hosts);
  const vs = diffSets(O.versions, N.versions);

  const lines = [];
  lines.push(`# Bundle diff — patch scope`);
  lines.push(`old: ${pos[0]}  (${O.apiPaths.length} endpoints, ${O.hosts.length} hosts)`);
  lines.push(`new: ${pos[1]}  (${N.apiPaths.length} endpoints, ${N.hosts.length} hosts)`);
  lines.push('');
  lines.push(`## Endpoints REMOVED in new bundle (${ep.removed.length}) — candidate patch scope`);
  ep.removed.forEach((x) => lines.push(`- \`${x}\``));
  lines.push('');
  lines.push(`## Endpoints ADDED in new bundle (${ep.added.length}) — new attack surface to inventory`);
  ep.added.forEach((x) => lines.push(`- \`${x}\``));
  lines.push('');
  lines.push(`## Host changes — removed: ${hs.removed.length}, added: ${hs.added.length}`);
  hs.removed.forEach((x) => lines.push(`- REMOVED ${x}`));
  hs.added.forEach((x) => lines.push(`- ADDED ${x}`));
  lines.push('');
  lines.push(`## Version markers — old: ${O.versions.slice(0, 5).join(', ') || 'none'} | new: ${N.versions.slice(0, 5).join(', ') || 'none'}`);
  lines.push('');
  lines.push('## Next steps (Phase 3 discipline)');
  lines.push('1. Removed endpoints → re-run the original PoCs against them (patch-verify.sh).');
  lines.push('2. Adjacent SAME-NAMESPACE endpoints that did NOT change → suspect per-endpoint patching; run the bypass ladder (path-bypass-fuzzer.sh).');
  lines.push('3. Version-differential tenants (tenant-diff.sh) — vendors roll patches per-tenant inconsistently (F13 pattern).');
  const report = lines.join('\n');
  if (out) { fs.writeFileSync(out, report + '\n'); console.error('Wrote ' + out); }
  console.log(report);
})().catch((e) => { console.error('ERROR: ' + e.message); process.exit(1); });
