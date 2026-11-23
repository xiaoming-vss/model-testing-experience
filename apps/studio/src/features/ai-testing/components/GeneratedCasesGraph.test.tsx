import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { buildGeneratedCasesModel } from '../utils/generatedCasesModel'
import { GeneratedCasesGraph } from './GeneratedCasesGraph'

const content = JSON.stringify({
  cases: [{
    case_id: '0a8f76e9-5f2c-4b1e-9a3d-0123456789ab',
    case_module: '清洗核验',
    case_type: '功能测试',
    case_title: '验证保存',
    priority: 'P1',
    precondition: ['已登录'],
    steps: ['打开页面', '点击保存'],
    expected_results: ['保存成功'],
  }],
})

function setup(overrides: Partial<Parameters<typeof GeneratedCasesGraph>[0]> = {}) {
  const model = buildGeneratedCasesModel(content)!
  const firstScene = model.modules[0].scenes[0]
  return render(<GeneratedCasesGraph
    model={model}
    selection={{ kind: 'case', key: model.entries[0].key }}
    expandedSceneIds={new Set([firstScene.id])}
    rootTitle="完整用例"
    canEdit={false}
    canDelete={false}
    onSelect={() => undefined}
    onSceneSelect={() => undefined}
    onModuleSelect={() => undefined}
    onCloseDetail={() => undefined}
    {...overrides}
  />)
}

beforeAll(() => {
  vi.stubGlobal('DOMMatrixReadOnly', class { m22 = 1 })
  vi.stubGlobal('ResizeObserver', class {
    callback: ResizeObserverCallback
    constructor(callback: ResizeObserverCallback) { this.callback = callback }
    observe(target: Element) { queueMicrotask(() => this.callback([{ target, contentRect: { width: 1000, height: 700 } } as ResizeObserverEntry], this as unknown as ResizeObserver)) }
    unobserve() {}
    disconnect() {}
  })
})
beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(430)
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(560)
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ x: 0, y: 0, width: 1000, height: 700, top: 0, right: 1000, bottom: 700, left: 0, toJSON: () => ({}) } as DOMRect)
})
afterAll(() => vi.unstubAllGlobals())
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('GeneratedCasesGraph', () => {
  it('在图内展示用例详情、完整编号与字段', async () => {
    setup()
    expect(await screen.findByRole('article', { name: '用例详情' })).toBeInTheDocument()
    expect(screen.getByText('验证保存')).toBeInTheDocument()
    expect(screen.getByText('0a8f76e9-5f2c-4b1e-9a3d-0123456789ab')).toBeInTheDocument()
    expect(screen.getByText('前置条件')).toBeInTheDocument()
    expect(screen.getByText('测试步骤')).toBeInTheDocument()
    expect(screen.getByText('预期结果')).toBeInTheDocument()
    expect(screen.getByText('打开页面')).toBeInTheDocument()
  })

  it('编辑态渲染可编辑字段并把修改交给父级', async () => {
    const onChangeCase = vi.fn()
    setup({ canEdit: true, onChangeCase })
    const name = await screen.findByRole('textbox', { name: '用例名称' })
    fireEvent.change(name, { target: { value: '验证更新' } })
    expect(onChangeCase).toHaveBeenCalledWith(expect.objectContaining({ key: '清洗核验:0' }), { case_title: '验证更新' })
    expect(screen.queryByRole('textbox', { name: '用例编号' })).not.toBeInTheDocument()
  })

  it('可删除时提供删除操作，只读时不展示', async () => {
    const onChangeCase = vi.fn()
    const onDeleteCase = vi.fn()
    const { unmount } = setup({ canEdit: true, canDelete: true, onChangeCase, onDeleteCase })
    const remove = await screen.findByRole('button', { name: '删除用例：验证保存' })
    fireEvent.click(remove)
    expect(onDeleteCase).toHaveBeenCalledWith(expect.objectContaining({ key: '清洗核验:0' }))
    unmount()
    setup()
    expect(await screen.findByRole('article', { name: '用例详情' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '删除用例：验证保存' })).not.toBeInTheDocument()
  })
})
