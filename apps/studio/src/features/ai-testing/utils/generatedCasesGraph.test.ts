import { describe, expect, it } from 'vitest'
import { buildGeneratedCasesModel } from './generatedCasesModel'
import { buildGeneratedCasesGraph, generatedCaseNodeId, type GeneratedCasesSelection } from './generatedCasesGraph'

const content = JSON.stringify({
  cases: [
    { case_id: 'case-a', case_module: '清洗核验', case_type: '功能测试', case_title: '验证保存' },
    { case_id: 'case-b', case_module: '清洗核验', case_type: '功能测试', case_title: '验证取消' },
    { case_id: 'case-c', case_module: '清洗核验', case_type: '异常测试', case_title: '验证失败' },
  ],
})

function model() {
  return buildGeneratedCasesModel(content)!
}

function graph(selection: GeneratedCasesSelection = { kind: 'overview' }, expanded = new Set<string>()) {
  return buildGeneratedCasesGraph({ model: model(), rootTitle: '完整用例', selection, expandedSceneIds: expanded })
}

describe('generatedCasesGraph', () => {
  it('默认只展示根、模块和用例类型，不展开用例', () => {
    const result = graph()
    expect(result.nodes.filter(node => node.data.kind === 'case' || node.data.kind === 'detail')).toHaveLength(0)
    expect(result.nodes.filter(node => node.data.kind === 'scene')).toHaveLength(2)
    expect(result.stageHeight).toBeGreaterThan(0)
  })

  it('展开用例类型后追加用例，选中用例时用详情卡替换同列节点', () => {
    const firstScene = model().modules[0].scenes[0].id
    const expanded = new Set([firstScene])
    const filled = graph({ kind: 'overview' }, expanded)
    expect(filled.nodes.filter(node => node.data.kind === 'case')).toHaveLength(2)

    const selected = graph({ kind: 'case', key: '清洗核验:0' }, expanded)
    const detail = selected.nodes.find(node => node.data.kind === 'detail')!
    const sibling = selected.nodes.find(node => node.id === generatedCaseNodeId(model().entries[1]))!
    expect(detail.position.x).toBe(sibling.position.x)
    expect(detail.height).toBe(560)
    expect(detail.position.y).not.toBe(sibling.position.y)
  })

  it('连线锚定真实卡片宽度，不写死节点 width', () => {
    const firstScene = model().modules[0].scenes[0].id
    const result = graph({ kind: 'overview' }, new Set([firstScene]))
    result.nodes.forEach(node => {
      expect(node.width).toBeUndefined()
      expect(node.height).toBeGreaterThan(0)
    })
  })

  it('模块或用例类型被选中时保留选中态', () => {
    const moduleId = model().modules[0].id
    const sceneId = model().modules[0].scenes[0].id
    expect(graph({ kind: 'module', id: moduleId }).nodes.find(node => node.id === moduleId)?.data).toMatchObject({ selected: true })
    expect(graph({ kind: 'scene', id: sceneId }).nodes.find(node => node.id === sceneId)?.data).toMatchObject({ selected: true, expanded: false })
  })
})
