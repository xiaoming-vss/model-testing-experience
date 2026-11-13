import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from coverage_workbench import initialize, bind, check, refresh

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.design = {'cases': [{'caseId': name, 'name': name, 'coverage': 'full', 'steps': [
            {'actions': [], 'expectations': [{'expectationId':'E1', 'status':'included',
             'target':'result total','value':'2','sourceQuote':'Exactly two records'},
             {'expectationId':'E2','status':'excluded','target':'unbounded pages','value':None}]}]}
            for name in ('one', 'two')]}
        self.rows = [{'name':name, 'enabled':True, 'stepsJson':[{'orderNo':1,'stepName':'Check',
                      'keyword':'assert_visible','locatorValue':'//table[count(tbody/tr)=2]','enabled':True}]}
                     for name in ('one','two')]

    def completed(self):
        book=initialize(self.design,self.rows)
        for case in book['cases']:
            target=case['targets'][0];target['verdict']='supported'
            target['clauses']=[{'claim':'Two records','object':'result body rows',
                'valueSource':'literal design value 2','scope':'prepared two-row result',
                'timing':'after query','counterexample':'one result row',
                'rejection':'count(tbody/tr)=2 is false',
                'refs':[{'orderNo':1,'field':'locatorValue'}]}]
        for case_id in ('one', 'two'):
            book=bind(self.design,self.rows,book,case_id)
        return book

    def test_current_fields_bound_and_all_targets_closed(self):
        book=self.completed();result=check(self.design,self.rows,book)
        self.assertEqual(result['verdictCounts']['supported'],2)
        self.assertEqual(book['cases'][0]['targets'][0]['clauses'][0]['refs'][0]['value'],self.rows[0]['stepsJson'][0]['locatorValue'])
        self.assertEqual(len(book['cases'][0]['targets']),1)

    def test_pending_and_old_generic_claim_cannot_close_audit(self):
        for book in [initialize(self.design,self.rows),self.completed()]:
            book['cases'][0]['targets'][0]['clauses']=[]
            with self.assertRaises(ValueError):check(self.design,self.rows,book)

    def test_candidate_change_invalidates_evidence_and_refresh_only_changed_case(self):
        book=self.completed();self.rows[0]['stepsJson'][0]['locatorValue']='//table[count(tbody/tr)=1]'
        with self.assertRaises(ValueError):check(self.design,self.rows,book)
        with self.assertRaises(ValueError):bind(self.design,self.rows,book,'one')
        fresh,changed=refresh(self.design,self.rows,book)
        self.assertEqual(changed,['one']);self.assertEqual(fresh['cases'][1],book['cases'][1])
        self.assertEqual(fresh['cases'][0]['targets'][0]['verdict'],'pending')

    def test_field_and_source_cannot_be_fabricated(self):
        book=self.completed();book['cases'][0]['targets'][0]['clauses'][0]['refs'][0]['value']='//body'
        with self.assertRaises(ValueError):check(self.design,self.rows,book)
        book=self.completed();book['cases'][0]['targets'][0]['source']['value']='1'
        with self.assertRaises(ValueError):check(self.design,self.rows,book)
        book=self.completed();book['cases'][0]['targets'][0]['clauses'][0]['refs'][0]['field']='stepName'
        with self.assertRaises(ValueError):bind(self.design,self.rows,book,'one')

    def test_missing_locator_requires_actual_gap_contract(self):
        self.rows[0]['stepsJson'][0].update(locatorValue=None,missingFields=[{'fields':['locatorValue'],'reason':'Unknown body locator'}])
        book=self.completed()
        with self.assertRaises(ValueError):check(self.design,self.rows,book)
        t=book['cases'][0]['targets'][0];t['verdict']='fillable_gap'
        with self.assertRaises(ValueError):check(self.design,self.rows,book)
        t['clauses'][0]['refs'].append({'orderNo':1,'field':'missingFields'})
        book=bind(self.design,self.rows,book,'one');self.assertEqual(check(self.design,self.rows,book)['verdictCounts']['fillable_gap'],1)

    def test_real_dependency_needs_no_fabricated_step(self):
        book=self.completed();t=book['cases'][0]['targets'][0]
        t.update(verdict='design_dependency',clauses=[],reason='Target requires unsupported conditional exit')
        self.assertEqual(check(self.design,self.rows,book)['unresolvedTargets'],['one/E1'])

    def test_observe_action_requires_value_channel_counterexample(self):
        step=self.design['cases'][0]['steps'][0]
        step['actions']=[{'actionId':'A1','status':'included','operation':'observe',
                          'target':'live input value','value':'empty','sourceQuote':'Observe empty input'}]
        step['expectations']=[]
        book=self.completed();del book['cases'][0]['targets'][0]['clauses'][0]['counterexample']
        with self.assertRaises(ValueError):check(self.design,self.rows,book)

    def test_counterexample_is_required_but_not_claimed_as_automatically_true(self):
        book=self.completed();del book['cases'][0]['targets'][0]['clauses'][0]['counterexample']
        with self.assertRaises(ValueError):check(self.design,self.rows,book)
        self.assertIn('semantic truth',check(self.design,self.rows,self.completed())['scope'])

if __name__=='__main__':unittest.main()
