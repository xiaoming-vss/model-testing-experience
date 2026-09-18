# TestPilot Studio

> 文档统一维护于此；以下项目命令在仓库根目录的 `apps/studio/` 中执行。整套平台的配置与部署见 [统一部署指南](../deployment.md)。

TestPilot Studio 是一个面向测试协作的前端工作台，用于围绕项目、迭代和需求管理测试资产与测试活动。

## 功能范围

- 项目、迭代、需求管理
- 功能测试集与测试用例维护
- API 自动化测试集、环境、用例、断言和运行报告
- UI 自动化测试集、步骤编排和运行配置
- AI 测试任务与 Skill 库入口
- 禅道连接管理与项目/迭代/需求绑定
- 登录态保护、项目切换、明暗主题切换

## 技术栈

- React 19
- TypeScript
- Vite 8
- Ant Design 6
- React Router 7
- TanStack React Query 5
- Zustand 5

## 本地开发

```bash
npm install
npm run dev
```

## 常用命令

```bash
npm run type-check
npm run lint
npm run build
npm run verify
```

## Docker 运行

构建生产镜像：

```bash
docker build -t testpilot-studio .
```

启动容器，并将 API 请求代理到宿主机的 `8080` 端口：

```bash
docker run --rm -p 8081:80 \
  -e API_UPSTREAM=http://host.docker.internal:8080 \
  testpilot-studio
```

浏览器访问 `http://localhost:8081`。在 Docker Compose 或同一容器网络中，`API_UPSTREAM` 可改为后端服务名，例如 `http://api:8080`。

默认使用同源代理，前端构建产物不会固化后端地址。如果浏览器必须直接访问独立 API 域名，可在构建时传入：

```bash
docker build \
  --build-arg VITE_API_BASE_URL=https://api.example.com \
  -t testpilot-studio .
```

说明：

- `npm run build` 会先执行 TypeScript 构建，再执行 Vite 构建。
- `npm run verify` 会依次执行 type-check、lint 和 build。

## 文档

- [功能文档](functional-specification.md)
- [系统设计](system-design.md)

## 本地文件约定

以下内容属于本地工具、运行产物或个人工作区，不应提交到仓库：

- `.agents/`
- `.codex/`
- `.trellis/`
- `.scratch/`
- `.trae/`
- `.zcode/`
- `skills-lock.json`
- `output/`
- `dist/`
- `node_modules/`
- `.env`

## 文档目录

- [MTX](CONTEXT.md)
- [风险分析报告条目级字段契约由 testpilot-studio 规范定义,worker 按此实装](adr/0001-risk-analysis-report-contract.md)
- [统一操作按钮](components/action-button.md)
- [项目彩色图标库](components/icons.md)
- [Design QA — Three Testing Lists](design-qa.md)
- [UI 用例 AI 生成与源码包上传——前端适配确认稿](frontend-ui-ai-generation-source-archive-confirmation.md)
- [已审核 UI 候选用例导入正式套件：前端适配确认稿](frontend-ui-case-import-confirmation.md)
- [TestPilot Studio 功能文档](functional-specification.md)
- [项目协作与个人授权前端接入](integration/project-membership.md)
- [模块需求:testpilot-studio(前端工作台)](specs/code-binding-risk-analysis.md)
- [已审核 UI 候选用例导入现有 UI 测试套件](specs/ui-approved-candidate-import.md)
- [ui-case-ai-generation-source-archive](specs/ui-case-ai-generation-source-archive.md)
- [TestPilot Studio 设计文档](system-design.md)
