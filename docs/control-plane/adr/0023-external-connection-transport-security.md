# ADR 0023：禅道/GitLab 连接的传输安全策略

- 状态：已接受
- 日期：2026-11-19
- 取代：—
- 被取代：—
- 关联：[ADR 0014](0014-pre-release-single-baseline.md)、[数据库结构](../database-schema.md)、[Studio 基础服务](../../studio/README.md)

## 背景

禅道 token 接口曾使用 `httpx.AsyncClient(..., verify=False)`，GitLab 连接也允许 `http://` 地址并发送个人访问令牌。两者都没有显式开关或告警：用户以为连接是安全的，实际既可能明文传输凭据，也可能接受任意证书。

现网存在大量自部署的禅道和 GitLab HTTP 实例，直接禁止 HTTP 会让这些部署无法接入；强制公共 CA 也会排除自签名和内网 CA 的场景。因此需要的是「安全默认 + 显式例外 + 可见告警」，而不是一刀切。

## 决策

1. 连接级新增 `allowHttp`（默认 `false`）。`http://` 地址只有在显式开启后才允许；未开启时创建、重命名、重新授权和资源请求都返回 400。
2. HTTPS 默认 `verify=True`。新增连接级 `insecureSkipVerify`（默认 `false`），仅用于自签名证书或内网 CA；不提供平台级全局关闭开关。
3. 删除所有硬编码 `verify=False`；两个开关同时作用于认证请求、GitLab 资源读写和禅道连接查询。
4. 使用明文 HTTP 或跳过证书校验时，控制面在每次建立客户端时记录 WARNING，包含供应商与地址；凭据加密方式不变。
5. 开关按连接保存：共享服务资源保存一份，个人连接在 `extra_json` 保存 `allowHttp` / `insecureSkipVerify`，用户授权或重新授权时继承共享服务的当前选择；修改服务地址或开关会触发重新认证。
6. `shared_services` 表新增 `allow_http`、`insecure_skip_verify` 两列，按 [ADR 0014](0014-pre-release-single-baseline.md) 直接修改唯一 baseline。

## 后果

- 默认配置下 HTTP 连接会被拒绝，错误信息要求显式开启 `allowHttp`；这是有意的破坏性变更，避免静默降级。
- 升级前已存在的 HTTP 连接在第一次认证或资源请求时会被拒绝，需要用户重新保存连接并勾选「允许明文 HTTP」。已有开发库可先补列，再执行：
  ```sql
  ALTER TABLE shared_services
    ADD COLUMN allow_http TINYINT(1) NOT NULL DEFAULT 0
      COMMENT '禅道/GitLab 服务地址是否允许明文 HTTP',
    ADD COLUMN insecure_skip_verify TINYINT(1) NOT NULL DEFAULT 0
      COMMENT '禅道/GitLab 的 HTTPS 是否跳过证书校验';

  UPDATE shared_services SET allow_http = 1 WHERE base_url LIKE 'http://%';
  ```
- 个人连接的开关保存在 `extra_json`，无开关的旧记录按 `false` 处理；重新授权会补齐。批量升级可直接写入旧记录：
  ```sql
  UPDATE integration_connections
  SET extra_json = JSON_SET(COALESCE(extra_json, JSON_OBJECT()),
                            '$.allowHttp', true,
                            '$.insecureSkipVerify', false)
  WHERE provider IN ('gitlab', 'zentao') AND base_url LIKE 'http://%';
  ```
- 自签名 HTTPS 用户需要显式勾选跳过校验，否则连接失败；日志会持续提示风险。
- API 请求和响应新增 `allowHttp` / `insecureSkipVerify` 字段，前后端需同批发布。

## 备选方案

- **完全禁止 HTTP**：排除大量自部署实例，用户会改用反向代理或干脆不用平台，不采用。
- **保留隐式 HTTP、仅记录 WARNING**：用户无法区分主动选择与历史遗留，不安全配置继续扩散，不采用。
- **平台级全局关闭证书校验**：一个开关影响所有连接，风险不可控，不采用。
- **为内网 CA 提供自定义 CA bundle**：更安全，但需要文件分发与轮换机制，首期以显式跳过校验覆盖该场景，后续可再加。
