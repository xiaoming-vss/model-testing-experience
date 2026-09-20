import json
import tempfile
import unittest
from datetime import datetime

from testing_agent_ai_worker.config.models import NanobotConfig
from testing_agent_ai_worker.models.execution import TaskStatus
from testing_agent_ai_worker.models.task import Task, TaskPayload
from testing_agent_ai_worker.tasks.functional_case_generate.executor import (
    FunctionalCaseNanobotExecutor,
)
from testing_agent_ai_worker.tasks.functional_case_generate.validation import (
    generate_validated,
    validate_output,
)


def relation_output():
    """关系输出协议 2.0 的完整样例：主骨 + 分支延续 + 共同后续 + 独立用例。"""

    return {
        "schema_version": "2.0",
        "main_paths": [
            {"path_id": "P01", "case_ids": ["C001", "C002", "C003"]},
        ],
        "edges": [
            {"edge_id": "E01", "from_case_id": "C001", "to_case_id": "C002", "relation_type": "next", "order": 1},
            {"edge_id": "E02", "from_case_id": "C002", "to_case_id": "C003", "relation_type": "next", "order": 1},
            {"edge_id": "E03", "from_case_id": "C002", "to_case_id": "C004", "relation_type": "branch", "order": 2},
            {"edge_id": "E04", "from_case_id": "C004", "to_case_id": "C005", "relation_type": "next", "order": 1},
            {"edge_id": "E05", "from_case_id": "C006", "to_case_id": "C003", "relation_type": "next", "order": 1},
        ],
    }


LEGACY_OUTPUT = {
    "schema_version": "1.0",
    "flows": [],
    "links": [{"case_id": "C001", "flow_links": []}],
}

CASE_IDS = [f"C00{i}" for i in range(1, 8)]


def edit(data, change):
    merged = json.loads(json.dumps(data))
    change(merged)
    return merged


class RelationContractTests(unittest.TestCase):
    def test_protocol_sample_round_trips(self):
        output = relation_output()
        canonical = json.loads(validate_output("relation_analysis", json.dumps(output)))
        self.assertEqual(canonical, output)
        self.assertIn("from_case_id", canonical["edges"][0])

    def test_empty_outputs_are_valid(self):
        empty = {"schema_version": "2.0", "main_paths": [], "edges": []}
        self.assertEqual(json.loads(validate_output("relation_analysis", json.dumps(empty))), empty)
        self.assertEqual(
            json.loads(
                validate_output("relation_analysis", json.dumps(empty), expected_case_ids=CASE_IDS)
            ),
            empty,
        )

    def test_schema_version_is_fixed(self):
        data = edit(relation_output(), lambda d: d.update(schema_version="2.1"))
        with self.assertRaises(ValueError):
            validate_output("relation_analysis", json.dumps(data))

    def test_legacy_flow_link_protocol_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_output("relation_analysis", json.dumps(LEGACY_OUTPUT))

    def test_references_must_come_from_input_cases(self):
        # C007 未被任何主骨或连线引用仍合法：未出现表示独立用例。
        validate_output("relation_analysis", json.dumps(relation_output()), expected_case_ids=CASE_IDS)

        def unknown_edge_target(data):
            data["edges"][3]["to_case_id"] = "C999"

        def unknown_edge_source(data):
            data["edges"][4]["from_case_id"] = "C999"

        def unknown_path_member_with_matching_edge(data):
            data["main_paths"][0]["case_ids"] = ["C001", "C999"]
            data["edges"][0]["to_case_id"] = "C999"

        for change in (unknown_edge_target, unknown_edge_source, unknown_path_member_with_matching_edge):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "未知 ID"):
                validate_output(
                    "relation_analysis",
                    json.dumps(edit(relation_output(), change)),
                    expected_case_ids=CASE_IDS,
                )

    def test_main_path_rules(self):
        def single_case_path(data):
            data["main_paths"][0]["case_ids"] = ["C001"]

        def repeated_case_in_path(data):
            data["main_paths"][0]["case_ids"] = ["C001", "C002", "C002"]

        def duplicated_path_sequence(data):
            data["main_paths"].append({"path_id": "P02", "case_ids": ["C001", "C002", "C003"]})

        def duplicated_path_id(data):
            data["main_paths"].append({"path_id": "P01", "case_ids": ["C002", "C004"]})

        for change in (single_case_path, repeated_case_in_path, duplicated_path_sequence, duplicated_path_id):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_output("relation_analysis", json.dumps(edit(relation_output(), change)))

    def test_adjacent_path_cases_need_matching_next_edge(self):
        def retyped_spine_edge(data):
            data["edges"][1]["relation_type"] = "branch"

        def missing_spine_edge(data):
            data["edges"] = [edge for edge in data["edges"] if edge["edge_id"] != "E02"]

        def skipped_spine_step(data):
            data["main_paths"][0]["case_ids"] = ["C001", "C003"]

        for change in (retyped_spine_edge, missing_spine_edge, skipped_spine_step):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "next"):
                validate_output("relation_analysis", json.dumps(edit(relation_output(), change)))

    def test_edge_identity_and_pairing_rules(self):
        def duplicated_edge_id(data):
            data["edges"].append(dict(data["edges"][0], from_case_id="C003", to_case_id="C006"))

        def self_edge(data):
            data["edges"][0]["to_case_id"] = "C001"

        def duplicated_directed_pair(data):
            data["edges"].append(dict(data["edges"][0], relation_type="branch", order=3))

        def duplicated_order_for_source(data):
            data["edges"].append(dict(data["edges"][3], from_case_id="C002", to_case_id="C005"))

        for change in (duplicated_edge_id, self_edge, duplicated_directed_pair, duplicated_order_for_source):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_output("relation_analysis", json.dumps(edit(relation_output(), change)))

    def test_order_must_be_positive_integer(self):
        def retyped(value):
            def change(data):
                data["edges"][0]["order"] = value

            return change

        for value in (0, -1, "1", 1.5, True, None):
            with self.subTest(order=value), self.assertRaises(ValueError):
                validate_output("relation_analysis", json.dumps(edit(relation_output(), retyped(value))))


class RelationValidationLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_repair_loop_receives_schema_and_expected_ids(self):
        calls = []

        async def generate(prompt):
            calls.append(prompt)
            if len(calls) == 1:
                return "{broken"
            return json.dumps(relation_output())

        output = await generate_validated(
            stage="relation_analysis",
            inputs="原始需求与分析",
            generate=generate,
            expected_case_ids=CASE_IDS,
        )
        self.assertEqual(json.loads(output), relation_output())
        self.assertIn('"from_case_id"', calls[0])
        self.assertIn("原始需求与分析", calls[1])

    async def test_unknown_case_id_triggers_repair_then_failure(self):
        calls = []

        async def generate(prompt):
            calls.append(prompt)
            data = relation_output()
            data["edges"][3]["to_case_id"] = "C999"
            return json.dumps(data)

        with self.assertRaisesRegex(Exception, "relation_analysis"):
            await generate_validated(
                stage="relation_analysis",
                inputs="输入",
                generate=generate,
                expected_case_ids=CASE_IDS,
            )
        self.assertEqual(len(calls), 3)
        self.assertIn("未知 ID", calls[1])


class RelationCheckpointTests(unittest.TestCase):
    def test_relation_stage_runs_skill_and_publishes_case_relations_only(self):
        calls, progress = [], []

        def skill_runner(**kwargs):
            calls.append(kwargs)
            return json.dumps(relation_output())

        cases = {
            "cases": [
                {"case_id": case_id, "case_module": "任务管理", "case_title": f"用例{i}", "case_type": "功能测试", "priority": "1", "precondition": ["1. 准备"], "test_steps": ["1. 执行"], "expected_results": ["1. 成功"]}
                for i, case_id in enumerate(CASE_IDS, 1)
            ]
        }
        prior = {"schema_version": "2.0", "main_paths": [], "edges": []}
        with tempfile.TemporaryDirectory() as tmp:
            task = Task(
                claim_id="c",
                task_id="t",
                run_id="r",
                generate_task_id="g",
                task_type="functional_case_generate",
                project_id="p",
                sprint_id="s",
                requirement_id="req",
                checkpoint_enabled=False,
                current_stage="relation_analysis",
                config_json=json.dumps(
                    {
                        "requirementAnalysis": {"functionalOverview": {}},
                        "caseNames": {"categories": []},
                        "resultYaml": json.dumps(cases, ensure_ascii=False),
                        "caseRelations": prior,
                    }
                ),
                payload=TaskPayload(
                    source_type="text",
                    document_type="text",
                    source_content="原始需求",
                    openapi_content="",
                ),
            )
            result = FunctionalCaseNanobotExecutor(
                nanobot_config=NanobotConfig(runtime_root=tmp), skill_runner=skill_runner
            ).execute(task, datetime.now().astimezone(), progress.append)

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["skill_name"], "analyze-test-case-relations")
        self.assertEqual(calls[0]["expected_case_ids"], CASE_IDS)
        body = calls[0]["input_text"]
        self.assertIn("【原始需求】", body)
        self.assertIn("【需求分析结果 JSON】", body)
        self.assertIn("【完整测试用例 JSON】", body)
        self.assertIn("【已有关系 JSON】", body)
        self.assertEqual(result.output_yaml, "")  # resultYaml 不被图谱产物覆盖
        config = json.loads(result.intermediate_json_text)
        self.assertEqual(config["caseRelations"], relation_output())
        self.assertEqual(config["requirementAnalysis"], {"functionalOverview": {}})
        summary = json.loads(result.result_summary_json)
        self.assertEqual(summary["caseCount"], 7)
        self.assertEqual(summary["mainPathCount"], 1)
        self.assertEqual(summary["edgeCount"], 5)
        self.assertEqual(summary["linkedCaseCount"], 6)

    def test_relation_stage_fails_without_platform_case_ids(self):
        def unexpected_skill_runner(**kwargs):
            raise AssertionError("缺少平台 case_id 时不应调用模型")

        with tempfile.TemporaryDirectory() as tmp:
            task = Task(
                claim_id="c",
                task_id="t",
                run_id="r",
                generate_task_id="g",
                task_type="functional_case_generate",
                project_id="p",
                sprint_id="s",
                requirement_id="req",
                checkpoint_enabled=False,
                current_stage="relation_analysis",
                config_json=json.dumps(
                    {
                        "requirementAnalysis": {"functionalOverview": {}},
                        "resultYaml": json.dumps({"cases": [{"case_module": "任务管理"}]}),
                    }
                ),
                payload=TaskPayload(
                    source_type="text",
                    document_type="text",
                    source_content="原始需求",
                    openapi_content="",
                ),
            )
            with self.assertRaisesRegex(ValueError, "case_id"):
                FunctionalCaseNanobotExecutor(
                    nanobot_config=NanobotConfig(runtime_root=tmp),
                    skill_runner=unexpected_skill_runner,
                ).execute(task, datetime.now().astimezone(), lambda event: None)


if __name__ == "__main__":
    unittest.main()
