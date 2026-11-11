"""Run: python3 -m unittest discover -s scripts -p 'test_*.py' -v"""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from case_store import ContractError, case_index, current_case_ids, load_request, load_store, read_json
from query_cases import get_cases, search_cases
from validate_graph import graph_index, validate_incremental

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parent / "references" / "examples"


class GraphToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="case-graph-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = read_json(EXAMPLES / "cases.json")
        self.file = self.write("cases.json", self.data)
        self.store = load_store(str(self.file))
        self.first = read_json(EXAMPLES / "round-1-output.json")
        self.second = read_json(EXAMPLES / "round-2-output.json")
        self.review = read_json(EXAMPLES / "round-2-change-review.json")
        self.empty = {"schema_version": "2.0", "main_paths": [], "edges": []}

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def request(self, round_number=2):
        data = read_json(EXAMPLES / ("round-%d-input.json" % round_number))
        data["case_file_path"] = str(self.file)
        return data

    def cli(self, script, *args):
        return subprocess.run([sys.executable, str(HERE / script), *map(str, args)],
                              capture_output=True, text=True, check=False)

    def test_two_rounds_cli_and_read_only_store(self):
        before = hashlib.sha256(self.file.read_bytes()).hexdigest()
        for number in (1, 2):
            request = self.write("request.json", self.request(number))
            check = self.cli("validate_graph.py", "--input", request, "--check-input")
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            args = ["--input", request, "--graph", EXAMPLES / ("round-%d-output.json" % number)]
            if number == 2:
                args += ["--changes", EXAMPLES / "round-2-change-review.json"]
            result = self.cli("validate_graph.py", *args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(json.loads(result.stdout)["valid"])
        result = self.cli("query_cases.py", "get", "--case-file", self.file, "--case-ids", '["C02"]')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["cases"], [self.store["C02"]])
        self.assertEqual(hashlib.sha256(self.file.read_bytes()).hexdigest(), before)
        self.assertTrue(self.file.exists())

    def test_query_ten_allowed_eleven_rejected(self):
        records = [dict(self.store["C01"], case_id="T%02d" % i) for i in range(11)]
        store = case_index(records)
        self.assertEqual(len(get_cases(store, list(store)[:10])["cases"]), 10)
        with self.assertRaises(ContractError):
            get_cases(store, list(store))

    def test_query_empty_duplicate_or_non_array_rejected(self):
        for ids in ([], ["C01", "C01"], "C01", [None], [""]):
            with self.subTest(ids=ids), self.assertRaises(ContractError):
                get_cases(self.store, ids)

    def test_original_ids_are_exact_and_missing_is_explicit(self):
        result = get_cases(self.store, ["C03", "c01", "C01 ", "C01"])
        self.assertEqual([c["case_id"] for c in result["cases"]], ["C03", "C01"])
        self.assertEqual(result["not_found_case_ids"], ["c01", "C01 "])

    def test_missing_id_cli_retains_found_records(self):
        result = self.cli("query_cases.py", "get", "--case-file", self.file, "--case-ids", '["C02","missing"]')
        self.assertEqual(result.returncode, 3)
        data = json.loads(result.stdout)
        self.assertEqual(data["not_found_case_ids"], ["missing"])
        self.assertEqual(data["cases"][0]["case_id"], "C02")

    def test_cli_rejects_oversized_query_before_file_read(self):
        result = self.cli("query_cases.py", "get", "--case-file", self.root / "absent.json",
                          "--case-ids", json.dumps([str(i) for i in range(11)]))
        self.assertEqual(result.returncode, 2)
        self.assertIn("at most 10", result.stdout)
        self.assertNotIn("Cannot read", result.stdout)

    def test_opaque_ids_with_shell_characters_are_data(self):
        cid = '--case $() `literal` 空格 " quote'
        self.write("cases.json", {"cases": [dict(self.store["C01"], case_id=cid)]})
        result = self.cli("query_cases.py", "get", "--case-file", self.file, "--case-ids", json.dumps([cid]))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["cases"][0]["case_id"], cid)

    def test_long_case_is_not_truncated(self):
        case = copy.deepcopy(self.store["C01"])
        case["expected_results"] = ["完整断言" * 20000]
        result = get_cases({"C01": case}, ["C01"])
        self.assertEqual(result["cases"][0], case)

    def test_search_limit_compact_results_and_no_listing(self):
        store = case_index([dict(self.store["C01"], case_id="T%02d" % i) for i in range(20)])
        result = search_cases(store, "提交", limit=10)
        self.assertEqual(len(result["matches"]), 10)
        self.assertTrue(result["has_more"])
        self.assertEqual(set(result["matches"][0]), {"case_id", "case_module", "case_title"})
        for query, limit in [("", 10), ("*", 10), ("提交", 11), ("提交", 0), ("提交", True)]:
            with self.subTest(query=query, limit=limit), self.assertRaises(ContractError):
                search_cases(store, query, limit=limit)

    def test_search_full_content_and_exact_module(self):
        result = search_cases(self.store, "故障 消除", limit=3)
        # No literal match for 消除 in case text; keyword search makes no semantic claim.
        self.assertEqual(result["matches"], [])
        result = search_cases(self.store, "故障 解除", limit=3)
        self.assertEqual(result["matches"][0]["case_id"], "C05")
        result = search_cases(self.store, module="账号资料")
        self.assertEqual([x["case_id"] for x in result["matches"]], ["C07"])

    def test_store_wrapper_is_only_cases(self):
        self.write("cases.json", dict(self.data, requirements=[]))
        with self.assertRaises(ContractError):
            load_store(str(self.file))

    def test_duplicate_ids_and_incomplete_cases_rejected(self):
        for records in ([self.store["C01"], self.store["C01"]], [{"case_id": "C01"}]):
            with self.subTest(records=len(records)), self.assertRaises(ContractError):
                case_index(records)

    def test_step_result_mismatch_rejected(self):
        case = copy.deepcopy(self.store["C01"])
        case["expected_results"].append("多余预期")
        with self.assertRaises(ContractError):
            case_index([case])

    def test_duplicate_json_keys_and_nonfinite_numbers_rejected(self):
        for body in ('{"cases":[],"cases":[]}', '{"cases":[],"x":NaN}'):
            self.file.write_text(body, encoding="utf-8")
            with self.assertRaises(ContractError):
                read_json(self.file)

    def test_input_no_longer_accepts_redundant_cases(self):
        request = self.request()
        request["cases"] = [self.store["C03"]]
        with self.assertRaises(ContractError):
            load_request(self.write("input.json", request))

    def test_mapping_must_reference_case_file(self):
        request = self.request()
        request["case_requirement_links"][0]["case_ids"].append("invented")
        with self.assertRaises(ContractError):
            load_request(self.write("input.json", request))

    def test_current_batch_is_derived_from_links(self):
        request = self.request()
        request["case_requirement_links"][0]["case_ids"].append("C01")
        loaded, _ = load_request(self.write("input.json", request))
        self.assertIn("C01", current_case_ids(loaded))
        self.assertNotIn("cases", loaded)

    def test_unbound_ids_are_included_in_batch(self):
        loaded, _ = load_request(self.write("input.json", self.request(1)))
        self.assertEqual(current_case_ids(loaded), ["C01", "C02", "C07"])
        result = self.cli("validate_graph.py", "--input", self.root / "input.json", "--check-input")
        summary = json.loads(result.stdout)
        self.assertEqual(summary["batch_case_count"], 3)
        self.assertNotIn("cases", summary)
        self.assertNotIn("advisories", summary)

    def test_all_unbound_cases_without_requirements_are_valid(self):
        request = self.request()
        request["requirements"] = []
        request["case_requirement_links"] = [{"requirement_id": None, "case_ids": ["C03", "C05"]}]
        loaded, _ = load_request(self.write("input.json", request))
        self.assertEqual(current_case_ids(loaded), ["C03", "C05"])

    def test_bound_and_unbound_overlap_rejected(self):
        for null_first in (True, False):
            request = self.request()
            bound = {"requirement_id": "R01", "case_ids": ["C03"]}
            unbound = {"requirement_id": None, "case_ids": ["C03"]}
            request["case_requirement_links"] = [unbound, bound] if null_first else [bound, unbound]
            with self.subTest(null_first=null_first), self.assertRaises(ContractError):
                load_request(self.write("input.json", request))

    def test_duplicate_null_groups_and_unknown_unbound_id_rejected(self):
        for groups in ([{"requirement_id": None, "case_ids": ["C03"]}, {"requirement_id": None, "case_ids": ["C05"]}],
                       [{"requirement_id": None, "case_ids": ["invented"]}],
                       [{"requirement_id": None, "case_ids": ["C03", "C03"]}]):
            request = self.request()
            request["case_requirement_links"] = groups
            with self.subTest(groups=groups), self.assertRaises(ContractError):
                load_request(self.write("input.json", request))

    def test_unbound_requires_actual_json_null(self):
        for rid in ("", "null", False, [], {}):
            request = self.request()
            request["case_requirement_links"] = [{"requirement_id": rid, "case_ids": ["C03"]}]
            with self.subTest(rid=rid), self.assertRaises(ContractError):
                load_request(self.write("input.json", request))

    def test_many_to_many_counts_unique_ids_not_mapping_occurrences(self):
        request = self.request()
        request["requirements"].append({"requirement_id": "R02", "requirement_title": "下载权限", "requirement_content": "有权限方可下载。"})
        request["case_requirement_links"] = [
            {"requirement_id": "R01", "case_ids": ["C03", "C06"]},
            {"requirement_id": "R02", "case_ids": ["C06"]},
            {"requirement_id": None, "case_ids": ["C07"]}]
        loaded, _ = load_request(self.write("input.json", request))
        self.assertEqual(current_case_ids(loaded), ["C03", "C06", "C07"])
        self.assertEqual(len(loaded["case_requirement_links"]), 3)

    def test_thirty_is_advisory_and_uses_deduplicated_count(self):
        records = [dict(self.store["C01"], case_id="T%02d" % i) for i in range(31)]
        self.write("cases.json", {"cases": records})
        for count in (30, 31):
            request = self.request()
            request["existing_graph"] = self.empty
            ids = [case["case_id"] for case in records[:count]]
            request["requirements"].append({"requirement_id": "R02", "requirement_title": "附加要求", "requirement_content": "同一用例可以绑定多个需求。"})
            request["case_requirement_links"] = [{"requirement_id": "R01", "case_ids": ids},
                                                {"requirement_id": "R02", "case_ids": ids}]
            request_path = self.write("input.json", request)
            result = self.cli("validate_graph.py", "--input", request_path, "--check-input")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["batch_case_count"], count)
            self.assertEqual("advisories" in summary, count > 30)

    def test_mapping_unknown_requirement_and_repeated_ids_rejected(self):
        for rid, ids in (("unknown", ["C03"]), ("R01", ["C03", "C03"])):
            request = self.request()
            request["case_requirement_links"] = [{"requirement_id": rid, "case_ids": ids}]
            with self.subTest(rid=rid), self.assertRaises(ContractError):
                load_request(self.write("input.json", request))

    def test_empty_batch_preserves_existing_graph(self):
        request = self.request()
        request["case_requirement_links"] = []
        loaded, store = load_request(self.write("input.json", request))
        self.assertEqual(validate_incremental(loaded["existing_graph"], self.first, store)["edge_count"], 1)
        with self.assertRaises(ContractError):
            validate_incremental(loaded["existing_graph"], self.empty, store)

    def test_old_cases_outside_current_batch_are_valid(self):
        request, store = load_request(self.write("input.json", self.request()))
        self.assertNotIn("C01", current_case_ids(request))
        self.assertEqual(validate_incremental(self.first, self.second, store, self.review)["edge_count"], 7)

    def test_unknown_graph_ids_rejected(self):
        graph = copy.deepcopy(self.first)
        graph["edges"][0]["to_case_id"] = "invented"
        with self.assertRaises(ContractError):
            graph_index(graph, self.store)

    def test_graph_schema_and_order_failures(self):
        variations = []
        graph = copy.deepcopy(self.first)
        graph["flows"] = []
        variations.append(graph)
        for key, value in (("order", True), ("order", 1.0), ("order", 0), ("order", "1"),
                           ("relation_type", "parallel"), ("to_case_id", "C01"), ("label", "extra")):
            graph = copy.deepcopy(self.first)
            graph["edges"][0][key] = value
            variations.append(graph)
        for i, graph in enumerate(variations):
            with self.subTest(i=i), self.assertRaises(ContractError):
                graph_index(graph, self.store)

    def test_duplicate_endpoint_and_order_rejected(self):
        for changes in ({"to_case_id": "C03"}, {"order": 2}):
            graph = copy.deepcopy(self.first)
            graph["edges"].append(dict(graph["edges"][0], edge_id="E02", **changes))
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                graph_index(graph, self.store)

    def test_paths_require_next_edges_and_nonredundant_sequences(self):
        for ids in (["C01"], ["C01", "C01"], ["C01", "C03"]):
            graph = copy.deepcopy(self.first)
            graph["main_paths"][0]["case_ids"] = ids
            with self.subTest(ids=ids), self.assertRaises(ContractError):
                graph_index(graph, self.store)
        graph = copy.deepcopy(self.second)
        graph["main_paths"].append({"path_id": "P02", "case_ids": ["C02", "C03"]})
        with self.assertRaises(ContractError):
            graph_index(graph, self.store)

    def test_multiple_parents_and_supported_cycle_not_forced_to_tree(self):
        graph = copy.deepcopy(self.second)
        graph["edges"].append({"edge_id": "E08", "from_case_id": "C08", "to_case_id": "C04", "relation_type": "next", "order": 1})
        self.assertEqual(len(graph_index(graph, self.store)[0]), 8)

    def test_path_extension_requires_boundary_review(self):
        with self.assertRaises(ContractError):
            validate_incremental(self.first, self.second, self.store)
        bad = copy.deepcopy(self.review)
        bad["path_changes"][0]["checked_case_ids"] = ["C03", "C06"]
        with self.assertRaises(ContractError):
            validate_incremental(self.first, self.second, self.store, bad)
        self.assertEqual(validate_incremental(self.first, self.second, self.store, self.review)["added_edge_count"], 6)

    def test_justified_removal_is_allowed_but_missing_or_stale_review_is_not(self):
        review = {"edge_changes": [{"edge_id": "E01", "reason": "两端没有实际业务衔接", "checked_case_ids": ["C01", "C02"]}],
                  "path_changes": [{"path_id": "P01", "reason": "依据不足，撤销该主骨", "checked_case_ids": ["C01", "C02"]}]}
        self.assertEqual(validate_incremental(self.first, self.empty, self.store, review)["removed_edge_count"], 1)
        with self.assertRaises(ContractError):
            validate_incremental(self.first, self.empty, self.store)
        with self.assertRaises(ContractError):
            validate_incremental(self.first, self.first, self.store, review)

    def test_unchanged_history_cannot_be_renumbered(self):
        graph = copy.deepcopy(self.first)
        graph["edges"][0]["edge_id"] = "E99"
        review = {"edge_changes": [{"edge_id": "E01", "reason": "尝试重编号", "checked_case_ids": ["C01", "C02"]}], "path_changes": []}
        with self.assertRaises(ContractError):
            validate_incremental(self.first, graph, self.store, review)

    def test_edge_identity_cannot_be_repurposed(self):
        old = dict(self.first, main_paths=[])
        graph = copy.deepcopy(old)
        graph["edges"][0]["relation_type"] = "branch"
        with self.assertRaises(ContractError):
            validate_incremental(old, graph, self.store)

    def test_display_order_can_change_without_semantic_review(self):
        graph = copy.deepcopy(self.first)
        graph["edges"][0]["order"] = 5
        self.assertEqual(validate_incremental(self.first, graph, self.store)["removed_edge_count"], 0)


if __name__ == "__main__":
    unittest.main()
