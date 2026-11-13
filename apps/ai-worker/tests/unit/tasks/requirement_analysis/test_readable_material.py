import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from testing_agent_ai_worker.models.task import Task, TaskPayload
from testing_agent_ai_worker.requirement_artifacts import validate_artifact
from testing_agent_ai_worker.tasks.requirement_analysis.confirmation_coverage import (
    collect_confirmation_references,
    validate_confirmation_coverage,
)
from testing_agent_ai_worker.tasks.requirement_analysis.material_stage import execute_material_stage
from testing_agent_ai_worker.tasks.requirement_analysis.validation import generate_validated


def material():
    return {
        "schemaVersion": "0.2",
        "artifactType": "readable_requirement_material",
        "title": "示例",
        "sources": [
            {"id": "S1", "name": "用户答复", "type": "user_confirmation", "location": None}
        ],
        "materialBlocks": [
            {
                "id": "B1",
                "sourceId": "S1",
                "parentId": None,
                "kind": "paragraph",
                "locator": "答复一",
                "content": {"text": "保存后显示成功"},
            }
        ],
        "functions": [
            {
                "id": "F1",
                "name": "保存",
                "sections": [
                    {
                        "title": "功能使用与业务规则",
                        "items": [
                            {
                                "text": "保存后显示成功",
                                "status": "confirmed",
                                "materialBlockIds": ["B1"],
                            }
                        ],
                    }
                ],
            }
        ],
        "questions": [],
    }


class ReadableMaterialTests(unittest.TestCase):
    def test_fresh_and_revision_material_reaches_review_for_both_document_types(self):
        for document_type in ("word", "richtext"):
            for revision in (False, True):
                with self.subTest(document_type=document_type, revision=revision):
                    source = material()
                    config = (
                        {"firstStepOutput": source, "revisionInstruction": "保留确认"}
                        if revision
                        else {}
                    )
                    task = Task(
                        task_id="test",
                        attempt_id="test",
                        task_type="requirement_analysis",
                        requirement_id="r",
                        current_stage="extracting_text",
                        checkpoint_enabled=True,
                        config_json=json.dumps(config),
                        payload=TaskPayload(
                            openapi_content="",
                            document_type=document_type,
                            metadata={"workflowVersion": 2},
                        ),
                    )
                    downloader = SimpleNamespace(
                        download_source=lambda **_: "/tmp/source",
                        download_images=lambda **_: [{"sourcePath": "/tmp/image.png"}],
                    )
                    calls, progress = [], []

                    def runner(**kwargs):
                        calls.append(kwargs)
                        return json.dumps(source, ensure_ascii=False)

                    with tempfile.TemporaryDirectory() as directory:
                        result = execute_material_stage(
                            task=task,
                            started_at=datetime.now().astimezone(),
                            progress_callback=progress.append,
                            config_path=None,
                            workspace=Path(directory),
                            skill_runner=runner,
                            source_downloader=downloader,
                            first_skill_name="mtx-organize-requirement-material",
                        )
                    body = json.loads(calls[0]["input_text"])
                    self.assertEqual(bool(body.get("currentArtifact")), revision)
                    if document_type == "richtext":
                        self.assertEqual(calls[0]["media"], ["/tmp/image.png"])
                    self.assertEqual(result.status.value, "success")
                    self.assertEqual(json.loads(result.output_yaml), source)

    def test_references_and_hierarchy_are_checked(self):
        self.assertEqual(validate_artifact(material(), "document_extraction"), material())
        for mutate in ("bad_ref", "cycle", "duplicate"):
            value = material()
            if mutate == "bad_ref":
                value["functions"][0]["sections"][0]["items"][0]["materialBlockIds"] = ["missing"]
            elif mutate == "cycle":
                value["materialBlocks"][0]["parentId"] = "B1"
            else:
                value["materialBlocks"].append(copy.deepcopy(value["materialBlocks"][0]))
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                validate_artifact(value, "document_extraction")

    def test_table_spans_must_fit_and_not_overlap(self):
        value = material()
        block = value["materialBlocks"][0]
        block.update(
            kind="table",
            content={
                "rows": [["标题", None], ["一", "二"]],
                "spans": [{"row": 0, "column": 0, "rowSpan": 1, "columnSpan": 2}],
            },
        )
        self.assertEqual(validate_artifact(value, "document_extraction"), value)
        block["content"]["spans"].append({"row": 0, "column": 1, "rowSpan": 2, "columnSpan": 1})
        with self.assertRaisesRegex(ValueError, "重叠"):
            validate_artifact(value, "document_extraction")

    def test_confirmation_must_be_referenced_by_business_content(self):
        value = material()
        required = collect_confirmation_references(value)
        self.assertEqual(required[0]["locator"], "答复一")
        value["functions"] = []
        with self.assertRaisesRegex(ValueError, "确认来源"):
            validate_confirmation_coverage(value, required)

    def test_invalid_output_is_repaired_against_new_schema(self):
        good = material()
        bad = copy.deepcopy(good)
        bad["functions"][0]["sections"][0]["items"][0]["materialBlockIds"] = ["missing"]
        calls = []

        def generate(**kwargs):
            calls.append(kwargs["extra_instruction"])
            return json.dumps(bad if len(calls) == 1 else good, ensure_ascii=False)

        task = Task(
            task_id="test",
            attempt_id="test",
            task_type="requirement_analysis",
            config_json="{}",
            payload=TaskPayload(openapi_content=""),
        )
        with tempfile.TemporaryDirectory() as directory:
            result = generate_validated(
                kind="document_extraction",
                task=task,
                stage="extracting_text",
                workspace=Path(directory),
                generate=generate,
                arguments={},
                report=lambda _: None,
            )
        self.assertEqual(result, good)
        self.assertEqual(len(calls), 2)
        self.assertIn("missing", calls[1])
        self.assertIn("readable_requirement_material", calls[0])

    def test_unified_categories_and_question_function_links_are_enforced(self):
        value = material()
        value["schemaVersion"] = "0.2"
        value["functions"][0]["sections"][0]["title"] = "功能使用与业务规则"
        value["questions"] = [
            {
                "id": "Q1",
                "question": "反馈如何显示？",
                "reason": "未说明",
                "materialBlockIds": ["B1"],
                "functionIds": ["F1"],
            }
        ]
        self.assertEqual(validate_artifact(value, "document_extraction"), value)
        invalid = copy.deepcopy(value)
        invalid["questions"][0]["functionIds"] = ["missing"]
        with self.assertRaises(ValueError):
            validate_artifact(invalid, "document_extraction")
        invalid = copy.deepcopy(value)
        invalid["functions"][0]["sections"][0]["title"] = "功能特有的标题"
        with self.assertRaises(ValueError):
            validate_artifact(invalid, "document_extraction")

    def test_duplicate_and_empty_categories_are_rejected(self):
        value = material()
        value["functions"][0]["sections"].append(
            copy.deepcopy(value["functions"][0]["sections"][0])
        )
        with self.assertRaises(ValueError):
            validate_artifact(value, "document_extraction")
        value = material()
        value["functions"][0]["sections"][0]["items"] = []
        with self.assertRaises(ValueError):
            validate_artifact(value, "document_extraction")
