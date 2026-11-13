import json
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import UUID

from tests.unit.tasks.functional_case_generate.fixtures import (
    analysis,
    case,
    material,
    traceable_points,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from testing_agent_ai_worker.tasks.api_case_generate.chain import run_chain
from testing_agent_ai_worker.tasks.functional_case_generate.chain import run_functional_chain


class _FakeResult:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeBot:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, str]] = []

    async def __aenter__(self) -> "_FakeBot":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def run(self, message: str, session_key: str) -> _FakeResult:
        self.calls.append({"message": message, "session_key": session_key})
        return _FakeResult(self.outputs[len(self.calls) - 1])


class _FakeFactory:
    def __init__(self, outputs: list[str]) -> None:
        self.last_kwargs: dict[str, str | None] | None = None
        self.bot = _FakeBot(outputs)

    def __call__(self, **kwargs):
        self.last_kwargs = kwargs
        return self.bot


class PiChainRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_chain_uses_skill_names_and_reuses_one_session_key(self) -> None:
        workspace = self.enterContext(tempfile.TemporaryDirectory())
        factory = _FakeFactory(
            [
                '{"login":{"path":"/login","method":"POST"}}',
                "cases:\n  - {name: login, orderNo: 1, method: POST, urlTemplate: /login}",
            ]
        )

        result = await run_chain(
            openapi_text='{"openapi":"3.0.0"}',
            session_key="demo:chain",
            config_path="D:/tmp/config.json",
            workspace=workspace,
            extractor_skill_name="openapi-test-config-extractor",
            generator_skill_name="api-cases-yaml-generator",
            extra_instruction="帮我生成登录、项目增删改查的用例",
            from_config=factory,
        )

        self.assertEqual(result.extractor_output, '{"login":{"path":"/login","method":"POST"}}')
        self.assertEqual(
            result.generator_output,
            "cases:\n  - {name: login, orderNo: 1, method: POST, urlTemplate: /login}",
        )
        self.assertEqual(
            factory.last_kwargs,
            {
                "config_path": "D:/tmp/config.json",
                "workspace": workspace,
            },
        )
        self.assertEqual(
            [call["session_key"] for call in factory.bot.calls],
            ["demo:chain", "demo:chain"],
        )
        self.assertIn(
            "请先加载本地 skill：openapi-test-config-extractor", factory.bot.calls[0]["message"]
        )
        self.assertIn('{"openapi":"3.0.0"}', factory.bot.calls[0]["message"])
        self.assertIn("帮我生成登录、项目增删改查的用例", factory.bot.calls[0]["message"])
        self.assertIn(
            "符合 openapi-test-config-extractor skill 要求的接口配置 JSON",
            factory.bot.calls[0]["message"],
        )
        self.assertIn(
            "不要返回测试用例、meta/config/testCases 结构", factory.bot.calls[0]["message"]
        )
        self.assertIn(
            "请先加载本地 skill：api-cases-yaml-generator", factory.bot.calls[1]["message"]
        )
        self.assertIn(
            '{"login":{"path":"/login","method":"POST"}}', factory.bot.calls[1]["message"]
        )
        self.assertIn("帮我生成登录、项目增删改查的用例", factory.bot.calls[1]["message"])
        self.assertIn(
            "符合 api-cases-yaml-generator skill 要求的 YAML 内容", factory.bot.calls[1]["message"]
        )
        self.assertIn("不要返回 JSON、meta/config/testCases 结构", factory.bot.calls[1]["message"])
        self.assertNotIn("请直接返回 JSON 内容", factory.bot.calls[1]["message"])

    async def test_run_functional_chain_uses_independent_audit_session(self) -> None:
        workspace = self.enterContext(tempfile.TemporaryDirectory())
        ref = Path(workspace) / "skills/mtx-generate-traceable-test-points/references"
        ref.mkdir(parents=True)
        (ref / "design-audit.md").write_text("审查")
        (ref / "independent-review.md").write_text("审查协议")
        value = traceable_points()
        factory = _FakeFactory(
            [
                json.dumps(analysis()),
                json.dumps(value),
                json.dumps({"issues": []}),
                json.dumps({"issues": []}),
                json.dumps({"issues": []}),
                json.dumps({"cases": [{**case("【登录】验证登录"), "case_id": "MODEL-99"}]}),
            ]
        )
        stage_outputs: list[str] = []
        result = await run_functional_chain(
            source_text=json.dumps(material()),
            session_key="demo:functional",
            workspace=workspace,
            analysis_skill_name="mtx-analyze-functional-requirements",
            case_name_skill_name="mtx-generate-traceable-test-points",
            detailed_case_skill_name="mtx-generate-solution-test-cases",
            on_requirement_analysis_result=stage_outputs.append,
            on_case_names_result=stage_outputs.append,
            from_config=factory,
        )
        points_output = json.loads(result.case_names_output)
        self.assertEqual(points_output["reviewStatus"], "independent_reviewed")
        self.assertEqual(len(stage_outputs), 2)
        generated_cases = json.loads(result.detailed_cases_output)["cases"]
        self.assertEqual(UUID(generated_cases[0]["case_id"]).version, 4)
        sessions = [call["session_key"] for call in factory.bot.calls]
        self.assertEqual(sessions[:2], ["demo:functional", "demo:functional"])
        self.assertEqual(len(set(sessions[2:5])), 3)
        self.assertTrue(all(":audit-" in session for session in sessions[2:5]))
        self.assertTrue(sessions[5].startswith("demo:functional:module:"))
        self.assertNotEqual(sessions[5], sessions[0])
        self.assertIn("mtx-generate-traceable-test-points", factory.bot.calls[1]["message"])
        self.assertIn('"module": "登录"', factory.bot.calls[5]["message"])

    async def test_each_stage_invokes_only_its_own_skill(self):
        from testing_agent_ai_worker.models.task import Task, TaskPayload
        from testing_agent_ai_worker.platform.skills import required_skills
        from testing_agent_ai_worker.tasks.api_case_generate.chain import run_api_stage

        extraction = '{"login":{"path":"/login","method":"POST"}}'
        yaml = "cases:\n  - {name: login, orderNo: 1, method: POST, urlTemplate: /login}"
        for stage, name, source, result in [
            ("openapi_extract", "openapi-test-config-extractor", "{}", extraction),
            ("generate", "api-cases-yaml-generator", extraction, yaml),
        ]:
            task = Task(
                task_id="t",
                task_type="api_case_generate",
                checkpoint_enabled=True,
                current_stage=stage,
                payload=TaskPayload(
                    openapi_content="{}", metadata={"apiWorkflowVersion": "api_two_stage/1.0"}
                ),
            )
            self.assertEqual(required_skills(task), [name])
            factory = _FakeFactory([result])
            output = await run_api_stage(
                stage=stage, input_text=source, session_key="run", from_config=factory
            )
            self.assertEqual(output, result)
            self.assertEqual(len(factory.bot.calls), 1)
            self.assertIn(name, factory.bot.calls[0]["message"])
