import listNameCss from '@/shared/styles/list-name.css?raw'
import { afterEach, describe, expect, it } from 'vitest'

// Shared typography must win over legacy feature styles in every list.
type NameStyle = {
  cursor: string
  fontSize: string
  fontWeight: string
  textUnderlineOffset: string
}

function computedNameStyle(markup: string): NameStyle {
  document.head.innerHTML = `<style>${listNameCss}</style>`
  document.body.innerHTML = `<div class="app-shell app-shell-macos"><div class="ant-table-wrapper"><div class="ant-table"><div class="ant-table-tbody">${markup}</div></div></div></div>`

  const style = getComputedStyle(document.querySelector('#list-name') as HTMLElement)
  return {
    cursor: style.cursor,
    fontSize: style.fontSize,
    fontWeight: style.fontWeight,
    textUnderlineOffset: style.textUnderlineOffset,
  }
}

afterEach(() => {
  document.head.innerHTML = ''
  document.body.innerHTML = ''
})

describe('列表名称样式统一', () => {
  const suiteNameMarkup = `
    <main class="functional-test-page">
      <div class="functional-suite-list-table">
        <div class="tp-list-name functional-suite-list-name"><span id="list-name" class="ant-typography">测试集名称</span></div>
      </div>
    </main>
  `

  it('表格列表名称使用共享字阶与交互色', () => {
    const style = computedNameStyle(suiteNameMarkup)

    expect(style).toEqual({
      cursor: 'pointer',
      fontSize: '13px',
      fontWeight: '400',
      textUnderlineOffset: '3px',
    })
  })
})
