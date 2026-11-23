import pytest

from testing_agent.domain.generation_content_hash import generation_content_hash


def test_json_hash_ignores_object_order_and_formatting_but_not_value_changes():
    first = generation_content_hash('{"名称": "用例", "count": 2}', "json")
    assert first == generation_content_hash('{ "count":2,"名称":"用例" }', "json")
    assert first != generation_content_hash('{"名称":"用例","count":3}', "json")


def test_text_and_yaml_normalize_line_endings_without_losing_format_or_spacing():
    text = generation_content_hash("a\r\nb\r", "text")
    assert text == generation_content_hash("a\nb\n", "text")
    assert text != generation_content_hash("a\n b\n", "text")
    assert text != generation_content_hash("a\nb\n", "yaml")


def test_invalid_json_or_unsupported_format_has_no_fingerprint():
    with pytest.raises(ValueError):
        generation_content_hash("{bad", "json")
    with pytest.raises(ValueError):
        generation_content_hash('{"n": NaN}', "json")
    with pytest.raises(ValueError):
        generation_content_hash('{"key":1,"key":2}', "json")
    with pytest.raises(ValueError):
        generation_content_hash("content", "unsupported")
