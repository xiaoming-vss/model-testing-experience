# 字段规则

## 1. 字段字符串

使用：

```text
"字段名": "数据类型 (是否必传, 附加约束) # 字段描述"
```

存在时保留这些约束：`maxLength:100`、`format:email`、`default:false`、`minimum`、`maximum`、`enum`。

没有描述时省略尾部注释，不补写描述。

## 2. 请求头与安全

根据 `interfaces[].security` 与 `interfaces[].securitySchemes` 添加认证：

- HTTP bearer → `"Authorization": "Bearer {{access_token}} # [必传]"`
- OAuth2 / OpenID Connect → `"Authorization": "Bearer {{access_token}} # [必传]"`
- HTTP basic → `"Authorization": "Basic {{basic_credentials}} # [必传]"`
- header 中的 apiKey → `"<headerName>": "{{<keyName>}} # [必传]"`
- query 中的 apiKey → 在 `query` 增加 `"<keyName>": "{{<keyName>}} # [必传]"`
- cookie 中的 apiKey → 在输出说明中保留原始 scheme 信息，不虚构请求头

`security` 与匹配的 scheme 都不存在时，不添加认证。显式声明的请求头原样保留。

请求体形态隐含或声明了 `Content-Type` 时一并保留：

- JSON 请求体使用 `json`
- 表单请求体使用 `data`

## 3. 登录接口噪声过滤

处理登录或认证接口时，丢弃以下四个框架生成的 OAuth2/FastAPI 样板字段：

- `grant_type`
- `scope`
- `client_id`
- `client_secret`

该过滤只对登录或认证接口生效。

其余表单字段无论名称、是否必传，都按源 schema 原样保留：不遗漏、不改名、不改变约束或描述。只有上述四个字段可以因此删除。

## 4. 响应关键字段标记

成功响应中明确可用于下游串联的字段，追加：

```text
# [关键提取] 用于后续操作传承
```

典型字段：`id`、`*_id`、`access_token`、`token`。不要过度标记无关字段。

## 5. 数组响应

顶层响应本身是数组时，`response` 必须直接是 JSON 数组：

```json
"response": [
  {
    "id": "string # [关键提取] 用于后续操作传承"
  }
]
```

不得增加 `items`、`list`、`data`、`model_item` 等包装键。

## 6. additionalProperties

字段包含 `additionalProperties: true` 时表示为：

```text
"object (允许任意键值对/any)"
```

不要复制 `additionalProp1` 之类的占位示例。

## 7. Schema 转换

- `string` → `string`
- `integer` → `integer`
- `number` → `number`
- `boolean` → `boolean`
- `object` → `object`
- `array` → 包含转换后元素 schema 的数组

必传状态按 schema 或参数级要求：

- 必传 → `必传`
- 可选 → `可选`

## 8. 分区

只在存在内容时创建：

- `headers`
- `path_params`
- `query`
- `json`
- `data`
- `response`

不为完整性创建空分区。
