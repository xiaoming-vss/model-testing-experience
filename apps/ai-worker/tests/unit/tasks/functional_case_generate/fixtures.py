def analysis():
    return {
        "schemaVersion": "1.0",
        "artifactType": "test_scope_impact_risk",
        "testObjects": [],
        "impactAreas": [],
        "risks": [],
        "openQuestions": [],
    }


def case(title="验证登录", module="登录"):
    return {
        "case_module": module,
        "case_title": title,
        "case_type": "功能测试",
        "priority": "2",
        "precondition": [],
        "test_steps": ["1. 登录"],
        "expected_results": ["1. 展示首页"],
    }


def points():
    return {
        "categories": [
            {
                "model": "登录",
                "data": [
                    {
                        "test_model": "功能场景",
                        "test_points": [{"case_name": "验证登录"}],
                    }
                ],
            }
        ]
    }


def material():
    return {
        "artifactType": "readable_requirement_material",
        "schemaVersion": "0.2",
        "materialBlocks": [{"id": "B1"}],
        "questions": [],
    }


def traceable_points():
    return {
        "schemaVersion": "1.0",
        "artifactType": "traceable_test_points",
        "reviewStatus": "self_review_only",
        "testPoints": [
            {
                "id": "P1",
                "module": "登录",
                "dimension": "功能场景",
                "name": "【登录】验证登录",
                "basis": "direct",
                "materialBlockIds": ["B1"],
                "testObjectIds": [],
                "impactAreaIds": [],
                "riskIds": [],
                "materialQuestionIds": [],
                "scopeQuestionIds": [],
            }
        ],
        "coverageGaps": [],
    }


def traceable_modules(*modules):
    value = traceable_points()
    template = value["testPoints"][0]
    value["testPoints"] = [
        {**template, "id": f"P{index}", "module": module, "name": f"【{module}】验证登录"}
        for index, module in enumerate(modules, 1)
    ]
    return value
