"""图谱轮次编排：批量切分、用例文件、每轮输入与产物校验。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from testing_agent_ai_worker.tasks.test_order_graph.rounds import (
    GRAPH_BATCH_SIZE,
    build_retry_suffix,
    empty_graph,
    parse_graph_text,
    split_batches,
    usable_cases,
    write_cases_file,
    write_round_graph,
    write_round_request,
)


def case(case_id: str, *, steps: bool = True) -> dict:
    return {
        "case_id": case_id,
        "case_module": "模块",
        "case_title": f"用例{case_id}",
        "case_type": "功能测试",
        "priority": "1",
        "precondition": [],
        "test_steps": ["1. 执行。"] if steps else [],
        "expected_results": ["1. 成功。"] if steps else [],
    }


class UsableCasesTest(unittest.TestCase):
    def test_skips_cases_without_steps_or_expected_results(self) -> None:
        cases = [case("C1"), case("C2", steps=False), {**case("C3"), "expected_results": []}]

        usable, skipped = usable_cases(cases)

        self.assertEqual(["C1"], [item["case_id"] for item in usable])
        self.assertEqual(["C2", "C3"], skipped)


class SplitBatchesTest(unittest.TestCase):
    def test_splits_by_batch_size_keeping_requirement_id(self) -> None:
        ids = [f"C{index:02d}" for index in range(1, 46)]
        links = [{"requirement_id": "REQ-001", "case_ids": ids}]

        batches = split_batches(links, set(ids))

        counts = [sum(len(item["case_ids"]) for item in batch) for batch in batches]
        self.assertEqual([GRAPH_BATCH_SIZE, 15], counts)
        # 单个分组超限时跨轮，每轮带同一个 requirement_id。
        for batch in batches:
            self.assertEqual(["REQ-001"], [item["requirement_id"] for item in batch])

    def test_one_batch_may_mix_groups_and_null_group(self) -> None:
        links = [
            {"requirement_id": "REQ-001", "case_ids": ["C1", "C2", "C3"]},
            {"requirement_id": None, "case_ids": ["C4", "C5"]},
        ]

        batches = split_batches(links, {"C1", "C2", "C3", "C4", "C5"})

        self.assertEqual(
            [
                [
                    {"requirement_id": "REQ-001", "case_ids": ["C1", "C2", "C3"]},
                    {"requirement_id": None, "case_ids": ["C4", "C5"]},
                ]
            ],
            batches,
        )

    def test_drops_unusable_ids_empty_groups_and_duplicates(self) -> None:
        links = [
            {"requirement_id": "REQ-001", "case_ids": ["C1", "C1", "C2"]},
            {"requirement_id": None, "case_ids": ["C3"]},
        ]

        # C2 与 C3 被跳过（没有步骤），因此只剩 C1；全被剔除的分组不产生空批次。
        batches = split_batches(links, {"C1"})

        self.assertEqual([[{"requirement_id": "REQ-001", "case_ids": ["C1"]}]], batches)

    def test_returns_no_batch_when_nothing_usable(self) -> None:
        links = [{"requirement_id": "REQ-001", "case_ids": ["C1"]}]

        self.assertEqual([], split_batches(links, set()))


class RoundFilesTest(unittest.TestCase):
    def test_cases_file_is_named_after_run_id_and_wraps_cases(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            run_dir = Path(root) / "run-1"

            path = write_cases_file(run_dir, "run-1", [case("C1")])

            self.assertEqual("run-1.json", path.name)
            self.assertEqual({"cases": [case("C1")]}, json.loads(path.read_text(encoding="utf-8")))

    def test_round_request_and_graph_files_are_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            run_dir = Path(root)

            request = write_round_request(run_dir, 2, {"requirements": []})
            graph = write_round_graph(run_dir, 2, empty_graph())

            self.assertEqual("round-2-request.json", request.name)
            self.assertEqual("round-2-graph.json", graph.name)
            self.assertEqual(empty_graph(), json.loads(graph.read_text(encoding="utf-8")))


class ParseGraphTextTest(unittest.TestCase):
    def test_accepts_valid_graph_and_strips_code_fence(self) -> None:
        graph = {
            "schema_version": "2.0",
            "main_paths": [{"path_id": "P01", "case_ids": ["C1", "C2"]}],
            "edges": [
                {
                    "edge_id": "E01",
                    "from_case_id": "C1",
                    "to_case_id": "C2",
                    "relation_type": "next",
                    "order": 1,
                }
            ],
        }

        parsed = parse_graph_text(f"```json\n{json.dumps(graph)}\n```", {"C1", "C2"})

        self.assertEqual(graph, parsed)

    def test_rejects_case_ids_outside_the_case_file(self) -> None:
        graph = {
            "schema_version": "2.0",
            "main_paths": [],
            "edges": [
                {
                    "edge_id": "E01",
                    "from_case_id": "C1",
                    "to_case_id": "C9",
                    "relation_type": "next",
                    "order": 1,
                }
            ],
        }

        with self.assertRaises(ValueError) as raised:
            parse_graph_text(json.dumps(graph), {"C1", "C2"})

        self.assertIn("C9", str(raised.exception))

    def test_retry_suffix_carries_validation_errors(self) -> None:
        suffix = build_retry_suffix(["invalid_json: 顶层必须是对象"])

        self.assertIn("未通过校验", suffix)
        self.assertIn("invalid_json", suffix)


if __name__ == "__main__":
    unittest.main()
