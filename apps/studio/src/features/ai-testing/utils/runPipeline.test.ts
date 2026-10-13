import { expect, it } from 'vitest'
import { getRunPipelineModel } from './runPipeline'

it('需求分析只展示生成和审核时，已通过的审核不能显示待审核', () => {
  const model = getRunPipelineModel(
    { status: 'success', reviewStatus: 'approved' },
    { stages: ['generate', 'review'] },
  )
  expect(model.stages.map(stage => stage.state)).toEqual(['done', 'done'])
  expect(model.statusLabel).toBe('审核通过')
})

it('完整流程审核通过后显示待导入', () => {
  expect(getRunPipelineModel({ status: 'success', reviewStatus: 'approved' }).statusLabel).toBe('待导入')
})

it('未审核和拒绝仍显示各自状态', () => {
  for (const [reviewStatus, label] of [['pending', '待审核'], ['rejected', '已拒绝']]) {
    expect(getRunPipelineModel({ status: 'success', reviewStatus }, { stages: ['generate', 'review'] }).statusLabel).toBe(label)
  }
})


it('两种待审核状态统一为琥珀色，执行中仍为蓝色', () => {
  const stages = ['generate', 'review'] as const
  for (const status of ['waiting_review', 'success']) {
    const model = getRunPipelineModel({ status, reviewStatus: 'pending' }, { stages: [...stages] })
    expect(model.statusLabel).toBe('待审核')
    expect(model.statusTone).toBe('warning')
  }
  expect(getRunPipelineModel({ status: 'running' }).statusTone).toBe('processing')
  expect(getRunPipelineModel({ status: 'error' }).statusTone).toBe('error')
  expect(getRunPipelineModel({ status: 'success', reviewStatus: 'approved' }, { stages: [...stages] }).statusTone).toBe('success')
})
