import unittest

from testing_agent_ai_worker.tasks.api_case_generate.design_contract import (
    DESIGN_SCHEMA_VERSION,
    DesignValidationError,
    validate_design_object,
)
from testing_agent_ai_worker.tasks.api_case_generate.generation_contract import (
    GenerationAlignmentError,
    validate_generated_cases_object,
)


def extraction() -> dict:
    return {
        "create_user": {
            "path": "/api/users",
            "method": "POST",
            "headers": {
                "Authorization": "Bearer {{access_token}} # [必传]",
            },
            "query": {"verbose": "boolean (可选) # 是否返回详情"},
            "json": {
                "name": "string (必传, maxLength:20) # 用户名",
                "password": "string (必传, minLength:8) # 密码",
                "age": "integer (可选, minimum:18, maximum:60) # 年龄",
                "role": "string (可选, enum:admin,user) # 角色",
                "email": "string (可选, format:email) # 邮箱",
            },
            "response": {
                "id": "string (format:uuid) # [关键提取] 用户 ID",
                "status": "string # 状态",
            },
        }
    }


def positive_case(case_id: str, title: str, *, patch: dict | None = None) -> dict:
    return {
        "id": case_id,
        "title": title,
        "category": "positive",
        "priority": "P0",
        "intent": title,
        "basis": {"kind": "positive", "section": "", "field": "", "constraint": ""},
        "patch": patch or {},
        "expected": {
            "statusClass": "2xx",
            "assertions": [
                {
                    "assertSource": "body_jsonpath",
                    "targetExpr": "$.id",
                    "comparator": "exists",
                    "expectedValue": "",
                }
            ]
            if case_id == "create_user_positive_full"
            else [],
        },
    }


def negative_case(
    case_id: str,
    title: str,
    *,
    kind: str,
    section: str,
    field: str,
    constraint: str,
    patch: dict,
) -> dict:
    return {
        "id": case_id,
        "title": title,
        "category": "negative",
        "priority": "P1",
        "intent": title,
        "basis": {
            "kind": kind,
            "section": section,
            "field": field,
            "constraint": constraint,
        },
        "patch": patch,
        "expected": {"statusClass": "4xx", "assertions": []},
    }


def boundary_case(
    case_id: str,
    title: str,
    *,
    value: int,
    status_class: str,
    constraint: str = "minimum:18",
) -> dict:
    return {
        "id": case_id,
        "title": title,
        "category": "boundary",
        "priority": "P1",
        "intent": title,
        "basis": {
            "kind": "constraint",
            "section": "json",
            "field": "/age",
            "constraint": constraint,
        },
        "patch": {"json": [{"op": "replace", "path": "/age", "value": value}]},
        "expected": {"statusClass": status_class, "assertions": []},
    }


def design() -> dict:
    return {
        "schemaVersion": DESIGN_SCHEMA_VERSION,
        "interfaces": {
            "create_user": {
                "method": "POST",
                "path": "/api/users",
                "cases": [
                    positive_case("create_user_positive_full", "创建用户-正向-全参数"),
                    positive_case(
                        "create_user_positive_minimal",
                        "创建用户-正向-仅必填",
                        patch={
                            "query": [{"op": "remove", "path": "/verbose"}],
                            "json": [
                                {"op": "remove", "path": "/age"},
                                {"op": "remove", "path": "/role"},
                                {"op": "remove", "path": "/email"},
                            ],
                        },
                    ),
                    negative_case(
                        "create_user_missing_password",
                        "创建用户-反向-缺少必填密码",
                        kind="required",
                        section="json",
                        field="/password",
                        constraint="required",
                        patch={"json": [{"op": "remove", "path": "/password"}]},
                    ),
                    negative_case(
                        "create_user_missing_name",
                        "创建用户-反向-缺少必填用户名",
                        kind="required",
                        section="json",
                        field="/name",
                        constraint="required",
                        patch={"json": [{"op": "remove", "path": "/name"}]},
                    ),
                    negative_case(
                        "create_user_missing_authorization",
                        "创建用户-反向-缺少认证头",
                        kind="required",
                        section="headers",
                        field="/Authorization",
                        constraint="required",
                        patch={"headers": [{"op": "remove", "path": "/Authorization"}]},
                    ),
                    negative_case(
                        "create_user_age_wrong_type",
                        "创建用户-反向-年龄类型非法",
                        kind="type",
                        section="json",
                        field="/age",
                        constraint="integer",
                        patch={"json": [{"op": "replace", "path": "/age", "value": "old"}]},
                    ),
                    negative_case(
                        "create_user_role_invalid_enum",
                        "创建用户-反向-角色枚举非法",
                        kind="constraint",
                        section="json",
                        field="/role",
                        constraint="enum:admin,user",
                        patch={"json": [{"op": "replace", "path": "/role", "value": "guest"}]},
                    ),
                    boundary_case(
                        "create_user_age_at_minimum",
                        "创建用户-边界-年龄等于最小值",
                        value=18,
                        status_class="2xx",
                    ),
                    boundary_case(
                        "create_user_age_below_minimum",
                        "创建用户-边界-年龄低于最小值",
                        value=17,
                        status_class="4xx",
                    ),
                    negative_case(
                        "create_user_email_invalid_format",
                        "创建用户-反向-邮箱格式非法",
                        kind="constraint",
                        section="json",
                        field="/email",
                        constraint="format:email",
                        patch={
                            "json": [{"op": "replace", "path": "/email", "value": "not-an-email"}]
                        },
                    ),
                ],
                "uncovered": [],
            }
        },
    }


def yaml_case(
    order: int,
    design_case: dict,
    *,
    body: dict,
    headers: dict | None = None,
    assertions: list[dict] | None = None,
) -> dict:
    status_class = design_case["expected"]["statusClass"]
    rules = [
        {
            "name": "状态码下界",
            "enabled": True,
            "orderNo": 1,
            "assertSource": "status_code",
            "targetExpr": "",
            "comparator": "gte",
            "expectedValue": "200" if status_class == "2xx" else "400",
        },
        {
            "name": "状态码上界",
            "enabled": True,
            "orderNo": 2,
            "assertSource": "status_code",
            "targetExpr": "",
            "comparator": "lt",
            "expectedValue": "300" if status_class == "2xx" else "500",
        },
    ]
    for index, item in enumerate(assertions or [], start=3):
        rules.append({"name": f"业务断言{index}", "enabled": True, "orderNo": index, **item})
    return {
        "name": design_case["title"],
        "description": design_case["intent"],
        "enabled": True,
        "orderNo": order,
        "method": "POST",
        "urlTemplate": "/api/users",
        "headers": headers if headers is not None else {"Authorization": "Bearer {{access_token}}"},
        "bodyType": "json",
        "bodyJson": body,
        "timeoutMs": 5000,
        "continueOnFailure": False,
        "extractRules": [],
        "assertRules": rules,
    }


def generated_cases() -> dict:
    rows = design()["interfaces"]["create_user"]["cases"]
    full = {
        "name": "张三",
        "password": "password1",
        "age": 30,
        "role": "admin",
        "email": "a@example.com",
    }
    minimal = {"name": "张三", "password": "password1"}
    missing_password = {"name": "张三", "age": 30, "role": "admin", "email": "a@example.com"}
    missing_name = {"password": "password1", "age": 30, "role": "admin", "email": "a@example.com"}
    wrong_type = {
        "name": "张三",
        "password": "password1",
        "age": "old",
        "role": "admin",
        "email": "a@example.com",
    }
    invalid_enum = {
        "name": "张三",
        "password": "password1",
        "age": 30,
        "role": "guest",
        "email": "a@example.com",
    }
    at_minimum = {
        "name": "张三",
        "password": "password1",
        "age": 18,
        "role": "admin",
        "email": "a@example.com",
    }
    below_minimum = {
        "name": "张三",
        "password": "password1",
        "age": 17,
        "role": "admin",
        "email": "a@example.com",
    }
    invalid_format = {
        "name": "张三",
        "password": "password1",
        "age": 30,
        "role": "admin",
        "email": "not-an-email",
    }
    bodies = [
        full,
        minimal,
        missing_password,
        missing_name,
        full,
        wrong_type,
        invalid_enum,
        at_minimum,
        below_minimum,
        invalid_format,
    ]
    assertion = [
        {
            "assertSource": "body_jsonpath",
            "targetExpr": "$.id",
            "comparator": "exists",
            "expectedValue": "",
        }
    ]
    cases = []
    for index, (row, body) in enumerate(zip(rows, bodies, strict=True), start=1):
        cases.append(
            yaml_case(
                index,
                row,
                body=body,
                headers={} if row["id"].endswith("missing_authorization") else None,
                assertions=assertion if row["id"].endswith("positive_full") else None,
            )
        )
    return {"cases": cases}


class DesignContractTests(unittest.TestCase):
    def test_accepts_valid_design(self) -> None:
        result = validate_design_object(design(), extraction())
        self.assertEqual(len(result["interfaces"]["create_user"]["cases"]), 10)

    def test_rejects_interface_set_mismatch(self) -> None:
        value = design()
        value["interfaces"]["another"] = value["interfaces"].pop("create_user")
        with self.assertRaisesRegex(DesignValidationError, "接口集合"):
            validate_design_object(value, extraction())

    def test_rejects_required_basis_not_in_extraction(self) -> None:
        value = design()
        case = value["interfaces"]["create_user"]["cases"][2]
        case["basis"]["field"] = "/unknown"
        with self.assertRaisesRegex(DesignValidationError, "不存在"):
            validate_design_object(value, extraction())

    def test_rejects_boundary_status_mismatch(self) -> None:
        value = design()
        value["interfaces"]["create_user"]["cases"][7]["expected"]["statusClass"] = "4xx"
        with self.assertRaisesRegex(DesignValidationError, "越界"):
            validate_design_object(value, extraction())

    def test_rejects_short_boundary_pair(self) -> None:
        value = design()
        cases = value["interfaces"]["create_user"]["cases"]
        value["interfaces"]["create_user"]["cases"] = [
            case for case in cases if case["id"] != "create_user_age_below_minimum"
        ]
        with self.assertRaisesRegex(DesignValidationError, "边界约束"):
            validate_design_object(value, extraction())

    def test_rejects_assertion_not_in_response(self) -> None:
        value = design()
        value["interfaces"]["create_user"]["cases"][0]["expected"]["assertions"][0][
            "targetExpr"
        ] = "$.unknown"
        with self.assertRaisesRegex(DesignValidationError, "响应"):
            validate_design_object(value, extraction())

    def test_rejects_duplicate_titles_and_ids(self) -> None:
        value = design()
        first, second = value["interfaces"]["create_user"]["cases"][:2]
        second["title"] = first["title"].upper()
        with self.assertRaisesRegex(DesignValidationError, "title"):
            validate_design_object(value, extraction())

    def test_rejects_patch_remove_missing_target(self) -> None:
        value = design()
        value["interfaces"]["create_user"]["cases"][1]["patch"]["json"].append(
            {"op": "remove", "path": "/unknown"}
        )
        with self.assertRaisesRegex(DesignValidationError, "不存在"):
            validate_design_object(value, extraction())


class GenerationAlignmentTests(unittest.TestCase):
    def test_accepts_aligned_cases(self) -> None:
        cases = validate_generated_cases_object(generated_cases(), extraction(), design())
        self.assertEqual(len(cases.cases), 10)

    def test_rejects_extra_case(self) -> None:
        value = generated_cases()
        value["cases"].append(
            dict(value["cases"][-1], name="额外用例", description="额外", orderNo=11)
        )
        with self.assertRaisesRegex(GenerationAlignmentError, "数量"):
            validate_generated_cases_object(value, extraction(), design())

    def test_rejects_disabled_case_or_assertion(self) -> None:
        value = generated_cases()
        value["cases"][0]["enabled"] = False
        with self.assertRaisesRegex(GenerationAlignmentError, "必须启用"):
            validate_generated_cases_object(value, extraction(), design())

        value = generated_cases()
        value["cases"][0]["assertRules"][0]["enabled"] = False
        with self.assertRaisesRegex(GenerationAlignmentError, "必须启用"):
            validate_generated_cases_object(value, extraction(), design())

    def test_rejects_missing_required_or_extra_body_fields(self) -> None:
        value = generated_cases()
        value["cases"][0]["bodyJson"] = {}
        with self.assertRaisesRegex(GenerationAlignmentError, "缺少必传字段"):
            validate_generated_cases_object(value, extraction(), design())

        value = generated_cases()
        value["cases"][0]["bodyJson"]["admin"] = True
        with self.assertRaisesRegex(GenerationAlignmentError, "基线之外"):
            validate_generated_cases_object(value, extraction(), design())

    def test_rejects_removing_path_parameter(self) -> None:
        extraction_value = extraction()
        extraction_value["create_user"]["path"] = "/api/users/{userId}"
        extraction_value["create_user"]["path_params"] = {"userId": "string (必传) # 用户 ID"}
        value = design()
        value["interfaces"]["create_user"]["path"] = "/api/users/{userId}"
        case = value["interfaces"]["create_user"]["cases"][2]
        case["basis"] = {
            "kind": "required",
            "section": "path_params",
            "field": "/userId",
            "constraint": "required",
        }
        case["patch"] = {"path_params": [{"op": "remove", "path": "/userId"}]}
        with self.assertRaisesRegex(DesignValidationError, "路径参数不能删除"):
            validate_design_object(value, extraction_value)

    def test_rejects_repaired_invalid_value(self) -> None:
        value = generated_cases()
        value["cases"][5]["bodyJson"]["age"] = 20
        with self.assertRaisesRegex(GenerationAlignmentError, "不一致"):
            validate_generated_cases_object(value, extraction(), design())

    def test_rejects_extra_extract_rules(self) -> None:
        value = generated_cases()
        value["cases"][0]["extractRules"] = [
            {
                "name": "提取ID",
                "enabled": True,
                "orderNo": 1,
                "source": "body_jsonpath",
                "sourceExpr": "$.id",
                "varKey": "id",
                "defaultValue": "",
            }
        ]
        with self.assertRaisesRegex(GenerationAlignmentError, "提取规则"):
            validate_generated_cases_object(value, extraction(), design())

    def test_rejects_missing_design_assertion(self) -> None:
        value = generated_cases()
        value["cases"][0]["assertRules"] = value["cases"][0]["assertRules"][:2]
        with self.assertRaisesRegex(GenerationAlignmentError, "业务断言"):
            validate_generated_cases_object(value, extraction(), design())

    def test_accepts_global_order_offset_for_batch(self) -> None:
        batch_design = {
            "schemaVersion": DESIGN_SCHEMA_VERSION,
            "interfaces": {
                "create_user": {
                    "method": "POST",
                    "path": "/api/users",
                    "cases": design()["interfaces"]["create_user"]["cases"][9:],
                    "uncovered": [],
                }
            },
        }
        batch_cases = {"cases": [dict(generated_cases()["cases"][9], orderNo=10)]}
        result = validate_generated_cases_object(
            batch_cases,
            extraction(),
            batch_design,
            start_order_no=10,
        )
        self.assertEqual(result.cases[0].orderNo, 10)


if __name__ == "__main__":
    unittest.main()
