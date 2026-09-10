"""Generate deterministic review/import payload; never writes the source mirror."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIRROR = ROOT.parent / 'plc-src' / 'Device' / 'Application'
MARKER = '// --- implementation (ST) ---'
SOURCE_RUN = ROOT / 'runs' / '20260910_151437_602000'
SOURCE_PROJECT = 'EbN0扫描捕获_1度波束扫描及误差电压EbN0双门限 - 副本.project'


def read(path):
    return path.read_text(encoding='utf-8-sig').replace('\r\n', '\n')


def mirror(path):
    text = read(path)
    kind = re.search(r'^# kind=(.+)$', text, re.M).group(1)
    name = re.search(r'^# name=(.+)$', text, re.M).group(1)
    text = re.sub(r'\A(?:#[^\n]*\n)+\s*', '', text)
    parts = text.split(MARKER, 1)
    decl = parts[0].strip()
    if kind == 'program':
        decl = 'PROGRAM ' + name + '\n' + decl
    elif kind == 'functionBlock' or kind == 'functionblock':
        decl = 'FUNCTION_BLOCK ' + name + '\n' + decl
    return dict(name=name, declaration=decl,
                implementation=parts[1].strip() if len(parts) == 2 else None)


def split_st(name):
    text = read(ROOT / (name + '.st')).strip()
    if name.startswith('GVL_'):
        return dict(name=name, kind='gvl', declaration=text, implementation=None)
    end = text.rfind('END_VAR') + len('END_VAR')
    assert end > len('END_VAR')
    body = re.sub(r'\s*END_(FUNCTION_BLOCK|PROGRAM)\s*$', '', text[end:]).strip()
    return dict(name=name, kind='fb' if name.startswith('FB_') else 'program',
                declaration=text[:end], implementation=body)


def build():
    # Reviewed live CODESYS source, not a reconstructed/lossy mirror declaration.
    snapshot = json.loads(read(SOURCE_RUN / 'source_snapshot.json'))
    report = read(SOURCE_RUN / 'report.txt')
    assert report.splitlines()[0].endswith('\\' + SOURCE_PROJECT)
    import xml.etree.ElementTree as ET
    for filename in ['baseline.xml', 'baseline.export']:
        ET.parse(SOURCE_RUN / filename)
    baseline = []
    for name in ['READ_485', 'SecurityCheck', 'AutoTrackingCal', 'Az_ctrl_1',
                 'El_ctrl_1', 'Ti_ctrl_1', 'Az_Ctrl_FB', 'El_Ctrl_FB', 'Modbus_Slave']:
        baseline.append(mirror(MIRROR / (name + '.txt')))
    for name in ['GVL', 'AxisStatus', 'Word2Bit']:
        baseline.append(mirror(MIRROR / '结构体' / (name + '.txt')))
    for item in baseline:
        matches = [(key, value) for key, value in snapshot.items()
                   if key.endswith('/' + item['name']) and value[0] is not None]
        assert len(matches) == 1, item['name']
        key, (declaration, implementation) = matches[0]
        item['declaration'] = declaration.replace('\r\n', '\n').strip()
        if item['implementation'] is not None:
            item['implementation'] = implementation.replace('\r\n', '\n').strip()
        item['source_path'] = key
    changes = []
    for name in ['READ_485', 'SecurityCheck']:
        item = dict(next(x for x in baseline if x['name'] == name))
        item['kind'] = 'existing'
        if name == 'READ_485':
            anchor = 'END_IF\n(*\n//加校验'
            assert item['implementation'].count(anchor) == 1
            item['implementation'] = item['implementation'].replace(
                anchor, read(ROOT / 'READ_485.append.st').strip() + '\n' + anchor)
        else:
            item['implementation'] += '\n\n(* PHASE_CAL_HOOK: once per 10 ms, LAST call. *)\nPRG_PhaseCalibration();'
        changes.append(item)
    changes += [split_st(n) for n in ['GVL_PhaseCal', 'FB_PhaseFit',
                                      'FB_PhaseTriangle', 'PRG_PhaseCalibration']]
    out = ROOT / 'generated'
    out.mkdir(exist_ok=True)
    for item in changes:
        (out / (item['name'] + '.declaration.txt')).write_text(
            item['declaration'] + '\n', encoding='utf-8-sig')
        if item['implementation'] is not None:
            (out / (item['name'] + '.implementation.txt')).write_text(
                item['implementation'] + '\n', encoding='utf-8-sig')
    payload = dict(schema=1, baseline=baseline, changes=changes,
                   source_project=SOURCE_PROJECT,
                   source_run=str(SOURCE_RUN.relative_to(ROOT)),
                   source_snapshot_sha256=hashlib.sha256((SOURCE_RUN/'source_snapshot.json').read_bytes()).hexdigest())
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    (ROOT / 'payload.json').write_bytes(data)
    (ROOT / 'payload.sha256').write_text(hashlib.sha256(data).hexdigest()+'\n', encoding='ascii')
    print('Generated 6 objects (4 new, 2 modified), original mirror unchanged.')


if __name__ == '__main__':
    build()
