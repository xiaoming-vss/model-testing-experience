import { describe, expect, it } from 'vitest'
import darkPolishCss from './dark-polish.css?raw'

describe('暗色侧栏品牌区域', () => {
  it('使用与侧栏和页头相同的固定底色', () => {
    const brandRowStyles = darkPolishCss.match(
      /:root\[data-theme='dark'\]\s+\.app-shell\.app-shell-macos\s+\.brand-row\s*\{([^}]*)\}/s,
    )?.[1]

    expect(brandRowStyles).toContain('background: #0d1117 !important;')
  })
})
