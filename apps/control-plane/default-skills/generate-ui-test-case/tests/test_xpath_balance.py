"""Reject broken XPath syntax before provenance-based locator exemptions."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from validate_ui_case import validate_locator

REAL_BROKEN = ["//table[count(tbody/tr)=1 and count(tbody/tr[td[2][normalize-space(.)='LeRobot'] and td[3][normalize-space(.)='1'] and td[4][contains(normalize-space(.),' / 1')] and td[5][normalize-space(.)='创建转换任务' or td[5][normalize-space(.)='转换中']])=1]", "//table[count(tbody/tr)=1 and count(tbody/tr[td[2][normalize-space(.)='LeRobot'] and td[3][normalize-space(.)='3'] and td[5][normalize-space(.)='创建转换任务' or td[5][normalize-space(.)='转换中']])=1]"]

class XPathBalance(unittest.TestCase):
    def check(self, value, evidence=None):
        validate_locator({'locatorType':'xpath','locatorValue':value}, 'case', 1, evidence)

    def test_formal_candidates_rejected_even_with_evidence(self):
        for value in REAL_BROKEN:
            for evidence in (None, False, {('xpath', value)}):
                with self.subTest(value=value, evidence=evidence), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    self.check(value, evidence)

    def test_mismatches_and_unclosed_literals(self):
        for value in ['//tr[(td])', '//tr[td', '//tr)', "//tr[td='value]", '//tr[td="value]']:
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.check(value)

    def test_quoted_delimiters_and_templates(self):
        for value in ["//tr[td='[(]']", '//tr[td="[)]"]', "//tr[td=concat('a', \"'\", '[)]')]", '//tr[td={{记录ID|xpath}} and count(td)=3]', '(//table//tr)[1]']:
            with self.subTest(value=value):
                self.check(value)

if __name__ == '__main__': unittest.main()
