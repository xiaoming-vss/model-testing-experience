import importlib.util
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_docs", ROOT / "scripts/check_docs.py")
check_docs = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = check_docs
spec.loader.exec_module(check_docs)


class DocumentationCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
        return path

    def issues(self, **kwargs) -> list[str]:
        return [str(issue) for issue in check_docs.run_checks(self.root, **kwargs)]

    def test_minimal_tree_passes(self):
        self.write("docs/README.md", "# Docs\n\n[Guide](guide.md)\n")
        self.write("docs/guide.md", "# Guide\n")
        self.write("docs/deployment.md", "Baseline `20261103_0001`.\n")
        self.write(
            "docs/control-plane/adr/0001-test.md",
            """\
            # ADR 0001: Test

            - 状态：已接受
            - 日期：2026-11-19
            - 取代：—
            - 被取代：—
            - 关联：—
            """,
        )
        self.assertEqual(self.issues(), [])

    def test_broken_relative_link_fails(self):
        self.write("docs/README.md", "[Missing](missing.md)\n")
        self.assertTrue(any("missing.md" in issue for issue in self.issues()))

    def test_missing_source_path_fails(self):
        self.write("docs/studio/README.md", "Use `src/missing.ts`.\n")
        self.assertTrue(any("src/missing.ts" in issue for issue in self.issues()))

        self.write("apps/studio/src/present.ts", "export {}\n")
        self.write("docs/studio/README.md", "Use `src/present.ts`.\n")
        self.assertFalse(any("src/present.ts" in issue for issue in self.issues()))

    def test_old_migration_revision_fails(self):
        self.write("docs/deployment.md", "迁移 20261003_0023。\n")
        self.assertTrue(any("20261003_0023" in issue for issue in self.issues()))

        self.write("docs/deployment.md", "基线 20261103_0001。\n")
        self.assertFalse(any("20261103_0001" in issue for issue in self.issues()))

        self.write("docs/deployment.md", "历史迁移 20261003_0023，已并入 baseline。\n")
        self.assertFalse(any("20261003_0023" in issue for issue in self.issues()))

    def test_adr_metadata_is_required(self):
        self.write(
            "docs/control-plane/adr/0001-test.md",
            "# ADR 0001: Test\n\n- 状态：已接受\n",
        )
        issues = self.issues(
            check_relative_links=False,
            check_source_paths=False,
            check_migration_revisions=False,
        )
        self.assertTrue(any("缺少元数据字段: 日期" in issue for issue in issues))

    def test_superseded_adr_requires_link(self):
        self.write(
            "docs/control-plane/adr/0001-test.md",
            """\
            # ADR 0001: Test

            - 状态：已取代
            - 日期：2026-11-19
            - 取代：—
            - 被取代：—
            - 关联：—
            """,
        )
        issues = self.issues(
            check_relative_links=False,
            check_source_paths=False,
            check_migration_revisions=False,
        )
        self.assertTrue(any("缺少替代 ADR 链接" in issue for issue in issues))

        self.write(
            "docs/control-plane/adr/0001-test.md",
            """\
            # ADR 0001: Test

            - 状态：已取代
            - 日期：2026-11-19
            - 取代：—
            - 被取代：[ADR 0002](0002-test.md)
            - 关联：[ADR 0002](0002-test.md)
            """,
        )
        self.write(
            "docs/control-plane/adr/0002-test.md",
            """\
            # ADR 0002: Replacement

            - 状态：已接受
            - 日期：2026-11-19
            - 取代：[ADR 0001](0001-test.md)
            - 被取代：—
            - 关联：[ADR 0001](0001-test.md)
            """,
        )
        self.assertEqual(self.issues(), [])

    def test_cli_exit_codes(self):
        import contextlib
        import io

        self.write("docs/README.md", "[Missing](missing.md)\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check_docs.main(["--root", str(self.root)]), 1)

        self.write("docs/README.md", "# Docs\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check_docs.main(["--root", str(self.root)]), 0)


if __name__ == "__main__":
    unittest.main()
