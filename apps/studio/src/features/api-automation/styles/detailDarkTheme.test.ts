import { describe, expect, it } from 'vitest'
import detailCss from './detail.css?raw'

describe('API 用例请求地址暗色样式', () => {
  it('不会继承亮色主题的白色内阴影', () => {
    const darkUrlGroupStyles = detailCss.match(
      /:root\[data-theme='dark'\]\s+\.api-case-url-group\s*\{([^}]*)\}/s,
    )?.[1]

    expect(darkUrlGroupStyles).toContain(
      'box-shadow: inset 0 1px 0 rgba(240, 246, 252, 0.04);',
    )
    expect(darkUrlGroupStyles).not.toContain('rgba(255, 255, 255, 0.88)')
  })
})
