import { describe, expect, it } from 'vitest'
import { getUiTestCaseStepCount, parseStepsJson, serializeSteps } from './uiTestCaseEditor'

describe('UI 用例步骤解析', () => {
  it('回显接口返回的结构化 stepsJson 步骤集合', () => {
    const stepsJson = [
      {
        orderNo: 1,
        stepName: '打开登录页',
        keyword: 'open',
        locatorType: 'css',
        locatorValue: '#login',
        operationValue: 'https://example.test/login',
        enabled: true,
        continueOnFailure: false,
      },
    ]

    expect(parseStepsJson(stepsJson)).toEqual([
      expect.objectContaining({
        orderNo: 1,
        stepName: '打开登录页',
        keyword: 'open',
        locatorType: 'css',
        locatorValue: '#login',
        operationValue: 'https://example.test/login',
      }),
    ])
    expect(getUiTestCaseStepCount({ name: '登录成功', stepsJson })).toBe(1)
  })

  it('继续兼容历史 JSON 字符串格式', () => {
    const stepsJson = JSON.stringify([
      { orderNo: 2, stepName: '提交登录', keyword: 'click' },
      { orderNo: 1, stepName: '输入用户名', keyword: 'fill' },
    ])

    expect(parseStepsJson(stepsJson).map((step) => step.stepName)).toEqual(['输入用户名', '提交登录'])
  })

  it('将旧断言值和超时字段迁移为 operationValue', () => {
    expect(
      parseStepsJson([
        { keyword: 'assert_text', expectValue: '登录成功' },
        { keyword: 'assert_visible', timeoutMs: 3000 },
        { keyword: 'assert_hidden', timeoutMs: 2000 },
      ]).map((step) => step.operationValue),
    ).toEqual(['登录成功', '3000', '2000'])
  })

  it('接受导入 YAML 中写成数字的毫秒数', () => {
    // 后端允许 assert_visible / sleep 的 operationValue 直接写毫秒数；
    // 曾经这里对数字调用 trim() 抛错，导致整条用例被解析成 0 个步骤。
    const stepsJson = [
      { orderNo: 1, stepName: '等待登录', keyword: 'assert_visible', locatorType: 'xpath', locatorValue: '//div', operationValue: 15000 },
      { orderNo: 2, stepName: '点击登录', keyword: 'click', locatorType: 'xpath', locatorValue: '//button' },
    ] as unknown as Parameters<typeof parseStepsJson>[0]

    expect(parseStepsJson(stepsJson).map((step) => step.operationValue)).toEqual(['15000', ''])
    expect(getUiTestCaseStepCount({ name: '数字超时步骤', stepsJson })).toBe(2)
  })

  it('只序列化关键字规范允许的步骤字段', () => {    const steps = JSON.parse(
      serializeSteps([
        {
          stepName: '断言提示文案',
          keyword: 'assert_text',
          locatorType: 'text',
          locatorValue: '请输入用户名',
          operationValue: '请输入用户名',
          expectValue: '旧期望值',
          comparator: 'contains',
          timeoutMs: 5000,
          description: '旧说明',
          enabled: true,
          continueOnFailure: false,
        },
        {
          stepName: '截图',
          keyword: 'screenshot',
          locatorType: 'css',
          locatorValue: '#legacy',
          operationValue: 'legacy.png',
          enabled: true,
          continueOnFailure: false,
        },
      ]),
    )

    expect(steps).toEqual([
      {
        orderNo: 1,
        stepName: '断言提示文案',
        keyword: 'assert_text',
        locatorType: 'text',
        locatorValue: '请输入用户名',
        operationValue: '请输入用户名',
        comparator: 'contains',
        continueOnFailure: false,
        enabled: true,
      },
      {
        orderNo: 2,
        stepName: '截图',
        keyword: 'screenshot',
        continueOnFailure: false,
        enabled: true,
      },
    ])
  })

  it('后置提取在解析与序列化之间不丢失', () => {
    const saveTo = [
      {
        name: 'taskId',
        source: 'text' as const,
        locatorType: 'xpath',
        locatorValue: '//td[1]',
        defaultValue: '',
      },
      { name: 'currentUrl', source: 'url' as const },
    ]

    const parsed = parseStepsJson([
      { orderNo: 1, stepName: '读取编号', keyword: 'click', saveTo },
    ])
    expect(parsed[0].saveTo).toEqual(saveTo)

    const serialized = JSON.parse(
      serializeSteps([{ stepName: '读取编号', keyword: 'click', saveTo }]),
    )
    expect(serialized[0].saveTo).toEqual(saveTo)
  })

  it('空名称的提取规则不会写进 stepsJson', () => {
    const serialized = JSON.parse(
      serializeSteps([
        {
          stepName: '读取编号',
          keyword: 'click',
          saveTo: [{ name: '  ', source: 'text' }],
        },
      ]),
    )

    expect(serialized[0].saveTo).toBeUndefined()
  })
})
