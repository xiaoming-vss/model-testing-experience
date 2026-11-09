"""Temporary context-preview prompt and receipt validation.

The real analysis skill is not available yet. This module asks the model to use
the read-only tools, inspect the prepared workspace, and return a structured
receipt proving the context reached the model.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import yaml

from testing_agent_ai_worker.tasks.code_risk_analysis.context import ContextPackage
from testing_agent_ai_worker.tasks.code_risk_analysis.workspace import CodeWorkspace


class ContextReceiptError(RuntimeError):
    """The model did not return a valid context receipt."""


PROMPT_TEMPLATE = """你是代码上下文预览助手，不是正式风险分析助手。

工作区根目录：{workspace_root}

请使用 read/grep/find/ls 工具查看代码，核对下面给出的仓库、commit、改动文件和需求/用例上下文。
只允许读取，不允许修改文件、执行 bash、写文件或访问网络。

请只输出 YAML，格式如下（字段值必须来自下方上下文或你实际读取到的文件）：

```yaml
analyzedAt: "ISO-8601 时间"
contextReceipt:
  receivedRepositories:
    - repositoryId: "仓库 ID"
      headCommit: "HEAD commit"
  summary: "一段话说明你收到的代码上下文和大致范围"
  filesRead:
    - "相对工作区的文件路径"
  toolsUsed:
    - "read"
    - "grep"
```

下面是本次上下文：

{context}
"""


def build_preview_prompt(context: ContextPackage, workspace: CodeWorkspace) -> str:
    return PROMPT_TEMPLATE.format(
        workspace_root=str(workspace.code_root),
        context=context.text,
    )


def validate_context_receipt(
    raw_output: str,
    workspace: CodeWorkspace,
) -> dict[str, Any]:
    """Parse and verify the model receipt against the prepared workspace."""

    text = _strip_fence(str(raw_output or "").strip())
    if not text:
        raise ContextReceiptError("模型输出为空")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ContextReceiptError(f"模型输出不是有效 YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ContextReceiptError("模型输出不是 YAML 对象")
    receipt = data.get("contextReceipt", data.get("context_receipt"))
    if not isinstance(receipt, dict):
        raise ContextReceiptError("模型输出缺少 contextReceipt")
    summary = receipt.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ContextReceiptError("contextReceipt 缺少 summary")
    received = receipt.get("receivedRepositories", receipt.get("received_repositories"))
    if not isinstance(received, list) or not received:
        raise ContextReceiptError("contextReceipt 缺少 receivedRepositories")

    expected = {(repo.binding.repository_id, repo.head_commit) for repo in workspace.repositories}
    actual: set[tuple[str, str]] = set()
    for item in received:
        if not isinstance(item, dict):
            raise ContextReceiptError("receivedRepositories 条目格式不合法")
        repository_id = str(item.get("repositoryId") or item.get("repository_id") or "").strip()
        head_commit = str(item.get("headCommit") or item.get("head_commit") or "").strip()
        if repository_id and head_commit:
            actual.add((repository_id, head_commit))
    missing = expected - actual
    if missing:
        missing_text = "、".join(f"{repo_id}@{commit}" for repo_id, commit in sorted(missing))
        raise ContextReceiptError(f"模型未收到完整仓库上下文: {missing_text}")

    files_read = receipt.get("filesRead", receipt.get("files_read")) or []
    tools_used = receipt.get("toolsUsed", receipt.get("tools_used")) or []
    if not isinstance(files_read, list) or not all(isinstance(item, str) for item in files_read):
        raise ContextReceiptError("filesRead 必须是字符串列表")
    if not isinstance(tools_used, list) or not all(isinstance(item, str) for item in tools_used):
        raise ContextReceiptError("toolsUsed 必须是字符串列表")
    return {
        "summary": summary.strip(),
        "filesRead": files_read,
        "toolsUsed": tools_used,
        "receivedRepositories": received,
    }


def build_result_receipt(
    workspace: CodeWorkspace,
    context: ContextPackage,
    model_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Merge deterministic workspace facts with the model's receipt."""

    return {
        "analyzedAt": datetime.now(UTC).isoformat(),
        "contextReceipt": {
            "mode": "context_preview",
            "repositories": workspace.manifest["repositories"],
            "counts": {
                "repositories": len(workspace.repositories),
                "changedFiles": sum(len(repo.changed_files) for repo in workspace.repositories),
                "diffChars": context.diff_chars,
            },
            "truncatedFiles": context.truncated_files,
            "summary": model_receipt["summary"],
            "filesRead": model_receipt["filesRead"],
            "toolsUsed": model_receipt["toolsUsed"],
            "receivedRepositories": model_receipt["receivedRepositories"],
        },
    }


def _strip_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) < 2 or not lines[-1].strip().startswith("```"):
        return text
    return "\n".join(lines[1:-1]).strip()
