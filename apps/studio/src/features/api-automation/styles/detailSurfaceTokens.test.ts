import { describe, expect, it } from 'vitest'
import editorTsx from '../components/ApiCaseEditor.tsx?raw'

/** 取出指定 class 开头的完整类名字符串。 */
function classBlockOf(source: string, className: string) {
  return source.match(new RegExp(`className="([^"]*${className}[^"]*)"`))?.[1]
}

describe('API 用例请求地址条样式', () => {
  it('地址条只用表面 token，不继承亮色主题的白色内阴影', () => {
    const classes = classBlockOf(editorTsx, 'api-wb-url-group')

    expect(classes).toBeTruthy()
    expect(classes).not.toContain('rgba(255, 255, 255')
    expect(classes).toContain('bg-[var(--srf-card)]')
  })

  it('聚焦环用色盘 token', () => {
    const classes = classBlockOf(editorTsx, 'api-wb-url-group')

    expect(classes).toContain('focus-within:shadow-[0_0_0_3px_var(--srf-accent-soft)]')
  })
})
