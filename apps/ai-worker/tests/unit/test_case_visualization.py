import asyncio
import copy
import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from testing_agent_ai_worker.agent import create_agent
from testing_agent_ai_worker.agent.base import AgentResult
from testing_agent_ai_worker.agent.nanobot import NanobotAgent
from testing_agent_ai_worker.agent.paths import resolve_task_workspace
from testing_agent_ai_worker.config.models import PiConfig
from testing_agent_ai_worker.models.execution import TaskStatus
from testing_agent_ai_worker.models.task import Task, TaskPayload
from testing_agent_ai_worker.platform.skills import required_skills
from testing_agent_ai_worker.tasks.case_visualization.contract import SKILL_NAME, TASK_TYPE
from testing_agent_ai_worker.tasks.case_visualization.executor import CaseVisualizationExecutor

ROOT = Path(__file__).resolve().parents[4]
SKILL = ROOT / "apps/control-plane/default-skills/mtx-analyze-case-visualization"
EXAMPLES = json.loads((SKILL / "references/examples.json").read_text())


class VisualizationExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = PiConfig(runtime_root=self.temp.name)
        self.task = Task(
            task_id="queue",
            attempt_id="attempt",
            generate_task_id="task",
            task_type=TASK_TYPE,
            payload=TaskPayload(openapi_content=""),
            config_json=json.dumps({"visualizationInput": EXAMPLES[0]["input"]}),
        )
        workspace = resolve_task_workspace(self.config, self.task)
        shutil.copytree(SKILL, workspace / "skills" / SKILL_NAME)

    def execute(self, output):
        with patch(
            "testing_agent_ai_worker.tasks.case_visualization.executor.task_config_path"
        ) as context:
            context.return_value.__enter__.return_value = "config"
            calls = []

            def runner(**kwargs):
                calls.append(kwargs)
                return AgentResult(content=json.dumps(output), finish_reason="stop")

            executor = CaseVisualizationExecutor(agent_config=self.config, prompt_runner=runner)
            result = executor.execute(self.task, datetime.now(UTC), lambda _: None)
        return result, calls

    def test_valid_output_uses_no_tools_and_one_call(self):
        result, calls = self.execute(EXAMPLES[0]["output"])
        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["tools"], ())
        self.assertEqual(json.loads(result.output_yaml)["status"], "ready")
        self.assertEqual(
            len(json.loads(result.result_summary_json)["visualization"]["skillDigest"]), 64
        )
        self.assertEqual(required_skills(self.task), [SKILL_NAME])

    def test_invalid_output_fails_without_semantic_retry(self):
        output = copy.deepcopy(EXAMPLES[0]["output"])
        output["executionEntryId"] = "wrong"
        result, calls = self.execute(output)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(len(calls), 1)
        self.assertFalse(result.output_yaml)

    def test_unchanged_state_with_distinct_ids_reports_safe_reason(self):
        example = copy.deepcopy(EXAMPLES[2])
        self.task.config_json = json.dumps({"visualizationInput": example["input"]})
        output = example["output"]
        visual = output["visuals"][0]
        previous = visual["data"]["beforeEntityId"]
        new_state = copy.deepcopy(next(e for e in output["entities"] if e["id"] == previous))
        new_state["id"] = "different-after"
        output["entities"].append(new_state)
        visual["entityIds"].append(new_state["id"])
        visual["data"]["afterEntityId"] = new_state["id"]
        result, calls = self.execute(output)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(
            result.error_message, "图解结果校验失败：状态保持时前后状态必须使用同一实体，请重新生成"
        )
        self.assertEqual(len(calls), 1)

    def test_changed_state_requires_distinct_known_states(self):
        example = copy.deepcopy(EXAMPLES[2])
        self.task.config_json = json.dumps({"visualizationInput": example["input"]})
        output = example["output"]
        visual = output["visuals"][0]
        visual["data"]["change"] = "changed"
        visual["data"]["afterEntityId"] = visual["data"]["beforeEntityId"]
        result, calls = self.execute(output)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error_message, "图解输入、技能或输出校验失败，请重试或使用文字模式")
        self.assertEqual(len(calls), 1)

    def test_state_visual_requires_state_entities(self):
        example = copy.deepcopy(EXAMPLES[2])
        self.task.config_json = json.dumps({"visualizationInput": example["input"]})
        output = example["output"]
        visual = output["visuals"][0]
        action = next(e for e in output["entities"] if e["kind"] == "action")
        visual["data"]["change"] = "unknown"
        visual["data"]["beforeEntityId"] = action["id"]
        visual["data"]["afterEntityId"] = None
        result, _ = self.execute(output)
        self.assertEqual(result.status, TaskStatus.FAILED)

    def test_negative_quantity_constraint_is_rejected(self):
        example = copy.deepcopy(EXAMPLES[3])
        self.task.config_json = json.dumps({"visualizationInput": example["input"]})
        output = example["output"]
        visual = output["visuals"][0]
        visual["data"]["totalConstraint"]["value"] = -1
        result, _ = self.execute(output)
        self.assertEqual(result.status, TaskStatus.FAILED)

    def test_empty_skill_never_calls_model(self):
        skill = resolve_task_workspace(self.config, self.task) / "skills" / SKILL_NAME
        (skill / "SKILL.md").write_text("", encoding="utf-8")
        result, calls = self.execute(EXAMPLES[0]["output"])
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertFalse(calls)

    def test_unsupported_is_success_not_execution_failure(self):
        output = copy.deepcopy(EXAMPLES[0]["output"])
        output["status"] = "unsupported"
        output["visuals"] = []
        output["limitations"] = [{"reason": "不能可靠表达", "sourceIds": ["e0"]}]
        result, _ = self.execute(output)
        self.assertEqual(result.status, TaskStatus.SUCCESS)

    def test_missing_skill_never_calls_model(self):
        shutil.rmtree(resolve_task_workspace(self.config, self.task) / "skills")
        result, calls = self.execute(EXAMPLES[0]["output"])
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertFalse(calls)

    def test_input_hash_tamper_never_calls_model(self):
        config = json.loads(self.task.config_json)
        config["visualizationInput"]["content"]["steps"][0]["action"] = "changed"
        self.task.config_json = json.dumps(config)
        result, calls = self.execute(EXAMPLES[0]["output"])
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertFalse(calls)


class NoToolsTests(unittest.TestCase):
    def test_nanobot_removes_tools_after_startup(self):
        sdk = _FakeSdk()

        async def run():
            async with NanobotAgent(sdk, no_tools=True) as agent:
                self.assertIsNone(sdk._mcp_provider)
                self.assertEqual(sdk._loop.tools.tool_names, [])
                await agent.run("prompt", session_key="session")

        asyncio.run(run())
        self.assertEqual(sdk.run_calls[0]["ephemeral"], True)

    def test_nanobot_fails_closed_when_tools_registered_during_run(self):
        sdk = _FakeSdk(register_during_run=True)

        async def run():
            async with NanobotAgent(sdk, no_tools=True) as agent:
                with self.assertRaises(RuntimeError):
                    await agent.run("prompt", session_key="session")

        asyncio.run(run())

    def test_nanobot_fails_closed_without_mcp_provider(self):
        class SDK:
            _loop = type("Loop", (), {"tools": type("Registry", (), {"tool_names": []})()})()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        async def run():
            with self.assertRaises(RuntimeError):
                async with NanobotAgent(SDK(), no_tools=True):
                    pass

        asyncio.run(run())

    def test_create_agent_treats_empty_tool_selection_as_no_tools(self):
        with patch.object(NanobotAgent, "from_config") as from_config:
            create_agent(config_path="config.json", workspace="workspace", tools=[])
        from_config.assert_called_once_with(
            config_path="config.json", workspace="workspace", no_tools=True
        )


class _FakeSdk:
    def __init__(self, *, register_during_run: bool = False) -> None:
        self._loop = type("Loop", (), {"tools": _FakeRegistry()})()
        self._mcp_provider = object()
        self.run_calls: list[dict] = []
        self._register_during_run = register_during_run

    async def __aenter__(self):
        self._loop.tools.tool_names.append("mcp_example")
        return self

    async def __aexit__(self, *args):
        return False

    async def run(self, message, *, session_key, media=None, **kwargs):
        self.run_calls.append({"message": message, "media": media, **kwargs})
        if self._register_during_run:
            self._loop.tools.tool_names.append("late_tool")
        return type(
            "Result",
            (),
            {"content": "{}", "stop_reason": "stop", "metadata": {}, "usage": None},
        )()


class _FakeRegistry:
    def __init__(self) -> None:
        self.tool_names: list[str] = []

    def unregister(self, name):
        self.tool_names.remove(name)
