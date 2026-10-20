# 认证、账号与系统管理员

浏览器使用 `Authorization: Bearer <JWT>` 访问业务接口。JWT 使用 HS256 签名，包含用户身份、令牌版本、到期时间、签发时间和每次登录独立的 `jti`。普通本地账号有效期默认 72 小时，系统超级管理员默认 24 小时；配置项为 `security.jwt.user_expire_hours` 和 `security.jwt.super_admin_expire_hours`。

## 注册与登录

注册字段为用户名、密码和邮箱。用户名创建后不可修改；邮箱必填且唯一，保存前统一去除首尾空白并转为小写。密码至少 10 个字符，且不能超过 bcrypt 的 72 字节上限。注册和自助改密都不发送验证邮件，也不生成重置链接。

登录只校验用户名和密码，成功后按账号类型签发对应有效期的 JWT。登录响应额外返回 `mustChangePassword`；为 `true` 时前端进入改密页，后端同时拦截除改密、登出和读取当前登录信息以外的业务请求，返回专用错误码 `1003`，不能只依赖前端跳转。

账号被禁用时登录返回 `1004`，已签发 Token 同时失效。连续登录失败默认达到 5 次后锁定 15 分钟，返回 `1005`；同一 IP 与用户名的失败尝试默认在 15 分钟窗口内累计 5 次后返回 `1006`。阈值和时长由 `security.login.max_failures`、`lock_minutes`、`rate_limit_window_minutes` 配置。锁定对系统超级管理员同样生效；运维 CLI 重置密码时会清除失败计数和锁定状态。

## 令牌失效

`revoked_access_tokens` 只保存用户主动登出时的单个 Token 摘要，不保存原始 Token。用户自助改密、超级管理员重置密码、禁用账号和强制下线使用 `users.token_version` 统一失效全部已签发 Token：JWT 中的 `ver` 必须与数据库当前版本一致，否则返回 401。旧版 Token 没有 `ver` 时按版本 0 处理；上线本能力时应轮换 JWT 密钥，使旧 Token 全部失效。

`POST /v1/logout` 仍只注销当前登录会话；同一用户的其他会话继续有效。服务端在提交数据库事务后返回成功，随后携带这个 Token 的业务请求返回 401。

## 个人设置与改密

`GET /v1/user` 返回 `userId`、`name`、`email`、`isSuperAdmin` 和 `mustChangePassword`。`PUT /v1/user` 只允许修改邮箱；用户名创建后不允许修改。

`PUT /v1/user/password` 接收 `oldPassword` 和 `newPassword`，验证旧密码、校验新密码规则并拒绝与旧密码相同的新密码；成功后版本号递增，所有已签发 Token 失效，需要重新登录。超级管理员首次登录、上线迁移和运维 CLI 重置后的强制改密复用同一接口，仍要求验证当前密码。

个人设置不再提供自行注销入口；账号删除统一由系统超级管理员执行。

## 系统超级管理员

系统只预置一个超级管理员，由控制面启动时根据 `security.super_admin` 创建：

```toml
[security.super_admin]
username = "admin"
email = "admin@example.com"
initial_password = "GENERATE"
```

`username` 和 `email` 必填；缺失时拒绝启动。`initial_password` 为空、缺失或为 `GENERATE` 时使用约定的 `mtx123456`，并在首次登录后强制改密；生产部署应通过统一配置生成或显式设置密码。启动时仅在不存在超级管理员时创建，已存在时重启不覆盖用户名、邮箱、密码或状态。若配置的用户名或邮箱已被普通账号占用，启动失败并提示先处理冲突，不会静默提升普通账号。数据库对 `users.super_admin_slot` 建立唯一约束，避免并发启动创建第二个超级管理员。

超级管理员可访问和操作全部项目业务资源，项目列表展示所有项目，但前端标识为“系统管理员”，不伪装成项目所有者。需要成为 Bug 责任人、测试单执行人等指派对象时，仍应显式加入项目。超级管理员不能查看、解密或使用其他用户的个人授权连接、共享服务授权或个人秘密环境变量，也不提供 impersonate 能力。

密码丢失时使用仅运维可用的 CLI：

```sh
uv run python -m testing_agent.cli.super_admin reset-password --config config/local.toml
# 或从标准输入读取，避免交互式终端
uv run python -m testing_agent.cli.super_admin reset-password --config config/local.toml --password-stdin
```

CLI 只按超级管理员标记定位账号，不创建第二个账号；不存在时提示先启动控制面完成初始化。重置后设置 `must_change_password=true`、递增令牌版本、清除失败计数和锁定状态，不通过公开 HTTP 接口提供。

## 账号禁用与删除

禁用保留账号行、项目成员关系、个人授权和已提交任务：不能登录、已签发 Token 立即失效，排队中或运行中的任务继续执行，但不能发起新任务。启用后账号可重新登录，但禁用前的旧 Token 不会恢复。禁用原因、操作人和时间保存在账号字段中，不单独建设审计表。

删除为物理删除，仅系统超级管理员可执行。删除时：

- 该用户拥有的项目自动转给系统超级管理员；重名时追加原用户名或序号并截断到 100 字符。
- 删除项目成员关系、共享服务授权、个人集成连接、个人秘密环境变量和已撤销 Token 记录。
- 撤销该用户发起的待执行或运行中任务授权，任务按现有失败流程结束；历史运行记录保留。
- 历史业务记录保留原始 `user_id`；用户查不到时前端显示“已删除账户”，不自动匹配同名新账号。
- 用户名和邮箱随账号释放；新账号使用新的 `user_id`，不回收旧标识。

删除操作在同一事务内完成，任一步失败整体回滚。

## 管理接口

以下接口要求当前账号为系统超级管理员：

- `GET /v1/admin/users?search=&status=&page=&pageSize=`
- `POST /v1/admin/users/{userId}/disable`
- `POST /v1/admin/users/{userId}/enable`
- `POST /v1/admin/users/{userId}/reset-password`
- `POST /v1/admin/users/{userId}/revoke-sessions`
- `PUT /v1/admin/users/{userId}/email`
- `DELETE /v1/admin/users/{userId}`

系统超级管理员账号不能禁用或删除，管理页面显示为受保护账号。

## 迁移与配置

部署本能力前执行数据库迁移：

```sh
python3 scripts/manage.py migrate
```

迁移 `20261020_0040` 为 `users` 增加超级管理员、账号状态、强制改密、密码更新时间、令牌版本和登录失败锁定字段，并新增 `login_rate_limits` 表。历史账号的 `status` 为 `active`、`must_change_password=false`、`token_version=0`；邮箱列保持可空以兼容存量数据，新注册和个人设置按必填校验。存量空邮箱由系统超级管理员在账号管理中补填。

`python3 scripts/manage.py upgrade-config` 会为已有统一配置补齐超级管理员、登录限流和 JWT 有效期配置；生成的控制面配置由 `configure` 写入运行配置。修改 JWT 有效期或轮换密钥后需要重启控制面。

## LDAP 外部身份扩展

LDAP 用户的身份只读、待关联状态、登录入口、配置切换及对账规则见 [LDAP 统一认证](ldap-authentication.md)。本地账号规则继续适用；LDAP 开启后自助注册关闭，普通本地账号不能通过本地入口登录。
