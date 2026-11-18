import { describe, expect, it } from 'vitest'
import headersTsx from '../components/ApiCaseHeadersPanel.tsx?raw'
import bodyTsx from '../components/ApiCaseBodyPanel.tsx?raw'
import shellCss from './api-detail-shell.module.css?raw'
import rulesCss from './api-detail-rules.module.css?raw'

/*
 * 请求头 / 请求体两个面板的样式契约。
 *
 * 页面布局与皮肤已迁到组件 utility，取值仍只允许来自 `surface-tokens.css` 的 `--srf-*` 色盘；
 * AntD 输入框与表格内部仍由 Module 的未分层规则负责。
 */

/** 取出所有 `selector { declarations }` 块；注释先剥掉，否则会被当成选择器的一部分。 */
function blocksOf(css: string) {
  return [...css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((match) => ({
    selector: match[1].trim(),
    declarations: match[2].trim(),
  }))
}

describe('API 请求编辑面板样式', () => {
  it('请求头与请求体不再写裸色值', () => {
    expect(headersTsx).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(bodyTsx).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(headersTsx).not.toMatch(/rgba?\(/)
    expect(bodyTsx).not.toMatch(/rgba?\(/)
  })

  it('行内按钮不重复覆盖公共按钮调色板', () => {
    const buttonOverrides = [...blocksOf(shellCss), ...blocksOf(rulesCss)].filter((block) =>
      block.selector.includes('.ant-btn')
      && /(?:^|;)\s*(?:color|background(?:-color)?|box-shadow|font-weight)\s*:/.test(block.declarations),
    )
    expect(buttonOverrides).toEqual([])
  })

  it('请求头工具条、表头与请求体状态条用表面 token', () => {
    expect(headersTsx).toContain('bg-[var(--srf-hover)]')
    expect(headersTsx).toContain('border-b border-[var(--srf-card-border)]')
    expect(bodyTsx).toContain('border-t border-[var(--srf-divider)] bg-[var(--srf-hover)]')
  })

  it('合法性徽标走九色盘 tone token', () => {
    expect(bodyTsx).toContain('border-[var(--srf-tone-border)]')
    expect(bodyTsx).toContain('bg-[var(--srf-tone-bg)]')
    expect(bodyTsx).toContain('text-[var(--srf-tone-text)]')
  })
})
