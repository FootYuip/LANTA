# -*- coding: utf-8 -*-
"""Run in CODESYS Tools > Scripting, NOT Windows Python. Offline candidate only."""
from __future__ import print_function
import os
import io
import json
import hashlib
import datetime
import traceback
import sys
if sys.platform == 'cli':
    import clr
    clr.AddReference('System.Xml')
    from System.Xml import XmlDocument
else:
    import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
EXPECTED = u'EbN0扫描捕获_1度波束扫描及误差电压EbN0双门限 - 副本.project'
# Payload rebased to the reviewed double-threshold project capture.
PREPARE_ONLY = False
OUT = os.path.join(ROOT, 'runs', datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
os.makedirs(OUT)
LOG = []


def norm(text):
    # Preserve tokens/comments, tolerate only editor line ending/indentation changes.
    return u'\n'.join(line.strip() for line in unicode(text).replace('\r', '').split('\n') if line.strip())


def find_one(app, name):
    matches = list(app.find(name, True))
    # Recursive find also returns task POU-call references (same name as POU).
    # Only actual declaration-bearing source objects may be edited.
    found = [obj for obj in matches if obj.has_textual_declaration]
    LOG.append('lookup=%s; all_matches=%d; source_matches=%d' %
               (name, len(matches), len(found)))
    if len(found) != 1:
        raise RuntimeError('Expected exactly one source object: %s (sources=%d, all=%d)' %
                           (name, len(found), len(matches)))
    return found[0]


def texts(obj):
    decl = unicode(obj.textual_declaration.text) if obj.has_textual_declaration else None
    body = unicode(obj.textual_implementation.text) if obj.has_textual_implementation else None
    return (decl, body)


def snapshot(obj, prefix=''):
    result = {}
    for child in obj.get_children():
        key = prefix + '/' + unicode(child.get_name())
        if key in result:
            raise RuntimeError('Duplicate tree path: ' + key)
        result[key] = texts(child)
        result.update(snapshot(child, key))
    return result


def export_xml(project, filename):
    project.export_xml(objects=list(project.get_children()), reporter=None,
        path=filename, recursive=True, export_folder_structure=True,
        declarations_as_plaintext=True)
    if sys.platform == 'cli':
        # CODESYS' bundled SimpleXMLTreeBuilder rejects UTF-8 BOM and lacks
        # modern ElementTree APIs. Let .NET handle encoding and namespaces.
        document = XmlDocument()
        document.XmlResolver = None
        document.Load(filename)
        return document
    return ET.parse(filename).getroot()


def tasks(root):
    if sys.platform == 'cli':
        return [(unicode(t.GetAttribute('name')), unicode(t.GetAttribute('interval')),
                 unicode(t.GetAttribute('priority')),
                 [unicode(p.GetAttribute('name')) for p in
                  t.SelectNodes("./*[local-name()='pouInstance']")])
                for t in root.SelectNodes("//*[local-name()='task']")]
    return [(t.get('name'), t.get('interval'), t.get('priority'),
             [p.get('name') for p in t if p.tag.split('}')[-1]=='pouInstance'])
            for t in root.iter() if t.tag.split('}')[-1]=='task']


def main():
    with open(os.path.join(ROOT, 'payload.json'), 'rb') as f:
        raw = f.read()
    with open(os.path.join(ROOT, 'payload.sha256'), 'r') as f:
        expected_hash = f.read().strip()
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise RuntimeError('Payload checksum mismatch. Regenerate the package.')
    data = json.loads(raw.decode('utf-8'))
    if not PREPARE_ONLY and data.get('source_project') != EXPECTED:
        raise RuntimeError('Payload targets a different project. Refusing apply.')
    project = projects.primary
    if project is None:
        raise RuntimeError('Open the source project first.')
    source = os.path.abspath(unicode(project.path))
    LOG.append(u'source=' + source)
    if os.path.basename(source) != EXPECTED:
        raise RuntimeError(u'Wrong source project. Expected: ' + EXPECTED)
    repo = os.path.abspath(os.path.join(ROOT, '..', '..'))
    if os.path.normcase(os.path.dirname(source)) != os.path.normcase(repo):
        raise RuntimeError('Source must be the originally designated project in LANTA.')
    app = project.active_application
    if app is None or unicode(app.get_name()) != 'Application':
        raise RuntimeError('Set Device.Application as active application first.')
    # Export the live source before changing any object, preserving its structure.
    project.export_native(objects=list(project.get_children()),
        destination=os.path.join(OUT, 'baseline.export'), recursive=True)
    before_xml = export_xml(project, os.path.join(OUT, 'baseline.xml'))
    if PREPARE_ONLY:
        captured = snapshot(project)
        with io.open(os.path.join(OUT, 'source_snapshot.json'), 'w', encoding='utf-8') as handle:
            handle.write(unicode(json.dumps(captured, ensure_ascii=False, indent=2)))
        LOG.append('PREPARE_ONLY: baseline and source snapshot captured; project unchanged.')
        print('BASELINE_CAPTURED. No project changes. Await package rebase.')
        return
    expected_task = ('Canopen', 'PT0.01S', '0', ['TimeAdd', 'AutoTrackingCal',
        'El_ctrl_1', 'Az_ctrl_1', 'Ti_ctrl_1', 'RealTimePosCal', 'SecurityCheck'])
    task_list = tasks(before_xml)
    if task_list.count(expected_task) != 1:
        raise RuntimeError('Canopen task does not match required 10 ms baseline/order.')
    if sum(t[3].count('SecurityCheck') for t in task_list) != 1:
        raise RuntimeError('SecurityCheck must be called by exactly one task.')
    if task_list.count(('SerialCom', 'PT0.005S', '1', ['READ_485', 'GPRMC_1'])) != 1:
        raise RuntimeError('SerialCom task does not match required baseline.')
    for item in data['baseline']:
        obj = find_one(app, item['name'])
        decl, body = texts(obj)
        if norm(decl) != norm(item['declaration']) or (
                item['implementation'] is not None and norm(body) != norm(item['implementation'])):
            raise RuntimeError('BASELINE_MISMATCH: ' + item['name'] +
                '. Source untouched. Send runs/baseline.export and baseline.xml for rebasing.')
    for item in data['changes']:
        if item['kind'] != 'existing' and list(app.find(item['name'], True)):
            raise RuntimeError('New object already exists: ' + item['name'])
    before = snapshot(project)
    if not hasattr(app, 'create_pou') or not hasattr(app, 'create_gvl'):
        raise RuntimeError('Required creation API unavailable. Use generated text files for manual insertion.')
    candidate = os.path.splitext(source)[0] + '.phase-candidate-' + os.path.basename(OUT) + '.project'
    if os.path.exists(candidate):
        raise RuntimeError('Candidate already exists; refusing overwrite.')
    project.save_as(candidate)
    LOG.append(u'candidate=' + candidate)
    changed = []
    for item in data['changes']:
        kind, name = item['kind'], item['name']
        if kind == 'existing':
            obj = find_one(app, name)
        elif kind == 'gvl':
            obj = app.create_gvl(name)
        elif kind == 'fb':
            obj = app.create_pou(name, PouType.FunctionBlock)
        else:
            obj = app.create_pou(name, PouType.Program)
        obj.textual_declaration.replace(item['declaration'])
        if item['implementation'] is not None:
            obj.textual_implementation.replace(item['implementation'])
        changed.append(obj)
        LOG.append('updated=' + name)
    after = snapshot(project)
    modified_names = set(['READ_485', 'SecurityCheck'])
    new_names = set(i['name'] for i in data['changes'] if i['kind'] != 'existing')
    for key, value in before.items():
        if key not in after:
            raise RuntimeError('Unexpected removed object: ' + key)
        if after[key] != value and key.split('/')[-1] not in modified_names:
            raise RuntimeError('Unexpected changed source: ' + key)
    added = set(after)-set(before)
    if len(added) != 4 or set(k.split('/')[-1] for k in added) != new_names:
        raise RuntimeError('Unexpected object inventory change.')
    for item in data['changes']:
        decl, body = texts(find_one(app, item['name']))
        if norm(decl) != norm(item['declaration']) or (
                item['implementation'] is not None and norm(body) != norm(item['implementation'])):
            raise RuntimeError('Source readback mismatch: ' + item['name'])
    project.save()
    app.build()
    error_count = 0
    for category in system.get_message_categories():
        LOG.append(u'category=' + unicode(system.get_message_category_description(category)))
        for message in system.get_message_objects(category):
            LOG.append(unicode(message.severity) + ': ' + unicode(message.text))
        error_count += len(system.get_message_objects(category, Severity.Error | Severity.FatalError))
    project.save()
    project.export_native(objects=list(project.get_children()),
        destination=os.path.join(OUT, 'candidate.export'), recursive=True)
    project.export_native(objects=changed,
        destination=os.path.join(OUT, 'phase-changes.export'), recursive=True)
    after_xml = export_xml(project, os.path.join(OUT, 'candidate.xml'))
    if tasks(after_xml) != task_list:
        raise RuntimeError('Task configuration unexpectedly changed.')
    LOG.append('source_readback=PASS; object_inventory=PASS; task_config=UNCHANGED')
    LOG.append('error_messages=' + str(error_count))
    LOG.append('runtime_motion_validation=NOT_PERFORMED; mirror_roundtrip=NEEDS_REVIEW')
    if error_count:
        raise RuntimeError('Candidate generated but messages contain errors. Do not download.')
    LOG.append('CANDIDATE_BUILD_NO_ERROR_MESSAGES; review warnings before commissioning.')
    print(candidate)


try:
    main()
except Exception:
    LOG.append(unicode(traceback.format_exc()))
    raise
finally:
    with io.open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8-sig') as f:
        f.write(u'\n'.join(LOG))
    print('Report: ' + OUT)
