import { afterEach, describe, expect, it } from 'vitest'
import workbenchCss from './workbench.css?raw'
import aiTestingSharedCss from '@/features/ai-testing/styles/index.css?raw'
import aiTestingListCss from '@/features/ai-testing/styles/task-list-v2.css?raw'
import testingCss from '@/features/testing/styles/index.css?raw'
import surfaceTokens from '@/shared/styles/surface-tokens.css?raw'
import listTableCss from '@/shared/styles/list-table.css?raw'

const aiTestingCss = `${aiTestingSharedCss}\n${aiTestingListCss}`

function computedListSurface(css: string, pageClass: string, tableClass: string) {
  document.head.innerHTML = `<style>${surfaceTokens}\n${listTableCss}\n${css}</style>`
  document.body.innerHTML = `
    <div class="app-shell app-shell-macos">
      <main class="${pageClass} tp-list-surface">
        <div class="${tableClass} tp-list-table">
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
  document.head.innerHTML = ''
  document.body.innerHTML = ''
})

describe('列表表面样式统一', () => {
  it('功能测试基准列表保留统一行高、内距与表头圆角', () => {
    const functional = computedListSurface(testingCss, 'functional-test-page', 'functional-suite-list-table')

    expect(functional.headerRadii).toEqual(['8px', '8px', '8px', '8px'])
    expect(functional).toMatchObject({
      headerHeight: '42px',
      headerPadding: '0px 16px',
      cellHeight: '48px',
      cellPadding: '8px 16px',
    })
    // jsdom 不解析背景中的 var()；在此锁定公共色值，最终级联另由浏览器验证。
    const tokens = getComputedStyle(document.documentElement)
    expect(tokens.getPropertyValue('--srf-list-header-bg').trim()).toBe('#f7f9fc')
    expect(tokens.getPropertyValue('--srf-list-row-bg').trim()).toBe('#ffffff')
    expect(tokens.getPropertyValue('--srf-list-row-hover').trim()).toBe('#f5f8ff')
  })

  it('需求列表与功能测试列表使用相同的表头和行样式', () => {
    const functional = computedListSurface(testingCss, 'functional-test-page', 'functional-suite-list-table')
    const requirements = computedListSurface(workbenchCss, 'project-overview-page', 'project-requirement-list-table')

    expect(requirements).toEqual(functional)
  })

  it('测试设计任务列表与功能测试列表使用相同的表头和行样式', () => {
    const functional = computedListSurface(testingCss, 'functional-test-page', 'functional-suite-list-table')
    const tasks = computedListSurface(aiTestingCss, 'ai-testing-page', 'ai-task-list-table')

    expect(tasks).toEqual(functional)
  })
})
