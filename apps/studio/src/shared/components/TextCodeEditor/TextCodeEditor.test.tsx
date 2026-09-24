import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { TextCodeEditor } from './TextCodeEditor'

afterEach(() => {
  cleanup()
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
      expect(screen.getByText('name')).toHaveStyle({ color: '#d97706' })
      expect(screen.getByText('登录成功')).toHaveStyle({ color: '#16a34a' })
      expect(screen.getByText('true')).toHaveStyle({ color: '#16a34a' })
      expect(screen.getAllByText(':')[0]).toHaveStyle({ color: '#475569' })
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
      expect(within(editor).getByText('"name"')).toHaveStyle({ color: '#d97706' })
      expect(within(editor).getByText('"登录成功"')).toHaveStyle({ color: '#16a34a' })
      expect(within(editor).getByText('true')).toHaveStyle({ color: '#56b6c2' })
      expect(within(editor).getByText('1')).toHaveStyle({ color: '#d19a66' })
    })
  })
})
