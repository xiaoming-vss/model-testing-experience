import { type CaseNameTreeNode } from './caseNameTree'
import { parseGeneratedCases, toDisplayText } from './functionalOutput'

/** Keep candidate identity separate from titles, which can repeat across case types. */
export function buildGeneratedCaseTree(content: string, rootTitle: string, query = '') {
  const entries = parseGeneratedCases(content).flatMap((group) => group.cases.map((testCase) => ({
    key: `${group.moduleName}:${testCase.sourceIndex}`,
    testCase,
    caseType: toDisplayText(testCase.raw.case_type) || toDisplayText(testCase.raw.caseType)
      || toDisplayText(testCase.raw.type) || '未分类用例',
  })))
  const search = query.trim().toLowerCase()
  const visible = entries.filter(({ testCase, caseType }) => `${testCase.moduleName} ${caseType} ${testCase.displayName}`.toLowerCase().includes(search))
  const tree: CaseNameTreeNode = { id: 'root', title: rootTitle, kind: 'root', children: [] }
  for (const entry of visible) {
    let module = tree.children.find((node) => node.title === entry.testCase.moduleName)
    if (!module) {
      module = { id: `module-${tree.children.length}`, title: entry.testCase.moduleName, kind: 'model', children: [] }
      tree.children.push(module)
    }
    let caseType = module.children.find((node) => node.title === entry.caseType)
    if (!caseType) {
      caseType = { id: `${module.id}-case-type-${module.children.length}`, title: entry.caseType, kind: 'testModel', children: [] }
      module.children.push(caseType)
    }
    caseType.children.push({ id: entry.key, title: entry.testCase.displayName, kind: 'point', children: [] })
  }
  return { tree, entries, visible }
}
