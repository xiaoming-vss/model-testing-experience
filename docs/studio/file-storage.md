# 文件直传

需求上传通过 `shared/api/files.ts` 申请签名 POST、直传 S3 并通知后端核验，然后以 `documentFileId` 创建或更新需求。上传进度在需求抽屉展示，失败保留表单供重新提交；未启用 S3 时提示配置错误，不回退本地上传。

平台业务请求继续使用统一 request 封装；对象存储上传使用独立 XMLHttpRequest，下载使用不携带平台令牌和 Cookie 的 fetch。图片、附件接入时复用上传能力和文件 ID，不在正文保存临时签名地址。

需求预览和下载在原下载入口请求 JSON 票据，仅接受 S3 下载票据，不兼容本地二进制响应。前端页面需 HTTPS（localhost 除外），并在存储服务上配置对应域名的 CORS。

配置、生命周期和验收参见 [控制面统一存储](../control-plane/file-storage.md)。


UI 源码包复用签名直传，purpose 为 `ui_source_archive`；完成核验后把 `fileId` 以 JSON 关联到 UI 任务，不再向业务接口发送 multipart 文件。上传或核验失败不替换当前包，旧任务运行固定使用启动时的文件 ID。S3 未启用时明确报错，无本地回退。


项目上传技能包使用 `project_skill` 签名直传并提交 fileId；下载经项目权限校验。UI 截图使用共享 `StoredImage` 组件按稳定文件路径申请票据、独立获取 Blob 并释放临时 URL；Trace 提供鉴权下载按钮。旧 Worker URL 不再加载，提示历史文件未存入 S3。
