import { createPortal } from 'react-dom'
import { CopyOutlined, DownloadOutlined } from '@ant-design/icons'
import CodeMirror from '@uiw/react-codemirror'
import { indentWithTab } from '@codemirror/commands'
import { json, jsonParseLinter } from '@codemirror/lang-json'
import { syntaxHighlighting } from '@codemirror/language'
import { linter } from '@codemirror/lint'
import { EditorView, keymap } from '@codemirror/view'
import { Button } from 'antd'
import { forwardRef, useImperativeHandle, useMemo, useRef, type ReactNode } from 'react'
import { message } from '@/shared/utils/feedback'
import { codeEditorTheme, jsonEditorHighlightStyle } from '../codeEditorTheme'

function tryFormatJson(value?: string) {
  if (!value?.trim()) {
    return { valid: true as const, formatted: '', compressed: '', errorMessage: '' }
  }

  try {
    const parsed = JSON.parse(value)
    return {
      valid: true as const,
      formatted: JSON.stringify(parsed, null, 2),
      compressed: JSON.stringify(parsed),
      errorMessage: '',
    }
  } catch (error) {
    return {
      valid: false as const,
      formatted: value,
      compressed: value,
      errorMessage: error instanceof Error ? error.message : 'JSON 格式不正确',
    }
  }
}

export type JsonEditorRef = {
  focus: () => void
  insertText: (text: string) => void
  formatDocument: () => void
  compressDocument: () => void
}

/** 光标位置按 1 基计数，与宿主状态栏「行 4, 列 18」的显示口径一致。 */
export type JsonEditorCursor = {
  line: number
  column: number
}

type JsonEditorProps = {
  value?: string
  onChange?: (value: string) => void
  minHeight?: number
  /** 自定义工具条；传 `null` 表示外壳不自带工具条，动作条由宿主画在编辑器之外。 */
  toolbar?: ReactNode
  /** 将编辑器操作并入宿主工具栏，默认仍显示在编辑器内部。 */
  toolbarContainer?: HTMLElement | null
  readOnly?: boolean
  foldable?: boolean
  ariaLabel?: string
  /** 下载按钮保存的文件名 */
  downloadFileName?: string
  /** 光标位置变化时回调，宿主用它渲染编辑器底部状态栏。 */
  onCursorChange?: (cursor: JsonEditorCursor) => void
}

export const JsonEditor = forwardRef<JsonEditorRef, JsonEditorProps>(({
  value,
  onChange,
  minHeight = 260,
  toolbar,
  toolbarContainer,
  readOnly = false,
  foldable = false,
  ariaLabel,
  downloadFileName = 'content.json',
  onCursorChange,
}, ref) => {
  const jsonState = useMemo(() => tryFormatJson(value), [value])
  const editorViewRef = useRef<EditorView | null>(null)
  const onCursorChangeRef = useRef(onCursorChange)
  onCursorChangeRef.current = onCursorChange

  /* 光标位置只回传行号与列号：宿主状态栏要显示「行 4, 列 18」，行内偏移量对它没有意义。 */
  const cursorListener = useMemo(
    () =>
      EditorView.updateListener.of((update) => {
        if (!update.selectionSet && !update.docChanged) return
        const head = update.state.selection.main.head
        const line = update.state.doc.lineAt(head)
        onCursorChangeRef.current?.({ line: line.number, column: head - line.from + 1 })
      }),
    [],
  )

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
    compressDocument() {
      if (readOnly) return
      if (!jsonState.valid || !value?.trim()) return
      if (jsonState.compressed !== value) {
        onChange?.(jsonState.compressed)
      }
      editorViewRef.current?.focus()
    },
  }), [jsonState.formatted, jsonState.compressed, jsonState.valid, onChange, readOnly, value])

  function handleBlur() {
    if (readOnly) return
    if (!jsonState.valid || !value?.trim()) return
    if (jsonState.formatted !== value) {
      onChange?.(jsonState.formatted)
    }
  }

  /* `toolbar` 传 null 表示编辑器外壳不自带工具条——宿主把动作条画在编辑器之外（如请求体面板）。 */
  const editorToolbar = toolbar === undefined ? (
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
  ) : toolbar === null ? null : (
    <div className="json-editor-toolbar">{toolbar}</div>
  )

  return (
    <div className={`json-editor-wrap${foldable ? ' foldable' : ''}${readOnly ? ' readonly' : ''}`}>
      <div className={`json-editor-shell${jsonState.valid ? '' : ' invalid'}`}>
        {toolbarContainer && editorToolbar ? createPortal(editorToolbar, toolbarContainer) : editorToolbar}
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
            cursorListener,
            ...(ariaLabel ? [EditorView.contentAttributes.of({ 'aria-label': ariaLabel })] : []),
            EditorView.lineWrapping,
            codeEditorTheme,
            syntaxHighlighting(jsonEditorHighlightStyle),
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
