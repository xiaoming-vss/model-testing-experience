import { describe, expect, it } from 'vitest'
import { normalizeApiConfigCases } from './apiConfigDiagram'
import { buildApiConfigContract, parseApiConfigFieldDescriptor } from './apiConfigContract'

function normalizeCase(body: Record<string, unknown>) {
  const data = normalizeApiConfigCases(JSON.stringify(body))
  if (!data) throw new Error('fixture must normalize')
  return data.cases[0]
}

describe('parseApiConfigFieldDescriptor', () => {
  it('解析类型、必传、约束和描述', () => {
    expect(parseApiConfigFieldDescriptor('string (必传, maxLength:20) # 用户名')).toMatchObject({
      type: 'string',
      required: true,
      optional: false,
      constraints: ['maxLength:20'],
      description: '用户名',
    })
  })

  it('保留 enum 值中的逗号并解析默认值', () => {
    expect(parseApiConfigFieldDescriptor('string (可选, enum:local,ldap, default:local) # 认证方式')).toMatchObject({
      type: 'string',
      optional: true,
      enumValue: 'local,ldap',
      defaultValue: 'local',
      description: '认证方式',
    })
  })

  it('识别请求头里的 [必传] 和 [关键提取] 标记', () => {
    expect(parseApiConfigFieldDescriptor('Bearer {{access_token}} # [必传]')).toMatchObject({
      type: 'value',
      value: 'Bearer {{access_token}}',
      required: true,
    })
    expect(parseApiConfigFieldDescriptor('string # [关键提取] 用于后续操作传承')).toMatchObject({
      type: 'string',
      keyExtraction: true,
      description: '用于后续操作传承',
    })
  })

  it('保留 additionalProperties 之类的原始约束', () => {
    expect(parseApiConfigFieldDescriptor('object (可选, 允许任意键值对/any)')).toMatchObject({
      type: 'object',
      optional: true,
      constraints: ['允许任意键值对/any'],
    })
  })

  it('不会把 default 值里的 # 当成描述分隔符', () => {
    expect(parseApiConfigFieldDescriptor('string (default:#fff) # 颜色')).toMatchObject({
      type: 'string',
      defaultValue: '#fff',
      description: '颜色',
    })
  })
})

describe('buildApiConfigContract', () => {
  it('汇总请求头、Path、Body 与嵌套响应字段', () => {
    const apiCase = normalizeCase({
      create_slice: {
        method: 'POST',
        path: '/v1/videos/{{videoId}}/semantic-slices',
        headers: { Authorization: 'Bearer {{token}} # [必传]' },
        path_params: { videoId: 'string (必传) # 视频 ID' },
        json: { segments: 'array (必传)', depthSwitch: 'boolean (可选, default:false)' },
        response: { code: 'integer (default:0)', data: { taskId: 'string # [关键提取] 轮询任务状态' } },
      },
    })
    const contract = buildApiConfigContract(apiCase)

    expect(contract.authHeader?.name).toBe('Authorization')
    expect(contract.requestFieldCount).toBe(4)
    expect(contract.responseFieldCount).toBe(2)
    expect(contract.totalFieldCount).toBe(6)
    expect(contract.usedVariables).toEqual(['videoId', 'token'])
    expect(contract.response.find((row) => row.name === 'data')).toMatchObject({ kind: 'object', childCount: 1 })
    expect(contract.response.find((row) => row.path === 'data.taskId')).toMatchObject({ depth: 1, keyExtraction: true })
    expect(contract.keyExtractions.map((row) => row.path)).toEqual(['data.taskId'])
  })

  it('把顶层数组响应展开为 items 节点与元素字段', () => {
    const apiCase = normalizeCase({
      list_items: { method: 'GET', path: '/items', response: [{ id: 'string # [关键提取]', name: 'string' }] },
    })
    const contract = buildApiConfigContract(apiCase)

    expect(contract.response[0]).toMatchObject({ name: 'items', kind: 'array', childCount: 2 })
    expect(contract.response[1]).toMatchObject({ path: '[].id', depth: 1 })
    expect(contract.responseFieldCount).toBe(2)
    expect(contract.keyExtractions[0].path).toBe('[].id')
  })

  it('识别表单请求体并保留原始文本 body', () => {
    const formCase = normalizeCase({
      login_form: { method: 'POST', path: '/login', data: { name: 'string (必传)' } },
    })
    expect(buildApiConfigContract(formCase).bodyLabel).toBe('Form')

    const rawCase = normalizeCase({ raw_body: { method: 'POST', path: '/raw', body: 'name=demo&age=1' } })
    expect(buildApiConfigContract(rawCase).rawBody).toBe('name=demo&age=1')
  })
})
