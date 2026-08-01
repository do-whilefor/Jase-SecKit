#!/usr/bin/env node
/**
 * CVSS 3.1 Base Score calculator — strict, per FIRST.org spec.
 *
 * Usage:
 *   node cvss31-calculator.js "AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L"
 *   node cvss31-calculator.js    # interactive prompt
 *
 * Prints: score, severity, and the full computation trail.
 * This is the calculator to run BEFORE submitting any report — strip the
 * four inflation patterns (PR:L→PR:N, UI:R→UI:N, AC:H→AC:L, narrative impact)
 * by re-reading your vector with the strictest defensible metrics.
 */

const METRICS = {
  AV: { N: 0.85, A: 0.62, L: 0.55, P: 0.2 },
  AC: { L: 0.77, H: 0.44 },
  PR_U: { N: 0.85, L: 0.62, H: 0.27 }, // Scope Unchanged
  PR_C: { N: 0.85, L: 0.68, H: 0.5 },  // Scope Changed
  UI: { N: 0.85, R: 0.62 },
  CIA: { H: 0.56, L: 0.22, N: 0 },     // C, I, A share factors
};

function severity(score) {
  if (score === 0) return "NONE";
  if (score < 4.0) return "LOW";
  if (score < 7.0) return "MEDIUM";
  if (score < 9.0) return "HIGH";
  return "CRITICAL";
}

// FIRST.org 3.1 roundup (avoid FP drift): Math.ceil(x*10)/10
function roundup(x) {
  return Math.ceil(x * 10) / 10;
}

function calc(vector) {
  const parts = vector.toUpperCase().split("/").map(p => p.trim()).filter(Boolean);
  if (parts.length < 8) {
    throw new Error(`Vector needs 8 metrics: AV/AC/PR/UI/S/C/I/A — got ${parts.length}`);
  }
  const m = {};
  for (const p of parts) {
    const [k, v] = p.split(":");
    if (!k || !v) throw new Error(`Bad metric "${p}" — expected KEY:VALUE`);
    m[k] = v;
  }
  for (const k of ["AV","AC","PR","UI","S","C","I","A"]) {
    if (!(k in m)) throw new Error(`Missing metric ${k}`);
  }

  const scopeChanged = m.S === "C";
  const pr = (scopeChanged ? METRICS.PR_C : METRICS.PR_U)[m.PR];
  if (pr === undefined) throw new Error(`Bad PR value ${m.PR}`);
  const av = METRICS.AV[m.AV]; if (av === undefined) throw new Error(`Bad AV ${m.AV}`);
  const ac = METRICS.AC[m.AC]; if (ac === undefined) throw new Error(`Bad AC ${m.AC}`);
  const ui = METRICS.UI[m.UI]; if (ui === undefined) throw new Error(`Bad UI ${m.UI}`);
  const c = METRICS.CIA[m.C]; if (c === undefined) throw new Error(`Bad C ${m.C}`);
  const i = METRICS.CIA[m.I]; if (i === undefined) throw new Error(`Bad I ${m.I}`);
  const a = METRICS.CIA[m.A]; if (a === undefined) throw new Error(`Bad A ${m.A}`);

  const ISCBase = 1 - (1 - c) * (1 - i) * (1 - a);

  let impact, impactLabel;
  if (scopeChanged) {
    // 3.1 Scope Changed formula (NOT the 3.0 formula)
    impact = 7.52 * ISCBase - 3.25 * (ISCBase - 0.029) - 3.25 * ISCBase ** 2;
    impactLabel = "Scope Changed";
  } else {
    impact = 6.42 * ISCBase;
    impactLabel = "Scope Unchanged";
  }

  const exploitability = 8.22 * av * ac * pr * ui;

  let baseScore;
  if (impact <= 0) {
    baseScore = 0;
  } else if (scopeChanged) {
    baseScore = roundup(Math.min(1.08 * (impact + exploitability), 10));
  } else {
    baseScore = roundup(Math.min(impact + exploitability, 10));
  }

  return {
    vector,
    ISCBase,
    impact,
    impactLabel,
    exploitability,
    baseScore,
    severity: severity(baseScore),
  };
}

function format(r) {
  const lines = [
    `Vector:    ${r.vector}`,
    `Score:     ${r.baseScore.toFixed(1)}`,
    `Severity:  ${r.severity}`,
    ``,
    `Computation:`,
    `  ISCBase     = 1 - (1-C)(1-I)(1-A) = ${r.ISCBase.toFixed(4)}`,
    `  Impact      = ${r.impact.toFixed(4)}  (${r.impactLabel})`,
    `  Exploit     = ${r.exploitability.toFixed(4)}`,
  ];
  if (r.impact <= 0) {
    lines.push(`  Base        = 0  (Impact <= 0)`);
  } else if (r.impactLabel === "Scope Changed") {
    lines.push(`  Base        = roundup(min(1.08 * (${r.impact.toFixed(3)} + ${r.exploitability.toFixed(3)}), 10)) = ${r.baseScore.toFixed(1)}`);
  } else {
    lines.push(`  Base        = roundup(min(${r.impact.toFixed(3)} + ${r.exploitability.toFixed(3)}, 10)) = ${r.baseScore.toFixed(1)}`);
  }
  return lines.join("\n");
}

// Main
const arg = process.argv[2];
if (arg) {
  try {
    console.log(format(calc(arg)));
  } catch (e) {
    console.error(`Error: ${e.message}`);
    console.error(`Usage: node cvss31-calculator.js "AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L"`);
    process.exit(1);
  }
} else if (process.stdin.isTTY) {
  const readline = require("readline");
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  rl.question("CVSS 3.1 vector (e.g. AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L): ", answer => {
    try {
      console.log(format(calc(answer)));
    } catch (e) {
      console.error(`Error: ${e.message}`);
      process.exit(1);
    }
    rl.close();
  });
} else {
  // Read from stdin pipe
  let data = "";
  process.stdin.on("data", chunk => data += chunk);
  process.stdin.on("end", () => {
    try {
      console.log(format(calc(data.trim())));
    } catch (e) {
      console.error(`Error: ${e.message}`);
      process.exit(1);
    }
  });
}

// Export for unit testing
if (typeof module !== "undefined") {
  module.exports = { calc, severity, roundup, METRICS };
}
