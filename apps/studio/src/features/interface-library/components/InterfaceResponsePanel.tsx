import { InterfaceFieldLabel } from './InterfaceFieldLabel'
import { FormatPainterOutlined } from '@ant-design/icons'
import { Button, Input, InputNumber } from 'antd'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import type { ApiInterface } from '../types'
import { jsonText, parseJsonText } from '../utils/interfaceForm'
import { JsonState } from './InterfaceBodyPanel'

type Props = {
  draft: ApiInterface
  readOnly: boolean
  schemaText: string
  exampleText: string
  onSchemaText: (value: string) => void
  onExampleText: (value: string) => void
  onChange: (patch: Partial<ApiInterface>) => void
}

export function InterfaceResponsePanel({
  draft,
  readOnly,
  schemaText,
  exampleText,
  onSchemaText,
  onExampleText,
  onChange,
}: Props) {
  const schemaState = parseJsonText(schemaText)
  const exampleState = parseJsonText(exampleText)

  function format(text: string, update: (value: string) => void) {
    const parsed = parseJsonText(text)
    if (!parsed.valid) return
    update(jsonText(parsed.value))
  }

  return (
    <div className="if-response-panel flex flex-col gap-3.5">
      <div className="if-response-meta flex flex-wrap items-end gap-3">
        <label className="flex w-[130px] flex-col gap-[5px] max-[760.01px]:w-[110px]">
          <InterfaceFieldLabel>状态码</InterfaceFieldLabel>
          <InputNumber
            className="w-full"
            min={100}
            max={599}
            value={draft.responseStatus}
            disabled={readOnly}
            aria-label="默认成功响应状态码"
            onChange={value => onChange({ responseStatus: value ?? 200 })}
          />
        </label>
        <label className="if-response-desc flex flex-[1_1_260px] w-auto flex-col gap-[5px]">
          <InterfaceFieldLabel>响应说明</InterfaceFieldLabel>
          <Input
            value={draft.responseDescription}
            disabled={readOnly}
            maxLength={512}
            placeholder="例如：查询成功"
            aria-label="默认成功响应说明"
            onChange={event => onChange({ responseDescription: event.target.value })}
          />
        </label>
      </div>
      <div className="if-field-hint if-response-hint -mt-1.5 text-[11px] leading-[18px] text-[var(--srf-text-muted)]">
        每个接口只保留一个默认成功响应，作为后续生成用例的响应输入。
      </div>
      <div className="if-body-editors grid grid-cols-2 gap-3.5 max-[960.01px]:grid-cols-1">
        <div className="if-editor-block flex min-w-0 flex-col gap-1.5">
          <div className="if-editor-block-head flex items-center justify-between gap-2 text-[11px] font-semibold text-[var(--srf-text-secondary)]">
            <span>响应 Schema（JSON）</span>
            <div className="if-editor-tools inline-flex items-center gap-1">
              <JsonState valid={schemaState.valid} error={schemaState.valid ? '' : schemaState.error} />
              {readOnly ? null : (
                <Button
                  type="text"
                  size="small"
                  icon={<FormatPainterOutlined />}
                  disabled={!schemaState.valid || !schemaText.trim()}
                  onClick={() => format(schemaText, onSchemaText)}
                >
                  格式化
                </Button>
              )}
            </div>
          </div>
          <TextCodeEditor
            value={schemaText}
            onChange={onSchemaText}
            readOnly={readOnly}
            ariaLabel="响应 Schema JSON"
            language="json"
            height={240}
          />
        </div>
        <div className="if-editor-block flex min-w-0 flex-col gap-1.5">
          <div className="if-editor-block-head flex items-center justify-between gap-2 text-[11px] font-semibold text-[var(--srf-text-secondary)]">
            <span>响应示例（JSON）</span>
            <JsonState valid={exampleState.valid} error={exampleState.valid ? '' : exampleState.error} />
          </div>
          <TextCodeEditor
            value={exampleText}
            onChange={onExampleText}
            readOnly={readOnly}
            ariaLabel="响应示例 JSON"
            language="json"
            height={240}
          />
        </div>
      </div>
    </div>
  )
}
