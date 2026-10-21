#!/usr/bin/env node
/**
 * CVSS 3.1 Base Score calculator, adapted from Web-Vulnhunt.
 * Corrected for webounty: Scope Changed, Roundup, vector validation and CLI.
 * Upstream attribution and license: ../THIRD_PARTY_NOTICES.md.
 * CVSS is owned by FIRST.Org, Inc. and used by permission.
 * Formula: https://www.first.org/cvss/v3.1/specification-document
 *
 * Usage:
 *   node cvss31-calculator.js "AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L"
 *   node cvss31-calculator.js --json "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
 *   node cvss31-calculator.js    # interactive prompt or piped input
 *
 * Prints: score, severity, and the full computation trail.
 * This calculates the supplied Base vector; it does not establish that the
 * vulnerability or the metric choices are supported by evidence.
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

// FIRST CVSS 3.1 Appendix A: round to five decimals before rounding upward.
function roundup(x) {
  const intInput = Math.round(x * 100000);
  return intInput % 10000 === 0
    ? intInput / 100000
    : (Math.floor(intInput / 10000) + 1) / 10;
}

function calc(vector) {
  const keys = ["AV", "AC", "PR", "UI", "S", "C", "I", "A"];
  const parts = vector.trim().toUpperCase().split("/").map(p => p.trim());
  if (parts[0].startsWith("CVSS:")) {
    if (parts.shift() !== "CVSS:3.1") {
      throw new Error("Only CVSS:3.1 Base vectors are supported");
    }
  }
  const m = {};
  for (const p of parts) {
    const fields = p.split(":");
    const [k, v] = fields;
    if (fields.length !== 2 || !k || !v) {
      throw new Error(`Bad metric "${p}" — expected KEY:VALUE`);
    }
    if (!keys.includes(k)) throw new Error(`Unsupported Base metric ${k}`);
    if (Object.hasOwn(m, k)) throw new Error(`Duplicate metric ${k}`);
    m[k] = v;
  }
  for (const k of keys) {
    if (!Object.hasOwn(m, k)) throw new Error(`Missing metric ${k}`);
  }
  if (!["U", "C"].includes(m.S)) throw new Error(`Bad S value ${m.S}`);

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
    // FIRST CVSS 3.1 section 7.1: Base Impact, not Modified Impact.
    impact = 7.52 * (ISCBase - 0.029) - 3.25 * (ISCBase - 0.02) ** 15;
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
    vector: "CVSS:3.1/" + keys.map(k => `${k}:${m[k]}`).join("/"),
    version: "3.1",
    metricGroup: "Base",
    metrics: m,
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

function main(args = process.argv.slice(2)) {
  const usage = 'Usage: node cvss31-calculator.js [--json] "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L"';
  if (args.length === 1 && args[0] === "--help") {
    console.log(usage);
    return;
  }
  const json = args.includes("--json");
  const vectors = args.filter(arg => arg !== "--json");
  if (vectors.length > 1 || vectors.some(arg => arg.startsWith("--"))) {
    console.error(usage);
    process.exitCode = 1;
    return;
  }
  const print = vector => {
    try {
      const result = calc(vector);
      console.log(json ? JSON.stringify(result) : format(result));
    } catch (e) {
      console.error(`Error: ${e.message}`);
      process.exitCode = 1;
    }
  };
  if (vectors.length) {
    print(vectors[0]);
  } else if (process.stdin.isTTY) {
    const readline = require("readline");
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question("CVSS 3.1 Base vector: ", answer => {
      print(answer);
      rl.close();
    });
  } else {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", chunk => data += chunk);
    process.stdin.on("end", () => print(data));
  }
}

// Importing the calculator never opens stdin or runs the CLI.
module.exports = { calc, severity, roundup, METRICS, format };
if (require.main === module) main();
