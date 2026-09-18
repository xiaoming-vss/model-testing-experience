import { afterEach, describe, expect, it } from 'vitest'
import workbenchCss from './workbench.css?raw'
import darkPolishCss from './dark-polish.css?raw'

function computedTagStyle(preset: string) {
  document.documentElement.dataset.theme = 'dark'
  document.head.innerHTML = `<style>${workbenchCss}</style><style>${darkPolishCss}</style>`
  document.body.innerHTML = `
    <div class="app-shell app-shell-macos">
      <span id="tag" class="ant-tag ant-tag-${preset}">状态</span>
    </div>
  `

  const styles = getComputedStyle(document.querySelector('#tag') as HTMLElement)
  return { background: styles.backgroundColor, color: styles.color }
}

afterEach(() => {
  delete document.documentElement.dataset.theme
  document.head.innerHTML = ''
  document.body.innerHTML = ''
})

describe('暗色主题语义标签', () => {
  it.each([
    ['default', 'rgb(179, 192, 209)', 'rgba(148, 163, 184, 0.14)'],
    ['gold', 'rgb(229, 178, 80)', 'rgba(217, 164, 65, 0.18)'],
    ['warning', 'rgb(229, 178, 80)', 'rgba(217, 164, 65, 0.18)'],
    ['cyan', 'rgb(109, 213, 200)', 'rgba(20, 184, 166, 0.16)'],
    ['purple', 'rgb(182, 154, 247)', 'rgba(139, 92, 246, 0.18)'],
    ['green', 'rgb(91, 192, 132)', 'rgba(63, 185, 116, 0.18)'],
    ['processing', 'rgb(91, 192, 132)', 'rgba(63, 185, 116, 0.18)'],
    ['success', 'rgb(91, 192, 132)', 'rgba(63, 185, 116, 0.18)'],
    ['error', 'rgb(239, 122, 122)', 'rgba(239, 92, 92, 0.16)'],
    ['red', 'rgb(242, 127, 137)', 'rgba(244, 63, 94, 0.18)'],
    ['volcano', 'rgb(242, 155, 112)', 'rgba(249, 115, 22, 0.18)'],
    ['orange', 'rgb(240, 164, 93)', 'rgba(245, 139, 47, 0.18)'],
    ['lime', 'rgb(168, 216, 104)', 'rgba(132, 204, 22, 0.18)'],
    ['blue', 'rgb(120, 174, 242)', 'rgba(74, 144, 226, 0.18)'],
    ['geekblue', 'rgb(154, 174, 255)', 'rgba(99, 102, 241, 0.18)'],
    ['magenta', 'rgb(240, 140, 188)', 'rgba(236, 72, 153, 0.18)'],
  ])('%s 保留对应的语义色', (preset, color, background) => {
    expect(computedTagStyle(preset)).toEqual({ background, color })
  })
})
