import { Input, InputNumber } from 'antd'
import type { ApiInterface } from '../types'
import { InterfaceFieldLabel } from './InterfaceFieldLabel'
import { InterfaceJsonEditorView } from './InterfaceJsonEditorView'

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
  return (
    <div className="if-response-panel flex h-full min-h-0 flex-col gap-3.5">
      <div className="if-response-meta flex flex-none flex-wrap items-end gap-3">
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
      <div className="if-field-hint if-response-hint -mt-1.5 flex-none text-[11px] leading-[18px] text-[var(--srf-text-muted)]">
        每个接口只保留一个默认成功响应，作为后续生成用例的响应输入。
      </div>
      <InterfaceJsonEditorView
        schemaLabel="响应 Schema（JSON）"
        exampleLabel="响应示例（JSON）"
        schemaSwitchLabel="Schema"
        schemaText={schemaText}
        exampleText={exampleText}
        readOnly={readOnly}
        onSchemaText={onSchemaText}
        onExampleText={onExampleText}
      />
    </div>
  )
}
