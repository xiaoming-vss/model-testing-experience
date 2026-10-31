import { afterEach, describe, expect, it } from 'vitest'
import sharedCss from './index.css?raw'
import reviewCss from './task-review.css?raw'
import candidateCss from './candidate-review.css?raw'
import resultCss from './run-result.css?raw'
import analysisCss from './requirement-analysis.css?raw'
import revisionCss from '../components/RevisionSidePanel.css?raw'
import artifactCss from './functional-artifact-modal.css?raw'
import uiGenerationCss from './ui-generation.css?raw'
import uiStageVisualCss from './ui-stage-visual.css?raw'
import uiStageVisualTokensCss from '@/shared/styles/ui-stage-visual-tokens.css?raw'

// jsdom 的 getComputedStyle 不解析 var()，注入前先把已登记色板解析成实际值。
const uiStageVisualTokenValues = new Map(
  [...uiStageVisualTokensCss.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map(match => [match[1], match[2].trim()]),
)
const uiStageVisualResolvedCss = uiStageVisualCss.replace(
  /var\((--[\w-]+)\)/g,
  (match, name: string) => uiStageVisualTokenValues.get(name) ?? match,
)

const aiTestingCss = `${sharedCss}\n${reviewCss}\n${candidateCss}\n${resultCss}`

afterEach(() => {
  document.head.innerHTML = ''
  document.body.innerHTML = ''
})

describe('运行结果弹框布局', () => {
  it('继续优化保留横向工作区，不被需求分析内部纵向布局覆盖', () => {
    document.head.innerHTML = `<style>${revisionCss}\n${aiTestingCss}\n${analysisCss}\n${artifactCss}</style>`
    document.body.innerHTML = `
      <div class="ant-modal functional-artifact-modal ai-task-run-result-modal ai-requirement-analysis-preview-modal review functional-stage-review-modal">
        <div class="ant-modal-body"><div class="revision-workspace is-revising">
          <div class="revision-source"><div class="ai-task-run-result-modal-content review"></div></div>
          <div class="revision-divider"></div><aside class="revision-side-panel"></aside>
        </div></div>
      </div>`
    const workspace = getComputedStyle(document.querySelector('.revision-workspace')!)
    expect(workspace.display).toBe('flex')
    expect(workspace.flexDirection || 'row').toBe('row')
    expect(getComputedStyle(document.querySelector('.revision-side-panel')!).display).toBe('flex')
  })

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

  it('UI 候选结果展开后由预览区内部滚动，不盖住审核备注', () => {
    document.head.innerHTML = `<style>${aiTestingCss}</style>`
    document.body.innerHTML = `
      <div class="ant-modal ui-task-candidate-result-modal ai-task-import-result-modal">
        <div class="ant-modal-container"><div class="ant-modal-body">
          <div class="ai-task-import-result-form">
            <div class="ant-tabs">
              <div class="ant-tabs-content-holder"><div class="ant-tabs-content">
                <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
                  <div class="ai-task-review-modal-content ai-task-import-result-preview-content single-column">
                    <div class="ai-task-review-modal-section">
                      <div class="ai-task-review-modal-preview ai-task-import-result-preview"></div>
                    </div>
                  </div>
                </div>
              </div></div>
            </div>
            <div class="ui-task-candidate-review-note"></div>
          </div>
        </div></div>
      </div>`

    const style = (selector: string) => getComputedStyle(document.querySelector<HTMLElement>(selector)!)
    expect(style('.ant-tabs-tabpane-active').display).toBe('flex')
    expect(style('.ant-tabs-tabpane-active').flexDirection).toBe('column')
    expect(style('.ant-tabs-tabpane-active').overflow).toBe('hidden')
    expect(style('.ai-task-import-result-preview-content').gridTemplateRows).toBe('minmax(0, 1fr)')
    expect(style('.ai-task-import-result-preview-content').alignItems).toBe('stretch')
    expect(style('.ai-task-import-result-preview').flexGrow).toBe('1')
    expect(style('.ai-task-import-result-preview').minHeight).toBe('0px')
  })

  it('三阶段审核复用功能阶段审核布局，编辑器占满剩余空间并由内部滚动', () => {
    document.head.innerHTML = `<style>${aiTestingCss}\n${uiGenerationCss}</style>`
    document.body.innerHTML = `
      <div class="ant-modal ai-task-run-result-modal functional-artifact-modal review functional-stage-review-modal">
        <div class="ant-modal-container"><div class="ant-modal-body">
          <div class="revision-workspace"><div class="revision-source">
            <div class="ai-task-run-result-modal-content review">
              <div class="ai-task-stage-review-popover ui-generation-stage-panel">
                <div class="ai-task-run-result-popover-header"></div>
                <div class="ui-generation-stage-editor">
                  <div class="json-editor-wrap"><div class="json-editor-shell">
                    <div class="json-editor-codemirror"><div class="cm-editor"><div class="cm-scroller"></div></div></div>
                  </div></div>
                </div>
              </div>
            </div>
          </div></div>
        </div><div class="ant-modal-footer"></div></div>
      </div>`

    const style = (selector: string) => getComputedStyle(document.querySelector<HTMLElement>(selector)!)
    const panel = style('.ui-generation-stage-panel')
    expect(panel.display).toBe('flex')
    expect(panel.flexDirection).toBe('column')
    expect(panel.overflowY).toBe('auto')
    expect(style('.ui-generation-stage-editor').display).toBe('flex')
    expect(style('.ui-generation-stage-editor').flexDirection).toBe('column')
    expect(style('.ui-generation-stage-editor').overflow).toBe('hidden')
    expect(style('.ui-generation-stage-editor').minHeight).toBe('260px')
    // CodeMirror 逐层约束高度，内容在编辑器内部滚动，不能盖住弹窗底部的审核动作。
    for (const selector of ['.json-editor-wrap', '.json-editor-shell', '.json-editor-codemirror', '.cm-editor']) {
      expect(style(selector).height).toBe('100%')
      expect(style(selector).minHeight).toBe('0px')
      expect(style(selector).overflow).toBe('hidden')
      expect(style(selector).flexGrow).toBe('1')
    }
    expect(style('.cm-scroller').overflow).toBe('auto')
    expect(style('.cm-scroller').minHeight).toBe('0px')
  })

  it('三阶段可视化视图填满审核正文，三个面板各自滚动', () => {
    document.head.innerHTML = `<style>${aiTestingCss}\n${uiGenerationCss}\n${uiStageVisualResolvedCss}</style>`
    document.body.innerHTML = `
      <div class="functional-stage-review-modal"><div class="ai-task-run-result-modal-content review">
        <div class="ai-task-stage-review-popover ui-generation-stage-panel">
          <div class="ui-generation-stage-visual"><div class="uisv">
            <aside class="uisv-pane uisv-nav"></aside>
            <main class="uisv-pane uisv-main"><div class="uisv-table-wrap"></div></main>
            <aside class="uisv-pane uisv-inspector"></aside>
          </div></div>
        </div>
      </div></div>`
    const style = (selector: string) => getComputedStyle(document.querySelector<HTMLElement>(selector)!)
    expect(style('.ui-generation-stage-visual').display).toBe('flex')
    expect(style('.ui-generation-stage-visual').flexGrow).toBe('1')
    expect(style('.ui-generation-stage-visual').minHeight).toBe('260px')
    expect(style('.ui-generation-stage-visual').overflow).toBe('hidden')
    expect(style('.uisv').display).toBe('grid')
    expect(style('.uisv').gridTemplateColumns).toContain('230px')
    expect(style('.uisv-main').overflow).toBe('hidden')
    expect(style('.uisv-table-wrap').overflow).toBe('auto')
  })

  it('暗色主题覆盖可视化面板、表格与原文编辑器', () => {
    document.documentElement.dataset.theme = 'dark'
    document.head.innerHTML = `<style>${aiTestingCss}\n${uiGenerationCss}\n${uiStageVisualResolvedCss}</style>`
    document.body.innerHTML = `
      <div class="ui-generation-stage-editor">
        <div class="json-editor-shell"><div class="json-editor-codemirror">
          <div class="cm-editor"><div class="cm-scroller"></div></div>
        </div></div>
      </div>
      <div class="uisv">
        <aside class="uisv-pane uisv-nav"><button class="uisv-page-item active"></button></aside>
        <main class="uisv-pane uisv-main">
          <div class="uisv-table-wrap"><div class="uisv-thead"></div><div class="uisv-row selected"></div></div>
        </main>
        <aside class="uisv-pane uisv-inspector"><div class="uisv-missing-box"></div></aside>
      </div>`
    try {
      const style = (selector: string) => getComputedStyle(document.querySelector<HTMLElement>(selector)!)
      expect(style('.uisv-pane').backgroundColor).toBe('rgb(22, 27, 34)')
      expect(style('.uisv-pane').borderTopColor).toBe('rgb(48, 54, 61)')
      expect(style('.uisv-page-item.active').backgroundColor).toBe('rgba(56, 139, 253, 0.15)')
      expect(style('.uisv-thead').backgroundColor).toBe('rgb(28, 33, 40)')
      expect(style('.uisv-row.selected').backgroundColor).toBe('rgba(56, 139, 253, 0.15)')
      expect(style('.uisv-row.selected').color).toBe('rgb(201, 209, 217)')
      expect(style('.uisv-missing-box').backgroundColor).toBe('rgba(210, 153, 34, 0.08)')
      expect(style('.cm-editor').backgroundColor).toBe('rgb(13, 17, 23)')
      expect(style('.json-editor-shell').backgroundColor).toBe('rgb(13, 17, 23)')
    } finally {
      delete document.documentElement.dataset.theme
    }
  })
})
