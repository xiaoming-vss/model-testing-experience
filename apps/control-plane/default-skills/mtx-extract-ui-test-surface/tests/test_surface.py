import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_surface import validate, normalize_surface, read_json


class SurfaceTests(unittest.TestCase):
    def setUp(self):
        self.surface = json.loads((ROOT / 'examples/pipeline/surface.json').read_text())
        self.cases = json.loads((ROOT / 'examples/pipeline/formal-cases.json').read_text())

    def errors(self):
        return validate(self.surface, cases=self.cases, source_root=ROOT / 'examples/pipeline/source')

    def test_complete_example(self):
        self.assertEqual(self.errors(), [])

    def test_malformed_shape_and_source_promotion(self):
        self.surface['controls'][0]['locatorCandidates'][0]['confirmed'] = True
        self.surface['controls'][0]['uniqueness'] = 'confirmed'
        self.assertTrue(self.errors())
        self.surface['controls'] = None
        self.assertTrue(self.errors())

    def test_all_non_ui_or_explained_unavailable_needs_no_fake_page(self):
        for key in ('pages','controls','containers','interactions','feedback'):
            self.surface[key] = []
        entry = self.surface['inspectionCoverage'][0]
        entry.update(status='non_ui',pageIds=[],componentFiles=[],reason='Only backend operations')
        self.assertEqual(self.errors(), [])
        entry.update(status='unavailable',reason='External renderer source unavailable')
        self.assertEqual(self.errors(), [])
        self.surface['unknowns'] = []
        self.assertTrue(self.errors())

    def test_empty_selection_allowed_but_missing_coverage_not_allowed(self):
        for key in ('pages','controls','containers','interactions','feedback','inspectionCoverage'):
            self.surface[key] = []
        self.assertTrue(self.errors())
        self.cases={'cases': []}
        self.assertEqual(self.errors(), [])

    def test_normalization_preserves_existing_description_and_input(self):
        item=self.surface['interactions'][0]
        item.update(effect='long effect '*10,description='Existing independent fact')
        before=copy.deepcopy(self.surface)
        result,_=normalize_surface(self.surface)
        self.assertIn(item['effect'],result['interactions'][0]['description'])
        self.assertIn(item['description'],result['interactions'][0]['description'])
        self.assertEqual(self.surface,before)

    def test_conflicting_row_metadata_is_not_overwritten(self):
        self.surface['containers']=[{'containerId':'table','rowLocator':{'description':'new key'},'rowKey':'existing key'}]
        before=copy.deepcopy(self.surface)
        with self.assertRaises(ValueError):normalize_surface(self.surface)
        self.assertEqual(self.surface,before)

    def test_interaction_control_reference_is_typed(self):
        self.surface['interactions'][0]['controlId']='page'
        self.assertTrue(self.errors())

    def test_runtime_proof_exact_match_and_pointer(self):
        control=self.surface['controls'][0]
        loc=control['locatorCandidates'][0]
        loc.update(evidenceType='runtime',confirmed=True,runtimeEvidenceRef='/locators/0',stability='runtime_only')
        control['uniqueness']='confirmed'
        self.surface['runtimeEvidence']={'locators':[{'count':1,'locatorType':loc['locatorType'],'locatorValue':loc['locatorValue']}]}
        self.assertEqual(self.errors(),[])
        loc['runtimeEvidenceRef']='/locators/-1'
        self.assertTrue(self.errors())
        loc['runtimeEvidenceRef']='/locators/0'
        self.surface['runtimeEvidence']['locators'][0]['count']=True
        self.assertTrue(self.errors())

    def test_duplicate_case_id_and_json_keys_rejected(self):
        self.cases['cases'].append(copy.deepcopy(self.cases['cases'][0]))
        self.assertTrue(self.errors())
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.json';p.write_text('{"app":{},"app":{}}')
            with self.assertRaises(ValueError):read_json(p)

    def test_failed_finalize_preserves_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'surface.json'
            self.surface['containers']=[{'containerId':'table','rowLocator':{'description':'new'},'rowKey':'old'}]
            path.write_text(json.dumps(self.surface));before=path.read_bytes()
            result=subprocess.run([sys.executable,str(ROOT/'scripts/validate_surface.py'),str(path),'--finalize'],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(path.read_bytes(),before)
            self.assertNotIn('Traceback',result.stderr)

if __name__=='__main__':unittest.main()
