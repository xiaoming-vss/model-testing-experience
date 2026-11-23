import { describe, expect, it } from 'vitest'
import { buildTraceablePointsModel } from './traceablePointsModel'

const content = JSON.stringify({
  artifactType: 'traceable_test_points',
  schemaVersion: '1.0',
  reviewStatus: 'independent_review_failed',
  testPoints: [
    {
      id: 'P1', module: '配置', dimension: '功能场景', name: '【配置】验证保存', basis: 'direct',
      materialBlockIds: ['B1'], testObjectIds: ['TO1'], impactAreaIds: ['IA1'], riskIds: ['R1'],
      materialQuestionIds: [], scopeQuestionIds: ['Q1'],
    },
    {
      id: 'P2', module: '配置', dimension: '异常场景', name: '【配置】验证失败', basis: 'derived',
      materialBlockIds: ['B1'], testObjectIds: ['TO2'], impactAreaIds: [], riskIds: [], materialQuestionIds: ['MQ1'], scopeQuestionIds: [],
    },
    {
      id: 'P3', module: '导出', dimension: '功能场景', name: '【导出】验证下载', basis: 'derived',
      materialBlockIds: ['B2'], testObjectIds: ['TO1'], impactAreaIds: [], riskIds: [], materialQuestionIds: [], scopeQuestionIds: [],
    },
  ],
  coverageGaps: [
    {
      id: 'G1', description: '状态待确认', blockedCoverage: '保存后状态', materialBlockIds: [],
      testObjectIds: ['TO1'], impactAreaIds: [], riskIds: [], materialQuestionIds: [], scopeQuestionIds: [],
    },
    {
      id: 'G2', description: '缺少下载失败依据', blockedCoverage: '下载失败', materialBlockIds: ['B2'],
      testObjectIds: [], impactAreaIds: [], riskIds: [], materialQuestionIds: [], scopeQuestionIds: [],
    },
  ],
  reviewIssues: [
    {
      kind: 'missing', targetType: 'testPoint', targetId: 'P2', issue: '缺少边界说明', suggestion: '补充失败边界',
      materialBlockIds: [], testObjectIds: [], impactAreaIds: [], riskIds: [], materialQuestionIds: [], scopeQuestionIds: [],
    },
    {
      kind: 'unsupported', targetType: 'coverageGap', targetId: 'G1', issue: '缺口没有依据', suggestion: '',
      materialBlockIds: [], testObjectIds: [], impactAreaIds: [], riskIds: [], materialQuestionIds: [], scopeQuestionIds: [],
    },
    {
      kind: 'missing', targetType: 'missing', targetId: null, issue: '遗漏兼容性', suggestion: '补充',
      materialBlockIds: [], testObjectIds: [], impactAreaIds: [], riskIds: [], materialQuestionIds: [], scopeQuestionIds: [],
    },
  ],
})

const materialContent = JSON.stringify({
  sources: [{ id: 'S1', name: '需求文档' }],
  materialBlocks: [
    { id: 'B1', sourceId: 'S1', kind: 'paragraph', locator: '第一段', content: { text: '保存规则' } },
    { id: 'B2', sourceId: 'S1', kind: 'paragraph', locator: '第二段', content: { text: '下载规则' } },
  ],
})

describe('traceablePointsModel', () => {
  it('按模块和场景建立索引，并保留测试点引用', () => {
    const model = buildTraceablePointsModel(content, materialContent)
    expect(model).not.toBeNull()
    expect(model!.modules.map(module => module.title)).toEqual(['配置', '导出'])
    expect(model!.modules[0].scenes.map(scene => scene.title)).toEqual(['功能场景', '异常场景'])
    expect(model!.points.map(point => point.name)).toEqual(['【配置】验证保存', '【配置】验证失败', '【导出】验证下载'])
    expect(model!.pointById.get('P1')?.derived).toBe(false)
    expect(model!.pointById.get('P2')?.derived).toBe(true)
    expect(model!.pointById.get('P1')?.refs.scopeQuestionIds).toEqual(['Q1'])
    expect(model!.reviewLabel).toBe('独立审查未通过')
    expect(model!.blockById.get('B1')?.locator).toBe('第一段')
  })

  it('从对象或材料引用推导缺口关联测试点', () => {
    const model = buildTraceablePointsModel(content, materialContent)!
    const g1 = model.gaps.find(gap => gap.id === 'G1')!
    const g2 = model.gaps.find(gap => gap.id === 'G2')!
    expect(g1.relatedPointIds).toEqual(['P1', 'P3'])
    expect(g1.relatedSceneIds).toHaveLength(2)
    expect(g2.relatedPointIds).toEqual(['P3'])
  })

  it('解析审查目标为测试点、缺口或遗漏项', () => {
    const model = buildTraceablePointsModel(content, materialContent)!
    expect(model.issues[0]).toMatchObject({ pointId: 'P2', sceneId: model.pointById.get('P2')?.sceneId })
    expect(model.issues[1]).toMatchObject({ gapId: 'G1' })
    expect(model.issues[2]).toMatchObject({ targetType: 'missing', targetId: '' })
  })

  it('无效产物返回 null', () => {
    expect(buildTraceablePointsModel('{}')).toBeNull()
    expect(buildTraceablePointsModel('not json')).toBeNull()
  })
})
