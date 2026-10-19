import { buildCaseNameTree, type CaseNameTreeNode } from './caseNameTree'
import { parseGeneratedCases, toDisplayText } from './functionalOutput'

/** Keep candidate identity separate from titles, which can repeat across scenes. */
export function buildGeneratedCaseTree(content: string, pointsContent: string, rootTitle: string, query = '') {
  const points = buildCaseNameTree(pointsContent, rootTitle)
  const entries = parseGeneratedCases(content).flatMap((group) => group.cases.map((testCase, index) => {
    const scenes = points?.children.filter((module) => module.title === group.moduleName)
      .flatMap((module) => module.children.filter((scene) => scene.children.some((point) => point.title === testCase.displayName))) ?? []
    const scene = toDisplayText(testCase.raw.test_model) || toDisplayText(testCase.raw.testModel)
      || (scenes.length === 1 ? scenes[0].title : '未分组场景')
    return { key: `${group.moduleName}:${index}`, testCase, scene }
  }))
  const search = query.trim().toLowerCase()
  const visible = entries.filter(({ testCase, scene }) => `${testCase.moduleName} ${scene} ${testCase.displayName}`.toLowerCase().includes(search))
  const tree: CaseNameTreeNode = { id: 'root', title: rootTitle, kind: 'root', children: [] }
  for (const entry of visible) {
    let module = tree.children.find((node) => node.title === entry.testCase.moduleName)
    if (!module) {
      module = { id: `module-${tree.children.length}`, title: entry.testCase.moduleName, kind: 'model', children: [] }
      tree.children.push(module)
    }
    let scene = module.children.find((node) => node.title === entry.scene)
    if (!scene) {
      scene = { id: `${module.id}-scene-${module.children.length}`, title: entry.scene, kind: 'testModel', children: [] }
      module.children.push(scene)
    }
    scene.children.push({ id: entry.key, title: entry.testCase.displayName, kind: 'point', children: [] })
  }
  return { tree, entries, visible }
}
