"""Built-in template functions are one module behind two independently packaged apps."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = {
    "api-ui-worker": ROOT
    / "apps/api-ui-worker/src/test_worker/template_functions.py",
    "control-plane": ROOT / "apps/control-plane/src/testing_agent/domain/template_functions.py",
}
CONTRACT = ROOT / "tests/fixtures/api-template-contract.json"


class TemplateFunctionsContractTests(unittest.TestCase):
    def test_the_worker_and_control_plane_bundle_the_same_functions(self):
        contents = [path.read_bytes() for path in COPIES.values()]
        self.assertEqual(contents[0], contents[1])

    def test_contract_fixture_names_every_case(self):
        cases = json.loads(CONTRACT.read_text(encoding="utf-8"))["cases"]
        names = [case["name"] for case in cases]
        self.assertEqual(len(names), len(set(names)))
        for case in cases:
            self.assertIn("template", case)
            self.assertIn("expected", case)


if __name__ == "__main__":
    unittest.main()
