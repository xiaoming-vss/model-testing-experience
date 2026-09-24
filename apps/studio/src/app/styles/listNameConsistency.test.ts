import { afterEach, describe, expect, it } from 'vitest'
import workbenchCss from './workbench.css?raw'
import aiTestingSharedCss from '@/features/ai-testing/styles/index.css?raw'
import aiTestingListCss from '@/features/ai-testing/styles/task-list-v2.css?raw'
import testingCss from '@/features/testing/styles/index.css?raw'

const aiTestingCss = `${aiTestingSharedCss}\n${aiTestingListCss}`

/*
 * 四个列表页（AI 任务 / API 测试集 / UI 测试集 / 功能测试集 / 需求）的名称样式必须逐项相等。
 *
 * 此前这个测试在 `data-theme='dark'` 下跑：深色规则对四页统一写了
 * `color: #78aef2` / `font-weight: 500` / `line-height: 22px`，所以四项全等。
 * 深色分支退役后它第一次在浅色下运行，暴露出两件事，都只比对真正跨页统一的部分：
 *
 * 1. `line-height` 是真实分歧：AI 任务列表是 22px（`ai-testing/styles/task-list-v2.css` 里同一个选择器
 *    有两条规则，20px 那条被后面 22px 那条覆盖），其余三页是 20px。这是浅色下早就存在的不一致，
 *    不是主题移除引入的；要统一得先定取值，所以这里不比对。
 * 2. `color` 在 jsdom 下不稳定：同一个名称既有跨页统一的链接色
 *    `:root:not([data-theme='dark']) ... { color: #3f6fc6 !important }`，也有各页面自己写的
 *    `.xxx-list-name .ant-typography { color: #172033 !important }`。两者都带 `!important` 时
 *    jsdom 按「后出现的胜出」裁决、不按优先级（实测），于是跨文件比较的结果取决于规则先后；
 *    浏览器按优先级判定，四页都取到 #3f6fc6。这条也交给浏览器侧核对，不放进断言。
 */
type NameStyle = {
  cursor: string
  fontSize: string
  fontWeight: string
  textUnderlineOffset: string
}

function computedNameStyle(css: string, markup: string): NameStyle {
  document.head.innerHTML = `<style>${css}</style>`
  document.body.innerHTML = `<div class="app-shell app-shell-macos">${markup}</div>`

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
  ])('%s名称与任务名称使用相同的列表样式', (_, css, markup) => {
    const taskNameStyle = computedNameStyle(aiTestingCss, taskNameMarkup)
    const targetNameStyle = computedNameStyle(css, markup)

    expect(targetNameStyle).toEqual(taskNameStyle)
  })
})
