import { toRecord } from '@/shared/utils/value'
import { toDisplayText } from '@/features/ai-testing/utils/functionalOutput'

export type CaseNameTreeNode = {
  id: string
  title: string
  kind: 'root' | 'model' | 'testModel' | 'point'
  children: CaseNameTreeNode[]
}

export function buildCaseNameTree(content: string, rootTitle: string): CaseNameTreeNode | null {
  if (!content.trim()) return null

  try {
    const parsed = JSON.parse(content)
    const record = toRecord(parsed)
    if (record?.artifactType === 'traceable_test_points' && Array.isArray(record.testPoints)) {
      const groups = new Map<string, Map<string, CaseNameTreeNode[]>>()
      record.testPoints.forEach((value, index) => {
        const point = toRecord(value)
        if (!point) return
        const module = toDisplayText(point.module) || '未分组模块'
        const scene = toDisplayText(point.dimension) || '未分组场景'
        const title = toDisplayText(point.name)
        if (!title) return
        const scenes = groups.get(module) ?? new Map<string, CaseNameTreeNode[]>()
        const points = scenes.get(scene) ?? []
        points.push({ id: toDisplayText(point.id) || `point-${index}`, title, kind: 'point', children: [] })
        scenes.set(scene, points)
        groups.set(module, scenes)
      })
      return { id: 'root', title: rootTitle || '功能测试用例生成', kind: 'root', children: [...groups.entries()].map(([module, scenes], moduleIndex) => ({
        id: `module-${moduleIndex}`, title: module, kind: 'model', children: [...scenes.entries()].map(([scene, points], sceneIndex) => ({
          id: `module-${moduleIndex}-scene-${sceneIndex}`, title: scene, kind: 'testModel', children: points,
        })),
      })) }
    }
    return null
  } catch {
    return null
  }
}

export function countCaseNameTree(tree: CaseNameTreeNode | null) {
  const models = tree?.children.length ?? 0
  const testModels = tree?.children.reduce((sum, model) => sum + model.children.length, 0) ?? 0
  const testPoints = tree?.children.reduce((sum, model) => sum + model.children.reduce((itemSum, testModel) => itemSum + testModel.children.length, 0), 0) ?? 0
  return { models, testModels, testPoints }
}