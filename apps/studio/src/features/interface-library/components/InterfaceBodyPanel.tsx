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
    <div className="if-body-panel">
      <div className="if-body-type-row">
        <span className="if-field-label">请求体类型</span>
        <div className="if-pill-group">
          {BODY_TYPES.map(type => (
            <button
              key={type.value}
              type="button"
              className={`if-pill${draft.bodyType === type.value ? ' is-active' : ''}`}
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
          className="if-body-empty"
        />
      ) : null}

      {draft.bodyType === 'raw' ? (
        <div className="if-editor-block">
          <div className="if-editor-block-head">
            <span>{isForm ? '表单内容' : '原始内容'}</span>
            <span className="if-field-hint">按文本保存，不做 JSON 校验</span>
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
        <div className="if-body-editors">
          <div className="if-editor-block">
            <div className="if-editor-block-head">
              <span>{isForm ? '表单字段定义（JSON）' : '请求体 Schema（JSON）'}</span>
              <div className="if-editor-tools">
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
          <div className="if-editor-block">
            <div className="if-editor-block-head">
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
    <span className={`if-json-state${valid ? ' is-valid' : ' is-invalid'}`} title={error || undefined}>
      {valid ? 'JSON 有效' : 'JSON 格式错误'}
    </span>
  )
}
