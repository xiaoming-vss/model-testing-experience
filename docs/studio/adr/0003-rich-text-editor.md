# 富文本编辑器选 tiptap，图片经统一文件管线

决定引入 **tiptap**（`@tiptap/react` + `@tiptap/starter-kit` + `@tiptap/extension-image`）作为唯一富文本实现，封装在 `shared/components/RichTextEditor`，全项目 `@tiptap/*` 的 import 只允许出现在这里（S5 清单已同步登记）。它满足 Bug 描述和需求正文所需的加粗、标题、列表、引用、代码块与粘贴截图能力，React 19 兼容、维护活跃，工具栏可按平台需要裁剪。

**图片链路与后端消毒约定**：粘贴或选择图片时立即上传统一文件管线（`uploadStoredFile`
purpose=`attachment`），编辑器里插入的 `<img>` 带 `data-file-id` 与一个**仅用于本次编辑预览**
的签名下载地址；`onChange` 输出前剥掉全部 `src`，存储值里只保留 `data-file-id`。
后端入库前用白名单消毒器（`control-plane` 的 `domain/rich_text.py`）重建 HTML——不保留
`src`/`href`/事件属性，也丢弃 script/style 子树；详情渲染时 `RichTextViewer` 按
`data-file-id` 现取短时效签名地址再加载，因此签名 URL 永不落库，权限随项目成员校验走。

**后果**：主包体积增加约 200 kB（gzip 约 60 kB），与现有「无代码分割」的取舍一致；
服务端必须保持消毒白名单与前端 `stripImageSources` 的约定同步——这是两处需要一起改的契约。
富文本一旦有第二个使用方（例如测试报告正文），应直接复用该组件而不是新起炉灶。
