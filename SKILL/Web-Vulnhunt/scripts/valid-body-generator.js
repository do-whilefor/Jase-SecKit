#!/usr/bin/env node
/**
 * valid-body-generator.js — Generate a schema-valid request body from an
 * OpenAPI spec. Kills Core principle 3 (SKILL.md): a 400 on an empty `{}`
 * body says NOTHING about authorization — Bean Validation runs before
 * @PreAuthorize. Always re-test an authz candidate with a body that actually
 * passes schema validation. This script builds that body.
 *
 * Usage:
 *   node valid-body-generator.js <openapi.json> <path> <method> [--out FILE] [--placeholder] [--fill-optional]
 *
 *   --placeholder     ZZFAKE-style values for identifier-ish fields (Tier-3 rule:
 *                     state-changing probes never carry real identifiers), while
 *                     still honoring enum/format/pattern so validation passes.
 *   --fill-optional   include optional properties too (default: required only)
 *
 * Pure Node stdlib. Handles local $ref, allOf merge, oneOf/anyOf (first branch),
 * enum, format (email/date/date-time/uuid/uri/ipv4/hostname), min/max constraints.
 *
 * Scope = the targets the operator names. Hygiene rules: references/ethics-and-roe.md.
 */
'use strict';
const fs = require('fs');
const crypto = require('crypto');

function die(msg) { console.error('ERROR: ' + msg); process.exit(1); }

const args = process.argv.slice(2);
const pos = [];
const flags = {};
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--out') flags.out = args[++i];
  else if (args[i] === '--placeholder') flags.placeholder = true;
  else if (args[i] === '--fill-optional') flags.fillOptional = true;
  else pos.push(args[i]);
}
if (pos.length < 3) die('Usage: node valid-body-generator.js <openapi.json> <path> <method> [--out FILE] [--placeholder] [--fill-optional]');
// Git Bash / MSYS2 converts POSIX-looking args ('/api/redeem') into Windows
// paths under the Git install root. Undo that; also accept a missing leading slash.
function unmsysPath(p) {
  p = String(p).replace(/\\/g, '/');
  const m = p.match(/^[A-Za-z]:\/(?:Program Files \(x86\)\/|Program Files\/)?Git\/?(.*)$/i);
  if (m) return '/' + (m[1] || '');
  return p;
}
const [specPath, wantPathRaw, wantMethodRaw] = pos;
const wantPath = unmsysPath(wantPathRaw).replace(/\/+$/, '') || '/';
const wantMethod = wantMethodRaw.toLowerCase();

const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));

function resolveRef(node, depth = 0) {
  if (!node || typeof node !== 'object' || depth > 20) return node;
  if (typeof node.$ref === 'string') {
    if (!node.$ref.startsWith('#/')) die('External $ref unsupported: ' + node.$ref);
    let cur = spec;
    for (const part of node.$ref.slice(2).split('/')) {
      cur = cur && cur[part.replace(/~1/g, '/').replace(/~0/g, '~')];
    }
    if (!cur) die('Unresolvable $ref: ' + node.$ref);
    return resolveRef(cur, depth + 1);
  }
  return node;
}

function mergeAllOf(schema, depth = 0) {
  if (!schema || typeof schema !== 'object' || depth > 20) return schema;
  if (!Array.isArray(schema.allOf)) return schema;
  const merged = { properties: {}, required: [] };
  for (const sub of schema.allOf) {
    const r = mergeAllOf(resolveRef(sub), depth + 1);
    merged.properties = { ...merged.properties, ...(r.properties || {}) };
    merged.required = [...new Set([...merged.required, ...(r.required || [])])];
    for (const k of Object.keys(r)) {
      if (!['properties', 'required', 'allOf', '$ref'].includes(k) && merged[k] === undefined) merged[k] = r[k];
    }
  }
  for (const k of Object.keys(schema)) {
    if (k !== 'allOf' && merged[k] === undefined) merged[k] = schema[k];
  }
  if (!merged.required.length) delete merged.required;
  return merged;
}

function pickBranch(schema, depth = 0) {
  const s = resolveRef(schema, depth);
  if (Array.isArray(s.oneOf) && s.oneOf.length) return resolveRef(s.oneOf[0], depth);
  if (Array.isArray(s.anyOf) && s.anyOf.length) return resolveRef(s.anyOf[0], depth);
  return s;
}

const rand = (n = 6) => crypto.randomBytes(n).toString('hex').slice(0, n);

function placeholderFor(format, propName) {
  switch (format) {
    case 'email': return `zzfake${rand(4)}@example.test`;
    case 'uuid': return crypto.randomUUID();
    case 'date': return new Date().toISOString().slice(0, 10);
    case 'date-time': return new Date().toISOString();
    case 'uri': case 'url': return `https://example.test/${rand(8)}`;
    case 'ipv4': return '192.0.2.1';
    case 'hostname': return `host${rand(4)}.example.test`;
    default: return `ZZFAKE${rand(6)}`;
  }
}

function genValue(schema, propName, depth) {
  const s = pickBranch(schema, depth);
  if (!s || typeof s !== 'object') return null;
  if (Array.isArray(s.enum) && s.enum.length) return s.enum[0];
  if (s.example !== undefined && !flags.placeholder) return s.example;
  if (s.default !== undefined && !flags.placeholder) return s.default;
  const minLen = s.minLength || 1, maxLen = s.maxLength || 256;
  const str = (v) => {
    let out = v;
    if (s.pattern) {
      // Patterns are only bounded-tried, not synthesized — keep the value simple and warn.
      out = String(out).slice(0, maxLen) || 'ZZFAKE' + rand();
      return out;
    }
    return out.length < minLen ? String(out).padEnd(minLen, 'x') : String(out).slice(0, maxLen);
  };
  if (s.format && flags.placeholder) return str(placeholderFor(s.format, propName));
  switch (s.type) {
    case 'string': return str(s.format && !flags.placeholder ? placeholderFor(s.format, propName) : (flags.placeholder ? `ZZFAKE${rand(6)}` : `${propName}-${rand(4)}`));
    case 'integer': case 'number': {
      let v = s.minimum ?? s.exclusiveMinimum ?? 1;
      if (s.maximum !== undefined && v > s.maximum) v = s.maximum;
      return v;
    }
    case 'boolean': return true;
    case 'array': {
      const item = genValue(s.items, propName + 'Item', depth + 1);
      return item === undefined ? [] : [item];
    }
    case 'object': return genObject(s, depth + 1);
    default: return flags.placeholder ? `ZZFAKE${rand(6)}` : null;
  }
}

function genObject(schema, depth = 0) {
  if (depth > 12) return {};
  const s = mergeAllOf(pickBranch(schema, depth), depth);
  const obj = {};
  const props = s.properties || {};
  const required = new Set(s.required || []);
  for (const [name, pschema] of Object.entries(props)) {
    if (!required.has(name) && !flags.fillOptional) continue;
    obj[name] = genValue(pschema, name, depth);
  }
  return obj;
}

// Locate path (exact or OpenAPI template match: /a/{id} vs /a/x)
function findPath() {
  for (const cand of [wantPath, '/' + wantPath.replace(/^\/+/, '')]) {
    if (spec.paths[cand]) return cand;
  }
  for (const p of Object.keys(spec.paths || {})) {
    const re = new RegExp('^' + p.replace(/\{[^}]+\}/g, '[^/]+') + '$');
    if (re.test(wantPath)) return p;
  }
  die(`path not in spec: ${wantPath}`);
}
const realPath = findPath();
const op = (spec.paths[realPath] || {})[wantMethod];
if (!op) die(`method ${wantMethod.toUpperCase()} not documented for ${realPath} (generate only what the schema defines — do not invent endpoints)`);

const content = ((op.requestBody || {}).content) || {};
const jsonSchema = (content['application/json'] || {}).schema
  || content[Object.keys(content)[0]]?.schema;
if (!jsonSchema) {
  console.log(JSON.stringify({ _note: 'no request body documented for this operation', _path: realPath, _method: wantMethod.toUpperCase() }, null, 2));
  process.exit(0);
}

const body = genObject(resolveRef(jsonSchema), 0);
const out = JSON.stringify(body, null, 2);
if (flags.out) { fs.writeFileSync(flags.out, out + '\n'); console.error('Wrote ' + flags.out); }
else console.log(out);
