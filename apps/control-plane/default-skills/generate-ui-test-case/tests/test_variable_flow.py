from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_variable_flow import check


def case(*steps):
    return {'enabled': True, 'stepsJson': list(steps)}


class VariableFlowTests(unittest.TestCase):
    def test_supplied_inputs_and_builtin_functions_are_supported(self):
        rows=[case({'operationValue':'{{baseUrl}}/{{$uuid}}/{{projectName}}', 'locatorValue':'//input[@name={{fieldName|xpath}}]'})]
        self.assertEqual(check(rows, ['projectName','fieldName'])['issues'], [])

    def test_fixture_name_is_not_a_binding_and_text_only_markers_are_not_consumers(self):
        rows=[case({'stepName':'{{notTemplated}}', 'operationValue':'{{preparedId}}',
                    'missingFields':[{'reason':'Supply {{otherId}} later'}]})]
        self.assertEqual([i['name'] for i in check(rows)['issues']], ['preparedId'])

    def test_successful_prior_capture_is_available_but_same_step_capture_is_not(self):
        capture={'locatorValue':'//input', 'saveTo':[{'name':'actual', 'source':'value'}], 'continueOnFailure':False}
        use={'locatorValue':"//input[{{actual|xpath}}='']"}
        self.assertEqual(check([case(capture,use)])['issues'], [])
        self.assertEqual(len(check([case({**capture,**use})])['issues']), 1)

    def test_later_disabled_or_failure_ignored_producer_does_not_establish_value(self):
        capture={'saveTo':[{'name':'actual','source':'text'}]}
        use={'operationValue':'{{actual}}'}
        for steps in [(use,capture), ({**capture,'enabled':False},use),
                      ({**capture,'continueOnFailure':True},use)]:
            with self.subTest(steps=steps):
                self.assertEqual(len(check([case(*steps)])['issues']), 1)

    def test_cross_case_outputs_require_explicit_existing_binding(self):
        rows=[case({'saveTo':[{'name':'createdId','source':'text'}]}),case({'operationValue':'{{createdId}}'})]
        self.assertEqual(check(rows)['issues'][0]['caseIndex'], 2)
        self.assertEqual(check(rows, ['createdId'])['issues'], [])

    def test_declared_gap_can_produce_after_completion(self):
        capture={'locatorValue':None, 'saveTo':[{'name':'actual','source':'value'}],
                 'missingFields':[{'fields':['locatorValue']}], 'continueOnFailure':False}
        self.assertEqual(check([case(capture,{'operationValue':'{{actual}}'})])['issues'], [])


if __name__ == '__main__':
    unittest.main()
