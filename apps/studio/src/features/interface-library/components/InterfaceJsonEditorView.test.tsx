import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { InterfaceJsonEditorView } from './InterfaceJsonEditorView'

afterEach(cleanup)

const schemaText = '{\n  "type": "object"\n}'
const exampleText = '{\n  "id": "A001"\n}'

function renderView(overrides: Partial<Parameters<typeof InterfaceJsonEditorView>[0]> = {}) {
  const onSchemaText = vi.fn()
  const onExampleText = vi.fn()
  const view = render(
    <InterfaceJsonEditorView
      schemaLabel="请求体 Schema（JSON）"
      exampleLabel="请求体示例（JSON）"
      schemaSwitchLabel="Schema"
      schemaText={schemaText}
      exampleText={exampleText}
      readOnly={false}
      onSchemaText={onSchemaText}
      onExampleText={onExampleText}
      {...overrides}
    />,
  )
  return { ...view, onSchemaText, onExampleText }
}

function editorRoot() {
  const root = screen.getByRole('textbox').closest('.if-editor-canvas')?.parentElement
  if (!(root instanceof HTMLElement)) throw new Error('editor root not found')
  return root
}

describe('InterfaceJsonEditorView', () => {
  it('switches the single canvas between schema and example', () => {
    renderView()

    expect(screen.getAllByRole('textbox')).toHaveLength(1)
    expect(screen.getByRole('textbox', { name: '请求体 Schema（JSON）' })).toBeInTheDocument()
    expect(editorRoot().className).toContain('flex-1')
    expect(editorRoot().style.height).toBe('')
    expect(screen.queryByRole('button', { name: /适应内容|撑满/ })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '示例' }))

    expect(screen.getAllByRole('textbox')).toHaveLength(1)
    expect(screen.getByRole('textbox', { name: '请求体示例（JSON）' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '示例' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Schema' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText('3 行')).toBeInTheDocument()
  })

  it('reports invalid JSON and disables formatting', () => {
    renderView({ schemaText: '{' })

    expect(screen.getByText('JSON 格式错误')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /格式化/ })).toBeDisabled()
  })

  it('keeps copy but drops formatting when read-only', () => {
    renderView({ readOnly: true })

    expect(screen.queryByRole('button', { name: /格式化/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /复制/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /适应内容|撑满/ })).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: '请求体 Schema（JSON）' })).toHaveAttribute('aria-readonly', 'true')
  })
})
