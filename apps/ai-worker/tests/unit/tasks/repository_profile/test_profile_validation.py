import unittest

from testing_agent_ai_worker.tasks.repository_profile.profile_validation import schema_errors


class ProfileSchemaTests(unittest.TestCase):
    def test_schema_accepts_fixed_profile_shape(self):
        self.assertEqual(
            [],
            schema_errors(
                {
                    "repositories": [],
                    "overallSummary": "当前需求主要涉及前端",
                }
            ),
        )

    def test_schema_reports_extra_fields_and_invalid_role(self):
        errors = schema_errors(
            {
                "repositories": [
                    {
                        "repositoryId": "repo-1",
                        "pathWithNamespace": "team/repo",
                        "role": "mobile",
                        "responsibilitySummary": "客户端",
                        "techStack": [],
                        "keyPaths": [],
                        "confidence": 0.5,
                        "evidence": ["package.json"],
                        "extra": True,
                    }
                ],
                "overallSummary": "总结",
            }
        )
        self.assertTrue(any(error["code"] == "additionalProperties" for error in errors))
        self.assertTrue(any(error["code"] == "enum" for error in errors))
