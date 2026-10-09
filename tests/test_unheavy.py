#!/usr/bin/env python3
"""Builds and tests outside `heavy` are found once per tree; queued, slotted, young and IDE ones are left alone; one issue
per owner per day. 2 Oct: load 16 on 8 cores with the soak's ffmpeg on the laptop; A0 asked for this rule to be enforced."""
import importlib.machinery, json, os, shutil, sys, tempfile

HOUSE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
lh = importlib.machinery.SourceFileLoader("lh", os.path.join(HOUSE, "bin/laptop-health")).load_module()
tmp = tempfile.mkdtemp(prefix=".siso-ephemeral-unheavy-test.")
try:
    lh.ISSUES = os.path.join(tmp, "issues.jsonl")
    lh.heavy_pids = lambda: {300}
    R = lambda ppid, age, args: {"ppid": ppid, "age": age, "cpu": 0, "args": args}
    rows = {
        10: R(1, 9000, "/Users/x/.local/bin/claude --model opus"),
        11: R(10, 90, "/bin/zsh -c pnpm -C apps/web build"),
        12: R(11, 90, "node /opt/homebrew/bin/pnpm -C apps/web build"),        # flagged (top of its tree)
        13: R(12, 80, "sh -c tsc --noEmit && vite build"),
        14: R(13, 80, "node apps/web/node_modules/.bin/../typescript/bin/tsc --noEmit"),
        20: R(10, 90, "Python /Users/x/.local/bin/heavy -- pnpm build"),      # queued under heavy
        21: R(20, 60, "node /opt/homebrew/bin/pnpm build"),
        300: R(10, 60, "node /opt/homebrew/bin/pnpm check"),                  # holds a heavy slot
        301: R(300, 60, "node node_modules/.bin/vitest run"),
        40: R(10, 10, "node /opt/homebrew/bin/pnpm test"),                    # too young
        50: R(10, 120, "/usr/bin/git log --remotes --format=%h -Sfathom.video/share/x"),  # history search: flagged
        51: R(10, 120, "/usr/bin/git log --oneline -20"),
        60: R(1, 900, "cargo check --workspace --message-format=json rust-analyzer"),
        61: R(1, 900, "rust-analyzer-proc-macro-srv"),
        70: R(10, 900, "node node_modules/.bin/vite --port 5601"),             # a dev server, not a build
        80: R(1, 500, "cargo test --lib"),                                     # no agent above it
    }
    found = {p: a for p, _, _, a in lh.unheavy(rows)}
    assert found == {12: 10, 50: 10, 80: None}, found
    assert sorted(lh.tree(12, rows)) == [12, 13, 14]

    lh.record_unheavy_issue("AGENT-BASE", 12, "pnpm build --token=abc123", "2026-10-02T15:40+07:00")
    lh.record_unheavy_issue("AGENT-BASE", 12, "pnpm build --token=abc123", "2026-10-02T15:41+07:00")   # same pid: no bump
    lh.record_unheavy_issue("AGENT-BASE", 14, "tsc --noEmit", "2026-10-02T15:42+07:00")
    lh.record_unheavy_issue("ESTATE", 50, "git log -S x", "2026-10-02T15:42+07:00")
    issues = [json.loads(l) for l in open(lh.ISSUES)]
    assert [(i["id"], i["owner"], i["seen"]) for i in issues] == [("H-0001", "AGENT-BASE", 2), ("H-0002", "ESTATE", 1)], issues
    assert "abc123" not in open(lh.ISSUES).read()
    print("ok: one flag per tree; heavy queue, slot, young, rust-analyzer, dev server skipped; issue per owner, deduped, masked")
finally:
    shutil.rmtree(tmp)
