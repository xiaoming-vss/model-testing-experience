import { expect, it } from 'vitest'
import { getRunPipelineModel } from './runPipeline'

it('失败和异常使用不同的状态文案', () => {
  expect(getRunPipelineModel({ status: 'failed' }).statusLabel).toBe('失败')
  expect(getRunPipelineModel({ status: 'error' }).statusLabel).toBe('异常')
  expect(getRunPipelineModel({ status: 'error' }).statusTone).toBe('error')
})

it('排队、领取和审核等待各用自己的状态文案', () => {
  for (const [status, label] of [
    ['pending', '待执行'],
    ['queued', '排队中'],
    ['claimed', '已领取'],
    ['running', '执行中'],
    ['waiting_review', '待审核'],
    ['stopping', '停止中'],
  ] as const) {
    expect(getRunPipelineModel({ status })).toEqual({ statusLabel: label, statusTone: 'processing' })
  }
})

it('取消和结束状态', () => {
  expect(getRunPipelineModel({ status: 'canceled' })).toEqual({ statusLabel: '已取消', statusTone: 'muted' })
  expect(getRunPipelineModel({ status: 'success' })).toEqual({ statusLabel: '成功', statusTone: 'success' })
  expect(getRunPipelineModel({})).toEqual({ statusLabel: '成功', statusTone: 'success' })
})
