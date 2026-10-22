"""Policy tests: watcher passes observe by default and action opt-in is explicit."""
import contextlib, importlib.machinery, io, json, os, tempfile
from srcload import load

HOUSE = os.path.dirname(os.path.dirname(__file__))
hw = load("hw_policy", os.path.join(HOUSE, "bin/health-watch"))
lh = load("lh_policy", os.path.join(HOUSE, "bin/laptop-health"))

tmp = tempfile.mkdtemp(prefix=".siso-watch-policy-")
try:
    hw.OWNER_POLICY = os.path.join(tmp, "missing-owner-policy.json")
    hw.CACHE = os.path.join(tmp, "cache")
    hw.STATE = os.path.join(hw.CACHE, "state.json")
    hw.WAKE = os.path.join(tmp, "wake.jsonl")
    hw.A0_INBOX = os.path.join(tmp, "inbox.log")
    hw.sample = lambda *a: {"cores": 4, "load5": 10, "pressure": 0, "ram": 50, "disk": 50, "disk_gb": 40}
    hw.top = lambda *a: []
    calls = []
    hw.tell = lambda msg: calls.append(msg) or True
    state = {}
    for _ in range(5):
        hw.one("box", {"os": "linux", "local": True}, state)
    row = json.loads(open(hw.WAKE).readline())
    assert not calls and row["told"] is False and row["notification"] == "suppressed"
    assert not os.path.exists(hw.A0_INBOX)

    state = {}
    for _ in range(5):
        hw.one("box", {"os": "linux", "local": True}, state, allow_actions=True)
    assert calls and json.loads(open(hw.WAKE).readlines()[-1])["notification"] == "sent"

    # A held watcher is skipped, and a thrown pass releases the lock for the next run.
    seen = []
    locked = os.path.join(hw.CACHE, "watch.lock")
    os.makedirs(hw.CACHE, exist_ok=True)
    with open(locked, "w") as held:
        import fcntl
        fcntl.flock(held.fileno(), fcntl.LOCK_EX)
        @hw.locked
        def skip(): seen.append("ran")
        skip()
    assert seen == []
    @hw.locked
    def explode(): raise RuntimeError("fixture")
    try: explode()
    except RuntimeError: pass
    @hw.locked
    def after(): seen.append("after")
    after()
    assert seen == ["after"]

    # Exercise the fleet once path itself: observation mode records samples but
    # never invokes the action helpers; opt-in invokes both helpers.
    hw.CACHE = os.path.join(tmp, "fleet-cache")
    hw.STATE = os.path.join(hw.CACHE, "state.json")
    fleet_calls = []
    hw.sample = lambda *a: {"cores": 4, "load5": 0, "pressure": 0, "ram": 50, "disk": 50, "disk_gb": 40}
    hw.top = lambda *a: []
    hw.tell = lambda msg: fleet_calls.append(("tell", msg)) or True
    hw.run = lambda cmd, timeout=12: fleet_calls.append(("run", cmd)) or "ok\n"
    hw.once()
    assert not any(x[0] == "run" and ("unheavy" in x[1] or "ramguard" in x[1]) for x in fleet_calls)
    hw.once(True)
    assert any(x[0] == "run" and "unheavy" in x[1] for x in fleet_calls)
    assert any(x[0] == "run" and "ramguard" in x[1] for x in fleet_calls)

    # Zero-event churn is a coverage block, not a fabricated one-start rate.
    lh.have_sudo = lambda: True
    lh.capture_events = lambda dur: ([], {}, {})
    out = io.StringIO()
    with contextlib.redirect_stdout(out): assert lh.cmd_churn(["10"]) == 1
    assert "BLOCKED" in out.getvalue() and "1 start" not in out.getvalue()
    lh.capture_events = lambda dur: ([("exec", 1)], {1: "node worker"}, {1: 0})
    out = io.StringIO()
    with contextlib.redirect_stdout(out): assert lh.cmd_churn(["10"]) == 0
    assert "6/min" in out.getvalue() and "BLOCKED" not in out.getvalue()

    # Scheduled helpers cannot enforce priority or notify without the explicit flag.
    lh.ps_rows = lambda: {9: {"ppid": 1, "age": 3600, "args": "pnpm build"}}
    lh.unheavy = lambda rows: [(9, "pnpm build", 3600, None)]
    actions = []
    lh.record_unheavy_issue = lambda *a: actions.append("record")
    lh.subprocess.run = lambda *a, **k: actions.append("priority")
    lh.cmd_unheavy([])
    assert actions == []
    lh.cmd_unheavy(["--enforce", "--allow-actions"])
    assert actions == ["priority", "record"]

    # Exercise the laptop scheduled pass with a low-disk monitor fixture.
    lh.CACHE = os.path.join(tmp, "laptop-cache")
    lh.loadavg = lambda: (1.0, 1.0, 1.0)
    lh.memory = lambda: {"free_mb": 2000, "compressor_mb": 0, "swap_used_mb": 0}
    lh.power = lambda: {"source": "AC", "low_power_mode_now": False}
    lh.free_gb = lambda: (1.0, 100)
    lh.sh = lambda *a, **k: ""
    lh.hogs = lambda secs: ({("agent", 9): {"threads": 2.0, "tips": ["build"]}}, {9: {}}, [], 0)
    lh.agent_info = lambda *a: {"pane": "P"}
    lh.agent_label = lambda *a: "P"
    lh.find_strays = lambda: [("monitors", 99, "fixture", "kill")]
    lh.have_sudo = lambda: False
    lh.tell_waste = lambda *a: (_ for _ in ()).throw(AssertionError("default watcher told"))
    lh.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(AssertionError("default watcher killed"))
    lh.clear_stale_cargo = lambda *a: (_ for _ in ()).throw(AssertionError("default watcher cleared Cargo"))
    lh.cargo_roots = lambda: []
    import fcntl
    os.makedirs(lh.CACHE, exist_ok=True)
    with open(os.path.join(lh.CACHE, "watch.lock"), "w") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX)
        with contextlib.redirect_stdout(out := io.StringIO()):
            lh.cmd_watch(["--once"])
        assert "watch lock held" in out.getvalue()
    lh.cmd_watch(["--once"])
    row = json.loads(open(os.path.join(lh.CACHE, "watch.jsonl")).readline())
    assert row["watch_mode"] == "observe" and row["notifications_suppressed"]
    told, killed, cargo = [], [], []
    lh.tell_waste = lambda *a: told.append(1) or "told"
    lh.subprocess.run = lambda *a, **k: killed.append(1)
    lh.clear_stale_cargo = lambda *a: cargo.append(1) or (1024, 1)
    lh.cargo_roots = lambda: []
    lh.cmd_watch(["--once", "--allow-actions"])
    row = json.loads(open(os.path.join(lh.CACHE, "watch.jsonl")).readlines()[-1])
    assert row["watch_mode"] == "actions" and told and killed and cargo

    # History must distinguish intentional deferral, blocked capture and legacy
    # missing coverage from a real measured zero, without running any probes.
    history = [
        {"at": "DEFER", "free_mb": None, "starts_per_min": None,
         "diagnostics": "deferred", "diagnostics_reason": "healthy",
         "churn_coverage": "not-sampled", "churn_probe": "not-needed"},
        {"at": "BLOCK", "free_mb": 413, "starts_per_min": None,
         "diagnostics": "sampled", "diagnostics_reason": "pressure-changed",
         "churn_coverage": "blocked", "churn_probe": "cooldown"},
        {"at": "ZERO", "free_mb": 0, "starts_per_min": 0},
        {"at": "VALUE", "free_mb": 250, "starts_per_min": 120},
        {"at": "LEGACY"},
    ]
    with open(os.path.join(lh.CACHE, "watch.jsonl"), "w") as f:
        for entry in history:
            f.write(json.dumps({"level": "ok", "load": [1.0], "told": [], "hogs": [], **entry}) + "\n")
    def no_probe(*a, **k): raise AssertionError("history started a probe or action")
    lh.sh = lh.memory = lh.power = lh.hogs = lh.subprocess.run = no_probe
    with contextlib.redirect_stdout(out := io.StringIO()):
        assert lh.cmd_watch([]) == 0
    text = out.getvalue()
    assert "None MB" not in text and "None/min" not in text
    assert "diagnostics deferred (healthy); churn not-sampled (not-needed)" in text
    assert "diagnostics sampled (pressure-changed); churn blocked (cooldown)" in text
    assert "diagnostics unknown (unknown); churn unknown (unknown)" in text
    assert "free 0 MB  starts 0/min" in next(line for line in text.splitlines() if "ZERO" in line)
    assert "free 250 MB  starts 120/min" in next(line for line in text.splitlines() if "VALUE" in line)
finally:
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
print("ok: observation-only notifications, explicit action opt-in, lock skip/release, zero-event coverage")
