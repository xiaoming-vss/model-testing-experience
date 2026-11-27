"""Prompt runner and GitLab credential stand-ins for executor tests; no collected cases."""

from typing import Any

from testing_agent_ai_worker.models.task import GitlabCredentials, Task


class ScriptedPromptRunner:
    """Prompt runner answering with ``outputs`` in order; the last output keeps repeating."""

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.outputs[min(len(self.calls) - 1, len(self.outputs) - 1)]


class FakeCredentialsFetcher:
    """Credentials of one repository on one connection; raises ``fail`` instead when given."""

    def __init__(
        self, *, fail: Exception | None = None, access_token: str = "secret-token-1"
    ) -> None:
        self.fail = fail
        self.access_token = access_token
        self.calls = 0

    def __call__(self, task: Task) -> list[GitlabCredentials]:
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        return [
            GitlabCredentials(
                connection_id="conn-1",
                base_url="https://gitlab.example.com",
                access_token=self.access_token,
                repository_ids=["repo-1"],
            )
        ]
