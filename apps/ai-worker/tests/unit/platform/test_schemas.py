import unittest

from testing_agent_ai_worker.platform.schemas import (
    PlatformClaimTask,
    PlatformGitlabCredentials,
    PlatformGitlabCredentialsResponse,
    PlatformLlmCredentials,
    PlatformResponseModel,
    PlatformSnapshotResponse,
    PlatformSnapshotRun,
)


class PlatformResponseCompatibilityTests(unittest.TestCase):
    def test_claim_task_ignores_unknown_control_plane_fields(self):
        task = PlatformClaimTask.model_validate(
            {
                "taskId": "task-1",
                "attemptId": "attempt-1",
                "taskType": "functional_case_generate",
                "newRolloutFlag": True,
            }
        )

        self.assertEqual("task-1", task.task_id)
        self.assertEqual("attempt-1", task.attempt_id)
        self.assertFalse(hasattr(task, "newRolloutFlag"))
        self.assertNotIn("newRolloutFlag", task.model_dump(by_alias=True))

    def test_snapshot_ignores_unknown_fields_at_both_levels(self):
        snapshot = PlatformSnapshotResponse.model_validate(
            {
                "taskType": "code_risk_analysis",
                "futureTopLevelField": {"enabled": True},
                "run": {
                    "taskId": "task-1",
                    "attemptId": "attempt-1",
                    "taskType": "code_risk_analysis",
                    "futureRunField": [1, 2, 3],
                },
            }
        )

        self.assertEqual("task-1", snapshot.run.task_id)
        self.assertEqual("attempt-1", snapshot.run.attempt_id)
        self.assertNotIn("futureTopLevelField", snapshot.model_dump(by_alias=True))
        self.assertNotIn("futureRunField", snapshot.run.model_dump(by_alias=True))

    def test_credential_responses_allow_extension(self):
        response = PlatformGitlabCredentialsResponse.model_validate(
            {
                "taskId": "task-1",
                "credentials": [
                    {
                        "connectionId": "connection-1",
                        "baseUrl": "https://gitlab.example",
                        "accessToken": "secret",
                        "repositoryIds": ["repo-1"],
                        "futureCredentialField": True,
                    }
                ],
                "futureResponseField": "ignored",
            }
        )

        self.assertEqual("task-1", response.task_id)
        self.assertEqual("connection-1", response.credentials[0].connection_id)
        self.assertNotIn("futureResponseField", response.model_dump(by_alias=True))
        self.assertNotIn("futureCredentialField", response.credentials[0].model_dump())

    def test_platform_response_models_share_explicit_extension_policy(self):
        response_models = (
            PlatformClaimTask,
            PlatformLlmCredentials,
            PlatformSnapshotRun,
            PlatformSnapshotResponse,
            PlatformGitlabCredentials,
            PlatformGitlabCredentialsResponse,
        )

        for model in response_models:
            with self.subTest(model=model.__name__):
                self.assertTrue(issubclass(model, PlatformResponseModel))
                self.assertEqual("ignore", model.model_config["extra"])


if __name__ == "__main__":
    unittest.main()
