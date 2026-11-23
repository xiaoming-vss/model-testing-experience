"""Adoption roots come from the selected candidate and live resources."""

from copy import deepcopy
from uuid import uuid4

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation_import_seed import seed_api_or_ui_import_graph

from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.generation_candidates import AiGenerationCandidate
from testing_agent.schemas.generation_candidates import CandidateAdoptRequest
from testing_agent.services.generation_adoption_roots import lock_adoption_roots
from testing_agent.services.generation_import_roots import lock_import_roots


async def test_ui_root_uses_candidate_selection_instead_of_current(database):  # noqa: F811
    sync, _, _ = database
    seed_api_or_ui_import_graph(sync, "ui", "[]")
    sync.add(FunctionTestSuite(suite_id="suite", requirement_id="req", name="module"))
    sync.flush()
    sync.add_all(
        [
            FunctionTestCase(case_id="functional-case", suite_id="suite", title="current case"),
            FunctionTestCase(case_id="other", suite_id="suite", title="candidate case"),
        ]
    )
    candidate = sync.query(AiGenerationCandidate).filter_by(candidate_id="ui-candidate-2").one()
    candidate.current_attempt_id = "ui-attempt"
    snapshot = deepcopy(candidate.source_snapshot_json)
    snapshot["source"]["functionalCases"] = [{"caseId": "other"}]
    candidate.source_snapshot_json = snapshot
    sync.commit()
    session = AsyncSessionAdapter(sync)
    body = CandidateAdoptRequest(
        action="adopt",
        candidate_id="ui-candidate-2",
        expected_candidate_token="ui-token-2",
        expected_attempt_id="ui-attempt",
        expected_current_token="ui-current-2",
        request_id=uuid4(),
    )
    options = dict(requirement_id="req", kind="ui", stage="ui_yaml")
    current_root = await lock_import_roots(
        session, expected_current_token="ui-current-2", **options
    )
    candidate_root = await lock_adoption_roots(session, request=body, **options)
    assert candidate_root != current_root
    sync.query(FunctionTestCase).filter_by(
        case_id="functional-case"
    ).one().title = "changed current"
    sync.flush()
    assert await lock_adoption_roots(session, request=body, **options) == candidate_root
    sync.query(FunctionTestCase).filter_by(case_id="other").one().title = "changed candidate"
    sync.flush()
    assert await lock_adoption_roots(session, request=body, **options) != candidate_root
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await lock_adoption_roots(
            session,
            request=body.model_copy(update={"expected_candidate_token": "stale"}),
            **options,
        )
