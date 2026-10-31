import { expect, it } from 'vitest'
import baseServicesCss from './index.css?raw'

it('基础服务卡片网格按可用宽度自动填充，宽屏不再固定为四列', () => {
  const css = baseServicesCss.replace(/\/\*[\s\S]*?\*\//g, '')
  expect(css).toMatch(
    /\.base-services-connection-grid\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fill,\s*minmax\(310px,\s*1fr\)\)/,
  )
  expect(css).not.toMatch(/repeat\(4,\s*minmax\(260px,\s*310px\)\)/)
})
