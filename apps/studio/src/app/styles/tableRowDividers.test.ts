import { afterEach, expect, it } from 'vitest'
import css from '@/shared/styles/table-row-dividers.css?raw'
import entry from '@/index.css?raw'
afterEach(() => { document.head.innerHTML = ''; document.body.innerHTML = '' })
it('全局横线覆盖数据行，跳过测量和展开行', () => {
  expect(entry).toContain("@import './shared/styles/table-row-dividers.css'")
  document.head.innerHTML = `<style>${css.replaceAll('var(--app-list-row-border)', 'rgb(220, 224, 239)')}</style>`
  document.body.innerHTML = `<div class="ant-table-wrapper"><table><tbody class="ant-table-tbody">${['ant-table-row', 'ant-table-measure-row', 'ant-table-expanded-row'].map((name, i) => `<tr class="${name}"><td class="ant-table-cell" id="cell${i}">内容</td></tr>`).join('')}</tbody></table></div>`
  expect(getComputedStyle(document.querySelector('#cell0')!).borderBottomWidth).toBe('1px')
  expect(getComputedStyle(document.querySelector('#cell0')!).borderBottomStyle).toBe('solid')
  for (const i of [1, 2]) expect(getComputedStyle(document.querySelector(`#cell${i}`)!).borderBottomStyle).not.toBe('solid')
})

const featureStyles = import.meta.glob('/src/features/**/*.css', { query: '?raw', import: 'default', eager: true }) as Record<string, string>
it('业务样式不另设行分隔色，避免再次出现不可辨识的横线', () => {
  const overrides = Object.entries(featureStyles).filter(([, source]) => /--app-list-row-border\s*:/.test(source.replace(/\/\*[\s\S]*?\*\//g, ''))).map(([path]) => path)
  expect(overrides).toEqual([])
})
