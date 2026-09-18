from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from testing_agent.core.errors import ErrSprintScheduleInvalid
from testing_agent.models.sprint import Sprint
from testing_agent.schemas.sprint import CreateSprintRequest, UpdateSprintRequest
from testing_agent.services.sprint import SprintService, derive_sprint_status, dump_sprint

START = datetime(2026, 9, 4, 1, tzinfo=UTC)
END = datetime(2026, 9, 11, 1, tzinfo=UTC)


def make_sprint(**overrides):
    values = {
        "sprint_id": "sprint-1",
        "project_id": "project-1",
        "name": "Sprint 1",
        "description": "",
        "start_time": START,
        "end_time": END,
        "created_at": START,
        "updated_at": START,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (START - timedelta(microseconds=1), "planned"),
        (START, "running"),
        (END - timedelta(microseconds=1), "running"),
        (END, "completed"),
        (END + timedelta(days=1), "completed"),
    ],
)
def test_derive_sprint_status_at_time_boundaries(now, expected):
    assert derive_sprint_status(START, END, now=now) == expected


def test_derive_sprint_status_treats_timezone_less_database_values_as_utc():
    assert (
        derive_sprint_status(
            START.replace(tzinfo=None),
            END.replace(tzinfo=None),
            now=END,
        )
        == "completed"
    )


def test_extending_end_time_recomputes_completed_sprint_as_running():
    now = END + timedelta(hours=1)
    assert derive_sprint_status(START, END, now=now) == "completed"
    assert derive_sprint_status(START, END + timedelta(days=1), now=now) == "running"


def test_dump_sprint_returns_derived_status_and_explicit_utc_times():
    result = dump_sprint(
        make_sprint(start_time=START.replace(tzinfo=None), end_time=END.replace(tzinfo=None)),
        now=START,
    )

    assert result["status"] == "running"
    assert result["startTime"] == "2026-09-04T01:00:00Z"
    assert result["endTime"] == "2026-09-11T01:00:00Z"


def test_create_sprint_requires_complete_ordered_timezone_aware_schedule():
    with pytest.raises(ValidationError):
        CreateSprintRequest(name="Sprint", startTime="2026-09-04T09:00:00+08:00")

    with pytest.raises(ValidationError, match="timezone"):
        CreateSprintRequest(
            name="Sprint",
            startTime="2026-09-04T09:00:00",
            endTime="2026-09-11T09:00:00",
        )

    with pytest.raises(ValidationError, match="later"):
        CreateSprintRequest(
            name="Sprint",
            startTime="2026-09-11T09:00:00+08:00",
            endTime="2026-09-04T09:00:00+08:00",
        )


def test_create_sprint_normalizes_schedule_to_utc():
    body = CreateSprintRequest(
        name="Sprint",
        startTime="2026-09-04T09:00:00+08:00",
        endTime="2026-09-11T09:00:00+08:00",
    )

    assert body.start_time == START
    assert body.end_time == END


def test_update_sprint_rejects_status_and_null_schedule_times():
    with pytest.raises(ValidationError, match="status"):
        CreateSprintRequest(
            name="Sprint",
            startTime="2026-09-04T09:00:00+08:00",
            endTime="2026-09-11T09:00:00+08:00",
            status="running",
        )

    with pytest.raises(ValidationError, match="status"):
        UpdateSprintRequest(status="completed")

    with pytest.raises(ValidationError, match="cannot be null"):
        UpdateSprintRequest(endTime=None)


class FakeSprintRepository:
    def __init__(self, sprint):
        self.sprint = sprint

    async def get_active_by_id(self, _sprint_id):
        return self.sprint

    async def commit(self):
        raise AssertionError("invalid schedule must not be committed")


class FakeProjectService:
    async def get_accessible_entity(self, _user_id, _project_id, *, action="read"):
        return object()


async def test_update_sprint_validates_partial_schedule_against_stored_time():
    service = SprintService(FakeSprintRepository(make_sprint()), FakeProjectService())
    body = UpdateSprintRequest(endTime="2026-09-01T00:00:00Z")

    with pytest.raises(type(ErrSprintScheduleInvalid)) as exc_info:
        await service.update("user-1", "sprint-1", body)

    assert exc_info.value.code == ErrSprintScheduleInvalid.code


def test_sprint_model_has_mandatory_schedule_and_no_persisted_status():
    assert "status" not in Sprint.__table__.columns
    assert Sprint.__table__.columns.start_time.nullable is False
    assert Sprint.__table__.columns.end_time.nullable is False
