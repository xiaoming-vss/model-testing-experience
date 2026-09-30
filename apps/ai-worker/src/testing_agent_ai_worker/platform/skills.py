"""Fetch only the default skills needed by this execution into an isolated workspace."""

import hashlib
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote

import httpx

from testing_agent_ai_worker.nanobot_runtime.paths import resolve_task_workspace

REQUIREMENT_SKILLS = {
    "extracting_text": "extract-docx-enhanced-text",
    "writing_requirement": "prd-requirement-writing-skill",
    "feature_understanding": "prd-feature-understanding-skill",
}
FUNCTIONAL_SKILLS = {
    "requirement_analysis": "analyze-functional-requirements",
    "case_names": "generate-solution-test-points",
    "detailed_cases": "generate-solution-test-cases",
    "relation_analysis": "analyze-test-case-relations",
}
TASK_SKILLS = {
    "api_case_generate": ["openapi-test-config-extractor", "api-cases-yaml-generator"],
    "ui_case_generate": ["generate-ui-test-case"],
    "code_risk_analysis": ["code-risk-analysis"],
    "test_report_generate": ["advanced-test-report-generator"],
    "test_order_graph": ["update-test-case-graph"],
}


def required_skills(task):
    stages = {
        "requirement_analysis": REQUIREMENT_SKILLS,
        "functional_case_generate": FUNCTIONAL_SKILLS,
    }.get(task.task_type)
    if stages is not None:
        if task.checkpoint_enabled:
            name = stages.get(task.current_stage)
            return [name] if name else []
        names = list(stages.values())
        return names[:3]  # Non-checkpoint functional generation has no relation-analysis step.
    return TASK_SKILLS.get(task.task_type, [])


class SkillPreparer:
    def __init__(self, client, nanobot_config, worker_id):
        self.client, self.config, self.worker_id = client, nanobot_config, worker_id

    def __call__(self, task):
        names = required_skills(task)
        if not names:
            return
        workspace = resolve_task_workspace(self.config, task)
        workspace.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".skills-", dir=workspace))
        try:
            for name in names:
                self._fetch(task, name, staging / name)
            target = workspace / "skills"
            if target.exists():
                shutil.rmtree(target)
            staging.rename(target)
        except httpx.HTTPStatusError as exc:
            # Do not put signed URLs or response payloads in task error messages.
            raise ValueError(
                f"获取默认 Skill 失败（HTTP {exc.response.status_code}），"
                f"请检查技能库及任务权限：{', '.join(names)}"
            ) from None
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def _fetch(self, task, name, target):
        base = f"/internal/ai-worker/tasks/{quote(task.task_id, safe='')}/skills/{name}"
        query = "?workerId=" + quote(self.worker_id, safe="")
        manifest = self.client.get(base + query)
        entries = manifest.get("files", []) if manifest else []
        if not entries or len(entries) > 2000:
            raise ValueError(f"默认 Skill 文件清单为空或超限: {name}")
        seen, total = set(), 0
        for entry in entries:
            path = entry["path"]
            if (
                "\\" in path
                or ":" in path
                or any(ord(c) < 32 for c in path)
                or any(p in {"", ".", ".."} for p in path.split("/"))
                or path.casefold() in seen
            ):
                raise ValueError("技能文件路径不合法")
            seen.add(path.casefold())
            total += entry["size"]
            if entry["size"] < 0 or total > 1024 * 1024 * 1024:
                raise ValueError("技能文件超出大小限制")
            content = self.client.get_signed_file_bytes(
                base + "/files/" + quote(entry["fileId"], safe="") + query
            )
            if (
                len(content) != entry["size"]
                or hashlib.sha256(content).hexdigest() != entry["sha256"]
            ):
                raise ValueError(f"技能文件校验失败: {name}/{path}")
            output = target / path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
        if not (target / "SKILL.md").is_file():
            raise ValueError(f"默认 Skill 缺少 SKILL.md: {name}")
