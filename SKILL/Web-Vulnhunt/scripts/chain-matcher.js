#!/usr/bin/env node
/**
 * chain-matcher.js — Vulnerability-chain matcher: turns a primitives
 * inventory into candidate chains by matching each finding's OUTPUTS against
 * every other finding's PRECONDITIONS (report-structure.md §Chain synthesis,
 * steps 1-3: inventory → output-input matching → precondition collapse).
 *
 * Usage:
 *   node chain-matcher.js <primitives.json> [--out report.md]
 *
 * Input format (primitives.json):
 * {
 *   "findings": [
 *     { "id": "F8",  "cvss": 5.4,
 *       "outputs": ["install-token", "workstation-bearer"],
 *       "preconditions": [],
 *       "notes": "unexpiring install-token mint (dormant primitive)" },
 *     { "id": "F5",  "cvss": 8.1,
 *       "outputs": ["keycloak-secret", "config-read"],
 *       "preconditions": ["workstation-bearer"],
 *       "notes": "missing @PreAuthorize config read" }
 *   ]
 * }
 *
 * Output: candidate chains A→B with composite-severity hint (max CVSS of the
 * pair, +1 band bump when A collapses B's only precondition) and the honest
 * boundaries (findings whose preconditions nothing satisfies).
 *
 * Pure Node stdlib. Scope = the targets the operator names. Hygiene rules:
 * references/ethics-and-roe.md — a matched chain is a report candidate, not a
 * license: Tier rules still govern what you do with the access it grants.
 */
'use strict';
const fs = require('fs');

const args = process.argv.slice(2);
let out = null;
const pos = [];
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--out') out = args[++i]; else pos.push(args[i]);
}
if (!pos.length) { console.error('Usage: node chain-matcher.js <primitives.json> [--out report.md]'); process.exit(1); }

const data = JSON.parse(fs.readFileSync(pos[0], 'utf8'));
const findings = data.findings || [];
if (findings.length < 2) { console.error('Need >=2 findings to match chains.'); process.exit(1); }

const norm = (s) => String(s).toLowerCase().trim().replace(/s$/, '');
const band = (n) => (n >= 9 ? 'Critical' : n >= 7 ? 'High' : n >= 4 ? 'Medium' : 'Low');
const BUMP = { Low: 'Medium', Medium: 'High', High: 'Critical', Critical: 'Critical' };

const chains = [];
const supplied = new Set(); // findings whose preconditions something satisfies
for (const A of findings) {
  for (const B of findings) {
    if (A.id === B.id) continue;
    const outs = new Set((A.outputs || []).map(norm));
    const pre = B.preconditions || [];
    if (!pre.length) continue;
    const hit = pre.filter((p) => outs.has(norm(p)));
    if (!hit.length) continue;
    supplied.add(B.id);
    const maxCvss = Math.max(A.cvss || 0, B.cvss || 0);
    let sev = band(maxCvss);
    const collapsed = hit.length === pre.length; // A collapses ALL of B's preconditions
    if (collapsed) sev = BUMP[sev];
    chains.push({ from: A.id, to: B.id, via: hit, collapsed, severityHint: sev, note: `${A.id} supplies ${hit.join('+')} → ${B.id}` });
  }
}

const orphans = findings.filter((f) => (f.preconditions || []).length && !supplied.has(f.id));

const lines = [];
lines.push('# Chain candidates (output-input matching)');
lines.push('');
lines.push('| Chain | Via | Precondition collapse | Composite hint |');
lines.push('|---|---|---|---|');
chains.forEach((c) => lines.push(`| ${c.from} → ${c.to} | ${c.via.join(', ')} | ${c.collapsed ? 'YES (all preconditions supplied)' : 'partial'} | ${c.severityHint} |`));
lines.push('');
lines.push('## Unsatisfied preconditions (honest boundaries — document as future work, do not omit)');
orphans.forEach((f) => lines.push(`- ${f.id}: needs ${ (f.preconditions || []).join(', ') } — nothing in the inventory supplies it`));
lines.push('');
lines.push('Composite-severity hints are a floor for the chain narrative, not a score: run the actual chain CVSS through scripts/cvss31-calculator.js with the collapsed-precondition vector (report-structure.md step 3).');
lines.push('Tier check before writing: state-changing steps use placeholder targets (SKILL.md Integrity discipline).');
const report = lines.join('\n');

if (out) { fs.writeFileSync(out, report + '\n'); console.error('Wrote ' + out); }
console.log(report);
console.error(`\n${chains.length} candidate chain(s), ${orphans.length} finding(s) with unsatisfied preconditions.`);
