import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { useThemeStore } from '@/shared/store/theme.store'
import { TextCodeEditor } from './TextCodeEditor'

afterEach(() => {
  cleanup()
  useThemeStore.getState().setMode('light')
})

describe('TextCodeEditor', () => {
  it('highlights YAML candidate fields in dark mode', async () => {
    useThemeStore.getState().setMode('dark')
    render(
      <TextCodeEditor
        value={'name: 登录成功\nenabled: true\norderNo: 1'}
        language="yaml"
        ariaLabel="候选结果 YAML"
      />,
    )

    expect(screen.getByRole('textbox', { name: '候选结果 YAML' })).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('name')).toHaveStyle({ color: '#f59e0b' })
      expect(screen.getByText('登录成功')).toHaveStyle({ color: '#4ade80' })
      expect(screen.getByText('true')).toHaveStyle({ color: '#4ade80' })
      expect(screen.getAllByText(':')[0]).toHaveStyle({ color: '#9fb7d6' })
    })
  })

  it('highlights JSON fields and values with the shared dark theme', async () => {
    useThemeStore.getState().setMode('dark')
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
      expect(within(editor).getByText('"name"')).toHaveStyle({ color: '#f59e0b' })
      expect(within(editor).getByText('"登录成功"')).toHaveStyle({ color: '#4ade80' })
      expect(within(editor).getByText('true')).toHaveStyle({ color: '#67e8f9' })
      expect(within(editor).getByText('1')).toHaveStyle({ color: '#f7b267' })
    })
  })
})
