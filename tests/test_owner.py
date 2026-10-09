#!/usr/bin/env python3
"""Regression for the 25 Sep whisper hunt: a CPU whisper loop under a Claude session must be attributed to that
session's herdr pane with the local-whisper tip, `tell` must never type into a pane whose input box has text, and
`pings` must name the agent that keeps starting the same command. Everything is simulated; nothing is sent."""
import importlib.machinery, os

HOUSE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
lh = importlib.machinery.SourceFileLoader("lh", os.path.join(HOUSE, "bin/laptop-health")).load_module()

AGENT, LOOP, WHISPER, HERDR = 100, 200, 300, 400
ROWS = {AGENT: {"ppid": 50, "age": 9000, "cpu": 1, "args": "/Users/x/.local/bin/claude"},
        50: {"ppid": 1, "age": 9000, "cpu": 1, "args": "/bin/zsh"},
        LOOP: {"ppid": AGENT, "age": 600, "cpu": 1, "args": "/bin/zsh -c source ~/.claude/shell-snapshots/s.sh && eval 'while read f; do whisper $f --model small.en; done < all.txt'"},
        WHISPER: {"ppid": LOOP, "age": 60, "cpu": 100, "args": "/opt/homebrew/Cellar/python/Python /opt/homebrew/bin/whisper a.opus --model small.en"},
        HERDR: {"ppid": 1, "age": 9000, "cpu": 1, "args": "/Users/x/.local/bin/herdr.real server"}}
BOX = {"w1-2": "  ⏺ done\n────\n❯\xa0\n────\n  status",
       "w1-3": "────\n❯\xa0yes promote the fix\n────",
       "w1-4": "  just output, no prompt visible"}
sent = []


def fake_sh(cmd, timeout=60):
    c = cmd if isinstance(cmd, list) else cmd.split()
    if c[:2] == ["ps", "eww"]:
        return "claude HERDR_ENV=1 HERDR_PANE_ID=p_11 HOME=/Users/x" if c[-1] == str(AGENT) else ""
    if c[:2] == ["ps", "-o"]:
        return "ttys014"
    if c[:3] == ["herdr", "pane", "get"]:
        return '{"result":{"pane":{"pane_id":"w1-2","tab_id":"w1:6","cwd":"/Users/x"}}}'
    if c[:3] == ["herdr", "pane", "list"]:
        return '{"result":{"panes":[{"pane_id":"w1-2","label":"BYK"},{"pane_id":"w1-3"},{"pane_id":"w1-4"}]}}'
    if c[:3] == ["herdr", "agent", "list"]:
        return '{"result":{"agents":[]}}'
    if c[:3] == ["herdr", "pane", "read"]:
        return BOX.get(c[3], "")
    if c[:3] == ["herdr", "pane", "send-text"] or c[:3] == ["herdr", "pane", "send-keys"]:
        sent.append(c); return ""
    return ""


lh.sh = fake_sh
lh.ps_rows = lambda: ROWS
lh.sample_run = lambda dur, every=0.25: ({WHISPER: 12, AGENT: 1, HERDR: 1}, 4, [4, 3, 4, 3])

# 1. the whisper load belongs to the Claude session's pane, with the local-whisper tip found via the process
groups, rows, samples, avg = lh.hogs(1)
g = groups[("agent", AGENT)]
assert abs(g["threads"] - 3.25) < 1e-9, g["threads"]
assert "local-whisper" in g["tips"], g["tips"]
i = lh.agent_info(AGENT, rows)
assert i["pane"] == "w1-2" and i["name"] == "BYK", i
assert ("kind", "other") in groups or any(k == "kind" for k, _ in groups), groups.keys()

# 2. the input-box guard: empty box -> send; text (typed or a suggestion) -> refuse; box not visible -> refuse
assert lh.input_box("w1-2") == ""
assert lh.input_box("w1-3") == "yes promote the fix"
assert lh.input_box("w1-4") is None
ok, why = lh.tell("w1-3", "hi")
assert not ok and not sent, (why, sent)
ok, why = lh.tell("w1-4", "hi")
assert not ok and not sent, (why, sent)
ok, why = lh.tell("BYK", "hi", dry=True)
assert ok and not sent and "w1-2" in why, why

# 3. pings: 90 starts of one command in 30 s, parents gone, grandparent is the agent
events, args, parent = [], {}, {}
for n in range(90):
    pid = 10000 + n
    events.append(("exec", pid)); args[pid] = "git rev-list --count HEAD"; parent[pid] = 9000
parent[9000] = AGENT
found = lh.pings(events, args, parent, 30)
assert found and found[0][0] == 180 and "w1-2" in found[0][2], found
print("ok: whisper loop -> pane w1-2 (BYK) with local-whisper tip; tell refuses a busy or hidden box; pings name the agent")
