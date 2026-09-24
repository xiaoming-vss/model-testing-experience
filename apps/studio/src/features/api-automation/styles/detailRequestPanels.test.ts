import { describe, expect, it } from 'vitest'
import panelsCss from './detail-request-panels-v2.css?raw'

/*
 * 请求头 / 请求体两个面板的样式契约。
 *
 * 这一层的取值只允许来自 `surface-tokens.css` 的 `--srf-*` 色盘，
 * 按钮外观由 app/styles/buttons.css 的公共层持有，面板不再增加反向覆盖。
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

  it('行内按钮不重复覆盖公共按钮调色板', () => {
    const buttonOverrides = blocksOf(panelsCss).filter((block) =>
      block.selector.includes('.ant-btn')
      && /(?:^|;)\s*(?:color|background(?:-color)?|box-shadow|font-weight)\s*:/.test(block.declarations),
    )
    expect(buttonOverrides).toEqual([])
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

  it('合法性徽标走九色盘 tone token', () => {
    const badge = blocksOf(panelsCss).find((block) => block.selector.endsWith('.api-wb-body-validity'))

    expect(badge?.declarations).toContain('color: var(--srf-tone-text)')
    expect(badge?.declarations).toContain('background: var(--srf-tone-bg)')
    expect(badge?.declarations).toContain('border: 1px solid var(--srf-tone-border)')
  })
})
