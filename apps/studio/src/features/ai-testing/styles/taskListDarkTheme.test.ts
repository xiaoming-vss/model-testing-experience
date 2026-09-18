import { afterEach, describe, expect, it } from 'vitest'
import aiTestingCss from './index.css?raw'

function computedTagColor(...classNames: string[]) {
  document.documentElement.dataset.theme = 'dark'
  document.head.innerHTML = `<style>${aiTestingCss}</style>`
  document.body.innerHTML = `
    <div class="app-shell app-shell-macos">
      <main class="ai-testing-page">
        <div class="ai-task-list-tags">
          <span id="tag" class="ant-tag ${classNames.join(' ')}">标签</span>
        </div>
      </main>
    </div>
  `

  return getComputedStyle(document.querySelector('#tag') as HTMLElement).color
}

function computedTaskNameColor() {
  document.documentElement.dataset.theme = 'dark'
  document.head.innerHTML = `<style>${aiTestingCss}</style>`
  document.body.innerHTML = `
    <div class="app-shell app-shell-macos">
      <main class="ai-testing-page">
        <div class="ai-task-list-table">
          <div class="ai-task-list-name">
            <span id="task-name" class="ant-typography">任务名称</span>
          </div>
        </div>
      </main>
    </div>
  `

  return getComputedStyle(document.querySelector('#task-name') as HTMLElement).color
}

function computedStatusColors(statusClass: string) {
  document.documentElement.dataset.theme = 'dark'
  document.head.innerHTML = `<style>${aiTestingCss}</style>`
  document.body.innerHTML = `
    <div class="app-shell app-shell-macos">
      <main class="ai-testing-page">
        <div class="ai-task-list-table">
          <table class="ant-table-tbody">
            <tr>
              <td></td>
              <td></td>
              <td>
                <div class="ai-task-list-tags">
                  <span id="status" class="ant-tag ai-task-status-tag ${statusClass}">
                    <span id="indicator" class="ai-task-status-indicator"></span>状态
                  </span>
                </div>
              </td>
            </tr>
          </table>
        </div>
      </main>
    </div>
  `

  return {
    indicator: getComputedStyle(document.querySelector('#indicator') as HTMLElement).backgroundColor,
    status: getComputedStyle(document.querySelector('#status') as HTMLElement).color,
  }
}

afterEach(() => {
  delete document.documentElement.dataset.theme
  document.head.innerHTML = ''
  document.body.innerHTML = ''
})

describe('任务列表暗色主题语义色', () => {
  it('暗色圆点覆盖第三列的全局文字颜色', () => {
    const indicatorStyles = aiTestingCss.match(
      /:root\[data-theme='dark'\]\s+\.app-shell\.app-shell-macos\s+\.ai-testing-page\s+\.ai-task-list-table\s+\.ant-table-tbody\s+td:nth-child\(3\)\s+\.ai-task-status-tag\s+\.ai-task-status-indicator\s*\{([^}]*)\}/s,
    )?.[1]

    expect(indicatorStyles).toContain('color: inherit !important;')
    expect(indicatorStyles).toContain('background: currentColor !important;')
  })

  it('任务名称保留蓝色可点击语义', () => {
    expect(computedTaskNameColor()).toBe('rgb(120, 174, 242)')
  })

  it.each([
    ['成功', 'ai-task-status-success', 'rgb(91, 192, 132)'],
    ['待审核', 'ai-task-status-waiting_review', 'rgb(229, 178, 80)'],
    ['未运行', 'ai-task-status-idle', 'rgb(179, 192, 209)'],
    ['失败', 'ai-task-status-failed', 'rgb(239, 122, 122)'],
  ])('%s 保留各自的状态颜色', (_, statusClass, color) => {
    expect(computedTagColor('ai-task-status-tag', statusClass)).toBe(color)
  })

  it.each([
    ['成功', 'ai-task-status-success'],
    ['待审核', 'ai-task-status-waiting_review'],
    ['未运行', 'ai-task-status-idle'],
    ['失败', 'ai-task-status-failed'],
  ])('%s 的圆点与状态文字颜色一致', (_, statusClass) => {
    const colors = computedStatusColors(statusClass)

    expect(colors.indicator).toBe(colors.status)
  })
})
