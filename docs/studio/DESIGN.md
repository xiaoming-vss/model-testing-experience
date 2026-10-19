# MTX Studio 前端设计说明

MTX Studio 是一个面向测试团队的 React 单页工作台。它把项目、迭代、需求、测试资产、AI 任务和执行证据放在同一个工作流中：用户从需求范围进入测试设计，审核 AI 产物，再将批准的结果导入正式资产并查看执行报告。

本文说明前端的设计边界和实现约定。业务术语以 [`docs/studio/CONTEXT.md`](CONTEXT.md) 为准，完整的目录规则见 [`docs/studio/STRUCTURE.md`](STRUCTURE.md)，尺寸、布局和交互规则见 [`docs/studio/UI-GUIDELINES.md`](UI-GUIDELINES.md)。出现冲突时，最新确认的产品需求和这些项目文档优先于本文的概括。

## 设计目标

- 让用户始终知道当前项目、迭代和需求范围，避免把不同范围的测试资产混在一起。
- 把 AI 任务拆成可观察的阶段：输入、运行、人工检查点、审核、正式资产导入和报告。
- 让自动化测试、人工审核和执行证据共享同一套资产标识与状态语义。
- 保持页面表面、按钮语义、分页和主题在各业务模块之间一致。
- 让新功能可以在单个 feature 内完成，减少跨模块耦合和重复实现。

## 用户与核心对象

工作台围绕以下对象组织：

| 对象 | 前端职责 |
| --- | --- |
| 项目 / 迭代 / 需求 | 提供全局范围和导航边界；项目角色决定可见操作。 |
| 测试资产 | 管理功能、API、UI 用例及测试套件，支持列表、编辑、执行和导入。 |
| AI 任务 | 展示任务输入、运行记录、人工检查点、候选结果和审核操作。 |
| 候选结果 | 允许在审核前编辑；批准后才能进入正式资产导入流程。 |
| 执行记录 / 报告 | 展示运行状态、步骤结果、日志、快照和结构化报告。 |
| 个人授权 / 项目共享服务 | 选择当前操作人可用的连接；前端不把个人凭据当作项目共享数据。 |

“审核”与“正式资产导入”是两个独立动作；“人工检查点”只是流程暂停点，不能当作审核结果展示。

## 应用结构

源码位于 `src/`，依赖方向从上到下：

```text
app/       应用装配：入口、路由、布局、Provider、全局样式
  ↓
features/  业务模块：auth、projects、test-cases、testing、ai-testing、api-automation、ui-automation 等
  ↓
shared/    无业务语义的请求封装、通用组件、工具和主题能力
```

- `src/main.tsx` 只转发到 `app/main.tsx`。
- `app/main.tsx` 装配 Query、主题和路由；`AppShell` 负责登录后的外壳与侧栏。
- `app/router/routes.tsx` 只维护顶层路由；登录和注册公开，其他页面由 `ProtectedRoute` 保护。
- feature 内部按 `api/`、`components/`、`hooks/`、`pages/`、`styles/`、`types.ts` 等职责拆分。
- feature 之间只通过对方的 `api/` 和 `types.ts` 通信；共享实现上提到 `shared/`，全局编排放在 `app/`。
- `shared/api/request.ts` 统一处理认证头、错误和响应；具体 API 留在所属 feature。

新增代码前先判断归属：无业务语义且全站唯一的实现进入 `shared/`；只服务一个业务域的实现留在对应 feature；被多个业务域使用但带业务语义的能力，应抽成明确的领域边界，而不是从一个 feature 深层引用。

## 路由与页面生命周期

页面进入后的典型生命周期如下：

1. 路由解析项目、迭代和需求范围。
2. 页面通过 TanStack Query 获取服务端数据，并在查询键中包含所有影响结果的范围参数。
3. 用户操作通过 feature API 或 mutation 提交；成功后由 feature 自己负责失效和刷新相关查询。
4. 页面区分首次空状态、筛选无结果、加载中和加载失败，并提供对应的创建、清空筛选或重试动作。
5. 离开页面时清理仅属于当前页面的草稿、轮询和临时选择；不能误删服务端数据或其他任务的运行记录。

长任务（AI 运行、API/UI 执行）使用运行记录作为事实来源。轮询或刷新只更新记录与详情，不通过临时 UI 状态推断“已完成”。删除运行记录失败时保留草稿和当前选择；删除非当前记录时不切换当前记录。

## 状态与数据流

- 服务端状态优先放在 TanStack Query；查询键必须表达项目、迭代、需求、任务和分页边界。
- 跨页面的轻量客户端状态（当前主题、认证信息、工作台范围）使用 Zustand 或专用 hook。
- 表单草稿只在拥有它的页面或 feature 中维护，提交成功后按业务规则清理。
- 认证使用 `Authorization: Bearer <JWT>`；兼容存储键为 `testpilot_access_token`。
- 所有异步操作都应有加载、成功、失败和可重试反馈；危险操作保留权限门控和确认流程。

## 视觉与交互

浅色主题采用清爽蓝主色（`#2563c9`）：主按钮为浅蓝底（`#e8f1ff`）、蓝色文字（`#24578f`）和浅蓝描边，导航选中项使用浅蓝底和蓝色文字，列表名称沿用蓝色链接。页面背景为浅灰蓝（`#f0f4f9`），内容面为白色，正文和辅助文字保持深灰蓝，避免整体过淡。颜色集中在既有浅色 token 文件及 Ant Design Provider 中；深色主题保留 GitHub Dark 配色。

- 页面统一使用公共 token、按钮层、列表表面层和 `ListPagination`；feature 不复制一套颜色、分页或按钮外观。
- CSS 放在 `app/styles/`、`shared/styles/` 或 `features/<feature>/styles/`；页面和组件目录不新增 CSS 文件。
- 列表工具栏按“标题 → 范围筛选 → 类型/环境 → 搜索 → 右侧动作”排列；表格表头、行高、分页和操作列遵循 UI 指南。
- 列表必须同时表达范围和状态；执行完成率与通过率使用不同文案和颜色语义。
- 图标按钮提供无障碍名称和用途提示，键盘焦点可见；删除使用危险色，禁用状态保留统一弱化样式。
- 空间不足时允许筛选换行，但不得让按钮、表格内容或分页溢出；桌面与窄屏都需要人工检查。
- 主题支持 `light`、`dark`、`system`，偏好存储在 `mtx-theme-preference`。新样式只消费语义 token；暗色只通过 token 映射，不新增针对 feature 类名的覆盖补丁。

## 可复用能力

以下能力只有一个实现入口，新代码应直接复用：

- 请求：`shared/api/request.ts`
- 下载：`shared/utils/download.ts`
- 值解析与格式化：`shared/utils/value.ts`、`shared/utils/payload.ts`
- JSON/YAML 编辑器：`shared/components/TextCodeEditor`、`JsonEditor`
- 富文本：`shared/components/RichTextEditor`；图片只持久化 `data-file-id`，签名 URL 仅用于预览
- 权限与操作按钮：`shared/components/ActionButton`
- 列表分页：`shared/components/ListPagination`

## 测试与验证

修改前端代码后，在 `apps/studio/` 执行与改动匹配的检查：

```sh
npm run type-check
npm run lint
npm run test
npm run check:theme
npm run build
```

页面或样式变更还要在浏览器核对桌面和窄屏：有数据、首次空状态、筛选无结果、长名称、无权限操作、加载失败和分页越界。jsdom 能验证行为和部分样式断言，但不能替代真实布局检查。完整命令、代理、容器运行方式和已知限制见 [`docs/studio/README.md`](README.md)。

## 变更检查清单

- 是否读过相关 feature 的上下文和 ADR，并使用了仓库既有术语？
- 新代码是否放在正确层级，依赖方向是否向下？
- 是否复用了请求、按钮、分页、编辑器和主题能力？
- 是否为加载、空状态、错误、权限和危险操作提供了完整反馈？
- 是否更新了对应 feature 测试，并运行类型检查、Lint、主题检查和构建？
- 如果改变布局、背景、边距或工具栏，是否按 UI 指南完成浏览器视觉核对？
