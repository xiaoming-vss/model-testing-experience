import { afterEach, describe, expect, it } from 'vitest'
import workbenchCss from './workbench.css?raw'
import aiTestingCss from '@/features/ai-testing/styles/index.css?raw'
import testingCss from '@/features/testing/styles/index.css?raw'

type NameStyle = {
  color: string
  cursor: string
  fontSize: string
  fontWeight: string
  lineHeight: string
  textUnderlineOffset: string
}

function computedNameStyle(css: string, markup: string): NameStyle {
  document.documentElement.dataset.theme = 'dark'
  document.head.innerHTML = `<style>${css}</style>`
  document.body.innerHTML = `<div class="app-shell app-shell-macos">${markup}</div>`

  const style = getComputedStyle(document.querySelector('#list-name') as HTMLElement)
  return {
    color: style.color,
    cursor: style.cursor,
    fontSize: style.fontSize,
    fontWeight: style.fontWeight,
    lineHeight: style.lineHeight,
    textUnderlineOffset: style.textUnderlineOffset,
  }
}

afterEach(() => {
  delete document.documentElement.dataset.theme
  document.head.innerHTML = ''
  document.body.innerHTML = ''
})

describe('列表名称样式统一', () => {
  const taskNameMarkup = `
    <main class="ai-testing-page">
      <div class="ai-task-list-table">
        <div class="ai-task-list-name"><span id="list-name" class="ant-typography">任务名称</span></div>
      </div>
    </main>
  `

  const suiteNameMarkup = (pageClass: string) => `
    <main class="functional-test-page ${pageClass}">
      <div class="functional-suite-list-table">
        <div class="functional-suite-list-name"><span id="list-name" class="ant-typography">测试集名称</span></div>
      </div>
    </main>
  `

  const requirementNameMarkup = `
    <main class="project-overview-page">
      <div class="project-requirement-list-table">
        <div class="project-requirement-list-name"><span id="list-name" class="ant-typography">需求名称</span></div>
      </div>
    </main>
  `

  it.each([
    ['API 测试集', testingCss, suiteNameMarkup('api-test-page')],
    ['UI 测试集', testingCss, suiteNameMarkup('ui-test-page')],
    ['功能测试集', testingCss, suiteNameMarkup('')],
    ['需求', workbenchCss, requirementNameMarkup],
  ])('%s名称与任务名称使用相同的深色主题样式', (_, css, markup) => {
    const taskNameStyle = computedNameStyle(aiTestingCss, taskNameMarkup)
    const targetNameStyle = computedNameStyle(css, markup)

    expect(targetNameStyle).toEqual(taskNameStyle)
  })
})
