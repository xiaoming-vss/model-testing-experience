import { afterEach, describe, expect, it } from 'vitest'
import darkPolishCss from './dark-polish.css?raw'
import workbenchCss from './workbench.css?raw'
import aiTestingCss from '@/features/ai-testing/styles/index.css?raw'
import testingCss from '@/features/testing/styles/index.css?raw'

function computedListSurface(css: string, pageClass: string, tableClass: string, theme: 'light' | 'dark') {
  if (theme === 'dark') {
    document.documentElement.dataset.theme = 'dark'
  } else {
    delete document.documentElement.dataset.theme
  }
  document.head.innerHTML = `<style>${css}</style>`
  document.body.innerHTML = `
    <div class="app-shell app-shell-macos">
      <main class="${pageClass}">
        <div class="${tableClass}">
          <table class="ant-table">
            <thead class="ant-table-thead"><tr><th id="header" class="ant-table-cell">名称</th></tr></thead>
            <tbody class="ant-table-tbody"><tr><td id="cell" class="ant-table-cell">内容</td></tr></tbody>
          </table>
        </div>
      </main>
    </div>
  `

  const header = getComputedStyle(document.querySelector('#header') as HTMLElement)
  const headerGroup = getComputedStyle(document.querySelector('.ant-table-thead') as HTMLElement)
  const cell = getComputedStyle(document.querySelector('#cell') as HTMLElement)

  return {
    headerBackground: header.backgroundColor,
    headerHeight: header.height,
    headerPadding: header.padding,
    headerClipPath: headerGroup.clipPath,
    headerRadii: [
      header.borderTopLeftRadius,
      header.borderTopRightRadius,
      header.borderBottomRightRadius,
      header.borderBottomLeftRadius,
    ],
    cellBackground: cell.backgroundColor,
    cellHeight: cell.height,
    cellPadding: cell.padding,
  }
}

afterEach(() => {
  delete document.documentElement.dataset.theme
  document.head.innerHTML = ''
  document.body.innerHTML = ''
})

describe('列表表面样式统一', () => {
  it.each(['light', 'dark'] as const)('功能测试基准表头在%s主题下保留四角圆弧', (theme) => {
    const functional = computedListSurface(testingCss, 'functional-test-page', 'functional-suite-list-table', theme)

    expect(functional.headerRadii).toEqual(['8px', '8px', '8px', '8px'])
  })

  it.each(['light', 'dark'] as const)('需求列表与功能测试列表使用相同的%s主题表头和行样式', (theme) => {
    const functional = computedListSurface(testingCss, 'functional-test-page', 'functional-suite-list-table', theme)
    const requirements = computedListSurface(`${workbenchCss}\n${darkPolishCss}`, 'project-overview-page', 'project-requirement-list-table', theme)

    expect(requirements).toEqual(functional)
  })

  it.each(['light', 'dark'] as const)('测试设计任务列表与功能测试列表使用相同的%s主题表头和行样式', (theme) => {
    const functional = computedListSurface(testingCss, 'functional-test-page', 'functional-suite-list-table', theme)
    const tasks = computedListSurface(aiTestingCss, 'ai-testing-page', 'ai-task-list-table', theme)

    expect(tasks).toEqual(functional)
  })
})
