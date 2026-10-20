"""Boundaries: local-only work, native metrics, no auto-prompt, pressure transitions."""
import contextlib, importlib.machinery, io, json, os, tempfile
from types import SimpleNamespace
HOUSE = os.path.dirname(os.path.dirname(__file__))
hw = importlib.machinery.SourceFileLoader('hw_cost', os.path.join(HOUSE, 'bin/health-watch')).load_module()
lh = importlib.machinery.SourceFileLoader('lh_cost', os.path.join(HOUSE, 'bin/laptop-health')).load_module()
vm = '''Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free: 10.
Pages inactive: 20.
Pages speculative: 5.
Pages purgeable: 5.
'''
calls = []
def native_run(cmd, timeout=12):
    calls.append(cmd)
    if cmd == ['/usr/bin/vm_stat']: return vm
    if cmd == ['/usr/sbin/ioreg', '-rn', 'AppleSmartBattery']:
        return '"ExternalConnected" = Yes\n"CurrentCapacity" = 50\n"InstantAmperage" = 145'
    raise AssertionError(cmd)
hw.run = native_run
orig_sysconf, orig_statvfs, orig_getloadavg = hw.os.sysconf, hw.os.statvfs, hw.os.getloadavg
hw.os.sysconf = lambda name: {'SC_PHYS_PAGES': 1000, 'SC_PAGE_SIZE': 16384}[name]
hw.os.statvfs = lambda path: SimpleNamespace(f_bavail=40, f_blocks=100, f_frsize=4096)
hw.os.getloadavg = lambda: (1, 2, 3)
v = hw.sample('laptop', {'local': True, 'os': 'macos'})
assert v['ram'] == 4 and v['disk'] == 40 and v['charge_ma'] == 145
assert v['load1'] == 1 and len(calls) == 2
try: hw.mac_available('broken')
except ValueError: pass
else: raise AssertionError('missing telemetry must not appear healthy')
hw.os.sysconf, hw.os.statvfs, hw.os.getloadavg = orig_sysconf, orig_statvfs, orig_getloadavg
with tempfile.TemporaryDirectory(prefix='.siso-health-cost-') as tmp:
    hw.CACHE = os.path.join(tmp, 'fleet')
    hw.STATE = os.path.join(hw.CACHE, 'state.json')
    hw.WAKE = os.path.join(tmp, 'wake.jsonl')
    hw.OWNER_POLICY = os.path.join(tmp, 'enabled.json')
    with open(hw.OWNER_POLICY, 'w') as f: json.dump({'enabled': True}, f)
    hw.maybe_owner = lambda *_: (_ for _ in ()).throw(AssertionError('observer auto-prompted'))
    seen = []
    hw.one = lambda name, cfg, state, allow_actions=False: seen.append(name) or {'machine': name, 'status': 'sampled'}
    with contextlib.redirect_stdout(io.StringIO()): hw.once()
    assert seen == ['laptop'], seen
    seen.clear()
    with contextlib.redirect_stdout(io.StringIO()): hw.once(include_remote=True)
    assert set(seen) == {'laptop', 'mini', 'siso-vps', 'halo-vps'}
    lh.CACHE = os.path.join(tmp, 'local'); os.makedirs(lh.CACHE)
    clock = [10000.0]; original_time = lh.time.time; lh.time.time = lambda: clock[0]
    def decision(load, free, force=False):
        due, reason, state = lh.watch_detail_policy([load, 0, 0], free, force)
        with open(os.path.join(lh.CACHE, 'detail-policy.json'), 'w') as f: json.dump(state, f)
        return due, reason
    assert decision(1, 60) == (False, 'healthy')
    assert decision(lh.NCPU + 1, 60) == (True, 'pressure-changed')
    clock[0] += 600
    assert decision(lh.NCPU + 1, 60) == (False, 'unchanged-pressure')
    assert decision(lh.NCPU + 1, 25) == (True, 'pressure-changed')
    clock[0] += 3600
    assert decision(lh.NCPU + 1, 25) == (True, 'pressure-refresh')
    assert decision(1, 60) == (False, 'healthy')
    assert decision(lh.NCPU + 1, 60) == (True, 'pressure-changed')
    assert decision(1, 60, True) == (True, 'explicit')
    assert decision(1, None) == (True, 'pressure-changed')
    lh.time.time = original_time
    lh.loadavg = lambda: [1, 1, 1]
    lh.memory = lambda: {'free_mb': 2000, 'compressor_mb': 0}
    lh.power = lambda: {'source': 'Battery', 'low_power_mode_now': False}
    lh.free_gb = lambda: (40, 100)
    lh.sh = lambda *a, **k: 'System-wide memory free percentage: 60%'
    forbidden = lambda *a, **k: (_ for _ in ()).throw(AssertionError('healthy watcher ran expensive diagnostics'))
    lh.hogs = lh.watch_churn = lh.find_strays = lh.memory = lh.power = lh.free_gb = forbidden
    with contextlib.redirect_stdout(io.StringIO()): lh.cmd_watch(['--once'])
    row = json.loads(open(os.path.join(lh.CACHE, 'watch.jsonl')).readlines()[-1])
    assert row['diagnostics'] == 'deferred' and row['strays'] is None and row['starts_per_min'] is None
print('PASS: native local metrics, zero default SSH, no observe-mode auto-prompt, pressure transitions, cheap healthy path')
