import { afterEach, describe, expect, it } from 'vitest'
import stylesheet from '../../testing/styles/index.css?raw'

afterEach(() => {
  document.head.querySelector('[data-requirement-preview-styles]')?.remove()
  document.body.innerHTML = ''
})

describe('requirement document preview layout', () => {
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
})
