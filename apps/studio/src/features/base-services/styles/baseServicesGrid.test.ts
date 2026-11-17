import { expect, it } from 'vitest'
import baseConnectionCss from '@/shared/styles/base-services-connection.module.css?raw'

it('基础服务卡片网格按可用宽度自动填充，宽屏不再固定为四列', () => {
  const css = baseConnectionCss.replace(/\/\*[\s\S]*?\*\//g, '')
  expect(css).toMatch(
    /\.base-services-connection-grid[^{]*\{[^}]*grid-template-columns:\s*repeat\(auto-fill,\s*minmax\(310px,\s*1fr\)\)/,
  )
  expect(css).not.toMatch(/repeat\(4,\s*minmax\(260px,\s*310px\)\)/)
})

it('基础服务卡片网格的断点按从宽到窄声明，窄屏列数不被宽屏规则覆盖', () => {
  const breakpoints = [...baseConnectionCss.matchAll(/@media \(max-width: (\d+)px\)/g)]
    .map((match) => Number(match[1]))
  expect(breakpoints).toEqual([1880, 1560, 1220, 980, 680])
  expect(baseConnectionCss).toMatch(
    /@media \(max-width: 980px\) \{[\s\S]*\.base-services-connection-grid\) \{[\s\S]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/,
  )
  expect(baseConnectionCss).toMatch(
    /@media \(max-width: 680px\) \{[\s\S]*\.base-services-connection-grid\) \{[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)/,
  )
})
