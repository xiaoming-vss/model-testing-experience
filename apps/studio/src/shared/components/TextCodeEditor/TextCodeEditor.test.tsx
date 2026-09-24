import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { TextCodeEditor } from './TextCodeEditor'
import editorTokens from '@/shared/styles/editor-tokens.css?raw'

let paletteStyle: HTMLStyleElement
beforeEach(() => {
  paletteStyle = document.createElement('style')
  paletteStyle.textContent = editorTokens
  document.head.append(paletteStyle)
})

// jsdom does not resolve var() to a color. Verify both the emitted syntax role
// and its light value; actual resolution is checked in the browser.
function expectSyntaxColor(element: HTMLElement, role: string, lightValue: string) {
  expect(element).toHaveStyle({ color: `var(--editor-syntax-${role})` })
  expect(getComputedStyle(document.documentElement).getPropertyValue(`--editor-syntax-${role}`).trim()).toBe(lightValue)
}

afterEach(() => {
  cleanup()
  paletteStyle.remove()
})

describe('TextCodeEditor', () => {
  it('highlights YAML candidate fields', async () => {
    render(
      <TextCodeEditor
        value={'name: 登录成功\nenabled: true\norderNo: 1'}
        language="yaml"
        ariaLabel="候选结果 YAML"
      />,
    )

    expect(screen.getByRole('textbox', { name: '候选结果 YAML' })).toBeInTheDocument()
    await waitFor(() => {
      expectSyntaxColor(screen.getByText('name'), 'key', '#d97706')
      expectSyntaxColor(screen.getByText('登录成功'), 'string', '#16a34a')
      expectSyntaxColor(screen.getByText('true'), 'string', '#16a34a')
      expectSyntaxColor(screen.getAllByText(':')[0], 'yaml-punctuation', '#475569')
    })
  })

  it('highlights JSON fields and values with the shared theme', async () => {
    render(
      <TextCodeEditor
        value={'{"name":"登录成功","enabled":true,"orderNo":1}'}
        language="json"
        ariaLabel="候选结果 JSON"
      />,
    )

    const editor = screen.getByRole('textbox', { name: '候选结果 JSON' })
    expect(editor.closest('.json-editor-wrap')?.querySelector('.cm-foldGutter')).toBeInTheDocument()
    await waitFor(() => {
      expectSyntaxColor(within(editor).getByText('"name"'), 'key', '#d97706')
      expectSyntaxColor(within(editor).getByText('"登录成功"'), 'string', '#16a34a')
      expectSyntaxColor(within(editor).getByText('true'), 'boolean', '#56b6c2')
      expectSyntaxColor(within(editor).getByText('1'), 'number', '#d19a66')
    })
  })
})
