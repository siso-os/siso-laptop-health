"""Runnable samples retain names, preserve counts, and never invent live owners."""
import collections
import ctypes
import importlib.machinery
import os
import types
from unittest.mock import patch

HOUSE = os.path.dirname(os.path.dirname(__file__))
lh = importlib.machinery.SourceFileLoader("lh_sampling", os.path.join(HOUSE, "bin/laptop-health")).load_module()


class Native:
    def __init__(self):
        self.sweep = -1
        self.calls = 0
        self.buffers = set()

    def proc_listallpids(self, buf, size):
        self.sweep += 1
        for i, pid in enumerate((0, 10, 11, 12)):
            buf[i] = pid
        return 4

    def proc_pidinfo(self, pid, flavor, arg, ptr, size):
        self.calls += 1
        assert flavor == 2 and size == 232
        self.buffers.add(id(ptr._obj))
        if pid == 12:
            return 0  # Old buffer contents must not count on a failed read.
        if pid == 11 and self.sweep == 1:
            return 0  # Gone before the second sweep and final process snapshot.
        info = ptr._obj
        info.task.run = {0: 2, 10: 1, 11: 3}[pid]
        info.bsd.start_sec = 100 + (self.sweep if pid == 10 else 0)
        info.bsd.start_usec = 0
        info.bsd.name = {0: b"kernel_task", 10: b"node", 11: b"git"}[pid]
        return size


native = Native()
ticks = iter(range(4))
clock = types.SimpleNamespace(time=lambda: next(ticks), sleep=lambda _: None)
observed = {}
with patch.object(lh.ctypes, "CDLL", return_value=native), patch.object(lh, "time", clock):
    run, samples, totals = lh.sample_run(3, observed=observed)
assert samples == 2 and totals == [6, 3]
assert run == {0: 4, 10: 2, 11: 3} and sum(run.values()) == sum(totals)
assert native.calls == 8 and len(native.buffers) == 1
assert observed[11][2] == "git" and observed[10] is None
assert lh.sampled_kind(0, {}, observed) == "macOS (kernel_task)"
assert lh.sampled_kind(11, {}, observed) == "short-lived: git"
assert lh.sampled_kind(10, {10: {"args": "codex"}}, observed) == "identity changed (unattributed)"
assert lh.sampled_kind(99, {}, observed) == "short-lived (identity unavailable)"


def sample(dur, observed):
    observed.update({0: (0, 0, "kernel_task"), 11: (100, 0, "git")})
    return collections.Counter({0: 4, 11: 3}), 2, [4, 3]


with patch.object(lh, "sample_run", sample), patch.object(lh, "ps_rows", return_value={}), \
     patch.object(lh, "load_tips", return_value=[]):
    groups, rows, samples, avg = lh.hogs(1)
assert not rows and samples == 2 and avg == 3.5
assert groups[("kind", "short-lived: git")]["threads"] == 1.5
assert groups[("kind", "macOS (kernel_task)")]["threads"] == 2
assert all(not group["procs"] and not group["tips"] for group in groups.values())
print("ok: ABI layout, one probe/process, reused buffer, exact runnable totals, kernel identity, exited names, PID reuse, no dead owner targets")
