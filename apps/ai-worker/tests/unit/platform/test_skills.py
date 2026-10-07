import hashlib
import tempfile
import unittest
from unittest.mock import Mock

from testing_agent_ai_worker.config.models import NanobotConfig
from testing_agent_ai_worker.models.task import Task, TaskPayload
from testing_agent_ai_worker.nanobot_runtime.paths import resolve_task_workspace
from testing_agent_ai_worker.platform.skills import SkillPreparer, required_skills


class SkillTests(unittest.TestCase):
    def task(self, **kwargs):
        return Task(
            task_id="task", project_id="project", payload=TaskPayload(openapi_content=""), **kwargs
        )

    def test_maps_active_skills_and_checkpoint_only_fetches_needed_one(self):
        names = set()
        for kind in [
            "requirement_analysis",
            "functional_case_generate",
            "api_case_generate",
            "ui_case_generate",
            "code_risk_analysis",
            "test_report_generate",
            "test_order_graph",
        ]:
            if kind == "requirement_analysis":
                for stage in ["extracting_text", "feature_understanding"]:
                    names.update(
                        required_skills(
                            self.task(task_type=kind, checkpoint_enabled=True, current_stage=stage)
                        )
                    )
            else:
                names.update(required_skills(self.task(task_type=kind)))
        task = self.task(
            task_type="functional_case_generate",
            checkpoint_enabled=True,
            current_stage="relation_analysis",
        )
        self.assertEqual(required_skills(task), ["analyze-test-case-relations"])
        names.update(required_skills(task))
        self.assertEqual(len(names), 12)

    def test_fresh_download_replaces_removed_files_and_preserves_other_task(self):
        with tempfile.TemporaryDirectory() as temp:
            config = NanobotConfig(runtime_root=temp)
            task = self.task(task_type="ui_case_generate")
            client = Mock()
            data = b"# skill"
            entry = {
                "path": "SKILL.md",
                "fileId": "id",
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            client.get.return_value = {"files": [entry]}
            client.get_signed_file_bytes.return_value = data
            prepare = SkillPreparer(client, config, "worker")
            prepare(task)
            skill = resolve_task_workspace(config, task) / "skills" / "generate-ui-test-case"
            self.assertEqual((skill / "SKILL.md").read_bytes(), data)
            (skill / "old.txt").write_text("old")
            other = task.model_copy(update={"task_id": "other"})
            other_workspace = resolve_task_workspace(config, other)
            other_workspace.mkdir(parents=True)
            (other_workspace / "keep").write_text("keep")
            prepare(task)
            self.assertFalse((skill / "old.txt").exists())
            self.assertEqual((other_workspace / "keep").read_text(), "keep")
            self.assertIn("workerId=worker", client.get.call_args.args[0])

    def test_bad_download_aborts_before_replacing_skill_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            config = NanobotConfig(runtime_root=temp)
            task = self.task(task_type="ui_case_generate")
            client = Mock()
            client.get.return_value = {
                "files": [{"path": "SKILL.md", "fileId": "id", "size": 5, "sha256": "0" * 64}]
            }
            client.get_signed_file_bytes.return_value = b"bad"
            with self.assertRaisesRegex(ValueError, "校验失败"):
                SkillPreparer(client, config, "worker")(task)
            self.assertFalse((resolve_task_workspace(config, task) / "skills").exists())

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            client = Mock()
            client.get.return_value = {"files": [{"path": "../escape", "size": 1}]}
            with self.assertRaisesRegex(ValueError, "路径"):
                SkillPreparer(client, NanobotConfig(runtime_root=temp), "w")(
                    self.task(task_type="ui_case_generate")
                )
            client.get_signed_file_bytes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
