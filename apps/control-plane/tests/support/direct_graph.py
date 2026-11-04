import json


def cases_output():
    return json.dumps(
        {
            "cases": [
                {
                    "case_id": f"case-{index}",
                    "case_module": "任务管理",
                    "case_title": f"用例{index}",
                    "case_type": "功能测试",
                    "priority": "1",
                    "precondition": ["1. 准备就绪"],
                    "test_steps": ["1. 提交任务"],
                    "expected_results": ["1. 任务成功"],
                }
                for index in range(1, 4)
            ]
        },
        ensure_ascii=False,
    )


def relations_output():
    return {
        "schema_version": "2.0",
        "main_paths": [{"path_id": "P01", "case_ids": ["case-1", "case-2", "case-3"]}],
        "edges": [
            {
                "edge_id": f"E0{index}",
                "from_case_id": f"case-{index}",
                "to_case_id": f"case-{index + 1}",
                "relation_type": "next",
                "order": 1,
            }
            for index in (1, 2)
        ],
    }
