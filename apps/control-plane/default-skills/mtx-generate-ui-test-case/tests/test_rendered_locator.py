import contextlib
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from validate_ui_case import validate_locator


class RenderedLocatorTests(unittest.TestCase):
    def test_exact_tokens_are_not_rejected_by_library_prefix(self):
        for kind, value in [
            ('css', '#format-menu .n-base-select-option'),
            ('xpath', "//div[@id='format-menu']/*[contains(concat(' ', normalize-space(@class), ' '), ' n-base-select-option ')]"),
        ]:
            validate_locator({'locatorType': kind, 'locatorValue': value}, 'fixture', 1)

    def test_ambiguous_class_substring_still_fails(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            validate_locator({'locatorType': 'xpath', 'locatorValue': "//div[contains(@class,'n-checkbox')]"}, 'fixture', 1)


if __name__ == '__main__':
    unittest.main()
