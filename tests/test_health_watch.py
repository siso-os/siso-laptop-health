#!/usr/bin/env python3
import importlib.machinery, json, os, shutil, tempfile

HOUSE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
hw = importlib.machinery.SourceFileLoader('hw', os.path.join(HOUSE, 'bin/health-watch')).load_module()
linux = '''4\n0.50 1.00 0.70 1/100 1\nsome avg10=2.00 avg60=3.00 avg300=1.00 total=5\nMemTotal: 1000 kB\nMemAvailable: 500 kB\nFilesystem 1024-blocks Used Available Capacity Mounted on\n/dev/root 1000 500 500 50% /\n'''
mac = '''8\n{ 0.80 1.00 1.20 }\nMach Virtual Memory Statistics: (page size of 4096 bytes)\nPages free: 10.\nPages inactive: 20.\nPages speculative: 5.\nPages purgeable: 5.\n1000000\nFilesystem 1024-blocks Used Available Capacity Mounted on\n/dev/disk1 1000 500 500 50% /System/Volumes/Data\n'''
assert hw.parse_sample('linux', linux) == {'cores':4,'load5':1.0,'pressure':3.0,'ram':50.0,'disk':50.0,'disk_gb':500/1048576}
m = hw.parse_sample('macos', mac)
assert m['cores'] == 8 and m['load5'] == 1.0 and m['ram'] == 40*4096/1000000*100 and m['disk'] == 50
m16 = hw.parse_sample('macos', mac.replace('page size of 4096', 'page size of 16384'))
assert m16['ram'] == 40*16384/1000000*100, m16   # Apple silicon: 16 KB pages (4096 hard-coded under-reported RAM 4x)
assert hw.charge_ma('"ExternalConnected" = Yes\n"CurrentCapacity" = 6\n"InstantAmperage" = 145') == 145.0   # 3 Oct: on AC at 6%, +145 mA
assert hw.charge_ma('"ExternalConnected" = Yes\n"CurrentCapacity" = 7\n"InstantAmperage" = 18446744073709550147') == -1469.0  # wrapped negative: draining on AC
assert hw.charge_ma('"ExternalConnected" = No\n"CurrentCapacity" = 6\n"InstantAmperage" = 145') == 9999.0
assert hw.charge_ma('"ExternalConnected" = Yes\n"CurrentCapacity" = 95\n"InstantAmperage" = 0') == 9999.0
assert hw.safe('--token=abc token=def key=ghi secret=j password=k Bearer l') == '--token=*** token=*** key=*** secret=*** password=*** Bearer ***'
tmp = tempfile.mkdtemp(prefix='.siso-ephemeral-')
try:
    hw.CACHE=os.path.join(tmp,'cache'); hw.STATE=os.path.join(hw.CACHE,'state.json'); hw.WAKE=os.path.join(tmp,'wake.jsonl')
    hw.sample=lambda machine,cfg: {'cores':4,'load5':10,'pressure':0,'ram':50,'disk':50,'disk_gb':40}
    hw.tell=lambda msg: True; hw.top=lambda cfg: [hw.safe('worker --token=x')]
    state={}; cfg={'os':'linux'}
    for _ in range(4): hw.one('box',cfg,state)
    assert not os.path.exists(hw.WAKE)
    hw.one('box',cfg,state); assert len(open(hw.WAKE).readlines()) == 1
    hw.one('box',cfg,state); assert len(open(hw.WAKE).readlines()) == 1
    assert '***' in open(hw.WAKE).read()
    hw.sample=lambda machine,cfg: {'cores':4,'load5':0,'pressure':0,'ram':50,'disk':50,'disk_gb':40}
    for _ in range(4): hw.one('box',cfg,state)
    assert len(open(hw.WAKE).readlines()) == 1
    hw.one('box',cfg,state)
    rows=[json.loads(x) for x in open(hw.WAKE)]; assert [x['state'] for x in rows] == ['opened','cleared']
    # unreachable is a separate consecutive counter and opens only at 15
    state={}; hw.sample=lambda *a: (_ for _ in ()).throw(RuntimeError('down'))
    for _ in range(14): hw.one('down',cfg,state)
    assert not any(x.get('machine')=='down' and x.get('metric')=='unreachable' for x in map(json.loads,open(hw.WAKE)))
    hw.one('down',cfg,state); rows=[json.loads(x) for x in open(hw.WAKE)]
    assert rows[-1]['machine']=='down' and rows[-1]['metric']=='unreachable'
    # a wake whose tell fails is retried each pass, then handed to the A0 inbox after 3 failures (2 Oct 17:13 miss)
    hw.A0_INBOX=os.path.join(tmp,'inbox.log'); sent=[]; hw.tell=lambda msg: (sent.append(msg), False)[1]
    hw.sample=lambda machine,cfg: {'cores':4,'load5':10,'pressure':0,'ram':50,'disk':50,'disk_gb':40}; state={}
    for _ in range(5): hw.one('retry',cfg,state)
    assert len(sent)==2, sent                     # the wake + its first retry in the same pass
    hw.one('retry',cfg,state); hw.one('retry',cfg,state)
    assert 'HEALTH pane unreachable' in open(hw.A0_INBOX).read() and not state['retry']['load']['pending']
    n=len(sent); hw.one('retry',cfg,state); assert len(sent)==n
    # disk_gb: an absolute floor that wakes after 2 samples even while the % disk alert has been open for days
    hw.tell=lambda msg: True; state={}; n=len(open(hw.WAKE).readlines())
    hw.sample=lambda machine,cfg: {'cores':4,'load5':0,'pressure':0,'ram':50,'disk':2,'disk_gb':2.5}
    hw.one('full',cfg,state); assert len(open(hw.WAKE).readlines()) == n
    hw.one('full',cfg,state); rows=[json.loads(x) for x in open(hw.WAKE)][n:]
    assert [(x['metric'],x['state']) for x in rows] == [('disk_gb','opened')], rows
    print('ok: Linux/macOS fixtures, 4/5/6 breach, 5 clean, masking, 15 unreachable, failed wake retried then to A0 inbox, disk_gb floor wakes after 2')
finally:
    shutil.rmtree(tmp, ignore_errors=True)
