import { InterfaceFieldLabel } from './InterfaceFieldLabel'
import { FormatPainterOutlined } from '@ant-design/icons'
import { Button, Empty } from 'antd'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import type { ApiInterface } from '../types'
import { BODY_TYPES, jsonText, parseJsonText } from '../utils/interfaceForm'

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
  const schemaState = parseJsonText(schemaText)
  const exampleState = parseJsonText(exampleText)
  const isForm = draft.bodyType === 'form'

  function format(text: string, update: (value: string) => void) {
    const parsed = parseJsonText(text)
    if (!parsed.valid) return
    update(jsonText(parsed.value))
  }

  return (
    <div className="if-body-panel flex flex-col gap-3.5">
      <div className="if-body-type-row flex items-center gap-3">
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
        <div className="if-editor-block flex min-w-0 flex-col gap-1.5">
          <div className="if-editor-block-head flex items-center justify-between gap-2 text-[11px] font-semibold text-[var(--srf-text-secondary)]">
            <span>{isForm ? '表单内容' : '原始内容'}</span>
            <span className="if-field-hint text-[11px] leading-[18px] text-[var(--srf-text-muted)]">按文本保存，不做 JSON 校验</span>
          </div>
          <TextCodeEditor
            value={draft.bodyText}
            onChange={value => onChange({ bodyText: value })}
            readOnly={readOnly}
            ariaLabel="请求体原始内容"
            language="plain"
            height={240}
          />
        </div>
      ) : null}

      {draft.bodyType === 'json' || draft.bodyType === 'form' ? (
        <div className="if-body-editors grid grid-cols-2 gap-3.5 max-[960.01px]:grid-cols-1">
          <div className="if-editor-block flex min-w-0 flex-col gap-1.5">
            <div className="if-editor-block-head flex items-center justify-between gap-2 text-[11px] font-semibold text-[var(--srf-text-secondary)]">
              <span>{isForm ? '表单字段定义（JSON）' : '请求体 Schema（JSON）'}</span>
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
              ariaLabel={isForm ? '表单字段定义 JSON' : '请求体 Schema JSON'}
              language="json"
              height={220}
            />
          </div>
          <div className="if-editor-block flex min-w-0 flex-col gap-1.5">
            <div className="if-editor-block-head flex items-center justify-between gap-2 text-[11px] font-semibold text-[var(--srf-text-secondary)]">
              <span>{isForm ? '表单示例（JSON）' : '请求体示例（JSON）'}</span>
              <JsonState valid={exampleState.valid} error={exampleState.valid ? '' : exampleState.error} />
            </div>
            <TextCodeEditor
              value={exampleText}
              onChange={onExampleText}
              readOnly={readOnly}
              ariaLabel={isForm ? '表单示例 JSON' : '请求体示例 JSON'}
              language="json"
              height={220}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}

export function JsonState({ valid, error }: { valid: boolean; error: string }) {
  return (
    <span className={`if-json-state inline-flex items-center gap-1 whitespace-nowrap rounded-full px-1.5 text-[10px] leading-[17px] before:h-[5px] before:w-[5px] before:rounded-full before:bg-current before:content-[''] ${valid ? ' is-valid bg-[color-mix(in_srgb,var(--srf-result-passed)_10%,var(--srf-card))] text-[var(--srf-result-passed)]' : ' is-invalid bg-[color-mix(in_srgb,var(--srf-result-failed)_10%,var(--srf-card))] text-[var(--srf-result-failed)]'}`} title={error || undefined}>
      {valid ? 'JSON 有效' : 'JSON 格式错误'}
    </span>
  )
}
