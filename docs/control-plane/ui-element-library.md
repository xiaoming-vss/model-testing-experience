# 元素库

一个软件仓库对应一个前端应用。库内按页面路由模板组织元素，每个应用有一个公共组供跨页面使用。首版由 Studio 手工维护，使用项目的读取和写入权限。设计见 [ADR 0033](adr/0033-software-repository-ui-element-library.md)。

## HTTP 接口

仓库内的列表和新建请求使用 `/v1/software-repositories/{softwareRepositoryId}` 前缀。详情和删除按条目业务标识定位，控制面从条目校验软件仓库和项目归属。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/v1/software-repositories/{softwareRepositoryId}/ui-element-groups` | 返回分组和各组元素数量。 |
| POST | `/v1/software-repositories/{softwareRepositoryId}/ui-element-groups` | 传 `name` 和 `routeTemplate`，创建页面组。 |
| DELETE | `/v1/ui-element-groups/{groupId}` | 删除空分组。 |
| GET | `/v1/software-repositories/{softwareRepositoryId}/ui-elements` | 支持 `groupId`、`keyword`、`verificationStatus`、`page` 和 `pageSize`。返回摘要、`items` 和筛选总数 `total`。 |
| POST | `/v1/software-repositories/{softwareRepositoryId}/ui-elements` | 新建元素。省略 `groupId` 或传 `null` 时写入公共组。 |
| GET | `/v1/ui-elements/{elementId}` | 返回定位值、参数定义和当前版本。 |
| PATCH | `/v1/ui-elements/{elementId}` | 传当前 `version` 和要修改的字段。显式 `groupId: null` 表示移动到公共组。 |
| DELETE | `/v1/ui-elements/{elementId}?version=1` | 以查询参数提供当前版本，删除元素。 |

公共组在第一次元素写入时创建，列表读取不产生写入。元素摘要的 `parameterized` 表示定位包含参数。新建或修改定位、作用范围、分组后，验证状态为 `pending`，在 Studio 显示「待验证」。

## 定位模板

```json
{
  "groupId": null,
  "name": "编辑订单按钮",
  "scope": "订单表格 · 指定订单行",
  "locatorType": "xpath",
  "locatorValue": "//tr[td[normalize-space(.)={{orderNo|xpath}}]]//button[normalize-space(.)='编辑']",
  "parameters": [{"name": "orderNo", "description": "订单号"}]
}
```

定位模板的参数定义需与占位符一致。XPath 使用 `{{参数名|xpath}}`，由执行器生成安全字面量。支持的转义形式沿用 [UI 环境变量与后置提取](ui-environment-variables.md#变量引用)。Studio 的样例输入用于本地预览，刷新后恢复空白。

相同分组、作用范围、定位类型和定位值的元素构成重复，返回 409 和已有 `elementId`。更新和删除时版本冲突也返回 409。工作流中的浏览器捕获、验证和 UI 生成消费由后续发布接入。
