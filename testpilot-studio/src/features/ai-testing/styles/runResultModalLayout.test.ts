import { afterEach, describe, expect, it } from 'vitest'
import aiTestingCss from './index.css?raw'

afterEach(() => {
  document.head.innerHTML = ''
  document.body.innerHTML = ''
})

describe('需求分析结果弹框布局', () => {
  it('将编辑区限制在 footer 上方并为超长内容提供纵向滚动', () => {
    document.head.innerHTML = `<style>${aiTestingCss}</style>`
    document.body.innerHTML = `
      <div class="ai-task-run-result-modal api-task-run-result-modal review">
        <div class="ant-modal-container">
          <div class="ant-modal-body">
            <div class="ai-task-run-result-modal-content api-task-run-result-modal-content review">
              <div class="ai-task-stage-review-popover">
                <div class="ai-task-run-result-popover-header"></div>
                <div class="ai-task-stage-review-note compact"></div>
                <div class="json-editor-wrap">
                  <div class="json-editor-shell">
                    <div class="json-editor-codemirror">
                      <div class="cm-editor"></div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="ant-modal-footer"></div>
        </div>
      </div>
    `

    const modal = document.querySelector<HTMLElement>('.ai-task-run-result-modal')!
    const body = document.querySelector<HTMLElement>('.ant-modal-body')!
    const container = document.querySelector<HTMLElement>('.ant-modal-container')!
    const content = document.querySelector<HTMLElement>('.ai-task-run-result-modal-content')!
    const review = document.querySelector<HTMLElement>('.ai-task-stage-review-popover')!
    const editorWrap = document.querySelector<HTMLElement>('.json-editor-wrap')!
    const editor = document.querySelector<HTMLElement>('.cm-editor')!
    const scroller = document.createElement('div')
    scroller.className = 'cm-scroller'
    editor.append(scroller)

    expect(getComputedStyle(modal).getPropertyValue('--ai-popover-surface').trim()).not.toBe('')
    expect(getComputedStyle(container).display).toBe('flex')
    expect(getComputedStyle(container).flexDirection).toBe('column')
    expect(getComputedStyle(container).overflow).toBe('hidden')
    expect(getComputedStyle(body).flexGrow).toBe('1')
    expect(getComputedStyle(body).overflow).toBe('hidden')
    expect(getComputedStyle(content).flexGrow).toBe('1')
    expect(getComputedStyle(content).height).toBe('auto')
    expect(getComputedStyle(content).overflowY).toBe('auto')
    expect(getComputedStyle(review).height).toBe('auto')
    expect(getComputedStyle(editorWrap).flexGrow).toBe('1')
    expect(getComputedStyle(editor).height).toBe('100%')
    expect(getComputedStyle(scroller).overflowY).toBe('auto')
  })
})
