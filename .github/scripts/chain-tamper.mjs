// chain.ordered-decision.v1: a modified table, a swapped position or a stale digest is rejected by both clients.
// Every modification below also recomputes candidate_digest, so the rejection comes from the mathematics.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";

const canonical = (x) => Array.isArray(x) ? "[" + x.map(canonical).join(",") + "]" :
  x && typeof x === "object" ? "{" + Object.keys(x).sort().map((k) => JSON.stringify(k) + ":" + canonical(x[k])).join(",") + "}" : JSON.stringify(x);
const digest = (x) => "sha256:" + createHash("sha256").update(canonical(x)).digest("hex");
const value = (ops, v) => { let a = v[v.length - 1]; for (let i = v.length - 2; i >= 0; i--) a = ops[i] === "|" ? v[i] | a : v[i] & a; return a; };
const truth = (ops, m, k) => {
  let t = 0n;
  for (let r = 0; r < 1 << k; r++) if (value(ops, Array.from({ length: m }, (_, i) => r >> i & 1))) t |= 1n << BigInt(r);
  return t.toString(16).padStart((1 << k) / 4, "0");
};
const flip = (c) => c === "|" ? "&" : "|";
const tampers = {
  "truth table bit": (c) => { const t = c.tables[c.tables.length - 1]; t.truth = (BigInt("0x" + t.truth) ^ 1n).toString(16).padStart(t.truth.length, "0"); },
  "table rewired, truth table recomputed": (c) => { const t = c.tables[c.tables.length - 1]; t.ops = flip(t.ops[0]) + t.ops.slice(1); t.truth = truth(t.ops, t.inputs.length, c.k); },
  "leaf table and its sub-list with two positions swapped": (c) => {
    const t = c.tables.find((x) => !("segments" in x) && x.inputs.length >= 2);
    [t.inputs[0], t.inputs[1]] = [t.inputs[1], t.inputs[0]];
    [t.computes.positions[0], t.computes.positions[1]] = [t.computes.positions[1], t.computes.positions[0]];
  },
  "segment cut moved": (c) => { const t = c.tables[c.tables.length - 1]; t.segments[0][1] += 1; if (t.segments[1]) t.segments[1][0] += 1; else t.bottom += 1; },
  "stale digest": null
};
const dir = fs.mkdtempSync(path.join(os.tmpdir(), "chain-tamper-"));
let failures = 0, runs = 0;
for (const name of process.argv.slice(2)) {
  const src = `examples/${name}.math`, pkg = JSON.parse(fs.readFileSync(`examples/${name}.result.json`, "utf8"));
  if (digest(pkg.result.candidate) !== pkg.result.candidate_digest) throw Error(`${name}: digest recomputation disagrees with the bundle`);
  for (const [label, mutate] of Object.entries(tampers)) {
    const forged = structuredClone(pkg), c = forged.result.candidate;
    if (mutate) { mutate(c); forged.result.candidate_digest = digest(c); }
    else c.tables[0].truth = (BigInt("0x" + c.tables[0].truth) ^ 1n).toString(16).padStart(c.tables[0].truth.length, "0");
    const file = path.join(dir, `${name}.forged.json`);
    fs.writeFileSync(file, JSON.stringify(forged));
    let both = true;
    for (const cli of ["bin/speedrunpapi.mjs", "python/src/speedrunpapi/speedrunpapi.mjs"]) {
      const out = spawnSync(process.execPath, [cli, "check", src, file], { encoding: "utf8" });
      const rejected = out.status === 1 && JSON.parse(out.stdout).source_bound === false;
      runs++;
      if (!rejected) { failures++; both = false; console.log(`ACCEPTED ${name} / ${label} / ${cli}`); }
    }
    if (both) console.log(`rejected by both clients: ${name}: ${label}`);
  }
}
console.log(`${runs - failures} of ${runs} forged bundles rejected`);
if (failures) process.exit(1);
