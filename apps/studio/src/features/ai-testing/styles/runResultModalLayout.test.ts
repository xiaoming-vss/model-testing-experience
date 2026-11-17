import { afterEach, describe, expect, it } from 'vitest'
import revisionModuleCss from './generation-chain.module.css?raw'
import uiStageModuleCss from './ui-stage-visual.module.css?raw'
import uiStageVisualTokensCss from '@/shared/styles/ui-stage-visual-tokens.css?raw'

/** jsdom 不认 CSS Modules 的 `:global(...)`；测试注入前只剥掉外壳，保留内部选择器。 */
function unglobal(css: string) {
  let result = ''
  let index = 0
  while (true) {
    const start = css.indexOf(':global(', index)
    if (start < 0) {
      result += css.slice(index)
      break
    }
    result += css.slice(index, start)
    let depth = 1
    let cursor = start + 8
    for (; cursor < css.length && depth > 0; cursor += 1) {
      if (css[cursor] === '(') depth += 1
      else if (css[cursor] === ')') depth -= 1
    }
    result += css.slice(start + 8, cursor - 1)
    index = cursor
  }
  return result
}

const revisionCss = unglobal(revisionModuleCss)

// jsdom 的 getComputedStyle 不解析 var()，注入前先把已登记色板解析成实际值。
const uiStageVisualTokenValues = new Map(
  [...uiStageVisualTokensCss.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map(match => [match[1], match[2].trim()]),
)
const uiStageVisualResolvedCss = unglobal(uiStageModuleCss).replace(
  /var\((--[\w-]+)\)/g,
  (match, name: string) => uiStageVisualTokenValues.get(name) ?? match,
)

afterEach(() => {
  document.head.innerHTML = ''
  document.body.innerHTML = ''
})

describe('运行结果弹框布局', () => {
  it('继续优化保留横向工作区', () => {
    document.head.innerHTML = `<style>${revisionCss}</style>`
    document.body.innerHTML = `
      <div class="scope">
        <div class="revision-workspace is-revising">
          <div class="revision-source"></div>
          <div class="revision-divider"></div><aside class="revision-side-panel"></aside>
        </div>
      </div>`
    const workspace = getComputedStyle(document.querySelector('.revision-workspace')!)
    expect(workspace.display).toBe('flex')
    expect(workspace.flexDirection || 'row').toBe('row')
    expect(getComputedStyle(document.querySelector('.revision-side-panel')!).display).toBe('flex')
  })


  it('暗色主题覆盖可视化面板、表格与原文编辑器', () => {
    document.documentElement.dataset.theme = 'dark'
    document.head.innerHTML = `<style>${uiStageVisualResolvedCss}</style>`
    document.body.innerHTML = `
      <div class="scope">
        <div class="ui-generation-stage-editor">
          <div class="json-editor-shell"><div class="json-editor-codemirror">
            <div class="cm-editor"><div class="cm-scroller"></div></div>
          </div></div>
        </div>
        <div class="uisv">
          <aside class="uisv-pane uisv-nav"><button class="uisv-page-item active"></button></aside>
          <main class="uisv-pane uisv-main">
            <div class="uisv-table-wrap"><div class="uisv-thead"></div><div class="uisv-row selected"></div></div>
          </main>
          <aside class="uisv-pane uisv-inspector"><div class="uisv-missing-box"></div></aside>
        </div>
      </div>`
    try {
      const style = (selector: string) => getComputedStyle(document.querySelector<HTMLElement>(selector)!)
      expect(style('.uisv-pane').backgroundColor).toBe('rgb(22, 27, 34)')
      expect(style('.uisv-pane').borderTopColor).toBe('rgb(48, 54, 61)')
      expect(style('.uisv-page-item.active').backgroundColor).toBe('rgba(56, 139, 253, 0.15)')
      expect(style('.uisv-thead').backgroundColor).toBe('rgb(28, 33, 40)')
      expect(style('.uisv-row.selected').backgroundColor).toBe('rgba(56, 139, 253, 0.15)')
      expect(style('.uisv-row.selected').color).toBe('rgb(201, 209, 217)')
      expect(style('.uisv-missing-box').backgroundColor).toBe('rgba(210, 153, 34, 0.08)')
      expect(style('.cm-editor').backgroundColor).toBe('rgb(13, 17, 23)')
      expect(style('.json-editor-shell').backgroundColor).toBe('rgb(13, 17, 23)')
    } finally {
      delete document.documentElement.dataset.theme
    }
  })
})
