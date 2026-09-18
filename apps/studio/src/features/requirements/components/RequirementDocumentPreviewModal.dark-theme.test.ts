import { afterEach, describe, expect, it } from 'vitest'
import stylesheet from '../../testing/styles/index.css?raw'

afterEach(() => {
  delete document.documentElement.dataset.theme
  document.head.querySelector('[data-requirement-preview-styles]')?.remove()
  document.body.innerHTML = ''
})

describe('requirement document preview dark theme', () => {
  it('uses the candidate-result modal constraint without extra workspace spacing', () => {
    const style = document.createElement('style')
    style.dataset.requirementPreviewStyles = 'true'
    style.textContent = stylesheet
    document.head.appendChild(style)
    document.body.innerHTML = `
      <div class="requirement-document-dialog">
        <div class="ant-modal-container">
          <div class="ant-modal-content">
            <div class="requirement-document-workspace"></div>
          </div>
        </div>
      </div>
    `

    const container = document.querySelector<HTMLElement>('.ant-modal-container')
    const workspace = document.querySelector<HTMLElement>('.requirement-document-workspace')

    expect(container).not.toBeNull()
    expect(workspace).not.toBeNull()
    expect(getComputedStyle(container!).maxHeight).toBe(`${window.innerHeight - 72}px`)
    expect(getComputedStyle(container!).padding).toBe('0px')
    expect(getComputedStyle(container!).borderTopWidth).toBe('0px')
    expect(getComputedStyle(container!).borderRadius).toBe('12px')
    expect(getComputedStyle(container!).boxShadow).toBe('none')
    expect(getComputedStyle(workspace!).padding).toBe('0px')
  })

  it('keeps enhanced-text headings readable on the dark content surface', () => {
    document.documentElement.dataset.theme = 'dark'
    const style = document.createElement('style')
    style.dataset.requirementPreviewStyles = 'true'
    style.textContent = stylesheet
    document.head.appendChild(style)
    document.body.innerHTML = `
      <div class="requirement-document-understanding-content">
        <h1>功能理解记录</h1>
        <h2>使用理解</h2>
        <h3>功能说明</h3>
      </div>
    `

    const [heading1, heading2, heading3] = Array.from(document.querySelectorAll('h1, h2, h3'))

    expect(getComputedStyle(heading1).color).toBe('rgb(226, 232, 240)')
    expect(getComputedStyle(heading2).color).toBe('rgb(203, 213, 225)')
    expect(getComputedStyle(heading3).color).toBe('rgb(184, 196, 216)')
  })

  it('keeps the enhanced-text empty state on a dark surface', () => {
    document.documentElement.dataset.theme = 'dark'
    const style = document.createElement('style')
    style.dataset.requirementPreviewStyles = 'true'
    style.textContent = stylesheet
    document.head.appendChild(style)
    document.body.innerHTML = `
      <div class="requirement-document-understanding-empty">
        <div class="ant-empty-description">暂无增强文本</div>
      </div>
    `

    const emptyState = document.querySelector<HTMLElement>('.requirement-document-understanding-empty')

    expect(emptyState).not.toBeNull()
    expect(getComputedStyle(emptyState!).backgroundColor).toBe('rgb(23, 29, 41)')
  })
})
