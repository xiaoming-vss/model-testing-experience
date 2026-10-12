# 需求富文本编辑

新建需求默认富文本，继续提供 Word 上传。复用 `shared/components/RichTextEditor`，支持标题、加粗、列表、引用、代码、基本表格、PNG/JPEG 图片选择与截图粘贴。新增表格能力保持在共享封装中；表格可插入、增加或删除行列及删除整表。

正文以 HTML 文件经统一上传管线保存到 S3，保存成功后关联需求。编辑时下载当前正文并回填编辑器，详情使用 `RichTextViewer` 展示并按图片文件 ID 获取临时访问地址。加载失败时禁用正文保存，图片上传中禁用保存；上传失败不会提交新的需求关联。正文与名称在一次需求更新中提交，不把富文本写进增强文本字段。

共享编辑器支持受控内容异步回填和 disabled 状态更新；切换需求或重新打开窗口不会保留上次正文。空段落不可提交，仅含有效图片的正文可提交。表格排版采用共享主题颜色，窄屏在编辑区域滚动。

工具栏右侧提供「放大编辑」：点击在弹框（宽 `min(1080px, 94vw)`，编辑区约 56vh 高、内部滚动）中继续编辑，内容与撤销历史实时同步到表单值；弹框内工具栏同一按钮变为「恢复内联编辑」，关闭弹框或点击底部按钮回到内联。放大能力属于共享编辑器，所有使用方（新建/编辑需求、Bug 描述等）一致生效。

历史 TXT 保持原有读取入口，不自动迁移。编辑时可切换为富文本重新填写，或切换为 Word 上传新文件；保存成功后替换文档关联。Word 上传行为保持兼容。AI 分析的 HTML 与图片读取已在后续 Worker 接入中补齐，见[需求富文本正文](../control-plane/requirement-rich-text.md)。

相关检查：需求 API、需求预览、ProjectsPage、RichTextEditor/RichTextViewer 测试及 `npm run verify`。服务端约定见 [需求富文本正文](../control-plane/requirement-rich-text.md)。

2026-10-08 验证：需求 API、抽屉、预览、详情编辑、ProjectsPage、共享富文本及 Bug 组件共 85 项相关测试通过（详情页修正测试选择器后单独重跑 8 项）。隔离页面使用真实组件，在 1680×1000 浅色及 760×1000 深色视口检查标题、列表、表格与工具栏；增行、保存、重新打开保持内容。窄屏抽屉宽 520px，无内部横向溢出。截图存于 `.scratch/requirement-rich-text/`。隔离页面没有真实 S3 请求，不代表部署后的端到端验收。


2026-10-08 后续开放编辑时的类型切换。列表与详情两个入口在切换时清除加载/保存错误，使旧请求失效；旧请求后续成功或失败均不能覆盖新内容或重新阻塞保存。切换会清空正文与文件选择，表单提前说明此行为；切换为 Word 必须提供新文件，不能复用切换前的文件名。文件与名称通过同一次替换请求提交，取消编辑或上传失败不会替换原关联。上传或保存进行中禁用切换。

本次 25 项相关测试通过：`npm test -- src/app/pages/RequirementDetailPage.test.tsx src/features/requirements/components/RequirementDrawer.test.tsx src/features/projects/pages/ProjectsPage.test.tsx src/features/requirements/api/requirements.api.test.ts`（页面测试修正 jsdom 不支持的鼠标定位输入为粘贴事件后重跑）。`npm run verify` 通过；浏览器隔离页面验证原文件缺失→富文本→完整输入保存，以及 760×1000 深色下切换 Word 后的必填提示。截图为 `.scratch/requirement-rich-text/type-switch-richtext.png` 与 `type-switch-word-dark.png`。Impeccable detector 唯一警告命中正文校验正则里的 `<img`，不是实际图片元素，判定为误报。此次未改后端或 AI 分析，未执行真实 S3 写入验收。

2026-10-10 新增「放大编辑」弹框：编辑器卡片由宿主 `rich-text-editor-host` 持有、同一 Tiptap 实例只挂载一次，放大/恢复通过 DOM 搬移进出弹框承接槽，内容、撤销历史与光标均保留；弹框内编辑区带卡片边框、约 56vh 高并内部滚动。`RichTextEditor.test.tsx` 新增 2 项（弹框打开/内容可见/内联卸载、关闭恢复内联且内容保留；禁用态不提供放大），共享编辑器及消费方 5 个测试文件 27 项通过。隔离页面（`.scratch/richtext-expand-preview/`，真实编辑器 + 新建需求抽屉形态）在 1680×1000 浅色内联/弹框及 760×1000 深色弹框核对：工具栏右侧放大按钮、弹框铺满编辑区、恢复内联闭环，无横向溢出。Impeccable detector 仅命中既有的 blockquote 左边框样式（非本次改动，保留）。jsdom 缺少 `elementFromPoint`，弹框内键盘输入的交互由浏览器验收覆盖。未提交真实业务写操作。

同日修复二次打开空弹框：antd 关闭后默认保留弹框节点，条件卸载/挂载 `EditorContent` 的重挂载时机会与之互踩（首次关闭后弹框内实例不再重新挂载）。改为编辑器只挂载一次，放大/恢复由 `useEffect` 把编辑器卡片 DOM 整体 `appendChild` 进出弹框承接槽；弹框面板晚一拍挂载，承接槽以回调 ref 记入 state 触发补跑。组件测试新增「二次打开编辑器重新出现」回归断言（4 项通过），浏览器以真实组件连开三轮均正常（开→恢复→开，编辑器与内容始终在弹框内、关闭后回到内联）。
