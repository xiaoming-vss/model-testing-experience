import listNameCss from '@/shared/styles/list-name.css?raw'
import { afterEach, describe, expect, it } from 'vitest'
import workbenchCss from './workbench.css?raw'
import aiTestingSharedCss from '@/features/ai-testing/styles/index.css?raw'
import aiTestingListCss from '@/features/ai-testing/styles/task-list-v2.css?raw'
import testingCss from '@/features/testing/styles/index.css?raw'
import requirementListCss from '@/features/projects/styles/requirements-list.css?raw'

const aiTestingCss = `${aiTestingSharedCss}\n${aiTestingListCss}`

// Shared typography must win over legacy feature styles in every list.
type NameStyle = {
  cursor: string
  fontSize: string
  fontWeight: string
  textUnderlineOffset: string
}

function computedNameStyle(css: string, markup: string): NameStyle {
  document.head.innerHTML = `<style>${css}\n${listNameCss}</style>`
  document.body.innerHTML = `<div class="app-shell app-shell-macos"><div class="ant-table-wrapper"><div class="ant-table"><div class="ant-table-tbody">${markup}</div></div></div></div>`

  const style = getComputedStyle(document.querySelector('#list-name') as HTMLElement)
  return {
    cursor: style.cursor,
    fontSize: style.fontSize,
    fontWeight: style.fontWeight,
    textUnderlineOffset: style.textUnderlineOffset,
  }
}

afterEach(() => {
  document.head.innerHTML = ''
  document.body.innerHTML = ''
})

describe('列表名称样式统一', () => {
  const taskNameMarkup = `
    <main class="ai-testing-page">
      <div class="ai-task-list-table">
        <div class="tp-list-name ai-task-list-name"><span id="list-name" class="ant-typography">任务名称</span></div>
      </div>
    </main>
  `

  const suiteNameMarkup = (pageClass: string) => `
    <main class="functional-test-page ${pageClass}">
      <div class="functional-suite-list-table">
        <div class="tp-list-name functional-suite-list-name"><span id="list-name" class="ant-typography">测试集名称</span></div>
      </div>
    </main>
  `

  const requirementNameMarkup = `
    <main class="project-overview-page">
      <div class="project-requirement-list-table requirements-list-table">
        <div class="tp-list-name project-requirement-list-name requirements-list-name"><a href="/requirements/example"><span id="list-name" class="ant-typography">需求名称</span></a></div>
      </div>
    </main>
  `

  it.each([
    ['API 测试集', testingCss, suiteNameMarkup('api-test-page')],
    ['UI 测试集', testingCss, suiteNameMarkup('ui-test-page')],
    ['功能测试集', testingCss, suiteNameMarkup('')],
    ['需求', `${workbenchCss}\n${requirementListCss}`, requirementNameMarkup],
  ])('%s名称与任务名称使用相同的列表样式', (_, css, markup) => {
    const taskNameStyle = computedNameStyle(aiTestingCss, taskNameMarkup)
    const targetNameStyle = computedNameStyle(css, markup)

    expect(targetNameStyle).toEqual(taskNameStyle)
  })
})
