"""Packaging and mocked CODESYS safety checks. These tests do NOT run IEC ST."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from xml.etree import ElementTree as ET
import build_package as bp


class Text:
    def __init__(self, text):
        self.text = text

    def replace(self, value):
        self.text = value


class Obj:
    def __init__(self, name, declaration=None, implementation=None):
        self.name = name
        self.children = []
        self.has_textual_declaration = declaration is not None
        self.has_textual_implementation = implementation is not None
        self.textual_declaration = Text(declaration)
        self.textual_implementation = Text(implementation)

    def get_name(self):
        return self.name

    def get_children(self):
        return self.children

    def find(self, name, recursive):
        matches = [x for x in self.children if x.name == name]
        if recursive:
            for child in self.children:
                matches.extend(child.find(name, True))
        return matches

    def create(self, name, body):
        obj = Obj(name, '', body)
        self.children.append(obj)
        return obj

    def create_gvl(self, name):
        return self.create(name, None)

    def create_program(self, name):
        return self.create(name, '')

    create_function_block = create_program

    def create_pou(self, name, pou_type):
        return self.create(name, '')

    def build(self):
        return None


class Project(Obj):
    def __init__(self, path, payload):
        super().__init__('project')
        self.path = str(path)
        self.saved_as = []
        self.active_application = Obj('Application')
        self.children = [self.active_application]
        for item in payload['baseline']:
            self.active_application.children.append(Obj(item['name'], item['declaration'], item['implementation']))

    def save_as(self, path):
        self.saved_as.append(path)
        self.path = path

    def save(self):
        pass

    def export_native(self, objects, destination, recursive):
        Path(destination).write_text('<mock-export/>', encoding='utf-8')

    def export_xml(self, **kwargs):
        root = ET.Element('project')
        for name, interval, priority, calls in [
            ('Canopen', 'PT0.01S', '0', ['TimeAdd', 'AutoTrackingCal', 'El_ctrl_1',
             'Az_ctrl_1', 'Ti_ctrl_1', 'RealTimePosCal', 'SecurityCheck']),
            ('SerialCom', 'PT0.005S', '1', ['READ_485', 'GPRMC_1'])]:
            task = ET.SubElement(root, 'task', name=name, interval=interval, priority=priority)
            for call in calls:
                ET.SubElement(task, 'pouInstance', name=call)
        # Real CODESYS export includes a UTF-8 BOM.
        Path(kwargs['path']).write_bytes(b'\xef\xbb\xbf' + ET.tostring(root, encoding='utf-8'))


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((bp.ROOT/'payload.json').read_text(encoding='utf-8'))

    def test_original_bodies_preserved(self):
        before = {x['name']: x for x in self.data['baseline']}
        after = {x['name']: x for x in self.data['changes']}
        self.assertEqual(len(after), 6)
        for name in ['READ_485', 'SecurityCheck']:
            self.assertEqual(before[name]['declaration'], after[name]['declaration'])
        addition = bp.read(bp.ROOT/'READ_485.append.st').strip()+'\n'
        self.assertEqual(after['READ_485']['implementation'].replace(addition, ''),
                         before['READ_485']['implementation'])
        self.assertTrue(after['SecurityCheck']['implementation'].startswith(before['SecurityCheck']['implementation']))
        self.assertEqual(after['SecurityCheck']['implementation'].count('PRG_PhaseCalibration();'), 1)

    def test_generated_parts_and_hash(self):
        for item in self.data['changes']:
            for suffix, key in [('declaration', 'declaration'), ('implementation', 'implementation')]:
                if item[key] is not None:
                    self.assertEqual(bp.read(bp.ROOT/'generated'/(item['name']+'.'+suffix+'.txt')).strip(), item[key])
        self.assertEqual(hashlib.sha256((bp.ROOT/'payload.json').read_bytes()).hexdigest(),
                         (bp.ROOT/'payload.sha256').read_text().strip())

    def run_mock(self, mismatch=False, build_error=False, task_reference=False, duplicate_source=False, prepare_only=False):
        with tempfile.TemporaryDirectory(prefix='phase-cal-test-') as temp:
            root = Path(temp)/'v1'/'phase-calibration'
            root.mkdir(parents=True)
            for name in ['payload.json', 'payload.sha256']:
                (root/name).write_bytes((bp.ROOT/name).read_bytes())
            project = Project(Path(temp)/'EbN0扫描捕获_1度波束扫描及误差电压EbN0双门限 - 副本.project', self.data)
            if task_reference or duplicate_source:
                folder = Obj('TaskConfiguration' if task_reference else 'DuplicateFolder')
                folder.children.append(Obj('READ_485', '' if duplicate_source else None))
                project.active_application.children.append(folder)
            if mismatch:
                project.active_application.find('SecurityCheck', True)[0].textual_implementation.text += '\nchanged'
            messages = [NS(severity=2, text='mock build error')] if build_error else []
            system = NS(get_message_categories=lambda: ['build'],
                        get_message_category_description=lambda cat: 'build',
                        get_message_objects=lambda *args: messages)
            env = dict(__file__=str(root/'apply_in_codesys.py'), unicode=str,
                       projects=NS(primary=project), system=system,
                       Severity=NS(Error=2, FatalError=1), PouType=NS(FunctionBlock=2, Program=1))
            script = bp.read(bp.ROOT/'apply_in_codesys.py')
            if not prepare_only:
                script = script.replace('PREPARE_ONLY = True', 'PREPARE_ONLY = False')
            else:
                script = script.replace('PREPARE_ONLY = False', 'PREPARE_ONLY = True')
            if mismatch or build_error or duplicate_source:
                with self.assertRaises(RuntimeError):
                    exec(compile(script, env['__file__'], 'exec'), env)
            else:
                exec(compile(script, env['__file__'], 'exec'), env)
            stopped = mismatch or duplicate_source or prepare_only
            self.assertEqual(len(project.saved_as), 0 if stopped else 1)
            self.assertEqual(len(project.active_application.children), len(self.data['baseline']) +
                             (0 if stopped else 4) + int(task_reference or duplicate_source))
            reports = list((root/'runs').glob('*/report.txt'))
            self.assertEqual(len(reports), 1)
            report = reports[0].read_text(encoding='utf-8-sig')
            if prepare_only:
                self.assertIn('PREPARE_ONLY:', report)
                self.assertTrue((reports[0].parent/'source_snapshot.json').is_file())
            if build_error:
                self.assertNotIn('CANDIDATE_BUILD_NO_ERROR_MESSAGES;', report)

    def test_mock_success(self):
        self.run_mock()

    def test_mismatch_stops_before_save(self):
        self.run_mock(mismatch=True)

    def test_build_errors_not_reported_success(self):
        self.run_mock(build_error=True)

    def test_same_named_task_reference_is_not_a_source_object(self):
        self.run_mock(task_reference=True)

    def test_duplicate_source_still_stops_before_save(self):
        self.run_mock(duplicate_source=True)

    def test_prepare_only_never_modifies_project(self):
        self.run_mock(prepare_only=True)

    def test_baseline_matches_actual_codesys_snapshot(self):
        snapshot = json.loads(bp.read(bp.SOURCE_RUN/'source_snapshot.json'))
        for item in self.data['baseline']:
            decl, body = snapshot[item['source_path']]
            self.assertEqual(item['declaration'], decl.replace('\r\n', '\n').strip())
            if item['implementation'] is not None:
                self.assertEqual(item['implementation'], body.replace('\r\n', '\n').strip())
        reader = next(x for x in self.data['changes'] if x['name']=='READ_485')
        self.assertIn('isFirst:BOOL:=TRUE;', reader['declaration'])


if __name__ == '__main__':
    unittest.main()
