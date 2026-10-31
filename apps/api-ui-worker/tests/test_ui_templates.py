from __future__ import annotations

import pytest

from test_worker.ui.templates import RenderContext, referenced_names, render_field


def render(
    template: str,
    variables: dict[str, str] | None = None,
    *,
    field: str = "operationValue",
    locator_type: str = "",
    keyword: str = "input",
) -> str:
    return render_field(
        template,
        variables or {},
        RenderContext(field, locator_type, keyword, {}),
    )


def test_literal_locators_insert_the_value_unchanged() -> None:
    value = '张三 O\'Neil "测试"'
    assert (
        render("{{name}}", {"name": value}, field="locatorValue", locator_type="text")
        == value
    )
    assert (
        render(
            "{{name}}",
            {"name": value},
            field="locatorValue",
            locator_type="placeholder",
        )
        == value
    )


def test_xpath_uses_single_quotes_for_plain_values() -> None:
    assert (
        render(
            "//tr[td={{name|xpath}}]",
            {"name": "新版本"},
            field="locatorValue",
            locator_type="xpath",
        )
        == "//tr[td='新版本']"
    )


def test_xpath_switches_quotes_when_value_contains_single_quote() -> None:
    assert (
        render(
            "//tr[td={{name|xpath}}]",
            {"name": "O'Neil"},
            field="locatorValue",
            locator_type="xpath",
        )
        == '//tr[td="O\'Neil"]'
    )


def test_xpath_uses_concat_when_value_contains_both_quotes() -> None:
    assert (
        render(
            "//tr[td={{name|xpath}}]",
            {"name": "a'b\"c"},
            field="locatorValue",
            locator_type="xpath",
        )
        == "//tr[td=concat('a', \"'\", 'b\"c')]"
    )


def test_xpath_rejects_missing_modifier() -> None:
    with pytest.raises(ValueError, match="xpath"):
        render(
            "//tr[td={{name}}]",
            {"name": "x"},
            field="locatorValue",
            locator_type="xpath",
        )


def test_css_string_context_escapes_quote_and_backslash() -> None:
    assert (
        render(
            '[data-id="{{id}}"]',
            {"id": 'a"b\\c'},
            field="locatorValue",
            locator_type="css",
        )
        == '[data-id="a\\"b\\\\c"]'
    )


def test_css_identifier_context_escapes_spaces_and_leading_digits() -> None:
    # 替换点前面已经是标识符字符时按标识符内部处理，数字不需要转义。
    assert (
        render("#row-{{id}}", {"id": "28"}, field="locatorValue", locator_type="css")
        == "#row-28"
    )
    assert (
        render("#row-{{id}}", {"id": "a b"}, field="locatorValue", locator_type="css")
        == "#row-a\\20 b"
    )
    # 标识符开头仍是数字时必须转义。
    assert (
        render("#{{id}}", {"id": "28"}, field="locatorValue", locator_type="css")
        == "#\\32 8"
    )


def test_css_rejects_modifier() -> None:
    with pytest.raises(ValueError, match="CSS"):
        render("{{id|xpath}}", {"id": "1"}, field="locatorValue", locator_type="css")


def test_open_url_encodes_values_but_not_base_url() -> None:
    values = {"baseUrl": "https://web.test", "id": "a/b c"}
    assert (
        render("{{baseUrl}}/orders/{{id}}", values, keyword="open")
        == "https://web.test/orders/a%2Fb%20c"
    )


def test_undefined_variable_raises() -> None:
    with pytest.raises(ValueError, match="没有变量|变量未定义"):
        render("{{missing}}")


def test_empty_base_url_raises() -> None:
    with pytest.raises(ValueError, match="基础地址"):
        render("{{baseUrl}}/orders", {"baseUrl": ""}, keyword="open")


def test_builtins_are_stable_within_one_render_context() -> None:
    context = RenderContext("operationValue", "", "input", {})
    first = render_field("{{$uuid}}", {}, context)
    second = render_field("{{$uuid}}", {}, context)
    assert first == second


def test_referenced_names_are_ordered_and_deduplicated() -> None:
    assert referenced_names(
        "//tr[td={{name|xpath}}]/td[{{id}}]",
        "{{name}} and {{$timestamp}}",
    ) == ["name", "id"]
