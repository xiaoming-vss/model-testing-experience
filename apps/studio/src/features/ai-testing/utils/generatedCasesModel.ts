import { parseGeneratedCases, toDisplayText, type GeneratedTestCase } from './functionalOutput'

export type GeneratedCaseEntry = {
  /** 稳定值，沿用旧的「模块名:源序号」约定，避免外部选中状态失效。 */
  key: string
  testCase: GeneratedTestCase
  moduleName: string
  caseType: string
}

export type GeneratedCaseScene = {
  id: string
  title: string
  cases: GeneratedCaseEntry[]
}

export type GeneratedCaseModule = {
  id: string
  title: string
  scenes: GeneratedCaseScene[]
  entries: GeneratedCaseEntry[]
}

export type GeneratedCasesModel = {
  entries: GeneratedCaseEntry[]
  modules: GeneratedCaseModule[]
  entryByKey: Map<string, GeneratedCaseEntry>
  moduleByEntryKey: Map<string, GeneratedCaseModule>
  sceneByEntryKey: Map<string, GeneratedCaseScene>
}

function caseTypeOf(testCase: GeneratedTestCase) {
  return toDisplayText(testCase.raw.case_type) || toDisplayText(testCase.raw.caseType)
    || toDisplayText(testCase.raw.type) || '未分类用例'
}

export function buildGeneratedCasesModel(content: string): GeneratedCasesModel | null {
  const groups = parseGeneratedCases(content)
  if (!groups.length) return null

  const entries: GeneratedCaseEntry[] = []
  const modules: GeneratedCaseModule[] = groups.map((group, moduleIndex) => ({
    id: `module-${moduleIndex}`,
    title: group.moduleName,
    scenes: [],
    entries: [],
  }))
  const entryByKey = new Map<string, GeneratedCaseEntry>()
  const moduleByEntryKey = new Map<string, GeneratedCaseModule>()
  const sceneByEntryKey = new Map<string, GeneratedCaseScene>()

  groups.forEach((group, moduleIndex) => {
    const module = modules[moduleIndex]
    group.cases.forEach((testCase) => {
      const caseType = caseTypeOf(testCase)
      const entry: GeneratedCaseEntry = {
        key: `${group.moduleName}:${testCase.sourceIndex}`,
        testCase,
        moduleName: group.moduleName,
        caseType,
      }
      let scene = module.scenes.find(item => item.title === caseType)
      if (!scene) {
        scene = { id: `${module.id}-scene-${module.scenes.length}`, title: caseType, cases: [] }
        module.scenes.push(scene)
      }
      module.entries.push(entry)
      scene.cases.push(entry)
      entries.push(entry)
      entryByKey.set(entry.key, entry)
      moduleByEntryKey.set(entry.key, module)
      sceneByEntryKey.set(entry.key, scene)
    })
  })

  return { entries, modules, entryByKey, moduleByEntryKey, sceneByEntryKey }
}
