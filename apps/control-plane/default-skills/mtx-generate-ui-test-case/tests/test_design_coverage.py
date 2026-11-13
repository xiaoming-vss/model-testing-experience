import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_design_coverage import check_coverage, initialize_account


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.design = {'cases': [{'caseId': 'c1', 'name': 'Full collection', 'coverage': 'partial',
            'steps': [{'actions': [{'actionId': 'a1', 'status': 'included'}],
                       'expectations': [{'expectationId': 'count', 'status': 'included'},
                                        {'expectationId': 'ids', 'status': 'included'},
                                        {'expectationId': 'excluded', 'status': 'excluded'}]}]}]}
        self.rows = [{'name': 'Full collection', 'stepsJson': [
            {'orderNo': 1, 'keyword': 'click', 'enabled': True},
            {'orderNo': 2, 'keyword': 'assert_text', 'enabled': True},
            {'orderNo': 3, 'keyword': 'assert_visible', 'enabled': True}]}]
        self.account = {'cases': [{'caseId': 'c1', 'targets': [
            {'id': 'a1', 'steps': [1], 'evidence': 'Click query'},
            {'id': 'count', 'steps': [2], 'evidence': 'Compare total against fixture count'},
            {'id': 'ids', 'steps': [3], 'evidence': 'Exact multiplicity predicate for every expected ID'}]}]}

    def test_count_only_account_cannot_hide_missing_full_list_target(self):
        self.account['cases'][0]['targets'].pop()
        with self.assertRaisesRegex(ValueError, 'ids'):
            check_coverage(self.design, self.rows, self.account)

    def test_complete_account_preserves_inputs(self):
        before = copy.deepcopy((self.design, self.rows, self.account))
        check_coverage(self.design, self.rows, self.account)
        self.assertEqual(before, (self.design, self.rows, self.account))

    def test_excluded_expectation_not_reintroduced(self):
        self.account['cases'][0]['targets'].append({'id': 'excluded', 'steps': [3], 'evidence': 'e'})
        with self.assertRaisesRegex(ValueError, 'excluded'):
            check_coverage(self.design, self.rows, self.account)

    def test_click_or_save_is_not_an_assertion(self):
        self.account['cases'][0]['targets'][-1]['steps'] = [1]
        with self.assertRaisesRegex(ValueError, 'assertion'):
            check_coverage(self.design, self.rows, self.account)

    def test_stale_missing_or_disabled_step_does_not_count(self):
        for change in ('stale', 'disabled', 'ignored'):
            rows, account = copy.deepcopy((self.rows, self.account))
            if change == 'stale': account['cases'][0]['targets'][-1]['steps'] = [99]
            elif change == 'disabled': rows[0]['stepsJson'][-1]['enabled'] = False
            else: rows[0]['stepsJson'][-1]['continueOnFailure'] = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                check_coverage(self.design, rows, account)

    def test_other_case_cannot_supply_the_account(self):
        self.account['cases'][0]['caseId'] = 'other'
        with self.assertRaisesRegex(ValueError, 'caseId'):
            check_coverage(self.design, self.rows, self.account)

    def test_negative_action_may_continue_when_outcome_is_asserted(self):
        self.rows[0]['stepsJson'][0]['continueOnFailure'] = True
        check_coverage(self.design, self.rows, self.account)

    def test_disabled_case_cannot_hide_retained_targets(self):
        self.rows[0]['enabled'] = False
        with self.assertRaisesRegex(ValueError, 'disabled'):
            check_coverage(self.design, self.rows, self.account)

    def test_required_click_cannot_be_replaced_by_disabled_observation(self):
        self.design['cases'][0]['steps'][0]['actions'][0]['operation'] = 'click'
        self.rows[0]['stepsJson'][0]['keyword'] = 'assert_visible'
        self.rows[0]['stepsJson'][0]['locatorValue'] = "//button[@disabled]"
        with self.assertRaisesRegex(ValueError, 'interaction'):
            check_coverage(self.design, self.rows, self.account)

    def test_equivalent_keyboard_interaction_is_not_rejected_by_account_check(self):
        self.design['cases'][0]['steps'][0]['actions'][0]['operation'] = 'click'
        self.rows[0]['stepsJson'][0]['keyword'] = 'press'
        check_coverage(self.design, self.rows, self.account)

    def test_observation_can_be_implemented_by_assertion(self):
        self.design['cases'][0]['steps'][0]['actions'][0]['operation'] = 'observe'
        self.rows[0]['stepsJson'][0]['keyword'] = 'assert_visible'
        check_coverage(self.design, self.rows, self.account)

    def test_explicit_negative_click_can_continue_to_effective_assertion(self):
        self.design['cases'][0]['steps'][0]['actions'][0]['operation'] = 'click'
        self.rows[0]['stepsJson'][0]['continueOnFailure'] = True
        check_coverage(self.design, self.rows, self.account)

    def test_initialized_account_contains_all_and_only_included_targets_and_starts_red(self):
        account = initialize_account(self.design)
        self.assertEqual([e['id'] for e in account['cases'][0]['targets']], ['a1', 'count', 'ids'])
        self.assertTrue(all(e['steps'] == [] and e['evidence'] == '' for e in account['cases'][0]['targets']))
        with self.assertRaisesRegex(ValueError, 'actual candidate'):
            check_coverage(self.design, self.rows, account)
