import json
import tempfile
import unittest

import yaml

from testing_agent_ai_worker.tasks.api_case_generate.chain import run_api_stage
from testing_agent_ai_worker.tasks.api_case_generate.design_contract import (
    DESIGN_SCHEMA_VERSION,
)

NAMES = ["read_alpha", "read_beta", "read_gamma", "read_delta", "read_epsilon", "read_zeta"]


def extraction(names: list[str]) -> dict:
    return {
        name: {
            "path": f"/api/{name}",
            "method": "GET",
            "query": {"q": "string (必传) # 查询关键字"},
            "response": {"id": "string # [关键提取]"},
        }
        for name in names
    }


def design_for(names: list[str]) -> dict:
    return {
        "schemaVersion": DESIGN_SCHEMA_VERSION,
        "interfaces": {
            name: {
                "method": "GET",
                "path": f"/api/{name}",
                "cases": [
                    {
                        "id": f"{name}_positive_full",
                        "title": f"{name}-正向-全参数",
                        "category": "positive",
                        "priority": "P0",
                        "intent": "验证完整参数查询成功",
                        "basis": {
                            "kind": "positive",
                            "section": "",
                            "field": "",
                            "constraint": "",
                        },
                        "patch": {},
                        "expected": {
                            "statusClass": "2xx",
                            "assertions": [
                                {
                                    "assertSource": "body_jsonpath",
                                    "targetExpr": "$.id",
                                    "comparator": "exists",
                                    "expectedValue": "",
                                }
                            ],
                        },
                    },
                    {
                        "id": f"{name}_missing_query",
                        "title": f"{name}-反向-缺少查询参数",
                        "category": "negative",
                        "priority": "P1",
                        "intent": "验证缺少必填查询参数时请求被拒绝",
                        "basis": {
                            "kind": "required",
                            "section": "query",
                            "field": "/q",
                            "constraint": "required",
                        },
                        "patch": {"query": [{"op": "remove", "path": "/q"}]},
                        "expected": {"statusClass": "4xx", "assertions": []},
                    },
                ],
                "uncovered": [],
            }
            for name in names
        },
    }


def prompt_payload(message: str) -> dict:
    return json.loads(message[message.index("{") : message.rindex("}") + 1])


def yaml_for(payload: dict) -> str:
    cases = []
    start = payload["batch"]["startOrderNo"]
    for offset, (name, interface) in enumerate(payload["apiDesign"]["interfaces"].items()):
        for inner, case in enumerate(interface["cases"]):
            order = start + offset * len(interface["cases"]) + inner
            status = case["expected"]["statusClass"]
            query = {"q": "value"}
            for op in case.get("patch", {}).get("query", []):
                if op["op"] == "remove" and op["path"] == "/q":
                    query.pop("q", None)
            rules = [
                {
                    "name": "状态码下界",
                    "orderNo": 1,
                    "assertSource": "status_code",
                    "targetExpr": "",
                    "comparator": "gte",
                    "expectedValue": "200" if status == "2xx" else "400",
                },
                {
                    "name": "状态码上界",
                    "orderNo": 2,
                    "assertSource": "status_code",
                    "targetExpr": "",
                    "comparator": "lt",
                    "expectedValue": "300" if status == "2xx" else "500",
                },
            ]
            for index, assertion in enumerate(case["expected"]["assertions"], start=3):
                rules.append(
                    {
                        "name": f"业务断言{index}",
                        "orderNo": index,
                        **assertion,
                    }
                )
            cases.append(
                {
                    "name": case["title"],
                    "description": case["intent"],
                    "enabled": True,
                    "orderNo": order,
                    "method": "GET",
                    "urlTemplate": f"/api/{name}",
                    "headers": {},
                    "query": query,
                    "bodyType": "none",
                    "bodyText": "",
                    "timeoutMs": 5000,
                    "continueOnFailure": False,
                    "extractRules": [],
                    "assertRules": rules,
                }
            )
    return yaml.safe_dump({"cases": cases}, allow_unicode=True, sort_keys=False)


class _Result:
    def __init__(self, content: str) -> None:
        self.content = content


class _Bot:
    def __init__(self, responder) -> None:
        self.responder = responder
        self.calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def run(self, message: str, session_key: str, **kwargs) -> _Result:
        self.calls.append(message)
        return _Result(self.responder(message))


class _Factory:
    def __init__(self, responder) -> None:
        self.bot = _Bot(responder)

    def __call__(self, **kwargs):
        return self.bot


class ApiStageBatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_design_uses_five_interface_batches_and_restores_order(self) -> None:
        workspace = self.enterContext(tempfile.TemporaryDirectory())
        events: list[dict] = []

        def respond(message: str) -> str:
            payload = prompt_payload(message)
            return json.dumps(design_for(payload["batch"]["interfaceNames"]))

        factory = _Factory(respond)
        output = await run_api_stage(
            stage="api_design",
            input_text=json.dumps(
                {
                    "apiExtraction": extraction(NAMES),
                    "requirement": {"requirementId": "r1", "name": "需求"},
                }
            ),
            session_key="run-1",
            workspace=workspace,
            from_config=factory,
            on_validation_progress=events.append,
        )

        result = json.loads(output)
        self.assertEqual(list(result["interfaces"]), NAMES)
        self.assertEqual(len(factory.bot.calls), 2)
        self.assertTrue(
            any(
                event.get("batchIndex") == 1
                and event.get("batchCount") == 2
                and event.get("interfaceNames") == NAMES[:5]
                for event in events
            )
        )
        self.assertTrue(
            any(
                event.get("batchIndex") == 2 and event.get("interfaceNames") == NAMES[5:]
                for event in events
            )
        )

    async def test_generation_uses_ten_case_batches_with_global_order(self) -> None:
        workspace = self.enterContext(tempfile.TemporaryDirectory())
        events: list[dict] = []
        extraction_data = extraction(NAMES)
        design = design_for(NAMES)

        factory = _Factory(lambda message: yaml_for(prompt_payload(message)))
        output = await run_api_stage(
            stage="generate",
            input_text=json.dumps(
                {
                    "apiExtraction": extraction_data,
                    "apiDesign": design,
                    "requirement": {"requirementId": "r1", "name": "需求"},
                }
            ),
            session_key="run-1",
            workspace=workspace,
            from_config=factory,
            on_validation_progress=events.append,
        )

        parsed = yaml.safe_load(output)
        self.assertEqual(len(parsed["cases"]), 12)
        self.assertEqual([case["orderNo"] for case in parsed["cases"]], list(range(1, 13)))
        self.assertEqual(len(factory.bot.calls), 2)
        self.assertTrue(
            any(event.get("batchIndex") == 1 and event.get("batchCount") == 2 for event in events)
        )
        self.assertTrue(
            any(event.get("batchIndex") == 2 and event.get("endOrderNo") == 12 for event in events)
        )

    async def test_design_revision_passes_current_subset(self) -> None:
        workspace = self.enterContext(tempfile.TemporaryDirectory())
        extraction_data = extraction(NAMES[:6])
        current = design_for(NAMES[:6])
        seen: list[dict] = []

        def respond(message: str) -> str:
            payload = prompt_payload(message)
            seen.append(payload)
            return json.dumps(design_for(payload["batch"]["interfaceNames"]))

        await run_api_stage(
            stage="api_design",
            input_text=json.dumps(
                {
                    "apiExtraction": extraction_data,
                    "currentDesign": current,
                    "revisionInstruction": "增加管理员角色场景",
                    "requirement": {"requirementId": "r1"},
                }
            ),
            session_key="run-1",
            workspace=workspace,
            from_config=_Factory(respond),
        )

        self.assertEqual(seen[0]["revisionInstruction"], "增加管理员角色场景")
        self.assertIn("read_alpha", seen[0]["currentDesign"]["interfaces"])
        self.assertNotIn("read_zeta", seen[0]["currentDesign"]["interfaces"])

    async def test_design_batch_failure_reports_batch_and_interfaces(self) -> None:
        workspace = self.enterContext(tempfile.TemporaryDirectory())
        calls = {"count": 0}

        def respond(message: str) -> str:
            calls["count"] += 1
            payload = prompt_payload(message)
            if payload["batch"]["index"] == 2:
                return "not-json"
            return json.dumps(design_for(payload["batch"]["interfaceNames"]))

        with self.assertRaisesRegex(ValueError, r"接口用例设计第 2/2 批（接口 read_zeta）失败"):
            await run_api_stage(
                stage="api_design",
                input_text=json.dumps(
                    {
                        "apiExtraction": extraction(NAMES),
                        "requirement": {"requirementId": "r1"},
                    }
                ),
                session_key="run-1",
                workspace=workspace,
                from_config=_Factory(respond),
            )
        self.assertEqual(calls["count"], 4)

    async def test_generation_batch_failure_reports_case_range(self) -> None:
        workspace = self.enterContext(tempfile.TemporaryDirectory())

        def respond(message: str) -> str:
            payload = prompt_payload(message)
            if payload["batch"]["index"] == 2:
                return yaml.safe_dump({"cases": []}, allow_unicode=True)
            return yaml_for(payload)

        with self.assertRaisesRegex(ValueError, r"API 用例生成第 2/2 批（用例 11-12）失败"):
            await run_api_stage(
                stage="generate",
                input_text=json.dumps(
                    {
                        "apiExtraction": extraction(NAMES),
                        "apiDesign": design_for(NAMES),
                        "requirement": {"requirementId": "r1"},
                    }
                ),
                session_key="run-1",
                workspace=workspace,
                from_config=_Factory(respond),
            )


if __name__ == "__main__":
    unittest.main()
