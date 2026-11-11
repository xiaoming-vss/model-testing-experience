import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from export_ui_case import serialize, checked_export
from coverage_workbench import initialize, bind
from check_design_coverage import initialize_account


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{'name': 'count', 'enabled': True, 'orderNo': 1, 'stepsJson': [
            {'orderNo': 1, 'stepName': 'Exactly two rows', 'keyword': 'assert_visible',
             'locatorType': 'xpath', 'locatorValue': '//table[count(tbody/tr)=2]',
             'operationValue': '5000', 'enabled': True, 'continueOnFailure': False}]}]
        self.design = {'cases': [{'caseId': 'count', 'name': 'count', 'coverage': 'full',
            'steps': [{'actions': [], 'expectations': [{'expectationId': 'E1', 'status': 'included',
                'target': 'result rows', 'value': 2, 'sourceQuote': 'Exactly two rows'}]}]}]}

    def evidence(self):
        account = initialize_account(self.design)
        account['cases'][0]['targets'][0].update(steps=[1], evidence='count(tbody/tr)=2 checks all result rows')
        audit = initialize(self.design, self.rows)
        audit['cases'][0]['targets'][0].update(verdict='supported', clauses=[{
            'claim': 'Exactly two rows', 'object': 'result tbody', 'valueSource': 'design literal 2',
            'scope': 'visible result table', 'timing': 'after query',
            'counterexample': 'One result row', 'rejection': 'count(tbody/tr)=2 is false',
            'refs': [{'orderNo': 1, 'field': 'locatorValue'}]}])
        return account, bind(self.design, self.rows, audit, 'count')

    def files(self, root):
        account, audit = self.evidence()
        values = {'candidate': self.rows, 'design': self.design, 'account': account, 'audit': audit}
        paths = {key: root / (key + '.json') for key in values}
        for key, value in values.items():
            paths[key].write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        paths['output'] = root / 'final.yaml'
        return paths

    def test_punctuation_templates_multiline_and_unicode_are_preserved(self):
        text = "成功项ID列(td[3]): 'quote' \"double\" {x} #tag\\path\n{{id|xpath}}\u0085\u2028\u2029"
        self.rows[0]['stepsJson'][0]['missingFields'] = [
            {'fields': [], 'target': text, 'operation': 'Observe', 'value': None, 'reason': text}]
        result = serialize(self.rows)
        self.assertTrue(result.startswith('- name:'))
        self.assertEqual(yaml.safe_load(result), self.rows)
        self.assertIn('\\u2028', result)

    def test_scalar_aliases_preserve_repetition_without_shared_mutable_objects(self):
        import copy
        repeated = "//div[@data-key='a: [b] {{id|xpath}}']" * 3
        step = self.rows[0]['stepsJson'][0]
        step['locatorValue'] = repeated
        duplicate = copy.deepcopy(step)
        duplicate['orderNo'] = 2
        self.rows[0]['stepsJson'].append(duplicate)
        result = serialize(self.rows)
        self.assertIn('&s', result)
        self.assertIn('*s', result)
        self.assertEqual(result.count(repeated), 1)
        restored = yaml.safe_load(result)
        self.assertEqual(restored, self.rows)
        self.assertIsNot(restored[0]['stepsJson'][0], restored[0]['stepsJson'][1])
        self.assertEqual(serialize(self.rows), result)

    def test_yaml_implicit_types_remain_strings_and_empty_selection_survives(self):
        for value in ['yes', 'null', '0123', '2026-10-29', '', '{{value}}']:
            self.rows[0]['name'] = value
            self.assertEqual(yaml.safe_load(serialize(self.rows)), self.rows)
        self.assertEqual(serialize([]), '[]\n')

    def test_unknown_fields_or_non_list_are_not_silently_dropped(self):
        with self.assertRaises(ValueError): serialize({'cases': self.rows})
        self.rows[0]['unexpected'] = 'keep me'
        with self.assertRaises(ValueError): serialize(self.rows)

    def test_real_checks_export_identical_data_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.files(Path(directory))
            before = paths['candidate'].read_bytes()
            report = checked_export(**paths)
            output = paths['output'].read_bytes()
            self.assertEqual(yaml.safe_load(output), self.rows)
            self.assertEqual(report['sha256'], hashlib.sha256(output).hexdigest())
            self.assertEqual(paths['candidate'].read_bytes(), before)

    def test_json_native_unicode_line_breaks_keep_json_semantics(self):
        self.rows[0]['stepsJson'][0]['stepName'] = 'Observe\u0085count\u2028and\u2029value'
        with tempfile.TemporaryDirectory() as directory:
            paths = self.files(Path(directory))
            checked_export(**paths)
            self.assertEqual(yaml.safe_load(paths['output'].read_text()), self.rows)
            # An audit previously built from lossy YAML decoding is stale,
            # rather than authorization to export the altered JSON value.
            normalized = yaml.safe_load(paths['candidate'].read_text())
            self.assertNotEqual(normalized, self.rows)
            audit = json.loads(paths['audit'].read_text())
            from coverage_workbench import refresh
            audit, _ = refresh(self.design, normalized, audit)
            target = audit['cases'][0]['targets'][0]
            target.update(verdict='unresolved', reason='Observe decoded input before review')
            paths['audit'].write_text(json.dumps(audit))
            previous = paths['output'].read_bytes()
            with self.assertRaises(subprocess.CalledProcessError): checked_export(**paths)
            self.assertEqual(paths['output'].read_bytes(), previous)

    def test_unknown_binding_blocks_export_until_explicitly_declared(self):
        self.rows[0]['stepsJson'][0]['locatorValue'] = '//table[count(tbody/tr)={{expectedCount|xpath}}]'
        with tempfile.TemporaryDirectory() as directory:
            paths = self.files(Path(directory))
            paths['output'].write_text('previous output')
            with self.assertRaises(subprocess.CalledProcessError): checked_export(**paths)
            self.assertEqual(paths['output'].read_text(), 'previous output')
            report = checked_export(**paths, external_variables=['expectedCount'])
            self.assertEqual(report['declaredExternalVariables'], ['expectedCount'])
            self.assertEqual(yaml.safe_load(paths['output'].read_text()), self.rows)

    def test_stale_audit_rejects_export_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.files(Path(directory))
            self.rows[0]['stepsJson'][0]['locatorValue'] = '//table[count(tbody/tr)=1]'
            paths['candidate'].write_text(json.dumps(self.rows))
            paths['output'].write_text('previous checked output')
            with self.assertRaises(subprocess.CalledProcessError): checked_export(**paths)
            self.assertEqual(paths['output'].read_text(), 'previous checked output')
            self.assertEqual(list(Path(directory).glob('.export-*')), [])

    def test_missing_coverage_rejects_export_and_inputs_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.files(Path(directory))
            paths['account'].write_text(json.dumps(initialize_account(self.design)))
            with self.assertRaises(subprocess.CalledProcessError): checked_export(**paths)
            self.assertFalse(paths['output'].exists())
            paths['output'] = paths['design']
            with self.assertRaises(ValueError): checked_export(**paths)


if __name__ == '__main__':
    unittest.main()
