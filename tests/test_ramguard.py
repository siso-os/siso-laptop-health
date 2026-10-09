#!/usr/bin/env python3
"""RAM guard: parks only done/idle agents idle > 60 min that are not kept, focused or unresumable; the soak, Agent Zero and
A0-DESK are never candidates; a busy input box or an agent that woke up is never typed into. 2 Oct: load 210 from RAM exhaustion."""
import importlib.machinery, os, sys, tempfile, shutil, time

HOUSE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
lh = importlib.machinery.SourceFileLoader("lh", os.path.join(HOUSE, "bin/laptop-health")).load_module()
A = lambda pane, status, title, cwd="/x", idle=200, focused=False, sid="s-1": {
    "pane_id": pane, "agent_status": status, "terminal_title_stripped": title, "cwd": cwd, "agent": "claude", "focused": focused,
    "agent_session": {"value": sid}, "_idle": idle}
agents = [A("p1", "done", "old chat"), A("p2", "idle", "A0-DESK"), A("p3", "done", "STREAMING-CLAUDE"), A("p4", "working", "busy"),
          A("p5", "done", "recent", idle=10), A("p6", "done", "watched", focused=True), A("p7", "done", "nosid", sid=""),
          A("p8", "done", "owner", cwd="/w/agent-zero/siso-firstmate"), A("p9", "idle", "HEALTH")]
lh.herdr_json = lambda *a: {"agents": agents}
lh.registry_kept = lambda: {"ownerone"}
lh.landed = lambda cwd: cwd.endswith("/landed")
agents.append(A("p10", "done", "ownerone"))
agents.append({**A("p11", "done", "codex-unlanded", cwd="/w/unlanded"), "agent": "codex"})
agents.append({**A("p12", "done", "codex-landed", cwd="/w/landed"), "agent": "codex"})
lh.herdr_names = lambda: {}
lh.agent_idle_min = lambda a: a["_idle"]
ok, skipped = lh.park_candidates()
assert [r[0] for r in ok] == ["p1", "p12"] or sorted(r[0] for r in ok) == ["p1", "p12"], ok
why = {r[0]: r[6] for r in skipped}
assert "keep" in why["p2"] and "keep" in why["p3"] and "keep" in why["p8"] and "keep" in why["p9"], why
assert "registry" in why["p10"] and "not landed" in why["p11"]
assert "focused" in why["p6"] and "only 10" in why["p5"] and "no session id" in why["p7"] and "p4" not in why, why

sent = []
lh.sh = lambda cmd, timeout=60: sent.append(cmd) or ""
lh.time.sleep = lambda s: None
lh.input_box = lambda pane: "half typed"
assert lh.park("p1", "claude", "s-1", "/x") == (False, "input box not empty") and not sent
lh.input_box = lambda pane: ""
agents[0]["agent_status"] = "working"
assert lh.park("p1", "claude", "s-1", "/x") == (False, "no longer idle") and not sent
agents[0]["agent_status"] = "done"
lh.sh = lambda cmd, timeout=60: sent.append(cmd) or ("Background work is running  1. Stop  2. Keep" if cmd[:3] == ["herdr", "pane", "read"] else "")
r = lh.park("p1", "claude", "s-1", "/x")
assert r == (False, "kept: background work") and ["herdr", "pane", "send-keys", "p1", "Escape"] in sent and ["herdr", "pane", "send-keys", "p1", "1"] not in sent, (r, sent)
sent.clear(); lh.sh = lambda cmd, timeout=60: sent.append(cmd) or ""
lh.park("p1", "claude", "s-1", "/x")
assert ["herdr", "pane", "send-text", "p1", "/exit"] in sent
agents[11]["agent_status"] = "done"; sent.clear(); assert lh.park("p12", "codex", "s", "/w/landed")[0] and ["herdr", "pane", "close", "p12"] in sent
assert lh.resume_cmd("codex", "abc", "/w") == "cd /w && codex resume abc"
print("ok: parks only stale non-kept idle agents; soak/A0/A0-DESK/HEALTH kept; never types into a busy box or a woken agent")

# the real landed(): a temp repo whose HEAD is in origin/main and clean is landed; an extra commit or a dirty file is not
import subprocess
importlib.machinery.SourceFileLoader("lh2", os.path.join(HOUSE, "bin/laptop-health")).load_module()
lh2 = importlib.machinery.SourceFileLoader("lh2b", os.path.join(HOUSE, "bin/laptop-health")).load_module()
tmp = tempfile.mkdtemp(prefix=".siso-ephemeral-landed.")
try:
    run = lambda *c: subprocess.run(c, cwd=tmp + "/r", capture_output=True, text=True, check=True)
    os.makedirs(tmp + "/r"); run("git", "init", "-q", "-b", "main"); run("git", "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "one")
    run("git", "update-ref", "refs/remotes/origin/main", "HEAD")
    assert lh2.landed(tmp + "/r") is True
    open(tmp + "/r/f", "w").write("x"); assert lh2.landed(tmp + "/r") is False        # uncommitted
    os.remove(tmp + "/r/f"); run("git", "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "two")
    assert lh2.landed(tmp + "/r") is False                                           # commit not in origin/main
    assert lh2.landed(tmp) is False                                                  # not a repo
    print("ok: real landed() on a temp repo: clean+merged True; dirty, unmerged, not-a-repo False")
finally:
    shutil.rmtree(tmp)
