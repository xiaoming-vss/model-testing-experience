"""Run: python3 -m unittest discover -s tests -v from this skill directory."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('relations_validate', ROOT / 'scripts/validate.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def read(name):
    return json.loads((ROOT / 'references' / name).read_text())


class RelationValidationTests(unittest.TestCase):
    def setUp(self):
        self.graph = read('example-relations.json')
        self.cases = read('example-cases.json')

    def invalid(self, graph=None, cases=None):
        with self.assertRaises(ValueError):
            validator.validate(self.graph if graph is None else graph,
                               self.cases if cases is None else cases)

    def cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/validate.py'), *map(str, args)],
                                capture_output=True, text=True,
                                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return result

    def test_complete_canvas_example(self):
        self.cli(ROOT / 'references/example-relations.json', '--cases', ROOT / 'references/example-cases.json',
                 '--material', ROOT / 'references/example-material.json', '--mode', 'canvas')
        self.assertEqual(len(validator.validate(self.graph, self.cases)), 7)
        # Eighth input remains a valid independent node, without an output node list.

    def test_history_examples_and_empty_cases(self):
        for prefix in ('parallel', 'overlap'):
            self.cli(ROOT / f'references/{prefix}-relations.json', '--cases',
                     ROOT / f'references/{prefix}-cases.json', '--mode', 'history')
        validator.validate({'schema_version': '2.0', 'main_paths': [], 'edges': []}, {'cases': []})

    def test_id_only_input_is_rejected(self):
        self.invalid(cases={'cases': [{'case_id': c['case_id']} for c in self.cases['cases']]})

    def test_case_text_and_array_requirements(self):
        for field, value in [('case_title', ''), ('case_module', None), ('priority', 2),
                             ('precondition', 'none'), ('test_steps', []),
                             ('expected_results', [' ']), ('test_steps', [1])]:
            with self.subTest(field=field, value=value):
                data = copy.deepcopy(self.cases)
                data['cases'][0][field] = value
                self.invalid(cases=data)
        data = copy.deepcopy(self.cases)
        del data['cases'][0]['precondition']
        self.invalid(cases=data)

    def test_history_format_and_platform_metadata_are_preserved(self):
        self.cases['metadata'] = {'revision': 'v1'}
        case = self.cases['cases'][0]
        case.update(precondition=[], priority='历史级别', case_type='平台自定义类型',
                    test_steps=['提交并查看结果'], expected_results=['任务进入待处理'], platform_tag='old')
        validator.validate(self.graph, self.cases)

    def test_missing_duplicate_and_unknown_case_ids(self):
        data = copy.deepcopy(self.cases)
        del data['cases'][0]['case_id']
        self.invalid(cases=data)
        data = copy.deepcopy(self.cases)
        data['cases'].append(copy.deepcopy(data['cases'][0]))
        self.invalid(cases=data)
        self.graph['edges'][0]['from_case_id'] = 'not-in-input'
        self.invalid()

    def test_case_ids_are_not_normalized(self):
        self.cases['cases'][0]['case_id'] = ' C001 '
        self.invalid()
        self.graph['main_paths'][0]['case_ids'][0] = ' C001 '
        self.graph['edges'][0]['from_case_id'] = ' C001 '
        validator.validate(self.graph, self.cases)

    def test_duplicate_and_contained_spines(self):
        for seq in (['C001', 'C002', 'C003', 'C007'], ['C002', 'C003'], ['C001', 'C002'], ['C003', 'C007']):
            with self.subTest(seq=seq):
                graph = copy.deepcopy(self.graph)
                graph['main_paths'].append({'path_id': 'P02', 'case_ids': seq})
                self.invalid(graph=graph)

    def test_shared_sections_and_returns_remain_legal(self):
        # No path fully contains another: shared nodes/edges remain protocol-valid.
        self.graph['edges'].append({'edge_id': 'E08', 'from_case_id': 'C008', 'to_case_id': 'C003',
                                    'relation_type': 'next', 'order': 1})
        self.graph['main_paths'].append({'path_id': 'P02', 'case_ids': ['C008', 'C003', 'C007']})
        self.graph['edges'].append({'edge_id': 'E09', 'from_case_id': 'C007', 'to_case_id': 'C001',
                                    'relation_type': 'next', 'order': 1})
        validator.validate(self.graph, self.cases)
        # These mutations exercise structure only; they do not assert example business support.

    def test_invalid_order_rejected_but_gaps_allowed(self):
        for value in (True, '1', 1.0, 0, -1):
            with self.subTest(value=value):
                graph = copy.deepcopy(self.graph)
                graph['edges'][0]['order'] = value
                self.invalid(graph=graph)
        self.graph['edges'][0]['order'] = 7
        validator.validate(self.graph, self.cases)

    def test_self_edges_duplicate_pairs_and_source_orders(self):
        graph = copy.deepcopy(self.graph)
        graph['edges'].append({'edge_id': 'self', 'from_case_id': 'C008', 'to_case_id': 'C008',
                               'relation_type': 'branch', 'order': 1})
        self.invalid(graph=graph)
        graph = copy.deepcopy(self.graph)
        edge = dict(graph['edges'][0], edge_id='duplicate-pair', order=3, relation_type='branch')
        graph['edges'].append(edge)
        self.invalid(graph=graph)
        graph = copy.deepcopy(self.graph)
        graph['edges'][3]['order'] = graph['edges'][1]['order']
        self.invalid(graph=graph)

    def test_spine_requires_next_and_unique_nodes(self):
        graph = copy.deepcopy(self.graph)
        graph['edges'][0]['relation_type'] = 'branch'
        self.invalid(graph=graph)
        graph = copy.deepcopy(self.graph)
        graph['main_paths'][0]['case_ids'].append('C001')
        self.invalid(graph=graph)

    def test_fixed_output_contract_rejects_extra_fields(self):
        self.graph['label'] = 'unexpected'
        self.invalid()
        self.invalid(graph={'flows': [], 'links': []})

    def test_explicit_mode_requirements(self):
        relation = ROOT / 'references/example-relations.json'
        cases = ROOT / 'references/example-cases.json'
        material = ROOT / 'references/example-material.json'
        self.cli(relation, '--cases', cases, '--mode', 'canvas', ok=False)
        self.cli(relation, '--mode', 'history', ok=False)
        self.cli(relation, '--cases', cases, '--material', material, '--mode', 'history', ok=False)
        self.cli(relation, '--material', material, ok=False)
        self.cli(relation, '--cases', cases)  # Existing CLI stays compatible, with limited-scope notice.
        result = self.cli(relation)
        self.assertIn('references NOT checked', result.stdout)

    def test_invalid_material_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'material.json'
            data = read('example-material.json')
            data['materialBlocks'][0]['parentId'] = data['materialBlocks'][0]['id']
            path.write_text(json.dumps(data))
            self.cli(ROOT / 'references/example-relations.json', '--cases', ROOT / 'references/example-cases.json',
                     '--material', path, '--mode', 'canvas', ok=False)

    def test_strict_json_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'invalid.json'
            for value in ('{"edges": [], "edges": []}', '{"order": NaN}', '{"order": Infinity}'):
                path.write_text(value)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    validator.read_json(path)


if __name__ == '__main__':
    unittest.main()
