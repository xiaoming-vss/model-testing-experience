import type { RequirementDesignKind } from '../api/requirementDesign.api'

export const requirementDesignKinds: { key: RequirementDesignKind; label: string }[] = [
  { key: 'requirement_analysis', label: '需求分析' }, { key: 'function', label: '功能测试' },
  { key: 'api', label: 'API 测试' }, { key: 'ui', label: 'UI 测试' },
]
export const requirementDesignStages = {
  requirement_analysis: [{ key: 'extracting_text', label: '材料提取与整理' }, { key: 'feature_understanding', label: '需求理解与确认' }],
  function: [{ key: 'requirement_analysis', label: '测试需求分析' }, { key: 'case_names', label: '测试点' }, { key: 'detailed_cases', label: '完整用例' }],
  api: [{ key: 'generate', label: 'API 用例生成' }],
  ui: [{ key: 'ui_surface', label: '元素控件清单' }, { key: 'ui_design', label: 'UI 用例设计' }, { key: 'ui_yaml', label: '用例 YAML' }],
}
export const requirementDesignArtifacts = {
  requirement_analysis: [{ key: 'firstStepOutput', label: '材料提取结果' }, { key: 'resultYaml', label: '需求理解记录' }],
  function: [{ key: 'requirementAnalysis', label: '测试需求分析' }, { key: 'caseNames', label: '测试点' }, { key: 'resultYaml', label: '完整用例' }, { key: 'caseRelations', label: '用例图谱' }],
  api: [{ key: 'resultYaml', label: 'API 用例' }],
  ui: [{ key: 'uiSurface', label: '元素控件清单' }, { key: 'uiDesign', label: 'UI 用例设计' }, { key: 'resultYaml', label: 'UI 用例' }],
}

/** 旧 UI 运行没有 uiWorkflowVersion，只有单阶段 generate，保持旧的单阶段名称。 */
export function designStageLabel(kind: RequirementDesignKind, run: { checkpointEnabled?: boolean; currentStage?: string }): string {
  const stage = run.currentStage ?? ''
  if (kind === 'ui' && !run.checkpointEnabled) return 'UI 用例生成'
  const stages = requirementDesignStages[kind]
  return stages.find(item => item.key === stage)?.label
    ?? (stage === 'completed' ? stages[stages.length - 1].label : stage === 'relation_analysis' ? '图谱分析' : stage)
}
