import unittest
from uuid import UUID

from testing_agent_ai_worker.tasks.functional_case_generate.case_ids import assign_case_ids

MODEL_ID = "MODEL-99"


def case(title, module="登录", steps="打开页面", expected="页面展示", case_id=None):
    item = {
        "case_module": module,
        "case_title": title,
        "test_steps": [f"1. {steps}"],
        "expected_results": [f"1. {expected}"],
    }
    if case_id is not None:
        item["case_id"] = case_id
    return item


def ids(cases):
    return [item.get("case_id") if isinstance(item, dict) else item for item in cases]


class AssignCaseIdsTests(unittest.TestCase):
    def assert_uuid4(self, value):
        parsed = UUID(value)
        self.assertEqual(parsed.version, 4)
        self.assertEqual(str(parsed), value)

    def test_every_case_gets_a_distinct_identifier(self):
        assigned = assign_case_ids([case("一"), case("二", "支付"), case("三")])
        for identifier in ids(assigned):
            self.assert_uuid4(identifier)
        self.assertEqual(len(set(ids(assigned))), 3)
        self.assertEqual(list(assigned[0])[:3], ["case_id", "case_module", "case_title"])

    def test_identifiers_do_not_repeat_across_sets(self):
        first = assign_case_ids([case("一"), case("二")])
        second = assign_case_ids([case("一"), case("二")])
        self.assertFalse(set(ids(first)) & set(ids(second)))

    def test_empty_set_stays_empty(self):
        self.assertEqual(assign_case_ids([]), [])

    def test_rewritten_content_keeps_identity_through_the_title(self):
        previous = assign_case_ids([case("一"), case("二")])
        assigned = assign_case_ids(
            [case("一", steps="新的步骤", expected="新的预期"), case("二")], previous
        )
        self.assertEqual(ids(assigned), ids(previous))

    def test_rewritten_title_keeps_identity_through_the_content(self):
        previous = assign_case_ids([case("一"), case("二")])
        assigned = assign_case_ids([case("一（补充说明）"), case("二")], previous)
        self.assertEqual(ids(assigned), ids(previous))

    def test_rewritten_title_and_content_keep_identity_by_position(self):
        previous = assign_case_ids([case("一"), case("二")])
        assigned = assign_case_ids(
            [
                case("一（重写）", steps="新的步骤"),
                case("二（重写）", steps="另一个步骤"),
            ],
            previous,
        )
        self.assertEqual(ids(assigned), ids(previous))

    def test_appended_case_gets_a_new_identifier(self):
        previous = assign_case_ids([case("一"), case("二")])
        assigned = assign_case_ids([case("一"), case("二"), case("三条新场景")], previous)
        self.assertEqual(ids(assigned)[:2], ids(previous))
        self.assertNotIn(ids(assigned)[2], ids(previous))

    def test_deleted_case_takes_its_identifier_with_it(self):
        previous = assign_case_ids([case("一"), case("二"), case("三")])
        assigned = assign_case_ids([case("一"), case("三")], previous)
        self.assertEqual(ids(assigned), [ids(previous)[0], ids(previous)[2]])
        self.assertNotIn(ids(previous)[1], ids(assigned))

    def test_case_next_to_a_deletion_keeps_its_identity(self):
        previous = assign_case_ids([case("一"), case("二", steps="提交订单"), case("三")])
        assigned = assign_case_ids([case("一（补充说明）"), case("三")], previous)
        self.assertEqual([ids(assigned)[0], ids(assigned)[1]], [ids(previous)[0], ids(previous)[2]])

    def test_matching_is_scoped_to_the_module(self):
        previous = assign_case_ids([case("一", module="登录"), case("一", module="支付")])
        assigned = assign_case_ids([case("一", module="支付")], previous)
        self.assertEqual(ids(assigned), [ids(previous)[1]])

    def test_model_supplied_ids_are_replaced(self):
        assigned = assign_case_ids([case("一", case_id=MODEL_ID), case("二", case_id=MODEL_ID)])
        self.assertNotIn(MODEL_ID, ids(assigned))
        self.assertEqual(len(set(ids(assigned))), 2)

    def test_unmatched_and_malformed_entries_are_tolerated(self):
        assigned = assign_case_ids(
            [case("一"), "not-a-case", {"case_module": "登录"}],
            [{"case_module": "登录", "name": "旧标题"}, "not-a-case", {"case_title": "无编号"}],
        )
        self.assertEqual(assigned[1], "not-a-case")
        self.assert_uuid4(ids(assigned)[0])
        self.assert_uuid4(ids(assigned)[2])
