import { afterEach, describe, expect, it } from 'vitest'
import '../../../App.css'

afterEach(() => {
  document.body.replaceChildren()
  delete document.documentElement.dataset.theme
})

describe('UI 用例编辑器暗色样式', () => {
  it('名称输入和步骤标题不会显示成近黑色横条', () => {
    document.documentElement.dataset.theme = 'dark'
    document.body.innerHTML = `
      <div class="app-shell app-shell-macos">
        <div class="ui-suite-case-editor-panel">
          <div class="ui-test-case-name-item">
            <input class="ant-input" value="登录成功-输入正确用户名密码跳转工作台" />
          </div>
          <div class="ui-test-case-step-card">
            <div class="ui-test-case-step-title-item">
              <span class="ant-input-affix-wrapper">
                <input class="ant-input ui-test-case-step-title-input" value="打开登录页" />
              </span>
            </div>
          </div>
        </div>
      </div>
    `

    const caseName = document.querySelector<HTMLInputElement>('.ui-test-case-name-item .ant-input')!
    const stepTitleWrapper = document.querySelector<HTMLElement>('.ui-test-case-step-title-item .ant-input-affix-wrapper')!
    const stepTitle = document.querySelector<HTMLInputElement>('.ui-test-case-step-title-input')!

    expect(getComputedStyle(stepTitleWrapper).backgroundColor).toBe('rgba(0, 0, 0, 0)')
    expect(getComputedStyle(stepTitle).backgroundColor).toBe('rgba(0, 0, 0, 0)')
    expect(getComputedStyle(caseName).backgroundColor).toBe('rgba(22, 27, 34, 0.72)')
  })

  it('用例状态和步骤数以轻量辅助信息展示', () => {
    document.body.innerHTML = `
      <div class="ui-test-case-editor-fixed-head">
        <div class="ui-test-case-toolbar">
          <div class="ui-test-case-name-block"></div>
          <div class="ui-test-case-toolbar-meta"></div>
        </div>
        <div class="ui-test-case-secondary-meta">
          <div class="ui-test-case-enabled-meta">当前用例已启用</div>
          <span class="ui-test-case-meta-separator">·</span>
          <span class="ui-test-case-step-count-meta">包含 2 个步骤</span>
        </div>
      </div>
    `

    const toolbar = document.querySelector<HTMLElement>('.ui-test-case-toolbar')!
    const meta = document.querySelector<HTMLElement>('.ui-test-case-secondary-meta')!

    expect(getComputedStyle(toolbar).alignItems).toBe('flex-end')
    expect(getComputedStyle(meta).display).toBe('flex')
    expect(getComputedStyle(meta).marginTop).toBe('10px')
    expect(getComputedStyle(meta).backgroundColor).toBe('rgba(0, 0, 0, 0)')
    expect(getComputedStyle(meta).borderTopStyle).toBe('none')
  })
})
