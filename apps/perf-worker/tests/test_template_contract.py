from __future__ import annotations

from pathlib import Path

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "testing_agent_perf_worker"
    / "compiler"
    / "templates"
    / "main.js"
)


def test_template_exposes_stable_contract() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")

    assert "const plan = JSON.parse(open('plan.json'))" in text
    assert "export const options = plan.options" in text
    assert "new SharedArray" in text
    assert "iterationInTest" in text
    assert "function extractValue" in text
    assert "step.onFailure" in text
    assert "export function handleSummary" in text
    assert "'summary.json': JSON.stringify(data)" in text


def test_template_resolves_supported_placeholder_prefixes() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")

    for prefix in ("data.", "var.", "env."):
        assert f"indexOf('{prefix}')" in text
    for builtin in ("uuid", "timestamp", "iteration", "vu"):
        assert f"key === '{builtin}'" in text
