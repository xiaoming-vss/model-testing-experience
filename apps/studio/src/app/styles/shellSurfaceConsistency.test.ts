import { afterEach, describe, expect, it } from 'vitest'
import shellHeaderCss from './shell-header.css?raw'

afterEach(() => {
  document.head.innerHTML = ''
  document.body.innerHTML = ''
})

describe('macOS 工作台板面', () => {
  it('workbench-panel-flat 压平玻璃底且不依赖 !important', () => {
    document.head.innerHTML = `<style>${shellHeaderCss}</style>`
    document.body.innerHTML = `
      <div class="app-shell-macos">
        <section id="flat" class="workbench-panel workbench-panel-flat"></section>
      </div>
    `
    const flat = getComputedStyle(document.querySelector('#flat') as HTMLElement)
    expect(parseFloat(flat.borderTopWidth)).toBe(0)
    expect(parseFloat(flat.borderTopLeftRadius)).toBe(0)
    expect(flat.backgroundColor).toBe('rgba(0, 0, 0, 0)')
    expect(flat.boxShadow).toBe('none')
    expect(flat.backdropFilter).toBe('none')
  })
})
