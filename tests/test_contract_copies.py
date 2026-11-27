import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ContractCopyTests(unittest.TestCase):
    def test_contract_copies_are_synchronized(self):
        result = subprocess.run(
            [sys.executable, "scripts/sync_contract_copies.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
