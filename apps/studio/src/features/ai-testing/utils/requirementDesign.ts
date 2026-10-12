import type { RequirementDesignKind } from '../api/requirementDesign.api'

export const requirementDesignKinds: { key: RequirementDesignKind; label: string }[] = [
  { key: 'requirement_analysis', label: '需求分析' }, { key: 'function', label: '功能测试' },
  { key: 'api', label: 'API 测试' }, { key: 'ui', label: 'UI 测试' },
]
export const requirementDesignStages = {
  requirement_analysis: [{ key: 'extracting_text', label: '材料提取与整理' }, { key: 'feature_understanding', label: '需求理解与确认' }],
  function: [{ key: 'requirement_analysis', label: '测试需求分析' }, { key: 'case_names', label: '测试点' }, { key: 'detailed_cases', label: '完整用例' }],
  api: [{ key: 'generate', label: 'API 用例生成' }], ui: [{ key: 'generate', label: 'UI 用例生成' }],
}
export const requirementDesignArtifacts = {
  requirement_analysis: [{ key: 'firstStepOutput', label: '材料提取结果' }, { key: 'resultYaml', label: '需求理解记录' }],
  function: [{ key: 'requirementAnalysis', label: '测试需求分析' }, { key: 'caseNames', label: '测试点' }, { key: 'resultYaml', label: '完整用例' }, { key: 'caseRelations', label: '用例图谱' }],
  api: [{ key: 'resultYaml', label: 'API 用例' }], ui: [{ key: 'resultYaml', label: 'UI 用例' }],
}
