import { CopyOutlined, DownloadOutlined } from '@ant-design/icons'
import CodeMirror from '@uiw/react-codemirror'
import { indentWithTab } from '@codemirror/commands'
import { json, jsonParseLinter } from '@codemirror/lang-json'
import { syntaxHighlighting } from '@codemirror/language'
import { linter } from '@codemirror/lint'
import { EditorView, keymap } from '@codemirror/view'
import { Button } from 'antd'
import { forwardRef, useImperativeHandle, useMemo, useRef, type ReactNode } from 'react'
import { useThemeStore } from '@/shared/store/theme.store'
import { message } from '@/shared/utils/feedback'
import {
  codeEditorDarkTheme,
  codeEditorLightTheme,
  jsonEditorDarkHighlightStyle,
  jsonEditorLightHighlightStyle,
} from '../codeEditorTheme'

function tryFormatJson(value?: string) {
  if (!value?.trim()) {
    return { valid: true as const, formatted: '', errorMessage: '' }
  }

  try {
    const parsed = JSON.parse(value)
    return {
      valid: true as const,
      formatted: JSON.stringify(parsed, null, 2),
      errorMessage: '',
    }
  } catch (error) {
    return {
      valid: false as const,
      formatted: value,
      errorMessage: error instanceof Error ? error.message : 'JSON 格式不正确',
    }
  }
}

export type JsonEditorRef = {
  focus: () => void
  insertText: (text: string) => void
  formatDocument: () => void
}

type JsonEditorProps = {
  value?: string
  onChange?: (value: string) => void
  minHeight?: number
  toolbar?: ReactNode
  readOnly?: boolean
  foldable?: boolean
  ariaLabel?: string
  /** 下载按钮保存的文件名 */
  downloadFileName?: string
}

export const JsonEditor = forwardRef<JsonEditorRef, JsonEditorProps>(({
  value,
  onChange,
  minHeight = 260,
  toolbar,
  readOnly = false,
  foldable = false,
  ariaLabel,
  downloadFileName = 'content.json',
}, ref) => {
  const jsonState = useMemo(() => tryFormatJson(value), [value])
  const themeMode = useThemeStore((state) => state.mode)
  const editorViewRef = useRef<EditorView | null>(null)
  const editorTheme = themeMode === 'dark' ? codeEditorDarkTheme : codeEditorLightTheme
  const editorHighlightStyle = themeMode === 'dark' ? jsonEditorDarkHighlightStyle : jsonEditorLightHighlightStyle

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value ?? '')
      message.success('已复制内容')
    } catch {
      message.error('复制失败，请手动复制')
    }
  }

  function handleDownload() {
    const blob = new Blob([value ?? ''], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = downloadFileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    message.success('已下载内容')
  }

  useImperativeHandle(ref, () => ({
    focus() {
      editorViewRef.current?.focus()
    },
    insertText(text: string) {
      const view = editorViewRef.current
      if (!view) return

      const selection = view.state.selection.main
      const anchor = selection.from + text.length
      view.dispatch({
        changes: {
          from: selection.from,
          to: selection.to,
          insert: text,
        },
        selection: { anchor, head: anchor },
      })
      view.focus()
    },
    formatDocument() {
      if (readOnly) return
      if (!jsonState.valid || !value?.trim()) return
      if (jsonState.formatted !== value) {
        onChange?.(jsonState.formatted)
      }
      editorViewRef.current?.focus()
    },
  }), [jsonState.formatted, jsonState.valid, onChange, readOnly, value])

  function handleBlur() {
    if (readOnly) return
    if (!jsonState.valid || !value?.trim()) return
    if (jsonState.formatted !== value) {
      onChange?.(jsonState.formatted)
    }
  }

  return (
    <div className={`json-editor-wrap${foldable ? ' foldable' : ''}${readOnly ? ' readonly' : ''}`}>
      <div className={`json-editor-shell${jsonState.valid ? '' : ' invalid'}`}>
        {toolbar ? (
          <div className="json-editor-toolbar">{toolbar}</div>
        ) : (
          <div className="json-editor-toolbar">
            <div className="json-editor-toolbar-actions">
              <Button
                className="json-editor-toolbar-btn"
                icon={<CopyOutlined />}
                onClick={handleCopy}
                disabled={!value?.trim()}
              >
                复制
              </Button>
              <Button
                className="json-editor-toolbar-btn"
                icon={<DownloadOutlined />}
                onClick={handleDownload}
                disabled={!value?.trim()}
              >
                下载
              </Button>
            </div>
          </div>
        )}
        <CodeMirror
          value={value ?? ''}
          minHeight={`${minHeight}px`}
          editable={!readOnly}
          readOnly={readOnly}
          basicSetup={{
            foldGutter: foldable,
            highlightActiveLine: false,
            highlightActiveLineGutter: false,
          }}
          extensions={[
            json(),
            linter(jsonParseLinter()),
            keymap.of([indentWithTab]),
            ...(ariaLabel ? [EditorView.contentAttributes.of({ 'aria-label': ariaLabel })] : []),
            EditorView.lineWrapping,
            editorTheme,
            syntaxHighlighting(editorHighlightStyle),
          ]}
          className="json-editor-codemirror"
          onCreateEditor={(view) => {
            editorViewRef.current = view
          }}
          onChange={(nextValue) => {
            if (!readOnly) onChange?.(nextValue)
          }}
          onBlur={handleBlur}
        />
      </div>
    </div>
  )
})

JsonEditor.displayName = 'JsonEditor'
