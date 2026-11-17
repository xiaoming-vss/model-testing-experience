import pytest
from support.stored_files import (
    files as files,
)
from support.stored_files import (
    longtext_sqlite as longtext_sqlite,
)
from support.stored_files import (
    upload as upload,
)

from testing_agent.models.perf_case import PerfCase
from testing_agent.models.perf_run import PerfRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.perf_case import PerfCaseRepository
from testing_agent.schemas.perf_case import PerfCaseCreate, PerfCaseUpdate
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.perf_case import PerfCaseService
from testing_agent.services.perf_worker import PerfWorkerService

_YAML_WITH_FILE = """
specVersion: "1.0"
case:
  name: csv
  data:
    - name: users
      source: users.csv
      strategy: cycle
  steps:
    - name: login
      method: POST
      path: /login
  load:
    model: vus
    vus: 1
    duration: "1s"
  acceptance:
    source: user_confirmed
    confirmed: true
    criteria:
      http_req_failed: ["rate<0.01"]
"""

_YAML_INLINE = """
specVersion: "1.0"
case:
  name: inline
  data:
    - name: users
      rows:
        - username: u1
          password: p1
  steps:
    - name: login
      method: POST
      path: /login
  load:
    model: vus
    vus: 1
    duration: "1s"
  acceptance:
    source: user_confirmed
    confirmed: true
    criteria:
      http_req_failed: ["rate<0.01"]
"""


@pytest.mark.asyncio
async def test_perf_case_attaches_s3_data_file_and_keeps_it_for_history(files):
    row, _ticket = await upload(
        files,
        content=b"username,password\nu1,p1\nu2,p2\n",
        filename="users.csv",
        purpose="perf_case_data",
    )
    await files.complete("owner", row.file_id)
    service = PerfCaseService(PerfCaseRepository(files.session), files=files)

    case = await service.create(
        "owner",
        "p",
        PerfCaseCreate(
            name="csv-case",
            yaml=_YAML_WITH_FILE,
            data_file_ids=[row.file_id],
        ),
    )
    assert case["dataFiles"][0]["filename"] == "users.csv"
    attached = await files.get(row.file_id)
    assert attached.status == "attached"
    assert attached.resource_type == "perf_case"
    assert attached.resource_id == case["caseId"]

    updated = await service.update(
        "owner",
        case["caseId"],
        PerfCaseUpdate(yaml=_YAML_INLINE, data_file_ids=[]),
    )
    assert updated["dataFiles"] == []
    historical = await files.get(row.file_id)
    assert historical.status == "attached"

    await service.delete("owner", case["caseId"])
    deleting = await files.get(row.file_id)
    assert deleting.status == "deleting"


@pytest.mark.asyncio
async def test_perf_worker_streams_frozen_data_file(files):
    content = b"username,password\nu1,p1\n"
    row, _ticket = await upload(
        files,
        content=content,
        filename="users.csv",
        purpose="perf_case_data",
    )
    await files.complete("owner", row.file_id)
    await files.attach(
        "owner",
        row.file_id,
        "p",
        "perf_case",
        "case-1",
        purpose="perf_case_data",
    )
    stored = await files.get(row.file_id)
    files.session.add(
        PerfCase(
            case_id="case-1",
            project_id="p",
            name="case",
            yaml="",
            created_by="owner",
        )
    )
    files.session.add(
        PerfRun(
            run_id="run-1",
            case_id="case-1",
            project_id="p",
            case_name="case",
            trigger_user_id="owner",
            status="running",
            data_files_json=[
                {
                    "fileId": stored.file_id,
                    "filename": stored.filename,
                    "size": stored.size,
                    "sha256": stored.sha256,
                }
            ],
        )
    )
    files.session.add(
        WorkerTask(
            domain="perf",
            task_id="task-1",
            task_type="perf_run",
            run_id="run-1",
            status="claimed",
            worker_id="worker-1",
        )
    )
    await files.session.commit()

    service = PerfWorkerService(
        files.session,
        files=files,
        credential_cipher=IntegrationCredentialCipher("test-integration-key"),
    )
    streamed, body = await service.data_file("task-1", stored.file_id, "worker-1")
    try:
        assert b"".join(body.iter_chunks(1024)) == content
    finally:
        body.close()
    assert streamed.sha256 == stored.sha256
    assert streamed.filename == "users.csv"
