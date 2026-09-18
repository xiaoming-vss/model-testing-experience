import { describe, expect, it } from 'vitest'
import {
  buildSprintCreatePayload,
  buildSprintUpdatePayload,
  buildUiTestCaseUpdatePayload,
} from './updatePayload'

describe('迭代载荷', () => {
  it('创建时同时提交带明确时区的开始和结束时间', () => {
    expect(buildSprintCreatePayload({
      name: '九月迭代',
      description: '接口调整',
      startTime: '2026-09-04T09:00:00+08:00',
      endTime: '2026-09-11T18:00:00+08:00',
    })).toEqual({
      name: '九月迭代',
      description: '接口调整',
      startTime: '2026-09-04T01:00:00.000Z',
      endTime: '2026-09-11T10:00:00.000Z',
    })
  })

  it('更新时永远不提交后端计算的状态', () => {
    const sprint = {
      name: '九月迭代',
      status: 'completed' as const,
      startTime: '2026-09-04T01:00:00.000Z',
      endTime: '2026-09-11T10:00:00.000Z',
    }
    const values = {
      name: '九月迭代（延长）',
      status: 'running',
      startTime: '2026-09-04T09:00:00+08:00',
      endTime: '2026-09-18T18:00:00+08:00',
    }

    expect(buildSprintUpdatePayload(sprint, values)).toEqual({
      name: '九月迭代（延长）',
      endTime: '2026-09-18T10:00:00.000Z',
    })
  })
})

describe('UI 用例更新载荷', () => {
  it('结构化响应与等价序列化步骤不会被判断为修改', () => {
    const stepsJson = [{ orderNo: 1, stepName: '打开登录页', keyword: 'open' }]

    expect(buildUiTestCaseUpdatePayload(
      { name: '登录成功', enabled: true, orderNo: 1, stepsJson },
      { name: '登录成功', enabled: true, orderNo: 1, stepsJson: JSON.stringify(stepsJson) },
    )).toEqual({})
  })
})
