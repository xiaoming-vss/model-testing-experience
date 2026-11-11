# 文件直传

需求上传通过 `shared/api/files.ts` 申请签名 POST、直传 S3 并通知后端核验，然后以 `documentFileId` 创建或更新需求。上传进度在需求抽屉展示，失败保留表单供重新提交；未启用 S3 时提示配置错误，不回退本地上传。

平台业务请求继续使用统一 request 封装；对象存储上传使用独立 XMLHttpRequest，下载使用不携带平台令牌和 Cookie 的 fetch。图片、附件接入时复用上传能力和文件 ID，不在正文保存临时签名地址。

需求预览和下载在原下载入口请求 JSON 票据，仅接受 S3 下载票据，不兼容本地二进制响应。前端页面需 HTTPS（localhost 除外），并在存储服务上配置对应域名的 CORS。

配置、生命周期和验收参见 [控制面统一存储](../control-plane/file-storage.md)。


UI 生成不再上传源码 ZIP，也不使用 `ui_source_archive` 用途。UI 源码配置只选择仓库画像版本、前端仓库、commit 模式和来源功能用例；启动后来源追溯展示仓库、分支、commit、画像版本和用例，不展示克隆地址、连接 ID 或凭据。历史 ZIP 运行数据已清理，不再提供上传、替换或归档只读展示。


项目上传技能包使用 `project_skill` 签名直传并提交 fileId；下载经项目权限校验。UI 截图使用共享 `StoredImage` 组件按稳定文件路径申请票据、独立获取 Blob 并释放临时 URL；Trace 提供鉴权下载按钮。旧 Worker URL 不再加载，提示历史文件未存入 S3。
