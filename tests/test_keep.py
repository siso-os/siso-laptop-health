#!/usr/bin/env python3
"""Regression: a server only identifiable by its folder (bare `node serve.mjs` in registry/curated) must be kept.
25 Sep: `clean` stopped the :8812 curated board because keep.txt was matched against the command line only.
Simulates two old, ownerless, client-less servers: the curated board (kept) and a docs http.server (flagged)."""
import importlib.machinery, os, sys

HOUSE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
lh = importlib.machinery.SourceFileLoader("lh", os.path.join(HOUSE, "bin/laptop-health")).load_module()

BOARD, DOCS = 900001, 900002
CWD = {BOARD: "/Users/x/SISO_Workspace/Great_Library_of_SISO/banks/siso-ui-base/registry/curated",
       DOCS: "/Users/x/SISO_Workspace/SISO_Agency/partners/halo/oracle/docs/site"}
lh.ps_rows = lambda: {BOARD: {"ppid": 1, "age": 50 * 3600, "cpu": 1, "args": "/Users/x/.hermes/node/bin/node serve.mjs"},
                      DOCS: {"ppid": 1, "age": 50 * 3600, "cpu": 1, "args": "Python -m http.server 8870 --bind 127.0.0.1"}}
lh.listening = lambda: {BOARD: {"8812"}, DOCS: {"8870"}}
lh.launchd_pids = lambda: set()
lh.clients = lambda port: 0
real_sh = lh.sh
lh.sh = lambda cmd, timeout=60: (f"p{cmd.split()[3]}\nn{CWD[int(cmd.split()[3])]}\n"
                                 if isinstance(cmd, str) and cmd.startswith("lsof -a -p") else real_sh(cmd, timeout))

flagged = {s[1] for s in lh.find_strays() if s[0] == "servers"}
assert BOARD not in flagged, "curated board (kept by folder) was flagged as a stray"
assert DOCS in flagged, "old ownerless docs server was not flagged"
print("ok: board kept by folder, stale docs server flagged")
