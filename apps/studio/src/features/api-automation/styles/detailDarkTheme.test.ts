import { describe, expect, it } from 'vitest'
import inspectorCss from './detail-inspector-v2.css?raw'

/** 取出 `selector { ... }` 的声明块；选择器里的 `.` `:` 只是字面量，不参与正则。 */
function declarationsOf(css: string, selector: string) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return css.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`))?.[1]
}

describe('API 用例请求地址条暗色样式', () => {
  it('地址条只用表面 token，不继承亮色主题的白色内阴影', () => {
    const declarations = declarationsOf(inspectorCss, '.api-collection-workbench-page .api-wb-url-group')

    expect(declarations).toBeTruthy()
    expect(declarations).not.toContain('rgba(255, 255, 255')
    expect(declarations).toContain('background: var(--srf-card)')
  })

  it('聚焦环用色盘 token，深色下随之换成深色描边', () => {
    const declarations = declarationsOf(inspectorCss, '.api-collection-workbench-page .api-wb-url-group:focus-within')

    expect(declarations).toContain('var(--srf-accent-soft)')
  })
})
