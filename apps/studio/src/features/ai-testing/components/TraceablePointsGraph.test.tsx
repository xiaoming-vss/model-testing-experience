import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { buildTraceablePointsModel } from '../utils/traceablePointsModel'
import { TraceablePointsGraph } from './TraceablePointsGraph'

const content = JSON.stringify({
  artifactType: 'traceable_test_points',
  schemaVersion: '1.0',
  reviewStatus: 'self_review_only',
  testPoints: [{
    id: 'P1', module: '配置', dimension: '功能场景', name: '【配置】验证保存', basis: 'derived',
    materialBlockIds: ['B1'], testObjectIds: ['TO1'], impactAreaIds: [], riskIds: [], materialQuestionIds: [], scopeQuestionIds: [],
  }],
  coverageGaps: [],
  reviewIssues: [],
})

const materialContent = JSON.stringify({
  sources: [{ id: 'S1', name: '需求文档' }],
  materialBlocks: [{ id: 'B1', sourceId: 'S1', kind: 'paragraph', locator: '第一段', content: { text: '保存规则' } }],
})

beforeAll(() => {
  vi.stubGlobal('DOMMatrixReadOnly', class { m22 = 1 })
  vi.stubGlobal('ResizeObserver', class {
    callback: ResizeObserverCallback
    constructor(callback: ResizeObserverCallback) { this.callback = callback }
    observe(target: Element) { queueMicrotask(() => this.callback([{ target, contentRect: { width: 180, height: 100 } } as ResizeObserverEntry], this as unknown as ResizeObserver)) }
    unobserve() {}
    disconnect() {}
  })
})
beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(180)
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(100)
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ x: 0, y: 0, width: 180, height: 100, top: 0, right: 180, bottom: 100, left: 0, toJSON: () => ({}) } as DOMRect)
})
afterAll(() => vi.unstubAllGlobals())
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('TraceablePointsGraph', () => {
  it('渲染测试点详情卡并可编辑名称，卡片不展示编号', async () => {
    const model = buildTraceablePointsModel(content, materialContent)!
    const rename = vi.fn()
    const openEvidence = vi.fn()
    const sceneId = model.modules[0].scenes[0].id
    render(<TraceablePointsGraph
      model={model}
      mode="points"
      selection={{ kind: 'point', id: 'P1' }}
      expandedSceneIds={new Set([sceneId])}
      rootTitle="测试点"
      canRenamePoints
      onSelect={() => undefined}
      onSceneSelect={() => undefined}
      onFindPoint={() => undefined}
      onRenamePoint={rename}
      onOpenEvidence={openEvidence}
    />)

    expect(await screen.findByRole('article', { name: '测试点详情' })).toBeInTheDocument()
    expect(screen.getByText('【配置】验证保存')).toBeInTheDocument()
    expect(screen.queryByText('P1')).not.toBeInTheDocument()
    expect(screen.getByText('推断')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '编辑测试点名称' }))
    const input = screen.getByRole('textbox', { name: '测试点名称' })
    fireEvent.change(input, { target: { value: '【配置】验证更新' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(rename).toHaveBeenCalledWith('P1', '【配置】验证更新')

    fireEvent.click(screen.getByRole('button', { name: /查看 1 块/ }))
    expect(openEvidence).toHaveBeenCalledWith(expect.objectContaining({ title: '【配置】验证保存', blockIds: ['B1'] }))
  })
})
