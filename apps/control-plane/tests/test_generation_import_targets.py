"""Import previews bind opaque fingerprints to locked formal target state."""

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401

from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.api_extract_rule import ApiExtractRule
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.repositories.generation_import_targets import lock_import_target_state


def seed(sync):
    sync.add_all(
        [
            FunctionTestSuite(suite_id="f", requirement_id="req", name="module"),
            FunctionTestSuite(suite_id="other-f", requirement_id="other", name="other"),
            ApiCollection(collection_id="api", project_id="p", requirement_id="req", name="api"),
            ApiCollection(
                collection_id="other-api", project_id="p", requirement_id="other", name="other"
            ),
            UiTestSuite(suite_id="ui", project_id="p", requirement_id="req", name="ui"),
        ]
    )
    sync.flush()
    sync.add_all(
        [
            FunctionTestCase(
                case_id="fcase", suite_id="f", title="secret test title", module="module"
            ),
            FunctionTestCase(case_id="other-fcase", suite_id="other-f", title="other"),
            ApiCase(
                case_id="acase",
                collection_id="api",
                name="api test",
                method="GET",
                url_template="/v1",
            ),
            UiTestCase(case_id="ucase", suite_id="ui", name="ui test", steps_json=[]),
        ]
    )
    sync.flush()
    sync.add_all(
        [
            ApiExtractRule(
                extract_rule_id="extract",
                case_id="acase",
                name="extract",
                source="body",
                source_expr="$.a",
                var_key="a",
            ),
            ApiAssertRule(
                assert_rule_id="assert",
                case_id="acase",
                name="assert",
                assert_source="body",
                target_expr="$.a",
                comparator="eq",
                expected_value="1",
            ),
        ]
    )
    sync.commit()


async def state(sync, kind, target="", requirement="req"):
    return await lock_import_target_state(
        AsyncSessionAdapter(sync), requirement_id=requirement, kind=kind, target_id=target
    )


async def test_function_target_covers_all_requirement_suites_but_not_other_requirements(database):  # noqa: F811
    sync, _, _ = database
    seed(sync)
    initial = await state(sync, "function")
    assert "secret test title" not in repr(initial) and len(initial.fingerprint) == 64
    sync.query(FunctionTestCase).filter_by(case_id="other-fcase").one().title = "changed other"
    sync.flush()
    assert (await state(sync, "function")).fingerprint == initial.fingerprint
    sync.query(FunctionTestCase).filter_by(case_id="fcase").one().title = "changed"
    sync.flush()
    assert (await state(sync, "function")).fingerprint != initial.fingerprint
    with pytest.raises(SourceClosureError, match="source_conflict"):
        await state(sync, "function", "f")


async def test_api_fingerprint_includes_assertions_and_extraction_rules(database):  # noqa: F811
    sync, _, _ = database
    seed(sync)
    first = await state(sync, "api", "api")
    sync.query(ApiExtractRule).filter_by(extract_rule_id="extract").one().source_expr = "$.changed"
    sync.flush()
    second = await state(sync, "api", "api")
    assert first.fingerprint != second.fingerprint
    sync.query(ApiAssertRule).filter_by(assert_rule_id="assert").one().expected_value = "2"
    sync.flush()
    assert (await state(sync, "api", "api")).fingerprint != second.fingerprint
    with pytest.raises(SourceClosureError, match="source_unknown"):
        await state(sync, "api", "other-api")


async def test_ui_target_detects_case_changes_and_missing_targets(database):  # noqa: F811
    sync, _, _ = database
    seed(sync)
    first = await state(sync, "ui", "ui")
    case = sync.query(UiTestCase).filter_by(case_id="ucase").one()
    case.steps_json = [{"action": "click", "target": "button"}]
    sync.flush()
    assert (await state(sync, "ui", "ui")).fingerprint != first.fingerprint
    with pytest.raises(SourceClosureError, match="source_unknown"):
        await state(sync, "ui", "missing")
