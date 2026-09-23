# 前端（studio）

React 单页应用，提供项目、迭代、需求、功能/API/UI 测试资产、AI 任务与执行报告的完整工作台。领域术语见 [CONTEXT](CONTEXT.md)，结构与代码规范见 [STRUCTURE](STRUCTURE.md)。

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

测试配置见 `vite.config.ts`：jsdom 环境，单项超时 30s，`maxWorkers: 4`（最多 4 个测试文件并行）。重型页面测试使用 `src/test/TestThemeProvider.tsx`——保留真实主题与组件，只关闭 jsdom 不执行的 CSS 动画，避免弹窗卡在进入动画的透明状态；并发过高会因 CPU 争用出现超时抖动，排查时用 `--maxWorkers=1` 串行复跑，以区分「超时」与「行为失败」。全量 64 个文件 411 项，耗时约 2 分钟。历史整改与验证过程见 git 提交 `72164d2`。

**列表页表面层的观感不在自动化覆盖内**（jsdom 不做布局）。UI 测试页重做时用一次性 Playwright 脚本对着 `npm run dev` 核对过浅色与深色两套：脚本用 `context.route('**/v1/**')` stub 掉 `/v1/user`、`/v1/projects`、`/v1/projects/:id/sprints`、`/v1/sprints/:id/requirements`、`/v1/requirements/:id/ui-test-suites`，然后在 `1680×1000` 下截整页。脚本没有落库——要复查时照这个思路现写即可；判据是「信息条 / 工具栏 / 表格三张卡片、徽标不换行、深色下底色与描边成对」。

同一套脚本还能抓「深色下多出来的容器」：把每个元素的 `backgroundColor` / `boxShadow` / `borderWidth` 采成一张表，浅深两跑做差，**浅色下完全无面、深色下却有面的元素就是漏的**——外壳的玻璃规则与 `*-v2.css` 的透明覆盖常常同权重，只在深色下现形（判据与三处已知坑见 [STRUCTURE.md](STRUCTURE.md) 的「列表页表面层」）。

## 与后端的交互

- 开发服务器代理 `/v1` 与 `/__document_preview_proxy`（后者重写去掉前缀）到 `VITE_API_PROXY_TARGET`
- 容器内由 nginx 监听 80 端口并代理同样的两个前缀，`proxy_read_timeout` 与 `proxy_send_timeout` 为 120s，`client_max_body_size` 为 105m
- 容器健康检查访问 `location = /healthz`
- 用户态认证使用 `Authorization` 头携带 JWT；浏览器存储键为 `testpilot_access_token` 与 `testpilot_theme_mode`，为兼容改名前的已登录用户而保留
