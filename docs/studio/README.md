# 前端（studio）

React 单页应用，提供项目、迭代、需求、功能/API/UI 测试资产、AI 任务与执行报告的完整工作台。领域术语见 [CONTEXT](CONTEXT.md)，界面设计规范见 [DESIGN](DESIGN.md)。

## 运行时与依赖

- Node 22.23.1（`.nvmrc`），包管理使用 npm（`package-lock.json`），包名 `@mtx/studio`
- React 19、TypeScript 6、Vite 8、React Router 7、Ant Design 6
- 数据与状态：TanStack Query 5、Zustand 5
- 其他：CodeMirror（JSON/YAML 编辑）、recharts（图表）、docx-preview、html-to-image
- 测试：Vitest 4 + jsdom + Testing Library

## 源码结构

`apps/studio/src/`：

| 路径 | 作用 |
| --- | --- |
| `main.tsx` | 唯一作用为 `import '@/app/main'` |
| `app/main.tsx` | 真正的应用装配入口 |
| `app/router/routes.tsx` | 顶层路由 |
| `app/layouts/AppShell.tsx` | 登录后的整体框架，业务页面在内部二次分发 |
| `app/providers/` | Query 与主题 Provider |
| `app/styles/` | 主题与设计断言测试 |
| `features/` | 按业务划分：`auth`、`projects`、`requirements`、`test-cases`、`testing`、`ai-testing`、`api-automation`、`ui-automation`、`base-services`、`profile` |
| `services/api.ts` | 各 feature API 的聚合出口 |
| `shared/` | `api/request.ts` 请求封装、通用组件、图标、主题 store |
| `test/`、`utils/` | 测试辅助与工具函数 |

HTML 入口是 `index.html`，它加载 `/src/main.tsx`，再转发到 `src/app/main.tsx`。顶层路由只有三条：`/login`、`/register`，其余全部交给 `ProtectedRoute` 包裹的 `AppShell`。

任务和执行详情的代码按职责维护：

- 功能用例生成页面负责运行选择与操作编排；`ai-testing/utils/functionalOutput.ts` 负责产物解析，`caseNameTree.ts` 负责树编辑与布局计算，三个结果展示组件分别负责需求分析、候选用例和测试点树。
- API 集合页面的查询、用例编辑、规则编辑和运行轮询分别在 `api-automation/hooks/useApiCollectionData.ts`、`useApiCaseEditing.ts`、`useApiRuleEditing.ts`、`useApiExecution.ts`。组件目录维护用例编辑器、规则弹窗、导入弹窗及运行历史/报告；查询键和缓存失效由对应 hook 管理。
- UI 套件页面保留草稿与执行编排，步骤编辑器、导入弹窗、运行历史和报告位于 `ui-automation/components/`；单用例和套件报告共用步骤结果渲染。
- `shared/utils/` 集中下载、分页文案与值格式化。任务产物使用 `formatStructuredContent` 保留 JSON 字符串表示；一般展示使用 `prettyPrintValue`，两者空值和字符串行为不同。

## 配置

无 TOML 配置，`scripts/manage.py` 不为前端生成 TOML。涉及两层变量：

- 构建期（Vite）：`VITE_API_PROXY_TARGET` 指定开发服务器代理目标，本地模式由 `manage.py configure --mode local` 写入 `.env.local`；`VITE_API_BASE_URL` 指定后端基地址，默认空（同源）。
- 运行期（容器）：`API_UPSTREAM` 由 nginx 模板用于 `proxy_pass`，Compose 中设为 `http://control-plane:9000`。

## 命令

在 `apps/studio/` 下执行：

```sh
npm ci                # 安装依赖
npm run dev           # 开发服务器，默认 127.0.0.1:5173
npm run type-check    # tsc -b --pretty false
npm run lint          # eslint .
npm run test          # vitest run
npm run build         # tsc -b && vite build
npm run verify        # type-check + lint + build
```

2026-09-20 整改与失败修复验证：类型检查、Lint 与构建通过；前端全量收集 305 项，301 项在该轮通过，剩余 4 项随后完成修复并复跑通过（UI 弹窗关闭/重开 1 项、需求分析整文件 19 项、GitLab 权限绑定整文件 5 项）。默认按文件串行执行，保留 30s 单项超时；重型页面使用关闭动画的测试主题，以避免 jsdom 动画和 CSS 计算造成的时序问题。完整过程及限制见 [整改验证记录](refactor-validation-2026-09-20.md)。

## 与后端的交互

- 开发服务器代理 `/v1` 与 `/__document_preview_proxy`（后者重写去掉前缀）到 `VITE_API_PROXY_TARGET`
- 容器内由 nginx 监听 80 端口并代理同样的两个前缀，`proxy_read_timeout` 与 `proxy_send_timeout` 为 120s，`client_max_body_size` 为 105m
- 容器健康检查访问 `location = /healthz`
- 用户态认证使用 `Authorization` 头携带 JWT；浏览器存储键为 `testpilot_access_token` 与 `testpilot_theme_mode`，为兼容改名前的已登录用户而保留
