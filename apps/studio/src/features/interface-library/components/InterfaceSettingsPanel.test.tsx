import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { blankInterface } from '../utils/interfaceForm'
import { InterfaceSettingsPanel } from './InterfaceSettingsPanel'

afterEach(cleanup)

function draft(overrides: Partial<ReturnType<typeof blankInterface>> = {}) {
  return {
    ...blankInterface('repo-1'),
    interfaceId: 'api-1',
    name: '查询订单',
    path: '/orders',
    description: '按订单号查询',
    tags: ['订单'],
    ...overrides,
  }
}

function renderPanel(value = draft()) {
  const onTagsText = vi.fn()
  const onChange = vi.fn()
  const view = render(
    <InterfaceSettingsPanel
      draft={value}
      readOnly={false}
      tagsText={value.tags.join(', ')}
      onTagsText={onTagsText}
      requirementOptions={[
        { requirementId: 'req-1', name: '下单流程', sprintId: 'sprint-1', sprintName: 'V1.0.0' },
      ]}
      onChange={onChange}
    />,
  )
  return { ...view, onTagsText, onChange }
}

describe('InterfaceSettingsPanel', () => {
  it('drops the duplicated update time and keeps a compact source rail', () => {
    renderPanel()

    expect(screen.getByText('来源与认证')).toBeInTheDocument()
    expect(screen.getByText('手工创建')).toBeInTheDocument()
    expect(screen.getByText('未声明认证')).toBeInTheDocument()
    expect(screen.queryByText('最近更新')).not.toBeInTheDocument()
    expect(screen.queryByText('原始安全定义')).not.toBeInTheDocument()
    expect(screen.queryByText('导入时间')).not.toBeInTheDocument()
    expect(screen.getByText('6 / 1024')).toBeInTheDocument()
  })

  it('summarizes imported auth and keeps the raw definition behind a disclosure', () => {
    renderPanel(
      draft({
        source: {
          type: 'openapi_file',
          name: 'Model Testing Experience API',
          url: '',
          version: '1.0.0',
          importedAt: '2026-11-23T22:47:10Z',
        },
        security: [{ bearerAuth: [] }],
        securitySchemes: {
          bearerAuth: { type: 'http', scheme: 'bearer', bearerFormat: 'JWT' },
        },
      }),
    )

    expect(screen.getByText('Model Testing Experience API')).toBeInTheDocument()
    expect(screen.getByText('OpenAPI 文档导入 · v1.0.0')).toBeInTheDocument()
    expect(screen.getByText('导入时间')).toBeInTheDocument()
    expect(screen.getByText('Bearer Token')).toBeInTheDocument()
    expect(screen.getByText('Authorization: Bearer {token}')).toBeInTheDocument()

    const details = screen.getByText('原始安全定义').closest('details')
    if (!details) throw new Error('原始安全定义缺少 details 容器')
    expect(details).not.toHaveAttribute('open')
    expect(screen.getByText(/"securitySchemes"/)).toBeInTheDocument()
  })
})
