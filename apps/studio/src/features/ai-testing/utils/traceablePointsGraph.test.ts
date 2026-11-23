import { describe, expect, it } from 'vitest'
import { buildTraceablePointsModel } from './traceablePointsModel'
import { buildTraceablePointsGraph, type TraceableGraphInput, type TraceableSelection } from './traceablePointsGraph'

const content = JSON.stringify({
  artifactType: 'traceable_test_points',
  schemaVersion: '1.0',
  reviewStatus: 'self_review_only',
  testPoints: [
    { id: 'P1', module: '配置', dimension: '功能场景', name: '验证保存', basis: 'direct', materialBlockIds: ['B1'], testObjectIds: ['TO1'], impactAreaIds: [], riskIds: [], materialQuestionIds: [], scopeQuestionIds: [] },
    { id: 'P2', module: '配置', dimension: '功能场景', name: '验证取消', basis: 'derived', materialBlockIds: ['B1'], testObjectIds: [], impactAreaIds: [], riskIds: [], materialQuestionIds: [], scopeQuestionIds: [] },
    { id: 'P3', module: '导出', dimension: '异常场景', name: '验证失败', basis: 'direct', materialBlockIds: ['B1'], testObjectIds: ['TO1'], impactAreaIds: [], riskIds: [], materialQuestionIds: [], scopeQuestionIds: [] },
  ],
  coverageGaps: [
    { id: 'G1', description: '状态待确认', blockedCoverage: '保存后状态', materialBlockIds: [], testObjectIds: ['TO1'], impactAreaIds: [], riskIds: [], materialQuestionIds: [], scopeQuestionIds: [] },
  ],
  reviewIssues: [],
})

function model() {
  return buildTraceablePointsModel(content)!
}

function input(overrides: Partial<TraceableGraphInput> = {}): TraceableGraphInput {
  const data = model()
  return {
    modules: data.modules,
    rootTitle: '测试点',
    mode: 'points',
    expandedSceneIds: new Set(),
    selection: { kind: 'overview' },
    issueCount: data.issues.length,
    totalPoints: data.points.length,
    totalGaps: data.gaps.length,
    reviewStatus: data.reviewStatus,
    reviewLabel: data.reviewLabel,
    ...overrides,
  }
}

function pointNodeIds(selection: TraceableSelection = { kind: 'overview' }, expanded = new Set<string>()) {
  return buildTraceablePointsGraph(input({ selection, expandedSceneIds: expanded })).nodes
    .filter(node => node.data.kind === 'point' || node.data.kind === 'detail')
    .map(node => node.id)
}

describe('traceablePointsGraph', () => {
  it('默认只展示模块和场景，展开后追加测试点', () => {
    const collapsed = buildTraceablePointsGraph(input())
    expect(collapsed.nodes.filter(node => node.data.kind === 'point' || node.data.kind === 'detail')).toHaveLength(0)
    expect(collapsed.edges.every(edge => !edge.target.startsWith('point-'))).toBe(true)

    const sceneId = model().modules[0].scenes[0].id
    expect(pointNodeIds({ kind: 'overview' }, new Set([sceneId]))).toEqual(['point-P1', 'point-P2'])
  })

  it('选中测试点时用详情卡替换同一列的测试点节点', () => {
    const sceneId = model().modules[0].scenes[0].id
    const graph = buildTraceablePointsGraph(input({ selection: { kind: 'point', id: 'P1' }, expandedSceneIds: new Set([sceneId]) }))
    const detail = graph.nodes.find(node => node.data.kind === 'detail')!
    const sibling = graph.nodes.find(node => node.id === 'point-P2')!
    expect(detail.position.x).toBe(sibling.position.x)
    expect(Math.abs(detail.position.y - sibling.position.y)).toBeGreaterThan(50)
  })

  it('缺口模式展示缺口卡，并从关联场景连线', () => {
    const data = model()
    const graph = buildTraceablePointsGraph(input({ mode: 'gaps', activeGap: data.gaps[0], selection: { kind: 'gap', id: 'G1' } }))
    const gap = graph.nodes.find(node => node.data.kind === 'gap')!
    expect(gap.position.x).toBe(graph.pointColumnX)
    expect(graph.nodes.some(node => node.data.kind === 'point')).toBe(false)
    expect(graph.edges.filter(edge => edge.target === gap.id)).toHaveLength(2)
    expect(graph.edges.find(edge => edge.target === gap.id)?.style).toMatchObject({ strokeDasharray: '4 4' })
  })

  it('审查问题关联测试点时把问题卡放到下一列', () => {
    const data = model()
    const issue = { index: 0, kind: 'missing', targetType: 'testPoint', targetId: 'P1', issue: '缺少边界', suggestion: '补充', pointId: 'P1', sceneId: data.points[0].sceneId }
    const graph = buildTraceablePointsGraph(input({ mode: 'issues', activeIssue: issue, issueCount: 1 }))
    const point = graph.nodes.find(node => node.id === 'point-P1')!
    const issueNode = graph.nodes.find(node => node.data.kind === 'issue')!
    expect(point.position.x).toBe(graph.pointColumnX)
    expect(issueNode.position.x).toBeGreaterThan(point.position.x)
    expect(graph.nodes.filter(node => node.data.kind === 'point')).toHaveLength(1)
    expect(graph.edges.some(edge => edge.source === point.id && edge.target === issueNode.id)).toBe(true)
  })

  it('审查问题关联缺口时同时展示缺口卡和问题卡', () => {
    const data = model()
    const issue = { index: 0, kind: 'unsupported', targetType: 'coverageGap', targetId: 'G1', issue: '缺口没有依据', suggestion: '', gapId: 'G1' }
    const graph = buildTraceablePointsGraph(input({ mode: 'issues', activeIssue: issue, issueCount: 1, activeGap: data.gaps[0] }))
    const gap = graph.nodes.find(node => node.data.kind === 'gap')!
    const issueNode = graph.nodes.find(node => node.data.kind === 'issue')!
    expect(gap.position.x).toBe(graph.pointColumnX)
    expect(issueNode.position.x).toBeGreaterThan(gap.position.x)
    expect(graph.edges.some(edge => edge.source === gap.id && edge.target === issueNode.id)).toBe(true)
  })

  it('没有审查问题时展示审查结果卡，搜索时收起测试点分支', () => {
    const graph = buildTraceablePointsGraph(input({ mode: 'issues' }))
    expect(graph.nodes.some(node => node.data.kind === 'review')).toBe(true)
    expect(input().mode).toBe('points')
    const searched = buildTraceablePointsGraph(input({ query: '保存', expandedSceneIds: new Set([model().modules[0].scenes[0].id]) }))
    expect(searched.nodes.some(node => node.data.kind === 'point' || node.data.kind === 'detail')).toBe(false)
  })

  it('布局为节点保留不重叠的列与纵向间距', () => {
    const sceneId = model().modules[0].scenes[0].id
    const graph = buildTraceablePointsGraph(input({ expandedSceneIds: new Set([sceneId]) }))
    const points = graph.nodes.filter(node => node.data.kind === 'point')
    expect(points[0].position.x).toBe(points[1].position.x)
    expect(points[1].position.y - points[0].position.y).toBeGreaterThanOrEqual(46)
    expect(graph.stageWidth).toBeGreaterThan(graph.pointColumnX)
    expect(graph.stageHeight).toBeGreaterThan(0)
  })
})
