import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from testing_agent_ai_worker_pi.models.task import Task, TaskPayload
from testing_agent_ai_worker_pi.tasks.requirement_analysis.artifact_handoff import (
    read_artifact_response,
)
from testing_agent_ai_worker_pi.tasks.requirement_analysis.validation import generate_validated

FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "tests/fixtures/requirement_artifacts/document-extraction.example.json"
)
RECEIPT = {"artifactFile": "document-extraction.json"}


class ArtifactHandoffTests(unittest.TestCase):
    def test_exact_receipt_reads_file_without_changing_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document-extraction.json"
            raw = FIXTURE.read_text()
            path.write_text(raw)
            for receipt in [RECEIPT, json.dumps(RECEIPT)]:
                self.assertEqual(
                    read_artifact_response(receipt, kind="document_extraction", output_path=path),
                    raw,
                )

    def test_bad_receipts_never_select_another_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document-extraction.json"
            path.write_text("{}")
            for raw in [
                {"artifactFile": "../secret.json"},
                {"artifactFile": str(path)},
                {**RECEIPT, "extra": True},
                '{"artifactFile":"document-extraction.json","artifactFile":"document-extraction.json"}',
            ]:
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    read_artifact_response(raw, kind="document_extraction", output_path=path)
            with self.assertRaises(ValueError):
                read_artifact_response(RECEIPT, kind="requirement_understanding", output_path=path)

    def test_missing_symlink_and_non_utf8_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document-extraction.json"
            with self.assertRaises(ValueError):
                read_artifact_response(RECEIPT, kind="document_extraction", output_path=path)
            other = Path(directory) / "other.json"
            other.write_text("{}")
            path.symlink_to(other)
            with self.assertRaises(ValueError):
                read_artifact_response(RECEIPT, kind="document_extraction", output_path=path)
            path.unlink()
            path.write_bytes(b"\xff")
            with self.assertRaises(ValueError):
                read_artifact_response(RECEIPT, kind="document_extraction", output_path=path)

    def test_replaced_parent_cannot_redirect_the_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "invocation"
            original.mkdir()
            path = original / "document-extraction.json"
            original.rename(root / "old")
            other = root / "another"
            other.mkdir()
            (other / "document-extraction.json").write_text(FIXTURE.read_text())
            original.symlink_to(other, target_is_directory=True)
            with self.assertRaises(ValueError):
                read_artifact_response(RECEIPT, kind="document_extraction", output_path=path)

    def run_generation(self, workspace, generate):
        task = Task(
            task_id="file-result",
            run_id="file-result",
            task_type="requirement_analysis",
            config_json="{}",
            payload=TaskPayload(openapi_content=""),
        )
        return generate_validated(
            kind="document_extraction",
            task=task,
            stage="extracting_text",
            workspace=workspace,
            generate=generate,
            arguments={},
            report=lambda p: None,
        )

    def test_file_errors_are_repaired_and_complete_artifact_returned(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = []

            def generate(**kwargs):
                path = Path(
                    re.search(r"到以下绝对路径：\n([^\n]+)", kwargs["extra_instruction"])[1]
                )
                paths.append(path)
                path.write_text("{bad" if len(paths) == 1 else FIXTURE.read_text())
                return json.dumps(RECEIPT)

            result = self.run_generation(Path(directory), generate)
            self.assertEqual(result, json.loads(FIXTURE.read_text()))
            self.assertEqual(len(paths), 2)
            self.assertEqual(paths[0], paths[1])

    def test_replaced_diagnostics_directory_cannot_redirect_repair_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            outside = root / "outside"
            outside.mkdir()

            def generate(**kwargs):
                path = Path(
                    re.search(r"到以下绝对路径：\n([^\n]+)", kwargs["extra_instruction"])[1]
                )
                path.parent.rename(root / "old")
                path.parent.symlink_to(outside, target_is_directory=True)
                return FIXTURE.read_text()

            with self.assertRaisesRegex(ValueError, "产物输出目录"):
                self.run_generation(workspace, generate)
            self.assertEqual(list(outside.iterdir()), [])

    def test_another_invocations_file_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)

            def first(**kwargs):
                path = Path(
                    re.search(r"到以下绝对路径：\n([^\n]+)", kwargs["extra_instruction"])[1]
                )
                path.write_text(FIXTURE.read_text())
                return RECEIPT

            self.run_generation(workspace, first)
            second = Mock(return_value=RECEIPT)
            with self.assertRaisesRegex(ValueError, "不存在"):
                self.run_generation(workspace, second)
            self.assertEqual(second.call_count, 3)

    def test_direct_artifacts_still_use_normal_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_generation(Path(directory), lambda **kwargs: FIXTURE.read_text())
            self.assertEqual(result, json.loads(FIXTURE.read_text()))
