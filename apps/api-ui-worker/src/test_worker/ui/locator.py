"""
元素定位器模块
支持多种定位方式
"""

from __future__ import annotations

import json

from playwright.async_api import Locator, Page

from ..contracts.types import UiStepDefinition


def resolve_locator(page: Page, step: UiStepDefinition) -> Locator:
    """
    解析元素定位器

    Args:
        page: Playwright 页面对象
        step: 步骤定义

    Returns:
        Playwright 定位器对象

    Raises:
        ValueError: 不支持的定位类型
    """
    locator_type = (step.locator_type or "css").lower()
    locator_value = step.locator_value or ""

    if not locator_value:
        step_name = step.step_name or step.keyword
        raise ValueError(f"step {step_name} 缺少 locator_value")

    if locator_type == "css":
        return page.locator(locator_value)
    elif locator_type == "xpath":
        return page.locator(f"xpath={locator_value}")
    elif locator_type == "text":
        return page.get_by_text(locator_value)
    elif locator_type == "placeholder":
        return page.get_by_placeholder(locator_value)
    elif locator_type == "label":
        return page.get_by_label(locator_value)
    elif locator_type in ("test_id", "testid"):
        return page.get_by_test_id(locator_value)
    elif locator_type == "role":
        return _resolve_role_locator(page, locator_value)
    else:
        raise ValueError(f"暂不支持的 locator_type: {locator_type}")


def _resolve_role_locator(page: Page, locator_value: str) -> Locator:
    """
    解析角色定位器

    Args:
        page: Playwright 页面对象
        locator_value: 定位器值，支持 JSON 格式或 role::name 格式

    Returns:
        Playwright 定位器对象
    """
    if locator_value.startswith("{"):
        # JSON 格式: {"role": "button", "name": "确定"}
        parsed = json.loads(locator_value)
        role = parsed.get("role")
        name = parsed.get("name")
        if name:
            return page.get_by_role(role, name=name)
        return page.get_by_role(role)

    # role::name 格式: button::确定
    parts = locator_value.split("::", 1)
    role = parts[0]
    if len(parts) > 1 and parts[1]:
        name = parts[1]
        return page.get_by_role(role, name=name)
    return page.get_by_role(role)
