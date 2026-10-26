#!/usr/bin/env node
/**
 * body-mutator.js — Request-body mutation for hypothesis-driven probing.
 * Takes a real (or valid-body-generator-produced) JSON body and emits named
 * mutant profiles. Pairs with sweep-all.sh / authz-matrix.sh re-tests and the
 * Tier-3 placeholder rule: identifier-ish fields get placeholder-substituted,
 * never real values.
 *
 * Usage:
 *   node body-mutator.js <body.json> [--profiles all|p1,p2,...] [--out-dir DIR] [--cap N]
 *
 * Profiles:
 *   type-juggle      string values → 1 / true / null / [1] / {"0":1} (claim-confusion battery)
 *   proto-pollution  __proto__ / constructor.prototype marker keys (server-side PP probe)
 *   unicode-control  NUL, overlong-UTF8-ish, RTL marks appended to string values
 *   oversized        10_000-char strings (boundary / parser-path probes)
 *   placeholder-swap identifier-ish fields → ZZFAKE / nobody@ / 0-prefixed (Tier-3)
 *   format-break     email/date/uri-shaped values → schema-valid-shaped garbage (validation differential)
 *   deep-nest        128-deep object (depth-limit probes)
 *   dup-keys         duplicate the first key with a conflicting value (parser-disagreement probe)
 *   number-forms     numeric values → 1e0 / 1.00 / 1e2 / -0 / 1e999 / 2^53+1 literals
 *                    (value-comparison checks confused by representation — bypass-catalogue §O6)
 *   json-escapes     all "/" escaped as \u002f (serialized-form checks miss the decoded slash)
 *
 * Output: <out-dir>/body.<profile>.<i>.json + manifest.tsv (file → profile → mutation note).
 * Pure Node stdlib. Scope = the targets the operator names. Hygiene rules:
 * references/ethics-and-roe.md — mutants are probes, one hypothesis per mutant.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const args = process.argv.slice(2);
const pos = []; const flags = { profiles: 'all', outDir: 'mutants', cap: 64 };
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--profiles') flags.profiles = args[++i];
  else if (args[i] === '--out-dir') flags.outDir = args[++i];
  else if (args[i] === '--cap') flags.cap = parseInt(args[++i], 10);
  else pos.push(args[i]);
}
if (!pos.length) { console.error('Usage: node body-mutator.js <body.json> [--profiles all|p1,p2] [--out-dir DIR] [--cap N]'); process.exit(1); }

const body = JSON.parse(fs.readFileSync(pos[0], 'utf8'));
const rand = () => crypto.randomBytes(4).toString('hex');
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const IDENT_KEYS = /(id|token|email|user(name)?|account|uuid|guid|session|phone|name)$/i;
const isPlaceholderish = (v) => typeof v === 'string' && (EMAIL_RE.test(v) || IDENT_KEYS.test(''));

// Deep clone + walk helpers
const clone = (o) => JSON.parse(JSON.stringify(o));
function walk(o, fn, k = null, parent = null) {
  if (Array.isArray(o)) { o.forEach((v, i) => walk(v, fn, k === null ? i : k, o)); return; }
  if (o && typeof o === 'object') { for (const [key, v] of Object.entries(o)) walk(v, fn, key, o); }
  else if (k !== null && parent !== null) fn(k, o, parent);
}

const profiles = {
  'type-juggle': (b) => {
    ['1', 'true', null, [1], { '0': 1 }].forEach((tv, i) => {
      const m = clone(b);
      walk(m, (k, v, p) => { if (typeof v === 'string') p[k] = i === 0 ? tv : p[k]; });
      // one mutant per representative type: swap the FIRST string prop
      const m2 = clone(b);
      let done = false;
      walk(m2, (k, v, p) => { if (!done && typeof v === 'string') { p[k] = tv; done = true; } });
      emit(`type-juggle.${i}`, m2, `first string prop → ${JSON.stringify(tv)}`);
    });
  },
  'proto-pollution': (b) => {
    const m1 = clone(b); m1['__proto__'] = { ppmarker: rand() }; emit('proto-pollution.0', m1, '__proto__.ppmarker key');
    const m2 = clone(b); m2['constructor'] = { prototype: { ppmarker: rand() } }; emit('proto-pollution.1', m2, 'constructor.prototype.ppmarker key');
  },
  'unicode-control': (b) => {
    ['\u0000', '%00', '\u202E', '\u0130'].forEach((u, i) => {
      const m = clone(b); let done = false;
      walk(m, (k, v, p) => { if (!done && typeof v === 'string') { p[k] = v + u; done = true; } });
      emit(`unicode-control.${i}`, m, `append ${JSON.stringify(u)} to first string`);
    });
  },
  'oversized': (b) => {
    const m = clone(b); let done = false;
    walk(m, (k, v, p) => { if (!done && typeof v === 'string') { p[k] = 'A'.repeat(10000); done = true; } });
    emit('oversized.0', m, 'first string → 10k chars');
  },
  'placeholder-swap': (b) => {
    const m = clone(b);
    walk(m, (k, v, p) => {
      if (typeof v !== 'string') return;
      if (EMAIL_RE.test(v)) p[k] = `nobody+${rand()}@example.test`;      // placeholder identity
      else if (/^[0-9a-f-]{36}$/i.test(v)) p[k] = '00000000-0000-0000-0000-000000000000';
      else if (IDENT_KEYS.test(k)) p[k] = `ZZFAKE${rand()}`;
    });
    emit('placeholder-swap.0', m, 'identifiers → ZZFAKE/nobody/0-UUID (Tier-3)');
  },
  'format-break': (b) => {
    const m = clone(b);
    walk(m, (k, v, p) => {
      if (typeof v !== 'string') return;
      if (EMAIL_RE.test(v)) p[k] = 'not-an-email';
      else if (/^\d{4}-\d{2}-\d{2}/.test(v)) p[k] = 'not-a-date';
      else if (/^https?:\/\//.test(v)) p[k] = 'not-a-url';
    });
    emit('format-break.0', m, 'format-shaped values → shaped garbage');
  },
  'deep-nest': (b) => {
    let m = clone(b); let cursor = m; let firstKey = null;
    for (const k of Object.keys(m)) { firstKey = k; break; }
    let node = { a: 1 };
    for (let i = 0; i < 128; i++) node = { a: node };
    if (firstKey !== null) m[firstKey] = node; else m.deep = node;
    emit('deep-nest.0', m, '128-deep nested object');
  },
  'dup-keys': (b) => {
    // Insert a "_dup" line after the FIRST key line: consumer reads last, validator reads first.
    const lines = JSON.stringify(b, null, 2).split('\n');
    const i = lines.findIndex((l) => /^  "/.test(l));
    if (i >= 0) {
      const key = lines[i].match(/"([^"]+)":/)[1];
      const comma = lines[i].trimEnd().endsWith(',') ? ',' : '';
      lines.splice(i + 1, 0, `  "${key}_dup": "zzdup"${comma}`);
    }
    emitRaw('dup-keys.0', lines.join('\n'), 'duplicate first key with _dup variant (text-level)');
  },
  'number-forms': (b) => {
    // Text-level literals: JSON.stringify(1e999) === "null", so literals are spliced post-serialization.
    const literals = ['1e0', '1.00', '1e2', '-0', '1e999', '9007199254740993'];
    let idx = 0;
    for (const lit of literals) {
      const tag = `__NUMLIT_${idx}__`;
      const m = clone(b); let done = false;
      walk(m, (k, v, p) => { if (!done && typeof v === 'number' && Number.isFinite(v)) { p[k] = tag; done = true; } });
      if (done) { emitRaw(`number-forms.${idx}`, JSON.stringify(m).split(`"${tag}"`).join(lit), `first numeric prop → literal ${lit}`); idx++; }
    }
  },
  'json-escapes': (b) => {
    const txt = JSON.stringify(b).split('/').join('\\u002f');
    emitRaw('json-escapes.0', txt, 'all / escaped as \\u002f (valid JSON text; decoded by the consumer)');
  },
};

let count = 0;
const manifest = [];
fs.mkdirSync(flags.outDir, { recursive: true });
function emit(name, obj, note) {
  if (count >= flags.cap) return;
  count++;
  const f = path.join(flags.outDir, `body.${name}.json`);
  fs.writeFileSync(f, JSON.stringify(obj, null, 2) + '\n');
  manifest.push([path.basename(f), name.split('.')[0], note]);
}
function emitRaw(name, txt, note) {
  if (count >= flags.cap) return;
  count++;
  const f = path.join(flags.outDir, `body.${name}.json`);
  fs.writeFileSync(f, txt + '\n');
  manifest.push([path.basename(f), name.split('.')[0], note]);
}

const wanted = flags.profiles === 'all' ? Object.keys(profiles) : flags.profiles.split(',');
for (const p of wanted) {
  if (!profiles[p]) { console.error(`Unknown profile: ${p} (known: ${Object.keys(profiles).join(', ')})`); process.exit(1); }
  profiles[p](body);
}
fs.writeFileSync(path.join(flags.outDir, 'manifest.tsv'), 'FILE\tPROFILE\tMUTATION\n' + manifest.map(r => r.join('\t')).join('\n') + '\n');
console.log(`Emitted ${count} mutants → ${flags.outDir}/ (manifest.tsv)`);
console.log('Run them one hypothesis at a time; record positive AND negative results in the ledger (hunt-ledger.sh).');
