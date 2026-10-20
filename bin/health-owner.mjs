#!/usr/bin/env node
// One bounded, authenticated HEALTH-host queue submission. Secret-bearing values
// are read only long enough to connect and never enter output or state.
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const HOME = os.homedir();
const DEFAULT_POLICY = path.join(process.cwd(), ".agents", "health-owner.json");
const SAFE_PHASES = new Set(["saved", "accepted", "started"]);
const FINISHED_PHASES = new Set(["accepted", "started", "cancelled"]);
function fail(reason) { console.log(JSON.stringify({ ok: false, reason })); return 1; }
function readJson(file) { return JSON.parse(fs.readFileSync(file, "utf8")); }
function atomic(file, value) { fs.mkdirSync(path.dirname(file), { recursive: true }); const tmp = `${file}.tmp-${process.pid}`; fs.writeFileSync(tmp, JSON.stringify(value, null, 2) + "\n", { mode: 0o600 }); fs.renameSync(tmp, file); try { fs.chmodSync(file, 0o600); } catch {} }
function mode(file) { return fs.statSync(file).mode & 0o777; }
function reasonOf(e) { return e && typeof e.code === "string" ? e.code : "blocked"; }
function activeTask(tasks) { return tasks.some(t => !t || !["done", "failed", "stopped", "error", "cancelled"].includes(t.status)); }
function validateMetadata(h) {
  if (!h || h.name !== "HEALTH" || typeof h.cwd !== "string" || typeof h.session !== "string" || !h.session || !Number.isInteger(Number(h.port)) || Number(h.port) < 1 || Number(h.port) > 65535 || typeof h.token !== "string" || !h.token) throw Error("host metadata");
  return h;
}
function validateHello(h, { bootstrap = false, automatic = true } = {}) {
  if (!h || h.name !== "HEALTH" || typeof h.session !== "string" || !h.session || h.child !== "running") throw Error("hello identity");
  const caps = h.capabilities ?? {};
  if (!h.queue || typeof h.queue.held !== "boolean" || !Array.isArray(h.queue.entries) ||
      caps.version !== 1 || typeof caps.compacting !== "boolean" ||
      !(caps.activeTurnId === null || typeof caps.activeTurnId === "string") ||
      !Array.isArray(h.pendingQuestions) || !Array.isArray(h.tasks)) throw Error("unsupported-protocol");
  if (caps.compacting || h.compacting) throw Error("host turn");
  if (automatic && caps.activeTurnId) throw Error("host turn");
  if (h.state !== "idle" && !(bootstrap && h.state === "working")) throw Error("host not idle");
  if (activeTask(h.tasks)) throw Error("active task");
  const q = h.queue ?? {};
  if (q.held) throw Error("queue held");
  const entries = q.entries;
  if (Array.isArray(h.pendingQuestions) && h.pendingQuestions.length) throw Error("pending question");
  if (entries.some(e => !FINISHED_PHASES.has(e?.phase))) throw Error("queue pending");
  return h;
}
function prompt(home, key) {
  const refs = [".agents/OWNER.md", ".agents/PLAN.md", ".agents/HANDOFF.md", ".agents/STATE.json", ".agents/role-health-ledger.jsonl"].map(f => path.join(home, f)).join(", ");
  return `[health-owner-key:${key}] Read ${refs}. Do one bounded next improvement for laptop health in <=15 minutes (max 1 helper). Do not run heavy local tests, estate-wide scans, or stop agents, apps, services, or worktrees. Never message or type into agent panes. Measure before and after, update .agents/PLAN.md and .agents/STATE.json, append .agents/role-health-ledger.jsonl and a RETURN, then update .agents/HANDOFF.md last. Read the owner plan and continue only if this is still useful.`;
}
async function submit(policy, opts = {}) {
  if (!policy || policy.enabled !== true) return { ok: false, reason: "disabled" };
  const policyFile = opts.policyPath || DEFAULT_POLICY;
  const ownerHome = policy.home || path.dirname(path.dirname(path.resolve(policyFile)));
  const hostPath = policy.hostPath ? path.resolve(policy.hostPath.replace(/^~/, HOME)) : path.join(HOME, ".local/state/agent-base/hosts", `name-${policy.host_name || "HEALTH"}.json`);
  const statePath = policy.statePath ? path.resolve(policy.statePath.replace(/^~/, HOME)) : path.join(path.dirname(path.resolve(policyFile)), "health-owner-state.json");
  try {
    if (mode(hostPath) !== 0o600) return { ok: false, reason: "host permissions" };
    const host = readJson(hostPath); validateMetadata(host);
    if (host.state !== "idle" && !(opts.enqueueNext === true && host.state === "working")) return { ok: false, reason: "host not idle" };
    if (host.child !== "running") return { ok: false, reason: "host child" };
    if (host.cwd !== ownerHome) return { ok: false, reason: "host cwd" };
    const now = Date.now(); const rawDue = Number(policy.cadence_seconds ?? policy.dueSeconds ?? 1800); if (!Number.isFinite(rawDue) || rawDue <= 0) return { ok: false, reason: "policy cadence" }; const due = Math.max(1800, rawDue); const slot = Math.floor(now / (due * 1000)); const key = `health-owner-${slot}`;
    let previous = {}; try { previous = readJson(statePath); } catch (e) {
      if (e.code !== "ENOENT") return { ok: false, reason: "state unavailable" };
    }
    if (!previous || typeof previous !== "object" || Array.isArray(previous)) return { ok: false, reason: "state unavailable" };
    if (["attempting", "ambiguous"].includes(previous.phase)) return { ok: false, reason: "unreconciled", key: previous.key };
    if (previous.key === key || Number(previous.cooldownUntil || 0) > now) return { ok: false, reason: "cooldown", key };
    const messageId = crypto.createHash("sha256").update(`${key}:${host.session}`).digest("hex").slice(0, 24); const cooldownUntil = now + due * 1000;
    const base = { key, messageId, session: host.session, phase: "attempting", at: now, cooldownUntil }; atomic(statePath, base);
    const url = `ws://127.0.0.1:${Number(host.port)}/ws?token=${encodeURIComponent(host.token)}`; const text = prompt(ownerHome, key);
    const result = await new Promise(resolve => {
      let done = false, hellos = 0, sent = false; const finish = value => { if (!done) { done = true; resolve(value); } }; let ws;
      try { ws = new WebSocket(url); } catch { finish({ ok: false, reason: "connect", phase: "blocked" }); return; }
      const timer = setTimeout(() => { try { ws.close(); } catch {} finish({ ok: false, reason: "timeout", phase: sent ? "ambiguous" : "blocked" }); }, 5000);
      ws.addEventListener("error", () => { clearTimeout(timer); finish({ ok: false, reason: "connection", phase: sent ? "ambiguous" : "blocked" }); });
      ws.addEventListener("message", ev => {
        if (done) return;
        let m; try { m = JSON.parse(String(ev.data)); } catch { return; }
        if (m.t === "hello") {
          if (++hellos !== 1) return; // duplicate hello is ignored; never send twice or invalidate a saved receipt
          try { validateHello(m, { bootstrap: opts.enqueueNext === true, automatic: opts.enqueueNext !== true }); } catch (e) { clearTimeout(timer); try { ws.close(); } catch {}; finish({ ok: false, reason: e?.message === "unsupported-protocol" ? "unsupported-protocol" : "hello blocked", phase: "blocked" }); return; }
          if (m.name !== host.name || m.session !== host.session) { clearTimeout(timer); try { ws.close(); } catch {}; finish({ ok: false, reason: "hello identity", phase: "blocked" }); return; }
          if (sent) return; sent = true;
          try { ws.send(JSON.stringify({ t: "prompt", text, images: [], delivery: "next", key, messageId })); }
          catch { clearTimeout(timer); try { ws.close(); } catch {} finish({ ok: false, reason: "connection", phase: "ambiguous" }); }
          return;
        }
        if (m.t !== "prompt.receipt" || m.key !== key || m.id !== messageId) return;
        clearTimeout(timer); try { ws.close(); } catch {} const phase = String(m.phase ?? "unknown");
        finish(SAFE_PHASES.has(phase) ? { ok: true, key, messageId, session: host.session, phase } : { ok: false, reason: phase === "failed" ? "failed" : "receipt", phase: phase === "failed" ? "failed" : "ambiguous" });
      });
    });
    atomic(statePath, { ...base, phase: result.phase ?? "ambiguous", ...(result.ok ? {} : { error: result.reason }) }); return result;
  } catch (e) { return { ok: false, reason: reasonOf(e) }; }
}
const args = process.argv.slice(2); const policyPath = args.includes("--policy") ? args[args.indexOf("--policy") + 1] : DEFAULT_POLICY;
export { submit, validateHello, validateMetadata };
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) { try { const result = await submit(readJson(policyPath), { enqueueNext: args.includes("--enqueue-next"), policyPath }); console.log(JSON.stringify(result)); process.exitCode = result.ok ? 0 : 1; } catch (e) { process.exitCode = fail(reasonOf(e)); } }
