import { describe, expect, it } from 'vitest'
import panelsCss from './detail-request-panels-v2.css?raw'

/*
 * 请求头 / 请求体两个面板的样式契约。
 *
 * 这一层的取值只允许来自 `surface-tokens.css` 的 `--srf-*` 色盘（深色主题靠 token 的深色分支覆盖），
 * 覆盖全局按钮皮肤的规则必须按 S14 的写法带 `.app-shell.app-shell-macos` 前缀与 `!important`，
 * 否则会在与全局皮肤同权重时静默失效。
 */

/** 取出所有 `selector { declarations }` 块；注释先剥掉，否则会被当成选择器的一部分。 */
function blocksOf(css: string) {
  return [...css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((match) => ({
    selector: match[1].trim(),
    declarations: match[2].trim(),
  }))
}

describe('API 请求编辑面板样式', () => {
  it('颜色只取 --srf 色盘，不写裸色值', () => {
    expect(panelsCss).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(panelsCss).not.toMatch(/rgba?\(/)
  })

  it('面板选择器都挂在页面类下，不污染其它页面', () => {
    const selectors = blocksOf(panelsCss)
      .map((block) => block.selector)
      .filter((selector) => selector.startsWith('.api-collection-workbench-page'))

    expect(selectors.length).toBeGreaterThan(20)
  })

  it('覆盖全局皮肤的规则带 app-shell 前缀与 !important', () => {
    const overrides = blocksOf(panelsCss).filter((block) => block.declarations.includes('!important'))
    const targets = ['.api-wb-hdr-row-actions', '.api-env-var-picker-trigger', '.api-wb-hdr-input']

    expect(overrides.length).toBeGreaterThan(0)
    for (const block of overrides) {
      // 前缀 + !important 缺一不可：全局皮肤是 (0,4,0) + !important，少一样就被它压回去。
      // 深色下同一份皮肤多一级 `:root[data-theme='dark']`，覆盖规则要跟着抬一级。
      const scoped = block.selector.replace(/^:root\[data-theme='dark'\]\s+/, '')
      expect(scoped.startsWith('.app-shell.app-shell-macos .api-collection-workbench-page')).toBe(true)
      // 选择器里可能带 `:is(a, b)`，所以整体判断，不按逗号切分。
      expect(targets.some((target) => block.selector.includes(target))).toBe(true)
    }
  })

  it('深色下覆盖全局输入框底色的规则抬了主题权重', () => {
    const darkInputOverrides = blocksOf(panelsCss).filter(
      (block) => block.declarations.includes('!important') && block.selector.includes('.api-wb-hdr-input'),
    )

    expect(darkInputOverrides.length).toBeGreaterThan(0)
    for (const block of darkInputOverrides) {
      expect(
        block.selector.startsWith(':root[data-theme=\'dark\'] .app-shell.app-shell-macos .api-collection-workbench-page'),
      ).toBe(true)
    }
  })

  it('请求头工具条、表头与请求体状态条用表面 token', () => {
    const toolbar = blocksOf(panelsCss).find((block) => block.selector.endsWith('.api-wb-hdr-toolbar'))
    const headCell = blocksOf(panelsCss).find((block) => block.selector.endsWith('.api-wb-hdr-table thead th'))
    const status = blocksOf(panelsCss).find((block) => block.selector.endsWith('.api-wb-body-status'))

    expect(toolbar?.declarations).toContain('background: var(--srf-hover)')
    expect(toolbar?.declarations).toContain('border-bottom: 1px solid var(--srf-card-border)')
    expect(headCell?.declarations).toContain('background: var(--srf-hover)')
    expect(status?.declarations).toContain('background: var(--srf-hover)')
  })

  it('合法性徽标走九色盘 tone token，深色下自动换色', () => {
    const badge = blocksOf(panelsCss).find((block) => block.selector.endsWith('.api-wb-body-validity'))

    expect(badge?.declarations).toContain('color: var(--srf-tone-text)')
    expect(badge?.declarations).toContain('background: var(--srf-tone-bg)')
    expect(badge?.declarations).toContain('border: 1px solid var(--srf-tone-border)')
  })
})
