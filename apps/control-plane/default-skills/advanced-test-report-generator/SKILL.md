# Advanced Test Report Generator

Use this skill when the user provides project, sprint, requirement, test metric, and bug data in JSON and asks to generate a software testing report from the perspective of a senior testing expert.

This skill produces a professional Chinese Markdown test report. The report should not merely restate data; it must evaluate testing sufficiency, defect risk, coverage risk, release readiness, and improvement actions.

## Input Contract

The expected input is a JSON object with the following structure. The latest contract keeps `function`, `api`, `ui`, and `bug` as top-level metric objects instead of nesting them under `metrics`. Use `snapshotDate` as the report date and data snapshot date.

```json
{
  "projectId": "",
  "sprintId": "",
  "snapshotDate": "",
  "function": {
    "total": 0,
    "executed": 0,
    "pending": 0,
    "success": 0,
    "failed": 0
  },
  "api": {
    "total": 0,
    "executed": 0,
    "pending": 0,
    "success": 0,
    "failed": 0
  },
  "ui": {
    "total": 0,
    "executed": 0,
    "pending": 0,
    "success": 0,
    "failed": 0
  },
  "bug": {
    "total": 0,
    "resolved": 0,
    "unresolved": 0,
    "fatal": 0,
    "serious": 0,
    "normal": 0,
    "suggestion": 0
  },
  "project": {
    "projectName": "",
    "description": ""
  },
  "sprint": {
    "sprintName": "",
    "startDate": "",
    "endDate": "",
    "description": ""
  },
  "requirements": [
    {
      "requirementName": "",
      "description": ""
    }
  ],
  "bugs": [
    {
      "title": "",
      "module": "",
      "severity": "",
      "status": "",
      "owner": "",
      "description": ""
    }
  ],
  "createdAt": "",
  "updatedAt": ""
}
```

Treat missing optional strings as `未提供`. Treat missing arrays as empty arrays. Treat missing numeric metrics as 0. If numbers arrive as numeric strings, coerce them to numbers before calculation.

Ignore platform metadata such as `projectId`, `sprintId`, `createdAt`, and `updatedAt` unless the user explicitly asks to include them. Do not create a `metrics` wrapper in the report logic; the metric objects are top-level fields.

## Field Meaning

- `snapshotDate`: report date and data snapshot date. Use this as `报告日期`.
- `project.projectName`: project name.
- `project.description`: project background, goal, or system description.
- `sprint.sprintName`: sprint or iteration name.
- `sprint.startDate`: sprint or test start date, preferably `YYYY-MM-DD`.
- `sprint.endDate`: sprint or test end date, preferably `YYYY-MM-DD`.
- `sprint.description`: sprint goal, delivery scope, or version notes.
- `requirements[].requirementName`: requirement name.
- `requirements[].description`: short requirement description.
- `function`: functional test case statistics.
- `api`: API test case statistics.
- `ui`: UI or automated UI test case statistics.
- `bug`: defect summary statistics.
- `bugs[]`: detailed defect list.
- `bugs[].title`: defect title.
- `bugs[].module`: module where the defect belongs.
- `bugs[].severity`: severity, such as `致命`, `严重`, `一般`, or `建议`.
- `bugs[].status`: status, such as `未解决`, `已解决`, `已关闭`, `待验证`, `resolved`, or `closed`.
- `bugs[].owner`: current assignee or responsible person.
- `bugs[].description`: defect symptom, impact, or short description.

## Derived Metrics

Calculate the following values and include them in the report:

- Functional execution rate: `function.executed / function.total * 100`.
- Functional pass rate: `function.success / function.executed * 100`.
- API execution rate: `api.executed / api.total * 100`.
- API pass rate: `api.success / api.executed * 100`.
- UI execution rate: `ui.executed / ui.total * 100`.
- UI pass rate: `ui.success / ui.executed * 100`.
- Bug resolved rate: `bug.resolved / bug.total * 100`.
- Bug unresolved rate: `bug.unresolved / bug.total * 100`.
- Critical bug count: `bug.fatal + bug.serious`.

When the denominator is 0, display the rate as `暂无数据` instead of `0%`, unless the business meaning is clearly zero execution with a nonzero total. For example, if `function.total > 0` and `function.executed = 0`, functional execution rate is `0.00%`, and functional pass rate is `暂无数据`.

Use two decimal places for percentages.

## Requirement And Bug Correlation Analysis

When both `requirements` and `bugs` are provided, perform requirement-aware defect analysis instead of only summarizing defect counts.

Correlation method:

1. Match defects to requirements by comparing keywords in `bugs[].title`, `bugs[].module`, `bugs[].description`, `requirements[].requirementName`, and `requirements[].description`.
2. Prefer exact business-domain matches first, such as `任务中心`, `视频采集`, `模板创建`, `审核`, `预处理`, `设备`, `EGO`, `本地化 Server`, `安装部署`, or other repeated domain terms from the input.
3. If a defect cannot be confidently mapped to a specific requirement, classify it as `未明确归属需求`, and do not force a relationship.
4. For each requirement, evaluate related defect count, serious/fatal defect count, unresolved defect count, and whether defects affect core flow continuity.
5. If multiple serious defects concentrate in one business area, explicitly identify it as a quality hotspot.
6. When all related defects are resolved or closed, still mention historical risk if the defects touched key flows such as data status flow, task creation, audit flow, synchronization, upload, preprocessing, or storage.
7. Do not infer that a requirement has passed only because its related defects are resolved. Passing still depends on test execution evidence and regression verification.

Generate a requirement risk level for each requirement when possible:

- `高`: related unresolved fatal/serious defects exist, or serious defects affect core process and regression evidence is insufficient.
- `中`: related defects are resolved/closed but involved important flows, or normal defects remain unresolved.
- `低`: no related defects are found, or only low-impact resolved suggestion/normal defects are found and test evidence is sufficient.
- `待确认`: requirement details are too sparse or defect mapping is not reliable.

Use this analysis in `缺陷质量分析`, `风险评估`, `测试结论`, and `发布建议`. Reference concrete requirement names and defect themes where useful.

## Senior Testing Expert Judgment Rules

Apply these rules when generating the conclusion and risk assessment:

1. If all test case totals are 0, the conclusion is `暂无结论`.
2. If functional test `total > 0` and `executed = 0`, do not say the test passed. The conclusion should be `暂无结论` or `不通过`, depending on the release context.
3. If any execution rate is below 80% for a test type with `total > 0`, clearly state that the testing evidence is insufficient.
4. If failed test cases exist, explain that failed cases require impact analysis and regression verification.
5. If there are unresolved fatal defects, the conclusion must be `不通过`, and the release recommendation must be `暂不建议发布`.
6. If there are unresolved serious defects, the conclusion should generally be `不通过` unless the report explicitly frames them as non-blocking and accepted by stakeholders. Without such evidence, do not recommend release.
7. If there are unresolved normal or suggestion defects only, the conclusion can be `有条件通过` when execution is otherwise sufficient.
8. If API test total is 0, mention API coverage risk, especially around interface contracts, permissions, abnormal returns, and data consistency.
9. If UI test total is 0, mention UI coverage risk, including interaction stability, display consistency, browser/client compatibility, and regression efficiency.
10. If defect summary counts and `bugs.length` are inconsistent, mention data consistency risk and recommend aligning with the defect management platform.
11. Treat `resolved` and `closed` bug statuses as resolved/closed states for narrative purposes, while still using the top-level `bug` summary as the primary statistical source.
12. Do not invent test environment, account, module ownership, root cause, or acceptance information that is absent from the input.
13. In the conclusion, connect release readiness to both test metrics and requirement-level defect impact. For example, mention whether defects concentrated around specific requirements such as task center, video collection, local server, device management, installation deployment, preprocessing, or audit flow.
14. Use a professional, objective, audit-friendly tone. Avoid exaggerated claims.

## Output Template

Generate the report in Chinese Markdown using this structure:

```markdown
# {{project.projectName}} 测试报告

## 一、报告概述

本报告基于 {{sprint.sprintName}} 的需求范围、测试执行数据及缺陷情况，对本轮迭代质量进行总结与评估。

- 项目名称：{{project.projectName}}
- 项目描述：{{project.description}}
- 迭代名称：{{sprint.sprintName}}
- 迭代周期：{{sprint.startDate}} 至 {{sprint.endDate}}
- 报告日期：{{snapshotDate}}
- 迭代说明：{{sprint.description}}

## 二、本轮测试范围

### 2.1 需求覆盖范围

本轮迭代共涉及 {{requirements.length}} 项需求，具体如下：

| 序号 | 需求名称 | 需求说明 |
|---|---|---|
| 1 | {{requirements[0].requirementName}} | {{requirements[0].description}} |

### 2.2 测试类型覆盖

| 测试类型 | 用例总数 | 已执行 | 未执行 | 通过 | 失败 |
|---|---:|---:|---:|---:|---:|
| 功能测试 | {{function.total}} | {{function.executed}} | {{function.pending}} | {{function.success}} | {{function.failed}} |
| 接口测试 | {{api.total}} | {{api.executed}} | {{api.pending}} | {{api.success}} | {{api.failed}} |
| UI测试 | {{ui.total}} | {{ui.executed}} | {{ui.pending}} | {{ui.success}} | {{ui.failed}} |

## 三、测试执行分析

### 3.1 用例执行情况

- 功能测试执行率：{{functionExecutionRate}}
- 功能测试通过率：{{functionPassRate}}
- 接口测试执行率：{{apiExecutionRate}}
- 接口测试通过率：{{apiPassRate}}
- UI测试执行率：{{uiExecutionRate}}
- UI测试通过率：{{uiPassRate}}

### 3.2 测试充分性评估

{{testAdequacyAssessment}}

## 四、缺陷统计与质量分析

### 4.1 缺陷总体情况

| 指标 | 数量 |
|---|---:|
| 缺陷总数 | {{bug.total}} |
| 已解决缺陷 | {{bug.resolved}} |
| 未解决缺陷 | {{bug.unresolved}} |
| 致命缺陷 | {{bug.fatal}} |
| 严重缺陷 | {{bug.serious}} |
| 一般缺陷 | {{bug.normal}} |
| 建议类缺陷 | {{bug.suggestion}} |

- 缺陷修复率：{{bugResolvedRate}}
- 未解决缺陷占比：{{bugUnresolvedRate}}
- 严重及以上缺陷数：{{criticalBugCount}}

### 4.2 缺陷明细

| 序号 | 缺陷标题 | 所属模块 | 严重级别 | 状态 | 责任人 | 缺陷说明 |
|---|---|---|---|---|---|---|
| 1 | {{bugs[0].title}} | {{bugs[0].module}} | {{bugs[0].severity}} | {{bugs[0].status}} | {{bugs[0].owner}} | {{bugs[0].description}} |

若缺陷明细为空，输出：`未提供缺陷明细。`

### 4.3 缺陷质量分析

{{bugQualityAnalysis}}

## 五、风险评估

### 5.1 测试执行风险

{{executionRisk}}

### 5.2 缺陷遗留风险

{{bugRisk}}

### 5.3 覆盖完整性风险

{{coverageRisk}}

## 六、测试结论

基于本轮测试数据，{{sprint.sprintName}} 当前测试结论为：**{{conclusionLevel}}**。

{{conclusionReason}}

## 七、发布建议

{{releaseRecommendation}}

## 八、后续改进建议

{{improvementSuggestions}}
```

## Conclusion Levels

Use one of the following:

- `通过`: testing execution is sufficient, blocking defects are closed, and data supports release readiness.
- `有条件通过`: non-blocking residual issues exist, and release requires explicit risk acceptance and follow-up repair plan.
- `不通过`: blocking defects exist, critical evidence is insufficient, or release risk is unacceptable.
- `暂无结论`: testing has not started, essential data is missing, or evidence cannot support a quality judgment.

## Writing Requirements

- Write in clear professional Chinese.
- Put data tables before interpretive conclusions.
- Keep the conclusion traceable to metrics, defects, and requirement-level impact.
- Be explicit when evidence is insufficient.
- Do not overstate confidence.
- If the input contains placeholder explanatory text instead of real values, treat it as missing data and ask the user to provide actual JSON values before producing a final report.

