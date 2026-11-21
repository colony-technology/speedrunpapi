// speedrunpapi credits: the packs are listed, --print opens no browser, and a job refused for lack of credits ends
// with the add-credits line. Runs both clients against a local mock API and a fake browser opener.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { spawn } from "node:child_process";

const LINE = "add credits: speedrunpapi credits buy";
const PACKS = [["500", "$10", "$0.020"], ["1000", "$18", "$0.018"], ["5000", "$75", "$0.015"], ["20000", "$240", "$0.012"], ["100000", "$1000", "$0.010"]];
const dir = fs.mkdtempSync(path.join(os.tmpdir(), "credits-cli-"));
const bin = path.join(dir, "bin"), marker = path.join(dir, "opened");
fs.mkdirSync(bin);
for (const name of ["open", "xdg-open"]) {
  fs.writeFileSync(path.join(bin, name), `#!/bin/sh\necho "$@" >> "${marker}"\n`);
  fs.chmodSync(path.join(bin, name), 0o755);
}
const JOB = "0f0f0f0f-0f0f-4f0f-8f0f-0f0f0f0f0f0f", KEY = "el_" + "a".repeat(32);
let mode = "reservation";
const server = http.createServer((req, res) => {
  const send = (status, body) => { res.writeHead(status, { "content-type": "application/json" }); res.end(JSON.stringify(body)); };
  let body = "";
  req.on("data", (c) => body += c);
  req.on("end", () => {
    if (req.url === "/v1/usage") return send(200, { balance: mode === "empty" ? 0 : 7, post_paid: false });
    if (req.url === "/v1/quotes") return mode === "quote402" ? send(402, { error: "Insufficient certificate balance. Buy a pack." }) : send(200, { quote: { id: "11111111-1111-4111-8111-111111111111" } });
    const failed = { id: JOB, state: "failed", error: "Insufficient available credits for this reservation" };
    if (req.url === "/v1/jobs") return send(201, { job: failed });
    if (req.url === "/v1/jobs/" + JOB) return send(200, { job: failed });
    send(404, { error: "not found" });
  });
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const api = "http://127.0.0.1:" + server.address().port;
const run = (cli, args, env = {}) => new Promise((resolve) => {
  const child = spawn(process.execPath, [cli, ...args], { env: { ...process.env, PATH: bin + path.delimiter + process.env.PATH, COLONY_API: api, ...env } });
  let out = "", err = "";
  child.stdout.on("data", (d) => out += d);
  child.stderr.on("data", (d) => err += d);
  child.on("close", (code) => resolve({ code, out, err }));
});
const lastLine = (s) => s.trim().split("\n").pop();
const opened = () => fs.existsSync(marker) ? fs.readFileSync(marker, "utf8") : "";
const source = path.join(dir, "chain.math");
fs.writeFileSync(source, JSON.stringify({ operator: "chain.ordered-decision.v1", args: { alternating: 12, k: 4, depth: 2 } }));
let failures = 0, checks = 0;
const ok = (cond, label) => { checks++; if (!cond) { failures++; console.log("FAIL " + label); } else console.log("ok " + label); };
for (const cli of ["bin/speedrunpapi.mjs", "python/src/speedrunpapi/speedrunpapi.mjs"]) {
  fs.rmSync(marker, { force: true });
  const list = await run(cli, ["credits", "buy"]);
  ok(list.code === 0 && PACKS.every(([n, usd, each]) => new RegExp("^\\s*" + n + " credits\\s+\\" + usd + "\\s+\\" + each + " each$", "m").test(list.out)) && opened() === "", cli + ": credits buy lists the five packs and opens nothing");
  const printed = await run(cli, ["credits", "buy", "1000", "--print"]);
  ok(printed.code === 0 && printed.out.includes("https://colony.technology/packs\n") && printed.out.includes("after payment this page asks for your receipt email and shows the API key") && opened() === "", cli + ": --print prints the link and opens no browser");
  const browse = await run(cli, ["credits", "buy", "1000"]);
  for (let i = 0; i < 50 && opened() === ""; i++) await new Promise((r) => setTimeout(r, 100));   // the opener runs detached
  ok(browse.code === 0 && opened().trim() === "https://colony.technology/packs", cli + ": without --print the link goes to the system opener");
  ok((await run(cli, ["credits", "buy", "700"])).code === 2, cli + ": an unknown pack is refused");
  mode = "reservation";
  const balance = await run(cli, ["credits"], { COLONY_API_KEY: KEY });
  ok(balance.code === 0 && JSON.parse(balance.out).credits === 7, cli + ": credits prints the balance");
  const solve = await run(cli, ["solve", source], { COLONY_API_KEY: KEY });
  ok(solve.code === 1 && lastLine(solve.err) === LINE && solve.err.includes("Insufficient available credits"), cli + ": a solve refused at reservation ends with the add-credits line");
  mode = "quote402";
  const refused = await run(cli, ["solve", source], { COLONY_API_KEY: KEY });
  ok(refused.code === 1 && lastLine(refused.err) === LINE && refused.err.includes("colony API 402"), cli + ": a 402 from the API ends with the add-credits line");
  mode = "empty";
  const empty = await run(cli, ["credits"], { COLONY_API_KEY: KEY });
  ok(empty.code === 0 && JSON.parse(empty.out).credits === 0 && lastLine(empty.err) === LINE, cli + ": an empty balance points to credits buy");
}
server.close();
console.log(`${checks - failures} of ${checks} credits checks passed`);
if (failures) process.exit(1);
