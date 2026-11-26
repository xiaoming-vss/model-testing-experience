import { expect, it } from 'vitest'
import { getRunPipelineModel } from './runPipeline'

it('失败和异常使用不同的状态文案', () => {
  expect(getRunPipelineModel({ status: 'failed' }).statusLabel).toBe('失败')
  expect(getRunPipelineModel({ status: 'error' }).statusLabel).toBe('异常')
  expect(getRunPipelineModel({ status: 'error' }).statusTone).toBe('error')
})

it('排队、领取和审核等待都属于执行中', () => {
  for (const status of ['queued', 'pending', 'claimed', 'running', 'waiting_review']) {
    expect(getRunPipelineModel({ status })).toEqual({ statusLabel: '执行中', statusTone: 'processing' })
  }
})

it('取消和结束状态', () => {
  expect(getRunPipelineModel({ status: 'canceled' })).toEqual({ statusLabel: '已取消', statusTone: 'muted' })
  expect(getRunPipelineModel({ status: 'success' })).toEqual({ statusLabel: '成功', statusTone: 'success' })
  expect(getRunPipelineModel({})).toEqual({ statusLabel: '成功', statusTone: 'success' })
})
