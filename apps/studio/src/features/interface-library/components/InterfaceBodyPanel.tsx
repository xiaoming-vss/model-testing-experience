import { Empty } from 'antd'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import type { ApiInterface } from '../types'
import { BODY_TYPES } from '../utils/interfaceForm'
import { InterfaceFieldLabel } from './InterfaceFieldLabel'
import { InterfaceJsonEditorView } from './InterfaceJsonEditorView'
import { interfaceEditorCanvasClass } from './interfaceEditorLayout'

type Props = {
  draft: ApiInterface
  readOnly: boolean
  schemaText: string
  exampleText: string
  onSchemaText: (value: string) => void
  onExampleText: (value: string) => void
  onChange: (patch: Partial<ApiInterface>) => void
}

export function InterfaceBodyPanel({
  draft,
  readOnly,
  schemaText,
  exampleText,
  onSchemaText,
  onExampleText,
  onChange,
}: Props) {
  const isForm = draft.bodyType === 'form'

  return (
    <div className="if-body-panel flex h-full min-h-0 flex-col gap-3.5">
      <div className="if-body-type-row flex flex-none items-center gap-3">
        <InterfaceFieldLabel>请求体类型</InterfaceFieldLabel>
        <div className="if-pill-group inline-flex rounded-full border border-[var(--srf-card-border)] bg-[var(--srf-hover)] p-0.5">
          {BODY_TYPES.map(type => (
            <button
              key={type.value}
              type="button"
              className={`if-pill h-[26px] min-w-14 cursor-pointer rounded-full border-0 px-3 py-0 font-[inherit] text-[12px] ${draft.bodyType === type.value ? ' is-active bg-[var(--srf-card)] font-semibold text-[var(--srf-accent-strong)] shadow-[0_1px_2px_var(--srf-shadow-color)]' : ' bg-transparent text-[var(--srf-text-secondary)] hover:not-disabled:text-[var(--srf-text)]'} disabled:cursor-default`}
              disabled={readOnly}
              onClick={() => onChange({ bodyType: type.value })}
            >
              {type.label}
            </button>
          ))}
        </div>
      </div>

      {draft.bodyType === 'none' ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="该接口没有请求体"
          className="if-body-empty py-[34px]"
        />
      ) : null}

      {draft.bodyType === 'raw' ? (
        <div className="if-editor-block flex min-h-0 min-w-0 flex-1 flex-col gap-1.5">
          <div className="if-editor-block-head flex items-center justify-between gap-2 text-[11px] font-semibold text-[var(--srf-text-secondary)]">
            <span>{isForm ? '表单内容' : '原始内容'}</span>
            <span className="if-field-hint text-[11px] leading-[18px] text-[var(--srf-text-muted)]">按文本保存，不做 JSON 校验</span>
          </div>
          <div className={interfaceEditorCanvasClass}>
            <TextCodeEditor
              value={draft.bodyText}
              onChange={value => onChange({ bodyText: value })}
              readOnly={readOnly}
              ariaLabel="请求体原始内容"
              language="plain"
              height="100%"
              minHeight={0}
            />
          </div>
        </div>
      ) : null}

      {draft.bodyType === 'json' || draft.bodyType === 'form' ? (
        <InterfaceJsonEditorView
          schemaLabel={isForm ? '表单字段定义（JSON）' : '请求体 Schema（JSON）'}
          exampleLabel={isForm ? '表单示例（JSON）' : '请求体示例（JSON）'}
          schemaSwitchLabel={isForm ? '字段定义' : 'Schema'}
          schemaText={schemaText}
          exampleText={exampleText}
          readOnly={readOnly}
          onSchemaText={onSchemaText}
          onExampleText={onExampleText}
        />
      ) : null}
    </div>
  )
}
