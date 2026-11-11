"""Validate actual supported extraction and unsafe template boundaries."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from validate_ui_case import validate_step

class EnvironmentContract(unittest.TestCase):
    def validate(self, step):
        return validate_step({'orderNo':1,'stepName':'观察','enabled':True,'continueOnFailure':False,**step},1,'实验','',False)
    def test_environment_navigation(self):
        self.validate({'keyword':'open','operationValue':'{{baseUrl}}/projects/{{项目ID}}'})
    def test_inherited_variable_locator(self):
        self.validate({'keyword':'assert_visible','locatorType':'xpath','locatorValue':'//tr[td={{项目名称|xpath}}]/td[1]','operationValue':1000,'saveTo':[{'name':'项目ID','source':'text'}]})
    def test_attribute_and_input_extraction(self):
        self.validate({'keyword':'input','locatorType':'test_id','locatorValue':'name','operationValue':'{{创建名称}}','saveTo':[{'name':'实际输入','source':'value'},{'name':'输入标识','source':'attribute','attribute':'id'}]})
    def test_unsafe_contracts_rejected(self):
        base={'keyword':'assert_visible','locatorType':'xpath','locatorValue':'//tr[td={{项目名称|xpath}}]','operationValue':1000}
        variants=[
            {'locatorValue':"//tr[td='{{项目名称|xpath}}']"},
            {'locatorValue':'//tr[td={{项目名称}}]'},
            {'saveTo':[{'name':'项目ID','source':'text','locatorType':'xpath','locatorValue':'//tr[td={{项目名称|xpath}}]'}]},
            {'saveTo':[{'name':'baseUrl','source':'text'}]},
            {'saveTo':[{'name':'项目ID','source':'attribute'}]},
            {'saveTo':[{'name':'项目ID','source':'url','locatorType':'css','locatorValue':'a'}]},
            {'saveTo':[{'name':'项目ID','source':'text','regex':'(.*)'}]},
        ]
        for variant in variants:
            with self.subTest(variant=variant),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                self.validate({**base,**variant})

if __name__=='__main__': unittest.main()
