import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { BugDescriptionView } from './BugDescriptionView'
import { TestThemeProvider } from '@/test/TestThemeProvider'

it('shows JSON as code only in render view and preserves the original RAW description', () => {
  const html = '<p>附件信息</p><p>{</p><p>"code":0,</p><p>"items":[false,null]</p><p>}</p>'
  const view = render(<TestThemeProvider><BugDescriptionView html={html} /></TestThemeProvider>)
  const code = view.container.querySelector('.rich-text-viewer pre code')
  expect(JSON.parse(code!.textContent!)).toEqual({ code: 0, items: [false, null] })
  fireEvent.click(screen.getByText('RAW 代码'))
  expect(view.container.querySelector('.bug-description-raw')?.textContent).toBe(html)
  fireEvent.click(screen.getByText('渲染视图'))
  expect(view.container.querySelectorAll('.rich-text-viewer pre code')).toHaveLength(1)
})
