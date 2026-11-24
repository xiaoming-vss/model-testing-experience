import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { ImportCommitResult, SoftwareRepository, ImportPreview } from '../types'
import { OpenApiImportModal } from './OpenApiImportModal'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))
vi.mock('../api/interfaceLibrary.api', () => ({
  interfaceLibraryApi: {
    previewOpenApiImport: vi.fn(),
    commitOpenApiImport: vi.fn(),
  },
}))

const app: SoftwareRepository = {
  softwareRepositoryId: 'app-1',
  projectId: 'project-1',
  name: '订单服务',
  description: '',
  basePath: '/api/v1',
  repository: {
    projectId: '41',
    path: 'commerce/order-service',
    name: 'order-service',
    instanceUrl: 'https://gitlab.example.com',
  },
  interfaceGroups: [],
  interfaceCount: 1,
  version: 4,
}

function preview(canApply: boolean): ImportPreview {
  return {
    source: {
      type: 'openapi',
      name: 'orders.yaml',
      url: '',
      version: '1.0.0',
      digest: 'digest-1',
      basePath: '/api/v2',
    },
    softwareRepository: {
      softwareRepositoryId: 'app-1',
      name: '订单服务',
      basePath: '/api/v1',
    },
    summary: { new: 1, modified: 1, unchanged: 1, libraryOnly: 1 },
    basePathChange: { current: '/api/v1', document: '/api/v2', canApply },
    warnings: [{ code: 'external_ref', message: '保留外部引用', method: 'GET', path: '/orders' }],
    items: [
      {
        key: 'GET:/orders',
        changeType: 'new',
        method: 'GET',
        path: '/orders',
        name: '查询订单列表',
        existingInterfaceId: null,
        existingVersion: null,
        changedFields: [],
        tags: ['Orders'],
        existingTags: [],
      },
      {
        key: 'POST:/orders',
        changeType: 'modified',
        method: 'POST',
        path: '/orders',
        name: '创建订单',
        existingInterfaceId: 'api-2',
        existingVersion: 2,
        changedFields: ['请求体 Schema'],
        tags: ['Orders'],
        existingTags: ['Orders'],
      },
      {
        key: 'GET:/orders/{orderId}',
        changeType: 'unchanged',
        method: 'GET',
        path: '/orders/{orderId}',
        name: '查询订单',
        existingInterfaceId: 'api-1',
        existingVersion: 1,
        changedFields: [],
        tags: ['Orders'],
        existingTags: ['Orders'],
      },
      {
        key: 'DELETE:/orders/{orderId}',
        changeType: 'library_only',
        method: 'DELETE',
        path: '/orders/{orderId}',
        name: '删除订单',
        existingInterfaceId: 'api-3',
        existingVersion: 1,
        changedFields: [],
        tags: ['Admin'],
        existingTags: ['Admin'],
      },
    ],
  }
}

const DEFAULT_COMMIT_RESULT: ImportCommitResult = {
  created: 1,
  updated: 1,
  skipped: 0,
  libraryOnly: 1,
  softwareRepositoryBasePath: '/api/v2',
  interfaces: [],
}

function renderModal(
  previewData = preview(true),
  commitResult: ImportCommitResult = DEFAULT_COMMIT_RESULT,
) {
  vi.mocked(interfaceLibraryApi.previewOpenApiImport).mockResolvedValue(previewData)
  vi.mocked(interfaceLibraryApi.commitOpenApiImport).mockResolvedValue(commitResult)
  return render(
    <OpenApiImportModal
      open
      repositories={[app]}
      defaultSoftwareRepositoryId="app-1"
      onClose={vi.fn()}
      onImported={vi.fn()}
    />,
  )
}

async function chooseFile(user: ReturnType<typeof userEvent.setup>) {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')
  expect(input).not.toBeNull()
  const file = new File(['openapi: 3.0.0'], 'orders.yaml', { type: 'application/yaml' })
  await user.upload(input!, file)
  return file
}

describe('OpenApiImportModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(cleanup)

  it('previews the file diff and commits selected items with versions and base path', async () => {
    const user = userEvent.setup()
    renderModal()
    const file = await chooseFile(user)

    await user.click(screen.getByRole('button', { name: '预览差异' }))
    expect(await screen.findByText('查询订单列表')).toBeInTheDocument()
    expect(screen.getByText('创建订单')).toBeInTheDocument()
    expect(screen.getByText('查询订单')).toBeInTheDocument()
    expect(screen.getByText('删除订单')).toBeInTheDocument()
    expect(interfaceLibraryApi.previewOpenApiImport).toHaveBeenCalledWith('app-1', file)
    const ordersGroup = screen.getByRole('group', { name: '分组 Orders' })
    expect(within(ordersGroup).getByText('Orders')).toBeInTheDocument()
    expect(within(ordersGroup).getByText('3')).toBeInTheDocument()
    expect(within(ordersGroup).queryByText('新建分组')).not.toBeInTheDocument()
    expect(within(ordersGroup).getByRole('checkbox', { name: '选择分组 Orders' })).toBeChecked()
    const adminGroup = screen.getByRole('group', { name: '分组 Admin' })
    expect(within(adminGroup).getByText('仅库中存在')).toBeInTheDocument()
    expect(within(adminGroup).getByRole('checkbox', { name: '选择分组 Admin' })).toBeDisabled()
    expect(screen.getByRole('status', { name: '已选 2 / 2' })).toBeInTheDocument()
    expect(screen.getByText(/保留库内标签和分组/)).toBeInTheDocument()

    await user.click(screen.getByRole('checkbox', { name: /同时更新软件仓库 base path/ }))
    await user.click(screen.getByRole('button', { name: '导入选中 2 项' }))

    await waitFor(() => expect(interfaceLibraryApi.commitOpenApiImport).toHaveBeenCalled())
    expect(interfaceLibraryApi.commitOpenApiImport).toHaveBeenCalledWith(
      'app-1',
      expect.objectContaining({
        file,
        sourceDigest: 'digest-1',
        selectedKeys: ['GET:/orders', 'POST:/orders'],
        expectedItems: { 'POST:/orders': 2 },
        applyBasePath: true,
        expectedSoftwareRepositoryVersion: 4,
      }),
    )
    expect(await screen.findByText('导入完成')).toBeInTheDocument()
  })

  it('marks groups created by new interfaces and updates the preview with selection', async () => {
    const user = userEvent.setup()
    const data = preview(true)
    data.items[0] = { ...data.items[0], tags: ['Payments'] }
    renderModal(data, {
      ...DEFAULT_COMMIT_RESULT,
      interfaces: [{ key: 'GET:/orders', interfaceId: 'api-9', changeType: 'new' }],
    })
    await chooseFile(user)

    await user.click(screen.getByRole('button', { name: '预览差异' }))
    await screen.findByText('查询订单列表')
    const paymentsGroup = screen.getByRole('group', { name: '分组 Payments' })
    expect(within(paymentsGroup).getByText('新建分组')).toBeInTheDocument()
    const ordersGroup = screen.getByRole('group', { name: '分组 Orders' })
    expect(within(ordersGroup).queryByText('新建分组')).not.toBeInTheDocument()
    expect(screen.getByRole('status', { name: '已选 2 / 2' })).toBeInTheDocument()

    const newRow = within(paymentsGroup)
      .getByText('查询订单列表')
      .closest('.if-import-row') as HTMLElement
    expect(newRow).toHaveTextContent('查询订单列表')

    await user.click(within(newRow).getByRole('checkbox'))
    expect(screen.getByRole('status', { name: '已选 1 / 2' })).toBeInTheDocument()
    expect(within(paymentsGroup).getByRole('checkbox', { name: '选择分组 Payments' })).not.toBeChecked()

    await user.click(within(newRow).getByRole('checkbox'))
    expect(screen.getByRole('status', { name: '已选 2 / 2' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '导入选中 2 项' }))
    await screen.findByText('导入完成')
    expect(screen.getByText('本次新建分组')).toBeInTheDocument()
    expect(screen.getByText('Payments')).toBeInTheDocument()
  })

  it('selects a whole group and filters the grouped preview by search', async () => {
    const user = userEvent.setup()
    renderModal()
    await chooseFile(user)

    await user.click(screen.getByRole('button', { name: '预览差异' }))
    await screen.findByText('查询订单列表')

    const search = screen.getByRole('textbox', { name: '搜索导入分组' })
    await user.type(search, 'Admin')
    expect(screen.getByRole('group', { name: '分组 Admin' })).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: '分组 Orders' })).not.toBeInTheDocument()
    await user.clear(search)

    const ordersGroup = screen.getByRole('group', { name: '分组 Orders' })
    const ordersCheckbox = within(ordersGroup).getByRole('checkbox', { name: '选择分组 Orders' })
    expect(ordersCheckbox).toBeChecked()
    await user.click(ordersCheckbox)
    expect(screen.getByRole('status', { name: '已选 0 / 2' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '导入选中 0 项' })).toBeDisabled()
    await user.click(ordersCheckbox)
    expect(screen.getByRole('status', { name: '已选 2 / 2' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '导入选中 2 项' })).toBeEnabled()
  })

  it('accepts a directly pasted JSON document through the shared editor', async () => {
    const user = userEvent.setup()
    renderModal()

    await user.click(screen.getByText('直接输入 JSON', { exact: true }))
    const editor = screen.getByRole('textbox', { name: 'OpenAPI JSON 内容' })
    await user.click(editor)
    await user.keyboard('{Control>}a{/Control}')
    await user.paste(JSON.stringify({
      openapi: '3.0.0',
      info: { title: '内联文档', version: '1.0.0' },
      paths: {},
    }))
    await user.click(screen.getByRole('button', { name: '预览差异' }))

    await waitFor(() => expect(interfaceLibraryApi.previewOpenApiImport).toHaveBeenCalled())
    const [, source] = vi.mocked(interfaceLibraryApi.previewOpenApiImport).mock.calls[0]
    expect(source.name).toBe('inline-openapi.json')
    expect(source.type).toBe('application/json')
    expect(await source.text()).toContain('"openapi":"3.0.0"')

    await user.click(screen.getByRole('button', { name: '导入选中 2 项' }))
    await waitFor(() => expect(interfaceLibraryApi.commitOpenApiImport).toHaveBeenCalled())
    const [, commitPayload] = vi.mocked(interfaceLibraryApi.commitOpenApiImport).mock.calls[0]
    expect(commitPayload.file.name).toBe('inline-openapi.json')
    expect(await commitPayload.file.text()).toContain('"openapi":"3.0.0"')
  })

  it('rejects invalid inline JSON before calling preview', async () => {
    const user = userEvent.setup()
    renderModal()

    await user.click(screen.getByText('直接输入 JSON', { exact: true }))
    const editor = screen.getByRole('textbox', { name: 'OpenAPI JSON 内容' })
    await user.click(editor)
    await user.keyboard('{Control>}a{/Control}')
    await user.paste('{not-json')
    await user.click(screen.getByRole('button', { name: '预览差异' }))

    expect(await screen.findByText(/JSON 格式错误：/)).toBeInTheDocument()
    expect(interfaceLibraryApi.previewOpenApiImport).not.toHaveBeenCalled()
  })

  it('blocks a member commit when the document changes the software repository base path', async () => {
    const user = userEvent.setup()
    renderModal(preview(false))
    await chooseFile(user)

    await user.click(screen.getByRole('button', { name: '预览差异' }))
    expect(await screen.findByText(/普通成员不能修改软件仓库 base path/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '导入选中 2 项' })).toBeDisabled()
  })
})
