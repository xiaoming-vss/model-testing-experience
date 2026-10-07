# 禅道同步任务交互

Studio 始终访问 control-plane，不直接访问 integration-worker、MCP 或业务数据库。状态入口统一返回 executionMode=worker，使用 `zentao-sync-jobs` 和 `zentao-field-update-jobs` 提交；旧同步方法已移除，所有项目的旧写路由已删除。未启用范围显示暂停原因，不回落旧写入口。

HTTP 202 只表示接受任务，界面显示“已提交”，不会据此显示同步成功。相同操作的网络重试复用 requestId；字段、目标或 Bug 改变后创建新的请求编号。状态查询按 activeJob/latestJob 恢复页面，queued/claimed/running 每三秒轮询。网络错误保留最后一次已知状态，终态区分整体完成、部分完成、失败、结果待核对和取消，并刷新 Bug 处理动态。Bug 已创建与全部附件/正文同步成功分别展示。

已有 Bug 的弹窗读取远端当前值，提交预览旧值及用户选择。未修改的历史影响版本、旧指派人无需重新选择候选；改变的字段仍必须属于有效候选。字段任务只写改变的字段，远端预览过期时拒绝覆盖，本地责任人不随其改变。

一次确认同时包含字段修改和内容补传时，先提交字段任务，明确成功后再提交补传；failed/unknown/canceled 不继续。已确认的后续补传仅保存字段 jobId 和后续 requestId，以操作人和 Bug 隔离在浏览器 sessionStorage 中，不保存 Token、下载票据或冻结正文。页面在同一浏览器会话内重新打开时，只有原操作人可继续该确认；其他成员查看旧结果不会替其提交。关闭浏览器会话后，已接受的服务器任务继续运行，尚未提交的补传需重新确认。后续提交仍由控制面重新校验当前权限、本人授权与本地目标。

创建 unknown 提供现有只读核对关联入口，附件 unknown 不提供普通重传，字段 unknown 通过远端当前值核对。正文 unknown 保留原只读确认及有界旧图片编码修复语义。对应控制面任务账本的恢复衔接已接入，见[实施记录](../control-plane/integration-worker-implementation.md)。

实现位于 bugs feature 的类型/API、`useBugZentaoStatus`、纯状态工具、`BugZentaoPushPanel` 及独立弹窗。组件专项 24 项覆盖接受任务、幂等重试、重新打开后的轮询、部分完成刷新、字段成功后继续、原操作人补传恢复及未知结果停止。

2026-10-07 使用实际组件和公共样式在隔离 Chrome 检查浅色/深色、1680×1000 和 760×1000，确认弹窗、排队重开、终态轮询、unknown 门控和只读权限通过，无页面横向溢出；结果与截图保存在 `.scratch/integration-browser/`。浏览器请求使用隔离 fixture，不作为真实后端、MCP 或禅道部署验收。

全量切换后 Studio 仅调用异步提交接口，客户端同步 POST/PATCH 方法已移除。关闭项目执行时显示暂停原因，仍可查询已接受任务；未知字段结果不触发内容补传。
