import { describe, expect, it } from 'vitest'
import { describeInterfaceAuth } from './interfaceSecurity'

describe('describeInterfaceAuth', () => {
  it('reports no auth for empty or missing security snapshots', () => {
    expect(describeInterfaceAuth(null, null)).toEqual({
      hasAuth: false,
      label: '未声明认证',
      hint: '生成 API 用例时不附加认证头。',
    })
    expect(describeInterfaceAuth([], {})).toMatchObject({ hasAuth: false, label: '未声明认证' })
  })

  it('summarizes bearer, api key and oauth schemes', () => {
    expect(
      describeInterfaceAuth(
        [{ bearerAuth: [] }],
        { bearerAuth: { type: 'http', scheme: 'bearer', bearerFormat: 'JWT' } },
      ),
    ).toEqual({
      hasAuth: true,
      label: 'Bearer Token',
      hint: 'Authorization: Bearer {token}',
    })

    expect(
      describeInterfaceAuth(
        [{ apiKey: [] }],
        { apiKey: { type: 'apiKey', in: 'header', name: 'X-API-Key' } },
      ),
    ).toEqual({
      hasAuth: true,
      label: 'API Key',
      hint: '参数位于请求头：X-API-Key',
    })

    expect(
      describeInterfaceAuth(
        [{ oauth: [] }],
        { oauth: { type: 'oauth2', flows: {} } },
      ),
    ).toEqual({
      hasAuth: true,
      label: 'OAuth 2.0',
      hint: '由 OAuth 2.0 流程获取访问令牌。',
    })
  })

  it('keeps multiple schemes legible without exposing raw JSON', () => {
    expect(
      describeInterfaceAuth(
        [{ bearerAuth: [] }, { apiKey: [] }],
        {
          bearerAuth: { type: 'http', scheme: 'bearer' },
          apiKey: { type: 'apiKey', in: 'query', name: 'token' },
        },
      ),
    ).toEqual({
      hasAuth: true,
      label: '2 种认证',
      hint: '包含 Bearer Token、API Key；生成 API 用例时按需补充认证头。',
    })
  })

  it('falls back to declared security names when scheme details are missing', () => {
    expect(describeInterfaceAuth([{ bearerAuth: [] }, { apiKey: [] }], null)).toEqual({
      hasAuth: true,
      label: '2 种认证',
      hint: '包含 bearerAuth、apiKey；生成 API 用例时用于补充认证头。',
    })
  })
})
