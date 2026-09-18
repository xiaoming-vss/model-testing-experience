import { describe, expect, it } from 'vitest'
import { parseUiCaseCandidate } from './uiCaseCandidate'

describe('UI 候选结果解析', () => {
  it('按 UI 用例标准结构解析最外层用例数组', () => {
    const yaml = `
- name: 登录成功
  enabled: true
  orderNo: 1
  stepsJson:
    - orderNo: 1
      stepName: 打开登录页
      keyword: open
      operationValue: https://example.test/login
- name: 登录失败
  enabled: true
  orderNo: 2
  stepsJson: []
`

    const result = parseUiCaseCandidate(yaml)

    expect(result.error).toBeUndefined()
    expect(result.cases).toHaveLength(2)
    expect(result.cases[0]).toMatchObject({ name: '登录成功', enabled: true, orderNo: 1 })
    expect(result.cases[0].steps).toHaveLength(1)
  })

  it('按 UI 用例标准结构解析单条用例及序列化 stepsJson', () => {
    const yaml = `
name: 登录页可见
enabled: true
orderNo: 1
stepsJson: '[{"orderNo":1,"stepName":"打开登录页","keyword":"open"}]'
`

    const result = parseUiCaseCandidate(yaml)

    expect(result.cases).toHaveLength(1)
    expect(result.cases[0].name).toBe('登录页可见')
    expect(result.cases[0].steps[0]).toMatchObject({ keyword: 'open' })
  })

  it('解析用例、步骤及未知字段供结构化预览使用', () => {
    const yaml = `cases:
  - name: 登录成功
    enabled: true
    orderNo: 1
    customCaseField: keep-me
    stepsJson:
      - orderNo: 1
        stepName: 打开登录页
        keyword: open
        operationValue: https://example.test/login
        continueOnFailure: false
        enabled: true
        customStepField: keep-step
`

    const result = parseUiCaseCandidate(yaml)

    expect(result.error).toBeUndefined()
    expect(result.cases[0]).toMatchObject({ name: '登录成功', enabled: true, orderNo: 1 })
    expect(result.cases[0].extraFields).toEqual({ customCaseField: 'keep-me' })
    expect(result.cases[0].steps[0].extraFields).toEqual({ customStepField: 'keep-step' })
  })

  it('无效 YAML 返回错误并保留原文作为回退内容', () => {
    const yaml = 'cases:\n  - name: [broken'
    const result = parseUiCaseCandidate(yaml)

    expect(result.error).toBeTruthy()
    expect(result.rawYaml).toBe(yaml)
    expect(result.cases).toEqual([])
  })
})
