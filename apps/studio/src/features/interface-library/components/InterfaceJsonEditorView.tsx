import {
  CopyOutlined,
  FormatPainterOutlined,
} from '@ant-design/icons'
import { Button } from 'antd'
import { useState } from 'react'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { message } from '@/shared/utils/feedback'
import { jsonText, parseJsonText } from '../utils/interfaceForm'
import { interfaceEditorCanvasClass } from './interfaceEditorLayout'

type EditorView = 'schema' | 'example'

type Props = {
  schemaLabel: string
  exampleLabel: string
  schemaSwitchLabel: string
  schemaText: string
  exampleText: string
  readOnly: boolean
  onSchemaText: (value: string) => void
  onExampleText: (value: string) => void
}

const viewButtonBaseClass = 'h-6 rounded-[5px] border-0 px-2.5 text-[11px]'
const viewButtonActiveClass = `${viewButtonBaseClass} bg-[var(--srf-card)] font-semibold text-[var(--srf-accent-strong)] shadow-[0_1px_2px_var(--srf-shadow-color)]`
const viewButtonIdleClass = `${viewButtonBaseClass} bg-transparent text-[var(--srf-text-secondary)] hover:text-[var(--srf-text)]`

function jsonStateClass(valid: boolean) {
  return `if-json-state inline-flex items-center gap-1 whitespace-nowrap rounded-full px-1.5 text-[10px] leading-[17px] before:h-[5px] before:w-[5px] before:rounded-full before:bg-current before:content-[''] ${valid ? ' is-valid bg-[color-mix(in_srgb,var(--srf-result-passed)_10%,var(--srf-card))] text-[var(--srf-result-passed)]' : ' is-invalid bg-[color-mix(in_srgb,var(--srf-result-failed)_10%,var(--srf-card))] text-[var(--srf-result-failed)]'}`
}

function JsonState({ valid, error }: { valid: boolean; error: string }) {
  return (
    <span className={jsonStateClass(valid)} title={error || undefined}>
      {valid ? 'JSON 有效' : 'JSON 格式错误'}
    </span>
  )
}

/**
 * 单个编辑画布：Schema / 示例通过分段切换，始终撑满剩余空间。
 * 请求体和响应共用这一套结构。
 */
export function InterfaceJsonEditorView({
  schemaLabel,
  exampleLabel,
  schemaSwitchLabel,
  schemaText,
  exampleText,
  readOnly,
  onSchemaText,
  onExampleText,
}: Props) {
  const [view, setView] = useState<EditorView>('schema')
  const isSchema = view === 'schema'
  const currentText = isSchema ? schemaText : exampleText
  const currentState = parseJsonText(currentText)
  const currentLabel = isSchema ? schemaLabel : exampleLabel
  const lineCount = currentText.split('\n').length

  function updateCurrentText(value: string) {
    if (isSchema) onSchemaText(value)
    else onExampleText(value)
  }

  function formatCurrentText() {
    if (!currentState.valid) return
    updateCurrentText(jsonText(currentState.value))
  }

  async function copyCurrentText() {
    try {
      await navigator.clipboard.writeText(currentText)
      message.success('已复制')
    } catch {
      message.error('复制失败，请手动选择')
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-none flex-wrap items-center gap-2 border-y border-[var(--srf-card-border)] py-1.5 text-[10px]">
        <div
          className="inline-flex rounded-[7px] border border-[var(--srf-card-border)] bg-[var(--srf-hover)] p-0.5"
          role="group"
          aria-label="编辑视图"
        >
          <button
            type="button"
            className={isSchema ? viewButtonActiveClass : viewButtonIdleClass}
            aria-pressed={isSchema}
            onClick={() => setView('schema')}
          >
            {schemaSwitchLabel}
          </button>
          <button
            type="button"
            className={isSchema ? viewButtonIdleClass : viewButtonActiveClass}
            aria-pressed={!isSchema}
            onClick={() => setView('example')}
          >
            示例
          </button>
        </div>
        <span className="text-[var(--srf-text-muted)]">{lineCount} 行</span>
        <div className="ml-auto flex flex-wrap items-center justify-end gap-1">
          <JsonState valid={currentState.valid} error={currentState.valid ? '' : currentState.error} />
          {readOnly ? null : (
            <Button
              type="text"
              size="small"
              icon={<FormatPainterOutlined />}
              disabled={!currentState.valid || !currentText.trim()}
              onClick={formatCurrentText}
            >
              格式化
            </Button>
          )}
          <Button type="text" size="small" icon={<CopyOutlined />} onClick={() => void copyCurrentText()}>
            复制
          </Button>
        </div>
      </div>
      <div className={interfaceEditorCanvasClass}>
        <TextCodeEditor
          value={currentText}
          onChange={updateCurrentText}
          readOnly={readOnly}
          ariaLabel={currentLabel}
          language="json"
          height="100%"
          minHeight={0}
        />
      </div>
      <div className="flex h-7 flex-none items-center gap-3 border-t border-[var(--srf-card-border)] text-[10px] text-[var(--srf-text-muted)]">
        <span>JSON</span>
        <span>{isSchema ? '结构定义' : '调用示例'}</span>
        <span className="ml-auto">UTF-8</span>
        <span>空格 2</span>
      </div>
    </div>
  )
}
