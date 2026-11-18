import { afterEach, describe, expect, it } from 'vitest'
import paginationCss from '@/shared/styles/pagination.css?raw'
import { tableFooterClass } from '@/shared/utils/surfaceClasses'

const styles = import.meta.glob('/src/**/*.css', { query: '?raw', import: 'default', eager: true }) as Record<string, string>
const footerSelector = /\.(?:table-footer|bugs-footer|case-library-footer|api-test-footer|ui-suite-list-footer|test-orders-footer|ai-task-list-footer|base-services-list-footer|api-environment-vars-footer|ant-pagination)(?![\w-])/

afterEach(() => { document.head.innerHTML = ''; document.body.innerHTML = '' })

describe('分页视觉一致性', () => {
  it('分页外观只由公共样式维护，页面不能重新覆盖', () => {
    const overrides = Object.entries(styles).filter(([path, css]) => {
      if (path.endsWith('/pagination.css')) return false
      const clean = css.replace(/\/\*[\s\S]*?\*\//g, '')
      return [...clean.matchAll(/([^{}]+)\{[^{}]*\}/g)].some((match) => footerSelector.test(match[1]))
    }).map(([path]) => path)
    expect(overrides).toEqual([])
  })

  it('普通列表和测试模块使用相同的页脚布局契约与分页圆角', () => {
    document.head.innerHTML = `<style>${Object.values(styles).join('\n')}\n${paginationCss}</style>`
    document.body.innerHTML = `<div class="app-shell app-shell-macos">${['', 'bugs-page', 'api-test-page', 'ui-test-page', 'case-library-page'].map(page => `
      <div class="${page ? 'testing-page' : ''}"><div class="${page}"><div class="api-automation-content"><section class="workbench-panel">
      <div class="table-footer ${tableFooterClass} ${page.replace('-page', '-footer')}"><span class="ant-typography">共 2 条</span><ul class="ant-pagination"><li class="ant-pagination-item ant-pagination-item-active">1</li></ul></div>
      </section></div></div></div>`).join('')}</div>`
    for (const footer of document.querySelectorAll('.table-footer')) {
      expect(footer.className).toContain(tableFooterClass)
      const item = getComputedStyle(footer.querySelector('.ant-pagination-item')!)
      expect([item.borderRadius, item.boxShadow]).toEqual(['8px', 'none'])
    }
  })
})
