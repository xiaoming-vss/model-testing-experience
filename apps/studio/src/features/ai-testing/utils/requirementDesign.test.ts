import { describe, expect, it } from 'vitest'
import { designStageLabel } from './requirementDesign'

describe('需求设计阶段标签', () => {
  it('三阶段 UI 运行按当前阶段显示中文标签', () => {
    expect(designStageLabel('ui', { checkpointEnabled: true, currentStage: 'ui_surface' })).toBe('元素控件清单')
    expect(designStageLabel('ui', { checkpointEnabled: true, currentStage: 'ui_design' })).toBe('UI 用例设计')
    expect(designStageLabel('ui', { checkpointEnabled: true, currentStage: 'completed' })).toBe('用例 YAML')
  })

  it('旧 UI 运行保持单阶段名称，不显示原始阶段值', () => {
    expect(designStageLabel('ui', { checkpointEnabled: false, currentStage: 'generate' })).toBe('UI 用例生成')
    expect(designStageLabel('ui', { checkpointEnabled: false, currentStage: 'completed' })).toBe('UI 用例生成')
  })

  it('其他类型保持既有回退', () => {
    expect(designStageLabel('function', { currentStage: 'relation_analysis' })).toBe('图谱分析')
    expect(designStageLabel('api', { currentStage: 'generate' })).toBe('API 用例生成')
  })
})
