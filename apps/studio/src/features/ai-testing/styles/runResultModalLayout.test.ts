import { afterEach, describe, expect, it } from 'vitest'
import sharedCss from './index.css?raw'
import reviewCss from './task-review.css?raw'
import candidateCss from './candidate-review.css?raw'
import resultCss from './run-result.css?raw'
import analysisCss from './requirement-analysis.css?raw'

const aiTestingCss = `${sharedCss}\n${reviewCss}\n${candidateCss}\n${resultCss}`

afterEach(() => {
  document.head.innerHTML = ''
  document.body.innerHTML = ''
})

describe('运行结果弹框布局', () => {
  it('需求分析 JSON 预览约束编辑器高度并由内部滚动', () => {
    document.head.innerHTML = `<style>${aiTestingCss}\n${analysisCss}</style>`
    document.body.innerHTML = `
      <div class="ai-requirement-analysis-preview-modal"><div class="ai-task-run-result-modal-content">
        <div class="json-editor-wrap"><div class="json-editor-shell">
          <div class="json-editor-toolbar"></div><div class="json-editor-codemirror">
            <div class="cm-editor"><div class="cm-scroller"></div></div>
          </div>
        </div></div>
      </div></div>`
    for (const selector of ['.json-editor-wrap', '.json-editor-shell', '.json-editor-codemirror', '.cm-editor']) {
      const style = getComputedStyle(document.querySelector(selector)!)
      expect(style.minHeight).toBe('0px')
      expect(style.overflow).toBe('hidden')
      expect(style.flexGrow).toBe('1')
    }
    const scroller = getComputedStyle(document.querySelector('.cm-scroller')!)
    expect(scroller.overflow).toBe('auto')
    expect(scroller.minHeight).toBe('0px')
    expect(getComputedStyle(document.querySelector('.json-editor-toolbar')!).flexShrink).toBe('0')
  })

  it('需求分析可视化在分析样式后加载时仍占满审核区', () => {
    document.head.innerHTML = `<style>${aiTestingCss}\n${analysisCss}</style>`
    document.body.innerHTML = `
      <div class="functional-stage-review-modal">
        <div class="ant-tabs ai-requirement-analysis-tabs review">
          <div class="ant-tabs-content-holder">
            <div class="ant-tabs-content"><div class="ant-tabs-tabpane ant-tabs-tabpane-active">
              <div class="ai-requirement-analysis-review-diagram"></div>
            </div></div>
          </div>
        </div>
      </div>`
    const holder = getComputedStyle(document.querySelector('.ant-tabs-content-holder')!)
    expect(holder.maxHeight).toBe('none')
    expect(holder.minHeight).toBe('0px')
    const diagram = getComputedStyle(document.querySelector('.ai-requirement-analysis-review-diagram')!)
    expect(diagram.height).toBe('100%')
    expect(diagram.minHeight).toBe('0px')
    expect(diagram.overflow).toBe('auto')
  })

  it('功能阶段审核保留视口高度和可收缩编辑区，不被通用结果弹窗覆盖', () => {
    document.head.innerHTML = `<style>${aiTestingCss}</style>`
    document.body.innerHTML = `
      <div class="ai-task-run-result-modal review functional-stage-review-modal">
        <div class="ant-modal-container">
          <div class="ant-modal-body">
            <div class="revision-workspace">
              <div class="revision-source">
                <div class="ai-task-run-result-modal-content review">
                  <div class="ai-task-stage-review-popover">
                    <div class="json-editor-wrap">
                      <div class="json-editor-shell">
                        <div class="json-editor-codemirror">
                          <div class="cm-editor"><div class="cm-scroller"></div></div>
                        </div>
                      </div>
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

    const style = (selector: string) => getComputedStyle(document.querySelector<HTMLElement>(selector)!)
    expect(style('.ant-modal-container').height).toBe('calc(100dvh - 72px)')
    expect(style('.ant-modal-container').maxHeight).toBe(`${window.innerHeight - 72}px`)
    expect(style('.ant-modal-body').flexBasis).toBe('0%')
    expect(style('.ant-modal-body').overflow).toBe('hidden')
    expect(style('.ai-task-stage-review-popover').flexBasis).toBe('0%')
    expect(style('.cm-editor').height).toBe('100%')
    expect(style('.cm-scroller').overflow).toBe('auto')
  })

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
