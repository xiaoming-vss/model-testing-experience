from types import SimpleNamespace

from testing_agent.domain.ai_execution_format import extra_config
from testing_agent.services.ai_execution import new_attempt, worker_input


class Session:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)


def run():
    return SimpleNamespace(
        run_id="run",
        snapshot_json={},
        config_json={"firstStepOutput": {}},
        result_yaml="",
        trigger_user_id="user",
    )


def test_revision_attempt_snapshot_contains_attachments():
    attempt = new_attempt(
        Session(),
        SimpleNamespace(id="stage"),
        {},
        run(),
        operation="revise",
        actor_id="user",
        llm_connection_id="llm",
        revision_attachments=(
            {"fileId": "image-1", "filename": "login.png", "contentType": "image/png"},
        ),
    )
    assert attempt.input_snapshot_json["config"]["revisionAttachments"] == [
        {"fileId": "image-1", "filename": "login.png", "contentType": "image/png"}
    ]


def test_non_revision_attempt_does_not_persist_attachments():
    attempt = new_attempt(
        Session(),
        SimpleNamespace(id="stage"),
        {},
        run(),
        operation="generate",
        actor_id="user",
        llm_connection_id="llm",
        revision_attachments=(
            {"fileId": "image-1", "filename": "login.png", "contentType": "image/png"},
        ),
    )
    assert "revisionAttachments" not in attempt.input_snapshot_json["config"]


def test_revision_attachments_stay_out_of_effective_config():
    assert "revisionAttachments" not in extra_config(
        {
            "firstStepOutput": {},
            "revisionAttachments": [
                {"fileId": "image-1", "filename": "login.png", "contentType": "image/png"}
            ],
        }
    )


def test_worker_input_preserves_attempt_attachments():
    snapshot = {
        "source": {},
        "config": {
            "revisionAttachments": [
                {"fileId": "image-1", "filename": "login.png", "contentType": "image/png"}
            ]
        },
        "currentOutput": "",
    }
    attempt = SimpleNamespace(
        input_snapshot_json=snapshot,
        revision_instruction="按截图补充",
    )
    _, config = worker_input(
        SimpleNamespace(scalar=lambda _query: attempt),
        run(),
        SimpleNamespace(task_id="worker"),
    )
    assert config["revisionAttachments"] == [
        {"fileId": "image-1", "filename": "login.png", "contentType": "image/png"}
    ]
    assert config["revisionInstruction"] == "按截图补充"
