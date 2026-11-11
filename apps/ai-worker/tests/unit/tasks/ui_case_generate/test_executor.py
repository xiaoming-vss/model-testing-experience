import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from testing_agent_ai_worker.config.models import PiConfig
from testing_agent_ai_worker.models.execution import TaskProgress, TaskStatus
from testing_agent_ai_worker.models.task import RepositoryBinding, Task, TaskPayload
from testing_agent_ai_worker.tasks.ui_case_generate.executor import (
    UiCaseExecutor,
    _validate_ui_cases_yaml,
    _validate_ui_stage_yaml,
)
from testing_agent_ai_worker.tasks.ui_case_generate.repository_source import (
    RepositorySource,
    RepositorySourceError,
)

VALID_YAML = """- name: 登录成功
  enabled: true
  stepsJson:
    - orderNo: 1
      stepName: 打开登录页
      keyword: open
      operationValue: /login
      continueOnFailure: false
      enabled: true
    - orderNo: 2
      stepName: 点击登录
      keyword: click
      locatorType: role
      locatorValue: button
      continueOnFailure: false
      enabled: true
  orderNo: 1
"""


ALL_KEYWORDS_YAML = """- name: 所有关键字字段规则
  enabled: true
  stepsJson:
    - {orderNo: 1, stepName: 打开页面, keyword: open, operationValue: /login, continueOnFailure: false, enabled: true}
    - {orderNo: 2, stepName: 刷新页面, keyword: reload, continueOnFailure: false, enabled: true}
    - {orderNo: 3, stepName: 点击元素, keyword: click, locatorType: css, locatorValue: button, continueOnFailure: false, enabled: true}
    - {orderNo: 4, stepName: 双击元素, keyword: dblclick, locatorType: xpath, locatorValue: //button, continueOnFailure: false, enabled: true}
    - {orderNo: 5, stepName: 输入内容, keyword: input, locatorType: placeholder, locatorValue: 用户名, operationValue: tester, continueOnFailure: false, enabled: true}
    - {orderNo: 6, stepName: 清空内容, keyword: clear, locatorType: label, locatorValue: 用户名, continueOnFailure: false, enabled: true}
    - {orderNo: 7, stepName: 按下回车, keyword: press, locatorType: test_id, locatorValue: username, operationValue: Enter, continueOnFailure: false, enabled: true}
    - {orderNo: 8, stepName: 等待文本, keyword: wait_text, locatorType: testid, locatorValue: result, operationValue: 成功, continueOnFailure: false, enabled: true}
    - {orderNo: 9, stepName: 断言文本, keyword: assert_text, locatorType: text, locatorValue: 成功, operationValue: 成功, comparator: contains, continueOnFailure: false, enabled: true}
    - {orderNo: 10, stepName: 断言可见, keyword: assert_visible, locatorType: role, locatorValue: button, operationValue: '3000', continueOnFailure: false, enabled: true}
    - {orderNo: 11, stepName: 断言隐藏, keyword: assert_hidden, locatorType: text, locatorValue: 转换格式必填, operationValue: '3000', continueOnFailure: false, enabled: true}
    - {orderNo: 12, stepName: 断言地址, keyword: assert_url, operationValue: /projects, comparator: eq, continueOnFailure: false, enabled: true}
    - {orderNo: 13, stepName: 截图, keyword: screenshot, continueOnFailure: false, enabled: true}
    - {orderNo: 14, stepName: 固定等待, keyword: sleep, operationValue: '1000', continueOnFailure: false, enabled: true}
  orderNo: 1
"""


class FakeRepositoryPreparer:
    def __init__(self, run_root: Path, *, error: Exception | None = None) -> None:
        self.run_root = run_root
        self.error = error
        self.credentials: list[object] = []

    def prepare(self, *, task: Task, credentials) -> RepositorySource:
        self.credentials.extend(credentials)
        if self.error is not None:
            raise self.error
        source_root = self.run_root / "source"
        source_root.mkdir(parents=True, exist_ok=True)
        (source_root / "Login.tsx").write_text("export const Login = () => null", encoding="utf-8")
        return RepositorySource(
            binding=task.bindings[0],
            run_root=self.run_root,
            source_root=source_root,
            commit="a1b2c3d",
        )


class UiCaseExecutorTests(unittest.TestCase):
    def _task(self) -> Task:
        return Task(
            task_id="ui-task-1",
            attempt_id="run-1",
            generate_task_id="generate-1",
            task_type="ui_case_generate",
            project_id="project-1",
            sprint_id="sprint-1",
            requirement_id="requirement-1",
            payload=TaskPayload(
                openapi_content="",
                source_content="不得传入技能",
                extra_instruction="覆盖登录流程",
                metadata={
                    "sourceKind": "repository",
                    "sourceRepository": {
                        "bindingId": "binding-1",
                        "repositoryId": "repo-1",
                        "pathWithNamespace": "team/web-admin",
                        "branch": "main",
                        "commit": "a1b2c3d",
                    },
                    "sourceCommit": "a1b2c3d",
                },
            ),
            bindings=[
                RepositoryBinding(
                    bindingId="binding-1",
                    repositoryId="repo-1",
                    pathWithNamespace="team/web-admin",
                    branch="main",
                    headCommit="a1b2c3d",
                    cloneUrl="https://gitlab.example.com/team/web-admin.git",
                )
            ],
            gitlab_credentials_url="/internal/ai-worker/tasks/worker-task-1/gitlab-credentials",
        )

    def _executor(
        self, temp_dir: str, *, preparer=None, skill_runner, error=None
    ) -> UiCaseExecutor:
        run_root = Path(temp_dir) / "run"
        return UiCaseExecutor(
            agent_config=PiConfig(runtime_root=temp_dir),
            repository_source_preparer=preparer or FakeRepositoryPreparer(run_root, error=error),
            credentials_fetcher=lambda task: ["credential"],
            skill_runner=skill_runner,
        )

    def test_execute_prepares_repository_and_returns_skill_yaml(self) -> None:
        captured: dict[str, object] = {}
        progress: list[TaskProgress] = []

        def fake_skill_runner(**kwargs):
            captured.update(kwargs)
            return VALID_YAML

        temp_dir = self.enterContext(tempfile.TemporaryDirectory())
        executor = self._executor(temp_dir, skill_runner=fake_skill_runner)
        result = executor.execute(self._task(), datetime.now().astimezone(), progress.append)

        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertEqual(VALID_YAML, result.output_yaml)
        self.assertEqual("generate-ui-test-case", captured["skill_name"])
        self.assertIn("sourceRoot", result.intermediate_json_text)
        self.assertIn('"sourceKind": "repository"', result.intermediate_json_text)
        self.assertIn('"repositoryId": "repo-1"', result.intermediate_json_text)
        self.assertIn("登录流程", captured["input_text"])
        self.assertIn("始终返回 YAML list", captured["input_text"])
        self.assertNotIn(
            "步骤必须包含 orderNo、stepName、keyword、operationValue", captured["input_text"]
        )
        self.assertNotIn("不得传入技能", captured["input_text"])
        self.assertEqual(1, len(progress))
        self.assertEqual("ui_case_generating", progress[0].current_stage)
        self.assertFalse((Path(temp_dir) / "run").exists())

    def test_execute_fails_when_repository_source_cannot_be_prepared(self) -> None:
        temp_dir = self.enterContext(tempfile.TemporaryDirectory())
        executor = self._executor(
            temp_dir,
            error=RepositorySourceError("UI 用例生成缺少仓库来源绑定"),
            skill_runner=lambda **kwargs: VALID_YAML,
        )
        result = executor.execute(self._task(), datetime.now().astimezone(), lambda _: None)
        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("缺少仓库来源绑定", result.error_message or "")

    def test_execute_never_returns_blank_failure_reason_for_timeout(self) -> None:
        def timed_out(**kwargs):
            raise TimeoutError()

        temp_dir = self.enterContext(tempfile.TemporaryDirectory())
        executor = self._executor(temp_dir, skill_runner=timed_out)
        result = executor.execute(self._task(), datetime.now().astimezone(), lambda _: None)
        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertEqual("UI 用例生成执行失败，未返回错误信息", result.error_message)

    def test_execute_fails_when_skill_output_is_not_a_complete_yaml_case(self) -> None:
        temp_dir = self.enterContext(tempfile.TemporaryDirectory())
        executor = self._executor(temp_dir, skill_runner=lambda **kwargs: "- name: incomplete")
        result = executor.execute(self._task(), datetime.now().astimezone(), lambda _: None)
        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("缺少必填字段", result.error_message or "")

    def test_validator_rejects_single_mapping(self) -> None:
        with self.assertRaisesRegex(ValueError, "顶层必须是 YAML list"):
            _validate_ui_cases_yaml(VALID_YAML.removeprefix("- ").replace("\n  ", "\n"))

    def test_validator_accepts_multiple_cases_with_empty_steps_and_incrementing_order(self) -> None:
        output = """- name: 登录成功
  enabled: true
  stepsJson: []
  orderNo: 1
- name: 用户名为空登录失败
  enabled: true
  stepsJson: []
  orderNo: 2
"""
        self.assertEqual(2, _validate_ui_cases_yaml(output))

    def test_validator_accepts_all_supported_keyword_contracts(self) -> None:
        self.assertEqual(1, _validate_ui_cases_yaml(ALL_KEYWORDS_YAML))
        self.assertEqual(1, _validate_ui_stage_yaml(ALL_KEYWORDS_YAML))

    def test_validator_rejects_invalid_case_and_step_order(self) -> None:
        with self.assertRaisesRegex(ValueError, "跨用例连续递增"):
            _validate_ui_cases_yaml(VALID_YAML.rsplit("orderNo: 1", 1)[0] + "orderNo: 2\n")
        with self.assertRaisesRegex(ValueError, "从 1 开始连续递增"):
            _validate_ui_cases_yaml(VALID_YAML.replace("- orderNo: 1", "- orderNo: 2", 1))

    def test_validator_rejects_unsupported_keyword_and_locator_type(self) -> None:
        with self.assertRaisesRegex(ValueError, "keyword 不受支持"):
            _validate_ui_cases_yaml(
                ALL_KEYWORDS_YAML.replace("keyword: reload", "keyword: wait_visible")
            )
        with self.assertRaisesRegex(ValueError, "locatorType 不受支持"):
            _validate_ui_cases_yaml(
                ALL_KEYWORDS_YAML.replace("locatorType: css", "locatorType: id", 1)
            )

    def test_validator_enforces_locator_rules(self) -> None:
        with self.assertRaisesRegex(ValueError, "locatorType 不受支持或缺失"):
            _validate_ui_cases_yaml(ALL_KEYWORDS_YAML.replace("locatorType: css, ", "", 1))
        with self.assertRaisesRegex(ValueError, "不应包含 locatorType/locatorValue"):
            _validate_ui_cases_yaml(
                ALL_KEYWORDS_YAML.replace(
                    "keyword: reload, ",
                    "keyword: reload, locatorType: css, locatorValue: body, ",
                    1,
                )
            )

    def test_validator_enforces_operation_value_rules(self) -> None:
        with self.assertRaisesRegex(ValueError, "必须包含 operationValue"):
            _validate_ui_cases_yaml(ALL_KEYWORDS_YAML.replace("operationValue: /login, ", "", 1))
        with self.assertRaisesRegex(ValueError, "不应包含 operationValue"):
            _validate_ui_cases_yaml(
                ALL_KEYWORDS_YAML.replace(
                    "keyword: clear, ", "keyword: clear, operationValue: value, ", 1
                )
            )

    def test_validator_enforces_comparator_rules(self) -> None:
        with self.assertRaisesRegex(ValueError, "comparator 必须是 eq 或 contains"):
            _validate_ui_cases_yaml(
                ALL_KEYWORDS_YAML.replace("comparator: contains", "comparator: ne")
            )
        with self.assertRaisesRegex(ValueError, "不应包含 comparator"):
            _validate_ui_cases_yaml(
                ALL_KEYWORDS_YAML.replace("keyword: click, ", "keyword: click, comparator: eq, ", 1)
            )

    def test_validator_requires_step_default_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "缺少必填字段"):
            _validate_ui_cases_yaml(VALID_YAML.replace("      continueOnFailure: false\n", "", 1))
        with self.assertRaisesRegex(ValueError, "缺少必填字段"):
            _validate_ui_cases_yaml(VALID_YAML.replace("      enabled: true\n", "", 1))


if __name__ == "__main__":
    unittest.main()
