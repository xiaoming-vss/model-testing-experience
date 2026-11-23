# 2026-11-20 EntityCard 颜色回归验收

- 日期：2026-11-20
- 状态：已验证
- 负责人：studio maintainers
- 来源：本地 Chromium、Vite 开发服务器和 EntityCard 实际组件
- 关联：[工单 48 对应的样式规范](../STRUCTURE.md#三样式归属与主题)

在 900×600 视口下分别使用浅色和深色主题渲染带链接标题的卡片。浏览器计算的链接和标题颜色一致：浅色 `rgb(39, 52, 73)`，深色 `rgb(230, 237, 243)`。将原有的 `color: inherit !important` 语义临时加回链接后，两种主题的组件截图逐字节相同。

证据：[浅色截图](assets/2026-11-20-entity-card/entity-card-light.png)、[深色截图](assets/2026-11-20-entity-card/entity-card-dark.png)、[验证脚本](assets/2026-11-20-entity-card/verify.py)。该检查验证标题链接静态颜色与该组件截图，不覆盖所有页面、交互或浏览器。

复验：在 `apps/studio` 启动 `npm run dev -- --port 5179 --strictPort`；在仓库根目录用 API/UI Worker 的 Playwright 环境执行 `apps/api-ui-worker/.venv/bin/python docs/studio/records/assets/2026-11-20-entity-card/verify.py`。脚本将临时截图写入 `.scratch/remediation-verification/`，依赖本机 Chromium。
