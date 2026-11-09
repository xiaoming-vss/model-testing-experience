# UI 环境变量与后置提取

UI 自动化运行时可读取项目环境变量，并在步骤成功后把页面上的值写回环境。环境与 API
自动化共用 `api_environments` / `api_environment_vars`，用 `kind` 区分 `api` 与 `ui`。
设计决策来源：`.scratch/ui-env-vars/spec.md`；原始需求见
`~/data/文档/test-agent/需求/已完成/UI自动化环境变量与测试数据复用需求.md`。

## 变量引用

- 写法 `{{变量名}}`，区分大小写；`$` 开头是内置函数，`data.` 开头是生成草稿数据。
- 只有 `locatorValue` 与 `operationValue` 参与替换；`stepName`、`description` 不替换。
- `keyword`、`locatorType`、`comparator` 禁止变量，导入时直接拒绝。
- 内置变量 `{{baseUrl}}` 取运行所选 UI 环境的基础地址；环境未配置基础地址时预检失败。
- 变量值不做二次解析、不 trim，空字符串也算“已定义”。
- 内置函数每个步骤重新生成，不跨步骤保持。

定位类型决定转义方式：

| 定位 | 规则 |
| --- | --- |
| `text` / `placeholder` / `label` / `test_id` / `role::name` | 原样替换 |
| `xpath` | 必须写 `{{名字\|xpath}}`，执行器生成单引号/双引号/`concat` 安全字面量 |
| `css` | 引号内按 CSS 字符串转义，引号外按 CSS 标识符转义 |
| `open` 的 `operationValue` | 除 `{{baseUrl}}` 外按 URL 组件编码 |

`role` 的 JSON 形式不支持变量，导入时要求改用 `role::name`。变量名不能为空、不能含
`{ } |` 或空白、长度不超过 120，不能以 `$` / `data.` 开头，不能叫 `baseUrl`。

## 运行前预检

运行创建时按步骤顺序遍历用例：先校验本步骤引用的变量，再登记本步骤 `saveTo` 声明的
名字。初始可用集合是环境变量、`baseUrl` 和内置函数；禁用步骤不参与。套件中任一用例
缺失则整轮不跑，一次返回全部缺失项（用例、步骤、字段、变量名），Studio 在弹窗中内联
补齐并重新提交。

预检不推算前面用例的提取结果：用例 2 依赖用例 1 的写入时，需要先让用例 1 单独跑过一次
或手工把值配进环境。

## 后置提取

规则写在步骤的 `saveTo` 数组里，按数组顺序执行：

```yaml
- orderNo: 7
  stepName: 刷新列表
  keyword: reload
  saveTo:
    - name: taskId
      source: text
      locatorType: xpath
      locatorValue: "//table//tr[1]/td[1]"
    - name: recordName
      source: text
      locatorType: xpath
      locatorValue: "//table//tr[1]/td[2]"
      defaultValue: ""
```

| 字段 | 规则 |
| --- | --- |
| `name` | 必填；命名规则同变量名，同一步骤内不能重名 |
| `source` | `text` / `value` / `attribute` / `url` |
| `locatorType` / `locatorValue` | 省略时继承本步骤已渲染的定位；显式填写时必须成对出现且不支持变量；`source=url` 时禁止填写 |
| `attribute` | 仅 `source=attribute`，必填 |
| `defaultValue` | 仅在零匹配或读到空值时使用 |
| `trim` | 默认 `true`，仅对 `text` 生效 |

读取语义：`text` 用 `text_content()`，`value` 用 `input_value()`（非表单控件直接失败，
不回退文本），`attribute` 用 `get_attribute()`（属性不存在视为空值），`url` 读
`page.url`。读取共用步骤超时；多元素匹配一律失败并要求收窄定位。

步骤成功后每条规则立刻写回环境（同名更新、不存在新建普通变量）。写回失败让步骤失败，
避免后续步骤读到旧值；同一步骤里前面的成功写入不会因后面的失败回滚。

## 完整导入示例

导入接口接受单个用例对象或数组；数组内 `orderNo` 从 1 连续递增，步骤的 `orderNo` 也必须与数组顺序一致。字符串里出现 `{{...}}` 时建议加引号，避免 YAML 把 `{` 解析成 flow mapping。

```yaml
- name: 登录成功-跳转工作台
  enabled: true
  orderNo: 1
  stepsJson:
    - orderNo: 1
      stepName: 打开登录页
      keyword: open
      operationValue: "{{baseUrl}}/login"
      continueOnFailure: false
      enabled: true
    - orderNo: 2
      stepName: 输入租户名
      keyword: input
      locatorType: placeholder
      locatorValue: 请输入租户名
      operationValue: "{{username}}"
      continueOnFailure: false
      enabled: true
    - orderNo: 3
      stepName: 点击登录
      keyword: click
      locatorType: role
      locatorValue: "button::登录"
      continueOnFailure: false
      enabled: true
    - orderNo: 4
      stepName: 等待进入工作台
      keyword: wait_text
      locatorType: text
      locatorValue: 商城
      operationValue: 商城
      continueOnFailure: false
      enabled: true
      saveTo:
        - name: currentUrl
          source: url
    - orderNo: 5
      stepName: 断言当前地址
      keyword: assert_url
      operationValue: "{{currentUrl}}"
      comparator: contains
      continueOnFailure: false
      enabled: true
```

其他提取来源：

```yaml
      saveTo:
        # 省略定位：继承本步骤（已渲染）的定位
        - name: recordName
          source: text
        # 显式静态定位；显式定位不支持变量
        - name: recordId
          source: text
          locatorType: xpath
          locatorValue: "//table//tr[1]/td[1]"
          defaultValue: ""
        # 属性来源；attribute 必填
        - name: detailUrl
          source: attribute
          attribute: href
          locatorType: xpath
          locatorValue: "//a[normalize-space(.)='详情']"
        # 读取当前地址；不填写定位和属性
        - name: currentUrl
          source: url
```

XPath 定位中的变量必须带 `|xpath` 且自己不要加引号；CSS 定位按引号上下文自动转义：

```yaml
locatorValue: "//tr[td[normalize-space(.)={{recordId|xpath}}]]/td[3]"
locatorValue: "[data-id=\"{{recordId}}\"]"
```

`sleep` / `assert_visible` / `assert_hidden` 的毫秒数可以直接写数字，也可以写 `{{waitMs}}` 模板；执行器渲染后再校验正整数。

## AI 生成结果校验

两个 AI Worker 的 UI YAML 阶段接受步骤 `saveTo` 和现有环境变量引用，提取规则与正式导入保持一致：校验变量名称、提取来源、属性、成对的静态提取定位，以及继承步骤定位。XPath 命名变量必须使用 `|xpath`；等待毫秒数可使用变量模板，在执行时检查实际值。生成校验不读取运行环境，也不保证变量已经有值，运行前预检仍负责这一边界。未声明步骤字段、非法提取规则仍被拒绝，历史不含 `saveTo` 的用例保持兼容。

## 控制面内部接口

执行器只通过 worker token 鉴权的内部接口读写变量，不直接访问数据库：

- `POST /internal/ui-runs/{runId}/variables:resolve`，入参
  `{taskId, workerId, names}`，返回 `{values, missing, secretNames}`；不落库，单次超时
  5 秒、失败重试 1 次。
- `POST /internal/ui-runs/{runId}/variables:write`，入参
  `{taskId, workerId, items: [{name, value, orderNo}]}`，返回
  `{results: [{name, success, created, previousValue}]}`；立即落库并记录旧值→新值。

`runId` 与 `taskId` 必须匹配同一条 worker 任务，环境必须是本次运行绑定的 `kind=ui`
环境。

## 运行记录

UI 用例运行与套件运行记录 `environment_id`、`environment_name`（名称快照）、
`used_variables_json`、`variable_writes_json`、`private_payload`：

- `used_variables_json` 记录每次引用的名字、值、步骤号，不去重。
- `variable_writes_json` 记录名字、旧值、新值、步骤号、是否新建。
- 私密变量的值在公开 JSON 中打码为 `********`，真实值加密保存在 `private_payload`；
  错误信息中的私密值同样会被替换。
- 私密变量填充的输入框在截图时通过 Playwright `mask` 遮罩；录屏与 trace 无法遮罩。

## 已知限制

1. 只能读取步骤执行后仍存在的元素；点击链接后读取自身 `href` 应把提取挂在前面的
   `wait_visible` 步骤上。
2. 同一步骤的多条提取规则不回滚，失败前已写入的值保留。
3. 不做并发控制，多人同时运行同一环境时后写覆盖。
4. 写回会覆盖他人的私密变量，没有保护。
5. 只有执行权限的用户无法在预检处补变量，需要找有写权限的人。
6. 存量用例中的 `{{普通名字}}` 升级后会被预检拦截；发版前运行
   `scripts/scan_ui_case_variables.py` 扫描。

## 存量扫描

```bash
cd apps/control-plane
uv run --locked python scripts/scan_ui_case_variables.py
```

脚本输出用例、步骤、字段与引用表达式；有命中时退出码为 1，可直接用于发版检查。
