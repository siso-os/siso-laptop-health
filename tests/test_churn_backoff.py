"""Scheduled logger retries back off without inventing a zero rate or losing samples."""
import importlib.machinery
import json
import os
import subprocess
import tempfile
from unittest.mock import patch

HOUSE = os.path.dirname(os.path.dirname(__file__))
lh = importlib.machinery.SourceFileLoader("lh_backoff", os.path.join(HOUSE, "bin/laptop-health")).load_module()
with tempfile.TemporaryDirectory(prefix=".siso-churn-backoff-") as tmp:
    lh.CACHE = tmp
    clock = [1000.0]
    lh.time.time = lambda: clock[0]
    calls = []
    lh.have_sudo = lambda: True
    lh.capture_events = lambda dur: calls.append(dur) or ([], {}, {})
    first = {}
    lh.watch_churn(first)
    assert calls == [10] and first["starts_per_min"] is None
    assert first["churn_coverage"] == "blocked"
    clock[0] += 600
    second = {}
    lh.watch_churn(second)
    assert calls == [10] and second["churn_probe"] == "cooldown"
    assert second["starts_per_min"] is None and second["pings"] == []
    clock[0] += 3001
    lh.watch_churn({})
    assert calls == [10, 10], "Expired coverage must be re-probed"
    lh.watch_churn({}, force=True)
    assert calls == [10, 10, 10], "Explicit probe overrides cooldown"
    lh.capture_events = lambda dur: ([("exec", 1)], {1: "fixture"}, {1: 0})
    lh.pings = lambda *a, **k: []
    resumed = {}
    lh.watch_churn(resumed, force=True)
    assert resumed["starts_per_min"] == 6 and resumed["churn_coverage"] == "observed"
    lh.have_sudo = lambda: False
    missing = {}
    lh.watch_churn(missing)
    assert missing["churn_probe"] == "no_sudo" and missing["starts_per_min"] is None
    with open(os.path.join(tmp, "churn-coverage.json"), "w") as f:
        f.write("corrupt fixture")
    lh.have_sudo = lambda: True
    lh.capture_events = lambda dur: ([], {}, {})
    repaired = {}
    lh.watch_churn(repaired)
    assert repaired["churn_probe"] == "sampled"
print("ok: one blind probe, skipped cooldown, expiry, forced recovery, unavailable/corrupt state")

# Exercise the real capture path: an early logger exit never waits out the
# window, signals a dead PID, snapshots processes, or reports a partial rate.
lh = importlib.machinery.SourceFileLoader("lh_capture", os.path.join(HOUSE, "bin/laptop-health")).load_module()
event = {"process": {"audit_token": {"pid": 10}, "ppid": 1},
         "event": {"exec": {"target": {"audit_token": {"pid": 11}}, "args": ["fixture"]}}}

class Logger:
    pid = 987654

    def __init__(self, early, stdout):
        self.early = early
        self.returncode = None
        self.waits = []
        stdout.write(json.dumps(event) + "\n")

    def wait(self, timeout):
        self.waits.append(timeout)
        if self.early:
            self.returncode = 1
        if self.returncode is None:
            raise subprocess.TimeoutExpired("fixture", timeout)
        return self.returncode

    def poll(self):
        return self.returncode

for early in (True, False):
    loggers, signals = [], []
    def start(cmd, stdout, stderr):
        logger = Logger(early, stdout)
        loggers.append(logger)
        return logger
    def stop(cmd, **kwargs):
        assert cmd[:4] == ["sudo", "-n", "kill", "-INT"]
        assert cmd[4] == str(loggers[0].pid)
        signals.append(cmd)
        loggers[0].returncode = -2
    with patch.object(lh.subprocess, "Popen", start), patch.object(lh.subprocess, "run", stop), \
         patch.object(lh, "sh", return_value="") as snapshot:
        events, args, parents = lh.capture_events(10)
    if early:
        assert (events, args, parents) == ([], {}, {})
        assert loggers[0].waits == [10] and not signals
        snapshot.assert_not_called()
    else:
        assert events == [("exec", 11)] and args[11] == "fixture"
        assert loggers[0].waits == [10, 5] and len(signals) == 1
        snapshot.assert_called_once()
print("ok: early logger exit returns unknown without waiting/signalling; live logger keeps full capture and cleanup")
