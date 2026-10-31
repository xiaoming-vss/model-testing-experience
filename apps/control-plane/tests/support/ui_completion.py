"""Shared UI completion draft fixtures; no collected tests."""


def draft():
    return dict(
        draftVersion="ui_yaml_draft/2.0",
        name="发布数据转换",
        enabled=True,
        orderNo=1,
        dataRequirements=[
            dict(
                id="release",
                title="已完成打包的发布数据",
                fields={
                    "id": dict(label="发布数据ID", value=None),
                    "version": dict(label="版本名称", value=None),
                },
                conditions=["已完成打包且无进行中的转换任务"],
                confirmed=False,
            )
        ],
        designConflicts=[],
        stepsJson=[
            dict(
                orderNo=1,
                stepName="勾选发布数据",
                keyword="click",
                locatorType="xpath",
                locatorValue=None,
                dataBindings={
                    "locatorValue": "//tr[td[1]={{data.release.id|xpath}}]//input[@type='checkbox']"
                },
                sourceRefs=["action:A1"],
                purpose="business",
                enabled=True,
                continueOnFailure=False,
            ),
            dict(
                orderNo=2,
                stepName="核对发布数据",
                keyword="assert_text",
                locatorType="xpath",
                locatorValue=None,
                operationValue=None,
                comparator="eq",
                dataBindings={
                    "locatorValue": "//tr[td[1]={{data.release.id|xpath}}]/td[2]",
                    "operationValue": "{{data.release.version}}",
                },
                sourceRefs=["expectation:E1"],
                purpose="business",
                enabled=True,
                continueOnFailure=False,
            ),
        ],
    )
