import { afterEach, expect, it } from 'vitest'
import surfaceCss from '@/shared/styles/surface-tokens.css?raw'
import paginationCss from '@/shared/styles/pagination.css?raw'

afterEach(() => { document.head.innerHTML = ''; document.body.innerHTML = '' })

it.each(['table', 'cards'])('单容器 %s 保留内收滚动区和独立页脚', kind => {
  document.head.innerHTML = `<style>${surfaceCss}\n${paginationCss}</style>`
  document.body.innerHTML = `<main class="tp-surface"><nav>页面页签</nav><section class="tp-board tp-list-panel"><header class="tp-list-toolbar">操作</header><div class="tp-list-body"><div class="tp-list-scroll">${kind}</div><footer class="table-footer">分页</footer></div></section></main>`
  const style = (selector: string) => getComputedStyle(document.querySelector(selector)!)
  expect(style('.tp-list-panel').flexDirection).toBe('column')
  expect(parseFloat(style('.tp-list-panel').gap)).toBe(0)
  expect(parseFloat(style('.tp-list-toolbar').borderRadius)).toBe(0)
  expect(parseFloat(style('.tp-list-body').borderRadius)).toBe(0)
  expect(style('.tp-list-scroll').padding).toBe('16px')
  expect(style('.tp-list-scroll').overflow).toBe('auto')
  expect(parseFloat(style('.tp-list-scroll').minHeight)).toBe(0)
  expect(style('.table-footer').flex).toBe('0 0 auto')
  expect(document.querySelector('.tp-list-scroll .table-footer')).toBeNull()
})
