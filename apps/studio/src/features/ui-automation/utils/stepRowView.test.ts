import { describe, expect, it } from 'vitest'

import { buildUiStepRowView } from './stepRowView'

/*
 * 步骤行的展示推导：字段显隐、字段标题与折叠摘要。规则来自既有编辑器的行为，
 * 这里把几条容易改坏的分支钉住。
 */

describe('步骤行展示推导', () => {
  it('没有关键字时摘要写未设置关键字，并保留启用状态', () => {
    expect(buildUiStepRowView({ enabled: true }).summary).toBe('未设置关键字 · 无需定位 · 已启用')
    expect(buildUiStepRowView({ enabled: false }).summary).toBe('未设置关键字 · 无需定位 · 已禁用')
  })

  it('open 这类不需要定位器的关键字，摘要里写无需定位', () => {
    const row = buildUiStepRowView({ keyword: 'open', operationValue: 'http://localhost:5173/login', enabled: true })

    expect(row.requiresLocator).toBe(false)
    expect(row.showLocatorFields).toBe(false)
    expect(row.showOperationField).toBe(true)
    expect(row.operationFieldLabel).toBe('操作值（页面 URL）')
    expect(row.locatorValueFieldClass).toBe('ui-test-case-step-field-wide')
    expect(row.summary).toBe('open · 无需定位 · 已启用')
  })

  it('必须定位的关键字缺定位时给出待设定位，而不是空摘要', () => {
    const row = buildUiStepRowView({ keyword: 'click', enabled: true })

    expect(row.requiresLocator).toBe(true)
    expect(row.showLocatorTypeField).toBe(true)
    // click 在 stepConfig 里没有专属提示，回落到通用提示
    expect(row.locatorFieldHint).toBe('当前关键字通常需要定位器。')
    expect(row.summary).toBe('click · 待设定位 · 已启用')
  })

  it('关键字带比较器时摘要补上比较器，且操作值与比较器并排（各占半宽）', () => {
    const row = buildUiStepRowView({ keyword: 'assert_url', comparator: 'contains', operationValue: '/dashboard', enabled: true })

    expect(row.usesComparator).toBe(true)
    expect(row.summary).toBe('assert_url · 无需定位 · contains · 已启用')
    expect(row.operationValueFieldClass).toBe('ui-test-case-step-field-half')
  })

  it('按需填过的定位值会把定位字段重新露出来，但摘要只读定位方式', () => {
    const row = buildUiStepRowView({ keyword: 'open', locatorValue: '#app', enabled: true })

    expect(row.showLocatorFields).toBe(true)
    expect(row.showLocatorTypeField).toBe(false)
    // 摘要里第二段一直是定位方式（不是定位值），与重做前的折叠行一致
    expect(row.summary).toBe('open · 无需定位 · 已启用')

    const typed = buildUiStepRowView({ keyword: 'input', locatorType: 'placeholder', enabled: true })
    expect(typed.summary).toBe('input · placeholder · 已启用')
  })
})
