/**
 * 请求体 / 响应编辑区共用的画布样式。
 *
 * 编辑区不再自带一层带边框的卡片，CodeMirror 外壳和画布背景都融进外层详情卡片，
 * 由外层卡片、工具栏 hairline 和 gutter 分隔线承担结构，避免「卡片里再套两个盒子」。
 */
export const interfaceEditorCanvasClass =
  'if-editor-canvas min-h-0 flex-1 [&_.json-editor-wrap]:h-full [&_.json-editor-shell]:h-full [&_.json-editor-shell]:rounded-none [&_.json-editor-shell]:border-0 [&_.json-editor-shell]:bg-transparent [&_.json-editor-shell]:focus-within:shadow-none [&_.json-editor-codemirror]:h-full [&_.json-editor-shell_.cm-editor]:bg-transparent [&_.json-editor-shell_.cm-gutters]:bg-transparent'
