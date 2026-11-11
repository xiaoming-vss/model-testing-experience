import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_state_assertions import build, literal
from ui_variable_template import parse_tokens
from validate_ui_case import validate_xpath_delimiters


def example():
    return {'anchorXPath': "//div[@id='detail']", 'rowXPath': "//div[@id='detail']//tbody/tr",
            'identityColumn': 2, 'stateColumn': 5, 'scope': 'all', 'requireProgress': True,
            'records': [{'identity': {'literal': identity}, 'beforeVariable': 'before' + identity}
                        for identity in ['A', 'B', 'C']],
            'transitions': {'待转换': ['待转换', '转换中', '转换成功', '转换失败'],
                            '转换中': ['转换中', '转换成功', '转换失败'],
                            '转换成功': ['转换成功'], '转换失败': ['转换失败']}}


class StateAssertionTests(unittest.TestCase):
    def test_both_sides_use_identity_and_keep_existing_executor_fields(self):
        plan = build(example())
        self.assertEqual(len(plan['beforeSteps']), 3)
        self.assertEqual(len(plan['afterSteps']), 1)
        for index, step in enumerate(plan['beforeSteps']):
            identity = 'ABC'[index]
            self.assertIn("normalize-space(td[2])='" + identity + "'", step['locatorValue'])
            self.assertEqual(step['saveTo'], [{'name': 'before' + identity, 'source': 'text'}])
        after = plan['afterSteps'][0]['locatorValue']
        for identity in 'ABC':
            self.assertIn("normalize-space(td[2])='" + identity + "'", after)
            self.assertIn('{{before' + identity + '|xpath}}', after)
        self.assertNotIn('/tr[1]', after)
        for step in plan['beforeSteps'] + plan['afterSteps']:
            self.assertEqual(step['keyword'], 'assert_visible')
            self.assertFalse(step['continueOnFailure'])
            validate_xpath_delimiters(step['locatorValue'], 'state plan')

    def test_reviewed_labels_are_not_replaced_or_extended(self):
        plan = build(example())
        after = plan['afterSteps'][0]['locatorValue']
        self.assertIn("='待转换'", after)
        self.assertNotIn('创建转换任务', after)
        self.assertNotIn('转换超时', after)

    def test_scope_and_progress_are_explicit(self):
        config = example()
        full = build(config)['afterSteps'][0]['locatorValue']
        self.assertIn("count(//div[@id='detail']//tbody/tr)=3", full)
        self.assertIn('normalize-space({{beforeA|xpath}})!=', full)
        config.update(scope='selected', requireProgress=False)
        selected = build(config)['afterSteps'][0]['locatorValue']
        self.assertNotIn("count(//div[@id='detail']//tbody/tr)=3", selected)
        self.assertNotIn('normalize-space({{beforeA|xpath}})!=', selected)
        del config['scope']
        with self.assertRaises(ValueError): build(config)

    def test_variable_id_values_are_checked_at_runtime(self):
        config = example()
        config['records'][0]['identity'] = {'variable': 'recordA'}
        config['records'][1]['identity'] = {'variable': 'recordB'}
        plan = build(config)
        for step in plan['beforeSteps'] + plan['afterSteps']:
            self.assertIn('{{recordA|xpath}}!={{recordB|xpath}}', step['locatorValue'])
            self.assertIn('string-length(normalize-space({{recordA|xpath}}))>0', step['locatorValue'])
            parse_tokens(step['locatorValue'])

    def test_duplicate_and_overwriting_bindings_are_rejected(self):
        for kind in ['identity', 'beforeVariable']:
            config = example()
            config['records'][1][kind] = copy.deepcopy(config['records'][0][kind])
            with self.assertRaises(ValueError): build(config)
        config = example()
        config['records'][0]['identity'] = {'variable': 'beforeA'}
        with self.assertRaises(ValueError): build(config)
        config = example()
        config['rowXPath'] = '//tbody[@data-task={{beforeA|xpath}}]/tr'
        with self.assertRaises(ValueError): build(config)

    def test_reserved_capture_variable_is_rejected_but_reference_is_allowed(self):
        config = example()
        config['records'][0]['beforeVariable'] = 'baseUrl'
        with self.assertRaisesRegex(ValueError, 'reserved saveTo'):
            build(config)
        config = example()
        config['records'][0]['identity'] = {'variable': 'baseUrl'}
        self.assertIn('{{baseUrl|xpath}}', build(config)['beforeSteps'][0]['locatorValue'])

    def test_quoted_id_and_bad_config(self):
        quoted = "A'\"中"
        config = example()
        config['records'][0]['identity'] = {'literal': quoted}
        plan = build(config)
        self.assertIn('concat(', plan['beforeSteps'][0]['locatorValue'])
        validate_xpath_delimiters(plan['afterSteps'][0]['locatorValue'], 'quoted state plan')
        with self.assertRaises(ValueError): literal('{{unsafe}}')
        for change in [{'records': []}, {'scope': []}, {'requireProgress': 'yes'}, {'identityColumn': 0},
                       {'stateColumn': 2}, {'transitions': {}}, {'extraProtocol': True}]:
            config = example(); config.update(change)
            with self.assertRaises(ValueError): build(config)


if __name__ == '__main__':
    unittest.main()
