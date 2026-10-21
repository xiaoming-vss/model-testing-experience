import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import yaml

from testing_agent_ai_worker_pi.tasks.api_case_generate.chain import run_chain
from testing_agent_ai_worker_pi.tasks.api_case_generate.contracts import (
    validate_cases,
    validate_extraction,
)

EXTRACTED = '{"login":{"path":"/login","method":"POST","response":{"token":"string"}}}'
CASES = "cases:\n  - {name: login, orderNo: 1, method: POST, urlTemplate: /login}"


class Bot:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def run(self, message, **kwargs):
        self.calls.append((message, kwargs))
        value = next(self.outputs)
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(content=value) if isinstance(value, str) else value


class ApiRepairTests(unittest.IsolatedAsyncioTestCase):
    async def run_chain(self, bot, root, progress, extracted):
        return await run_chain(
            openapi_text='{"openapi":"3.0.0","paths":{}}',
            session_key="run",
            extractor_skill_name="openapi-test-config-extractor",
            generator_skill_name="api-cases-yaml-generator",
            workspace=root,
            extra_instruction="只处理登录",
            from_config=lambda **kw: bot,
            on_extractor_result=extracted.append,
            on_validation_progress=lambda event, prior: progress.append((event, prior)),
        )

    async def test_repairs_each_stage_without_repeating_successful_extraction(self):
        bot = Bot(["not json", EXTRACTED, "cases: []", CASES])
        progress, extracted = [], []
        with tempfile.TemporaryDirectory() as root:
            result = await self.run_chain(bot, root, progress, extracted)
            self.assertEqual(len(list(Path(root).rglob("attempt-*.json"))), 4)
        self.assertEqual(result.generator_output, CASES)
        self.assertEqual(extracted, [EXTRACTED])
        self.assertEqual(
            [p[0]["stage"] for p in progress], ["openapi_extract", "api_case_generating"]
        )
        self.assertEqual(progress[1][1], EXTRACTED)
        self.assertTrue(bot.calls[1][0].startswith(bot.calls[0][0]))
        self.assertTrue(bot.calls[3][0].startswith(bot.calls[2][0]))
        self.assertIn("只处理登录", bot.calls[3][0])
        self.assertTrue(all(call[1]["session_key"] == "run" for call in bot.calls))

    async def test_exhaustion_in_each_stage_does_not_publish_invalid_output(self):
        for values, expected_calls, expected_extracted in [
            (["{}"] * 3, 3, []),
            ([EXTRACTED] + ["cases: []"] * 3, 4, [EXTRACTED]),
        ]:
            bot, extracted = Bot(values), []
            with tempfile.TemporaryDirectory() as root:
                with self.assertRaisesRegex(ValueError, "3 次"):
                    await self.run_chain(bot, root, [], extracted)
            self.assertEqual(len(bot.calls), expected_calls)
            self.assertEqual(extracted, expected_extracted)

    async def test_service_failures_and_truncation_do_not_trigger_repair(self):
        for failure in [
            RuntimeError("network"),
            SimpleNamespace(content="{}", error="denied"),
            SimpleNamespace(content=EXTRACTED, stop_reason="max_tokens"),
        ]:
            bot = Bot([failure])
            with tempfile.TemporaryDirectory() as root:
                with self.assertRaises((RuntimeError, ValueError)):
                    await self.run_chain(bot, root, [], [])
            self.assertEqual(len(bot.calls), 1)


class ApiContractTests(unittest.TestCase):
    def test_rejects_unimportable_fields_rules_and_body(self):
        good = yaml.safe_load(CASES)
        for field, value in [
            ("method", "INVALID"),
            ("orderNo", True),
            ("url", "/wrong"),
            ("bodyJson", []),
            ("extractRules", [{"name": "token", "source": "missing", "varKey": "token"}]),
            (
                "assertRules",
                [{"name": "status", "assertSource": "status_code", "comparator": "bad"}],
            ),
        ]:
            data = deepcopy(good)
            data["cases"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_cases(yaml.safe_dump(data))
        with self.assertRaises(ValueError):
            validate_cases(CASES.replace("orderNo: 1", "orderNo: 1, orderNo: 2"))
        with self.assertRaises(ValueError):
            validate_extraction('{"meta":{},"config":{}}')
        with self.assertRaises(ValueError):
            validate_extraction(EXTRACTED.replace('"POST"', '["POST"]'))

    def test_valid_rules_and_templates_are_preserved(self):
        data = yaml.safe_load(CASES)
        data["cases"][0].update(
            bodyType="json",
            bodyJson={"password": "{{password}}"},
            extractRules=[
                {
                    "name": "token",
                    "source": "body_jsonpath",
                    "varKey": "token",
                    "sourceExpr": "$.token",
                }
            ],
            assertRules=[
                {
                    "name": "status",
                    "assertSource": "status_code",
                    "comparator": "eq",
                    "expectedValue": "200",
                }
            ],
        )
        validate_cases(yaml.safe_dump(data))
        validate_extraction(EXTRACTED)
