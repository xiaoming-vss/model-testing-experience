"""UI step variables: import rules, pre-run check and worker resolution."""

from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase
from pydantic import ValidationError

from testing_agent.core.errors import AppError
from testing_agent.domain.ui_variable_check import missing_variables
from testing_agent.domain.ui_variable_template import parse_tokens, validate_step_variables
from testing_agent.models.api_environment import ApiEnvironment
from testing_agent.models.api_environment_var import ApiEnvironmentVar
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.api_environment_var import ApiEnvironmentVarRequest
from testing_agent.schemas.ui_variables import (
    ResolveUiRunVariablesRequest,
    WriteUiRunVariablesRequest,
)
from testing_agent.services.execution_secrets import private_payload
from testing_agent.services.ui_run_variable_records import record_step_variable_usage
from testing_agent.services.ui_run_variables import resolve_run_variables, write_run_variables
from testing_agent.services.ui_test_case import validate_ui_import_payload


def step(**overrides):
    base = {
        "orderNo": 1,
        "stepName": "点击",
        "keyword": "click",
        "locatorType": "xpath",
        "locatorValue": "//button",
        "continueOnFailure": False,
        "enabled": True,
    }
    base.update(overrides)
    return base


def case_payload(value):
    return {"name": "用例", "enabled": True, "orderNo": 1, "stepsJson": [value]}


def test_parse_tokens_skips_builtins_and_returns_modifiers() -> None:
    tokens = parse_tokens("{{$timestamp}} {{name}} {{id|xpath}}")
    assert [(token.name, token.modifier) for token in tokens] == [
        ("name", ""),
        ("id", "xpath"),
    ]


def test_step_variables_reject_data_references() -> None:
    with pytest.raises(ValueError, match="data"):
        validate_step_variables(step(locatorValue="//tr[td={{data.release.id}}]"))


def test_step_variables_reject_bad_modifier() -> None:
    with pytest.raises(ValueError, match="修饰符"):
        validate_step_variables(step(locatorValue="//tr[td={{name|css}}]"))


def test_import_requires_xpath_modifier() -> None:
    with pytest.raises(AppError, match="xpath"):
        validate_ui_import_payload(case_payload(step(locatorValue="//tr[td={{name}}]")))


def test_import_rejects_quoted_xpath_placeholder() -> None:
    with pytest.raises(AppError, match="引号"):
        validate_ui_import_payload(case_payload(step(locatorValue="//tr[td='{{name|xpath}}']")))


def test_import_accepts_css_and_text_variables() -> None:
    result = validate_ui_import_payload(
        case_payload(
            step(
                locatorType="css",
                locatorValue='[data-id="{{recordId}}"]',
            )
        )
    )
    assert result[0]["stepsJson"][0]["locatorValue"] == '[data-id="{{recordId}}"]'


def test_import_accepts_text_locator_variable() -> None:
    result = validate_ui_import_payload(
        case_payload(step(locatorType="text", locatorValue="{{recordName}}"))
    )
    assert result[0]["stepsJson"][0]["locatorValue"] == "{{recordName}}"


def test_import_rejects_role_json_variable() -> None:
    with pytest.raises(AppError, match="role"):
        validate_ui_import_payload(
            case_payload(
                step(
                    locatorType="role",
                    locatorValue='{"role":"button","name":"{{label}}"}',
                )
            )
        )


def test_import_rejects_modifier_in_operation_value() -> None:
    with pytest.raises(AppError, match="修饰符"):
        validate_ui_import_payload(
            case_payload(
                step(
                    keyword="input",
                    locatorValue="#name",
                    operationValue="{{value|xpath}}",
                )
            )
        )


def test_operation_value_accepts_plain_variable() -> None:
    result = validate_ui_import_payload(
        case_payload(
            step(
                keyword="input",
                locatorType="css",
                locatorValue="#name",
                operationValue="{{recordName}}",
            )
        )
    )
    assert result[0]["stepsJson"][0]["operationValue"] == "{{recordName}}"


def test_import_accepts_variable_milliseconds() -> None:
    result = validate_ui_import_payload(
        case_payload(
            step(
                keyword="sleep",
                locatorType=None,
                locatorValue=None,
                operationValue="{{timeout}}",
            )
        )
    )

    assert result[0]["stepsJson"][0]["operationValue"] == "{{timeout}}"


def test_import_rejects_non_numeric_milliseconds() -> None:
    with pytest.raises(AppError, match="毫秒"):
        validate_ui_import_payload(
            case_payload(
                step(
                    keyword="sleep",
                    locatorType=None,
                    locatorValue=None,
                    operationValue="3s",
                )
            )
        )


def test_variable_name_rules_reject_reserved_and_unsafe_names() -> None:
    with pytest.raises(ValidationError):
        ApiEnvironmentVarRequest(varKey="baseUrl")
    with pytest.raises(ValidationError):
        ApiEnvironmentVarRequest(varKey="$timestamp")
    with pytest.raises(ValidationError):
        ApiEnvironmentVarRequest(varKey="bad name")
    assert ApiEnvironmentVarRequest(varKey="版本名称").var_key == "版本名称"


def test_import_accepts_save_to_and_keeps_inheritance_implicit() -> None:
    result = validate_ui_import_payload(
        case_payload(step(saveTo=[{"name": "taskId", "source": "text"}]))
    )

    assert result[0]["stepsJson"][0]["saveTo"] == [
        {
            "name": "taskId",
            "source": "text",
        }
    ]


def test_import_rejects_duplicate_save_to_names() -> None:
    with pytest.raises(AppError, match="重复"):
        validate_ui_import_payload(
            case_payload(
                step(
                    saveTo=[
                        {"name": "taskId", "source": "text"},
                        {"name": "taskId", "source": "value"},
                    ]
                )
            )
        )


def test_import_rejects_variable_in_extraction_locator() -> None:
    with pytest.raises(AppError, match="不支持变量"):
        validate_ui_import_payload(
            case_payload(
                step(
                    saveTo=[
                        {
                            "name": "taskId",
                            "source": "text",
                            "locatorType": "xpath",
                            "locatorValue": "//td[.={{id|xpath}}]",
                        }
                    ]
                )
            )
        )


def test_import_rejects_attribute_on_text_source() -> None:
    with pytest.raises(AppError, match="attribute"):
        validate_ui_import_payload(
            case_payload(step(saveTo=[{"name": "taskId", "source": "text", "attribute": "href"}]))
        )


def test_precheck_registers_save_to_names_in_step_order() -> None:
    cases = [
        {
            "caseId": "c1",
            "name": "用例一",
            "stepsJson": [
                {
                    "orderNo": 1,
                    "stepName": "打开详情",
                    "keyword": "click",
                    "locatorType": "css",
                    "locatorValue": "#go",
                    "enabled": True,
                    "saveTo": [{"name": "taskId", "source": "text"}],
                },
                {
                    "orderNo": 2,
                    "stepName": "输入编号",
                    "keyword": "input",
                    "locatorType": "css",
                    "locatorValue": "#id",
                    "operationValue": "{{taskId}}",
                    "enabled": True,
                },
            ],
        }
    ]

    assert missing_variables(cases, set(), base_url="http://web.example.test") == []


def test_precheck_ignores_save_to_of_disabled_steps() -> None:
    cases = [
        {
            "caseId": "c1",
            "name": "用例一",
            "stepsJson": [
                {
                    "orderNo": 1,
                    "keyword": "click",
                    "locatorType": "css",
                    "locatorValue": "#go",
                    "enabled": False,
                    "saveTo": [{"name": "taskId", "source": "text"}],
                },
                {
                    "orderNo": 2,
                    "keyword": "input",
                    "locatorType": "css",
                    "locatorValue": "#id",
                    "operationValue": "{{taskId}}",
                    "enabled": True,
                },
            ],
        }
    ]

    missing = missing_variables(cases, set(), base_url="http://web.example.test")

    assert [(item["orderNo"], item["name"]) for item in missing] == [(2, "taskId")]


def test_precheck_does_not_carry_save_to_across_cases() -> None:
    cases = [
        {
            "caseId": "c1",
            "name": "用例一",
            "stepsJson": [
                {
                    "orderNo": 1,
                    "keyword": "click",
                    "locatorType": "css",
                    "locatorValue": "#go",
                    "enabled": True,
                    "saveTo": [{"name": "taskId", "source": "text"}],
                }
            ],
        },
        {
            "caseId": "c2",
            "name": "用例二",
            "stepsJson": [
                {
                    "orderNo": 1,
                    "keyword": "input",
                    "locatorType": "css",
                    "locatorValue": "#id",
                    "operationValue": "{{taskId}}",
                    "enabled": True,
                }
            ],
        },
    ]

    missing = missing_variables(cases, set(), base_url="http://web.example.test")

    assert [(item["caseId"], item["name"]) for item in missing] == [("c2", "taskId")]


def test_precheck_reports_missing_by_case_and_field() -> None:
    cases = [
        {
            "caseId": "c1",
            "name": "用例一",
            "stepsJson": [
                {
                    "orderNo": 2,
                    "stepName": "输入",
                    "keyword": "input",
                    "locatorType": "css",
                    "locatorValue": "#name",
                    "operationValue": "{{recordName}}",
                    "enabled": True,
                },
                {
                    "orderNo": 1,
                    "stepName": "打开",
                    "keyword": "open",
                    "operationValue": "{{baseUrl}}/orders/{{recordId}}",
                    "enabled": True,
                },
            ],
        }
    ]

    missing = missing_variables(cases, {"recordName"}, base_url="")

    assert [(item["orderNo"], item["field"], item["name"]) for item in missing] == [
        (1, "operationValue", "baseUrl"),
        (1, "operationValue", "recordId"),
    ]
    assert missing[0]["reason"] == "环境未配置基础地址"


def test_precheck_skips_disabled_steps() -> None:
    cases = [
        {
            "caseId": "c1",
            "name": "用例一",
            "stepsJson": [
                {
                    "orderNo": 1,
                    "keyword": "open",
                    "operationValue": "{{baseUrl}}/orders/{{recordId}}",
                    "enabled": False,
                }
            ],
        }
    ]
    assert missing_variables(cases, set(), base_url="") == []


@pytest.mark.asyncio
async def test_resolve_returns_current_values_case_sensitively(monkeypatch) -> None:
    database = AuthorizationDatabase(environment=True)
    database.sync.add(
        ApiEnvironment(
            environment_id="ui-env",
            project_id="project-1",
            kind="ui",
            name="ui-env",
            base_url="https://web.example.test",
        )
    )
    database.sync.add_all(
        [
            ApiEnvironmentVar(
                env_var_id="v-lower", environment_id="ui-env", var_key="taskId", value="31"
            ),
            ApiEnvironmentVar(
                env_var_id="v-upper", environment_id="ui-env", var_key="TaskId", value="99"
            ),
            ApiEnvironmentVar(
                env_var_id="v-secret",
                environment_id="ui-env",
                var_key="token",
                value="s3",
                is_secret=True,
                secret_user_id="user-1",
            ),
        ]
    )
    database.sync.add(
        WorkerTask(
            domain="ui",
            task_id="task-1",
            task_type="case_debug",
            run_id="run-1",
            worker_id="worker-1",
            status="running",
        )
    )
    database.sync.commit()

    async def fake_authorize(session, task):
        return SimpleNamespace(run=SimpleNamespace(environment_id="ui-env"))

    monkeypatch.setattr(
        "testing_agent.services.ui_run_variables.authorize_execution", fake_authorize
    )

    payload = await resolve_run_variables(
        database,
        "run-1",
        ResolveUiRunVariablesRequest(
            taskId="task-1",
            workerId="worker-1",
            names=["taskId", "TaskId", "baseUrl", "token", "missing"],
        ),
    )

    assert payload["values"] == {
        "taskId": "31",
        "TaskId": "99",
        "baseUrl": "https://web.example.test",
        "token": "s3",
    }
    assert payload["secret_names"] == ["token"]
    assert payload["missing"] == ["missing"]


@pytest.mark.asyncio
async def test_resolve_rejects_task_from_another_run(monkeypatch) -> None:
    database = AuthorizationDatabase(environment=True)

    async def fake_authorize(session, task):
        raise AssertionError("must not authorize a mismatched task")

    monkeypatch.setattr(
        "testing_agent.services.ui_run_variables.authorize_execution", fake_authorize
    )

    with pytest.raises(AppError):
        await resolve_run_variables(
            database,
            "run-2",
            ResolveUiRunVariablesRequest(taskId="missing-task", workerId="worker-1", names=[]),
        )


def _ui_run_database(monkeypatch):
    database = AuthorizationDatabase(environment=True)
    # 写入接口会新建变量，沿用仓库其他用例的同步 Session 作为 add 入口。
    database.add = database.sync.add
    database.sync.add(
        ApiEnvironment(
            environment_id="ui-env",
            project_id="project-1",
            kind="ui",
            name="ui-env",
            base_url="https://web.example.test",
        )
    )
    database.sync.add_all(
        [
            ApiEnvironmentVar(
                env_var_id="v-task", environment_id="ui-env", var_key="taskId", value="20"
            ),
            ApiEnvironmentVar(
                env_var_id="v-secret",
                environment_id="ui-env",
                var_key="token",
                value="old-secret",
                is_secret=True,
                secret_user_id="user-1",
            ),
        ]
    )
    database.sync.add(
        WorkerTask(
            domain="ui",
            task_id="task-1",
            task_type="case_debug",
            run_id="run-1",
            worker_id="worker-1",
            status="running",
        )
    )
    database.sync.commit()

    run = SimpleNamespace(
        environment_id="ui-env",
        used_variables_json=None,
        variable_writes_json=None,
        private_payload=None,
    )

    async def fake_authorize(session, task):
        return SimpleNamespace(run=run)

    monkeypatch.setattr(
        "testing_agent.services.ui_run_variables.authorize_execution", fake_authorize
    )
    return database, run


@pytest.mark.asyncio
async def test_write_creates_updates_and_masks_secret_values(monkeypatch) -> None:
    database, run = _ui_run_database(monkeypatch)

    payload = await write_run_variables(
        database,
        "run-1",
        WriteUiRunVariablesRequest(
            taskId="task-1",
            workerId="worker-1",
            items=[
                {"name": "taskId", "value": "31", "orderNo": 7},
                {"name": "token", "value": "new-secret", "orderNo": 8},
                {"name": "newVar", "value": "x", "orderNo": 9},
            ],
        ),
    )

    assert [(item.name, item.created) for item in payload["results"]] == [
        ("taskId", False),
        ("token", False),
        ("newVar", True),
    ]
    assert payload["results"][0].previous_value == "20"
    assert payload["results"][1].previous_value == "********"

    assert run.variable_writes_json == [
        {
            "name": "taskId",
            "previousValue": "20",
            "value": "31",
            "orderNo": 7,
            "created": False,
        },
        {
            "name": "token",
            "previousValue": "********",
            "value": "********",
            "orderNo": 8,
            "created": False,
        },
        {
            "name": "newVar",
            "previousValue": None,
            "value": "x",
            "orderNo": 9,
            "created": True,
        },
    ]
    private = private_payload(run)
    assert private["variableWrites"][1]["value"] == "new-secret"
    assert private["secrets"] == ["new-secret", "old-secret"]


def test_used_variable_records_mask_secret_values() -> None:
    run = SimpleNamespace(used_variables_json=None, private_payload=None)

    record_step_variable_usage(
        run,
        [
            {
                "orderNo": 3,
                "usedVariables": [
                    {"name": "taskId", "value": "31", "secret": False},
                    {"name": "token", "value": "s3", "secret": True},
                ],
            }
        ],
    )

    assert run.used_variables_json == [
        {"name": "taskId", "value": "31", "orderNo": 3},
        {"name": "token", "value": "********", "masked": True, "orderNo": 3},
    ]
    assert private_payload(run)["secrets"] == ["s3"]
