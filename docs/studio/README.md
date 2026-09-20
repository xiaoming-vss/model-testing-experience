# 前端（studio）

React 单页应用，提供项目、迭代、需求、功能/API/UI 测试资产、AI 任务与执行报告的完整工作台。领域术语见 [CONTEXT](CONTEXT.md)。

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

`npm run test` 全量运行 289 项（279 通过、10 失败）。10 项失败集中在 `FunctionalCaseGenerateTaskDetailPage.test.tsx`、`RequirementAnalysisTaskDetailPage.test.tsx` 与 `UiCaseGenerateTaskDetailPage.test.tsx`，表现为 30s 超时或时序敏感的元素查找失败；抽查同名用例在未改动的 `HEAD` 上同样失败，属既有的负载相关抖动，与本轮改动无关。

## 与后端的交互

- 开发服务器代理 `/v1` 与 `/__document_preview_proxy`（后者重写去掉前缀）到 `VITE_API_PROXY_TARGET`
- 容器内由 nginx 监听 80 端口并代理同样的两个前缀，`proxy_read_timeout` 与 `proxy_send_timeout` 为 120s，`client_max_body_size` 为 105m
- 容器健康检查访问 `location = /healthz`
- 用户态认证使用 `Authorization` 头携带 JWT；浏览器存储键为 `testpilot_access_token` 与 `testpilot_theme_mode`，为兼容改名前的已登录用户而保留
