#!/usr/bin/env python3
"""Check documentation links, source paths, migration revisions and ADR metadata."""

from __future__ import annotations

import argparse
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

BASELINE_REVISION = "20261103_0001"
REVISION_RE = re.compile(r"\b20\d{6}_\d{4}\b")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
ADR_FIELDS = ("状态", "日期", "取代", "被取代", "关联")
ADR_STATUSES = {"已接受", "已取代", "已废弃"}
ADDRESSES = {
    "control-plane": "apps/control-plane",
    "ai-worker": "apps/ai-worker",
    "api-ui-worker": "apps/api-ui-worker",
    "integration-worker": "apps/integration-worker",
    "perf-worker": "apps/perf-worker",
    "studio": "apps/studio",
}
# These files are historical implementation or design records. They may cite
# removed revisions and paths; current operational docs must not.
HISTORICAL_DOCS = {
    "docs/control-plane/integration-worker-implementation.md",
    "docs/control-plane/bug-zentao-push.md",
    "docs/ai-worker/requirement-analysis-two-stage-design.md",
}
HISTORICAL_MARKERS = (
    "历史",
    "已并入",
    "不再单独",
    "旧 revision",
    "旧版本",
    "迁移前",
    "当时",
    "已从代码库移除",
)
# Referenced as a forbidden file that the CSS structure gate must keep absent.
ALLOWED_MISSING_PATHS = {"src/App.css"}
SKIP_PATH_PARTS = (".scratch/", ".codex-", "node_modules/", "/app/")


@dataclass(frozen=True)
class Issue:
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def markdown_files(root: Path) -> list[Path]:
    files = sorted((root / "docs").rglob("*.md"))
    agents = root / "AGENTS.md"
    if agents.is_file():
        files.append(agents)
    files.extend(sorted((root / "apps").glob("*/AGENTS.md")))
    return files


def is_adr(path: Path) -> bool:
    return len(path.parts) >= 2 and path.parent.name == "adr"


def doc_project(path: Path, root: Path) -> Path | None:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return None
    if len(parts) >= 3 and parts[0] == "docs":
        project = ADDRESSES.get(parts[1])
        if project:
            return root / project
    return None


def check_links(root: Path, files: list[Path]) -> list[Issue]:
    issues: list[Issue] = []
    for path in files:
        rel = display_path(path, root)
        in_fence = False
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for match in LINK_RE.finditer(line):
                target = match.group(1).strip()
                if target.startswith(("http://", "https://", "mailto:", "data:", "#")):
                    continue
                target = target.split("#", 1)[0]
                if not target or ".scratch/" in target:
                    continue
                if any(char in target for char in "<>{}"):
                    continue
                destination = (path.parent / target).resolve()
                if not destination.exists():
                    issues.append(Issue(rel, lineno, f"相对链接不存在: {target}"))
    return issues


def normalized_path_token(token: str) -> str | None:
    token = token.strip()
    if not token or token.startswith(("http://", "https://", "mailto:", "#")):
        return None
    if any(char in token for char in "<>*{}$?…`|"):
        return None
    if any(part in token for part in SKIP_PATH_PARTS):
        return None
    token = token.split()[0]
    token = token.split("::", 1)[0]
    token = re.sub(r":\d+(?:-\d+)?$", "", token)
    if token in ALLOWED_MISSING_PATHS:
        return None
    if not token.startswith(("src/", "apps/", "docs/", "scripts/", "tests/", "alembic/")):
        return None
    return token


def path_candidates(token: str, path: Path, root: Path) -> list[Path]:
    project = doc_project(path, root)
    if token.startswith("apps/") or token.startswith("docs/"):
        return [root / token]
    if token.startswith("src/"):
        return [project / token] if project else []
    if token.startswith("scripts/"):
        candidates = [root / token]
        if project:
            candidates.append(project / token)
        return candidates
    if token.startswith("tests/"):
        candidates = [root / token]
        if project:
            candidates.insert(0, project / token)
        return candidates
    if token.startswith("alembic/"):
        return [project / token] if project else []
    return []


def check_paths(root: Path, files: list[Path]) -> list[Issue]:
    issues: list[Issue] = []
    for path in files:
        if is_adr(path):
            continue
        rel = display_path(path, root)
        in_fence = False
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for match in INLINE_CODE_RE.finditer(line):
                token = normalized_path_token(match.group(1))
                if token is None:
                    continue
                candidates = path_candidates(token, path, root)
                if not candidates:
                    continue
                if not any(candidate.exists() for candidate in candidates):
                    issues.append(Issue(rel, lineno, f"引用的路径不存在: {token}"))
    return issues


def check_revisions(root: Path, files: list[Path]) -> list[Issue]:
    issues: list[Issue] = []
    for path in files:
        if is_adr(path):
            continue
        rel = display_path(path, root)
        if rel in HISTORICAL_DOCS:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(marker in line for marker in HISTORICAL_MARKERS):
                continue
            for match in REVISION_RE.finditer(line):
                revision = match.group(0)
                if revision == BASELINE_REVISION:
                    continue
                issues.append(
                    Issue(rel, lineno, f"当前操作文档引用了非基线迁移号: {revision}")
                )
    return issues


def check_adrs(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for path in sorted((root / "docs").glob("*/adr/*.md")):
        rel = display_path(path, root)
        text = path.read_text(encoding="utf-8")
        for field in ADR_FIELDS:
            if not re.search(rf"^- {field}：", text, re.MULTILINE):
                issues.append(Issue(rel, 1, f"ADR 缺少元数据字段: {field}"))
        status_match = re.search(r"^- 状态：(.*)$", text, re.MULTILINE)
        if status_match:
            status = status_match.group(1).strip()
            if status not in ADR_STATUSES:
                issues.append(Issue(rel, 1, f"ADR 状态不在允许值内: {status}"))
            if status == "已取代":
                superseded = re.search(r"^- 被取代：(.*)$", text, re.MULTILINE)
                if superseded is None or "](" not in superseded.group(1):
                    issues.append(Issue(rel, 1, "已取代 ADR 缺少替代 ADR 链接"))
        date_match = re.search(r"^- 日期：(.*)$", text, re.MULTILINE)
        if date_match and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_match.group(1).strip()):
            issues.append(Issue(rel, 1, "ADR 日期不是 YYYY-MM-DD"))
    return issues


def check_external_links(files: list[Path], timeout: float = 10.0) -> list[Issue]:
    issues: list[Issue] = []
    urls: set[str] = set()
    for path in files:
        for match in LINK_RE.finditer(path.read_text(encoding="utf-8")):
            target = match.group(1).strip()
            if target.startswith(("http://", "https://")):
                urls.add(target)
    for url in sorted(urls):
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "mtx-check-docs"})
        try:
            urllib.request.urlopen(request, timeout=timeout).close()
        except urllib.error.HTTPError as exc:
            if exc.code == 405:
                try:
                    urllib.request.urlopen(url, timeout=timeout).close()
                except Exception as retry:  # noqa: BLE001 - report URL-level failure only
                    issues.append(Issue("<url>", 1, f"外部链接失败: {url} ({retry})"))
            else:
                issues.append(Issue("<url>", 1, f"外部链接失败: {url} (HTTP {exc.code})"))
        except Exception as exc:  # noqa: BLE001 - network failures are reported, not raised
            issues.append(Issue("<url>", 1, f"外部链接失败: {url} ({exc})"))
    return issues


def run_checks(
    root: Path,
    *,
    check_relative_links: bool = True,
    check_source_paths: bool = True,
    check_migration_revisions: bool = True,
    check_adr_metadata: bool = True,
    check_urls: bool = False,
) -> list[Issue]:
    files = markdown_files(root)
    issues: list[Issue] = []
    if check_relative_links:
        issues.extend(check_links(root, files))
    if check_source_paths:
        issues.extend(check_paths(root, files))
    if check_migration_revisions:
        issues.extend(check_revisions(root, files))
    if check_adr_metadata:
        issues.extend(check_adrs(root))
    if check_urls:
        issues.extend(check_external_links(files))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check documentation links, paths, migration revisions and ADR metadata."
    )
    parser.add_argument("--check-links", action="store_true", help="check relative links")
    parser.add_argument("--check-paths", action="store_true", help="check referenced source paths")
    parser.add_argument(
        "--check-revisions", action="store_true", help="check migration revision references"
    )
    parser.add_argument("--check-adr", action="store_true", help="check ADR metadata")
    parser.add_argument(
        "--check-urls", action="store_true", help="also check external URLs (network required)"
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)

    explicit = any(
        (
            args.check_links,
            args.check_paths,
            args.check_revisions,
            args.check_adr,
            args.check_urls,
        )
    )
    run_all = not explicit
    issues = run_checks(
        args.root.resolve(),
        check_relative_links=run_all or args.check_links or args.check_urls,
        check_source_paths=run_all or args.check_paths,
        check_migration_revisions=run_all or args.check_revisions,
        check_adr_metadata=run_all or args.check_adr,
        check_urls=args.check_urls,
    )
    for issue in issues:
        print(issue)
    if issues:
        print(f"documentation check failed: {len(issues)} issue(s)")
        return 1
    print(f"documentation check passed: {len(markdown_files(args.root.resolve()))} Markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
