import { expect, it } from 'vitest'
import entryCss from '@/index.css?raw'

const styles = import.meta.glob('/src/**/*.css', {
  query: '?raw', import: 'default', eager: true,
}) as Record<string, string>

it('全站滚动条由公共入口加载，页面不能另设尺寸、配色或隐藏滚动条', () => {
  expect(entryCss).toContain("@import './shared/styles/scrollbars.css';")
  const overrides = Object.entries(styles).filter(([path, css]) => {
    if (path.endsWith('/shared/styles/scrollbars.css')) return false
    const clean = css.replace(/\/\*[\s\S]*?\*\//g, '')
    return /::-webkit-scrollbar|(?:^|[;{\s])(?:scrollbar-width|scrollbar-color|-ms-overflow-style)\s*:/m.test(clean)
  }).map(([path]) => path)
  expect(overrides).toEqual([])
})
