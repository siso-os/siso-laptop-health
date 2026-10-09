#!/usr/bin/env python3
"""Stale cargo incremental caches go; the ones a build touched recently stay; nothing goes while rustc runs.
1 Oct: one Oracle worktree held 201 stale incremental folders (8.7 GB) and the disk fell to 15.6 GB free."""
import importlib.machinery, os, shutil, sys, tempfile, time

HOUSE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
lh = importlib.machinery.SourceFileLoader("lh", os.path.join(HOUSE, "bin/laptop-health")).load_module()
lh.CACHE = tmp = tempfile.mkdtemp(prefix=".siso-ephemeral-cargo-test.")
try:
    inc = os.path.join(tmp, "repo", "oracle-rs", "target", "debug", "incremental")
    old, new = os.path.join(inc, "oracle_worker-old"), os.path.join(inc, "oracle_worker-new")
    for d in (os.path.join(old, "s-1"), os.path.join(new, "s-2"), os.path.join(tmp, "repo", "node_modules", "x", "target", "debug", "incremental", "y")):
        os.makedirs(d)
        open(os.path.join(d, "query-cache.bin"), "w").write("x" * 4096)
    ago = time.time() - 5 * 3600
    for d, _, fs in os.walk(old):
        for x in [d] + [os.path.join(d, f) for f in fs]:
            os.utime(x, (ago, ago))
    real_sh = lh.sh
    rustc = [""]
    lh.sh = lambda cmd, timeout=60: rustc[0] if cmd[:3] == ["pgrep", "-x", "rustc"] else real_sh(cmd, timeout)
    root = os.path.join(tmp, "repo")

    assert [d for _, d in lh.stale_cargo([root])] == [old], lh.stale_cargo([root])
    rustc[0] = "4242\n"
    assert lh.clear_stale_cargo([root]) == (0, 0) and os.path.isdir(old), "removed a cache while rustc was running"
    rustc[0] = ""
    kb, n = lh.clear_stale_cargo([root])
    assert n == 1 and not os.path.exists(old) and os.path.isdir(new), (kb, n)
    print("ok: stale incremental removed, fresh one kept, node_modules skipped, nothing removed while rustc runs")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
