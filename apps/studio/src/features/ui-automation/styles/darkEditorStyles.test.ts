import { afterEach, describe, expect, it } from 'vitest'
import '../../../App.css'
import '@/shared/styles/surface-tokens.css'
import '@/features/ui-automation/styles/detail-workbench-v2.css'
import '@/features/ui-automation/styles/detail-pipeline-v2.css'

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

  it('用例信息条是一条两行的裸卡片，不是又一层有色容器', () => {
    document.body.innerHTML = `
      <div class="app-shell app-shell-macos">
        <div class="ui-suite-detail-page tp-surface">
          <section class="ui-wb-case-meta">
            <div class="ui-wb-case-meta-head">
              <span class="ui-wb-case-serial">CASE-02</span>
              <div class="ui-test-case-name-item ui-wb-case-name-item"><input class="ant-input" /></div>
              <div class="ui-wb-case-meta-actions"></div>
            </div>
            <div class="ui-wb-case-meta-sub">
              <div class="ui-wb-case-meta-flags">当前用例已启用 · 包含 7 个步骤</div>
              <div class="ui-wb-case-meta-links">用例导入 删除用例</div>
            </div>
          </section>
        </div>
      </div>
    `

    const head = document.querySelector<HTMLElement>('.ui-wb-case-meta-head')!
    const sub = document.querySelector<HTMLElement>('.ui-wb-case-meta-sub')!
    const serial = document.querySelector<HTMLElement>('.ui-wb-case-serial')!

    // 第一行是序号 + 名称 + 动作的单行排布，第二行左右分开
    expect(getComputedStyle(head).display).toBe('flex')
    expect(getComputedStyle(head).alignItems).toBe('center')
    expect(getComputedStyle(sub).display).toBe('flex')
    expect(getComputedStyle(sub).flexWrap).toBe('wrap')
    expect(getComputedStyle(sub).justifyContent).toBe('space-between')
    // 第二行是裸行：没有自己的底色与上边框（设计稿里它贴在卡片内部）
    expect(getComputedStyle(sub).backgroundColor).toBe('rgba(0, 0, 0, 0)')
    expect(getComputedStyle(sub).borderTopStyle).toBe('none')
    // 序号是方形小色块，不是胶囊
    expect(getComputedStyle(serial).borderRadius).toBe('4px')
  })
})
