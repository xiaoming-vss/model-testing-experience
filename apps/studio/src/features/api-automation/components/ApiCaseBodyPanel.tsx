import { bodyTypeOptions } from '@/features/api-automation/config/collectionConfig'
import type { TemplatesProps } from '@/features/api-automation/components/apiCaseEditorProps'
import { Text, validateJsonText } from '@/features/api-automation/utils/detailView'
import type { ApiCaseFormValues } from '@/features/api-automation/utils/apiCaseEditor'
import { JsonEditor, type JsonEditorCursor } from '@/shared/components/JsonEditor/JsonEditor'
import { message } from '@/shared/utils/feedback'
import { CheckCircleFilled, CodeOutlined, CompressOutlined, FormatPainterOutlined, WarningFilled } from '@ant-design/icons'
import { Card, Form, Input } from 'antd'
import { useState } from 'react'

import type { ApiCase } from '@/services/api'

type Props = {
  bodyType: NonNullable<ApiCase['bodyType']>
  templates: TemplatesProps
}

/** 与 `.json-editor-codemirror` 的格式化缩进一致，状态条上的「空格」照着它显示。 */
const INDENT_WIDTH = 2

function isJsonTextValid(value?: string) {
  if (!value?.trim()) return true
  try {
    JSON.parse(value)
    return true
  } catch {
    return false
  }
}

function formatByteSize(bytes: number) {
  return bytes >= 1024 ? `${(bytes / 1024).toFixed(2)} KB` : `${bytes} B`
}

/**
 * 请求体面板：类型胶囊条 + 编辑器动作条 + 编辑器 + 底部状态条。
 * 设计稿的状态条同时承担语法结论与光标位置，所以光标位置由编辑器回传。
 */
export function ApiCaseBodyPanel({ bodyType, templates }: Props) {
  const { renderEnvVarPicker, insertTemplateTextIntoJson, handleFormatBodyJson, handleCompressBodyJson, bodyJsonEditorRef } = templates
  const caseForm = Form.useFormInstance<ApiCaseFormValues>()
  const watchedBodyJson = Form.useWatch('bodyJson', caseForm)
  const bodyJson = watchedBodyJson ?? String(caseForm.getFieldValue('bodyJson') ?? '')
  const [cursor, setCursor] = useState<JsonEditorCursor>({ line: 1, column: 1 })

  const jsonValid = isJsonTextValid(bodyJson)
  const sizeText = formatByteSize(new TextEncoder().encode(bodyJson).length)

  function guardJsonAction(action: () => void, actionLabel: string) {
    if (!jsonValid) {
      message.warning(`${actionLabel}已跳过：当前请求体不是合法 JSON`)
      return
    }
    action()
  }

  return (
    <div className="api-wb-body-panel">
      <div className="api-wb-body-bar">
        <div className="api-wb-body-types" role="tablist" aria-label="请求体类型">
          {bodyTypeOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              role="tab"
              aria-selected={option.value === bodyType}
              className={`api-wb-body-type${option.value === bodyType ? ' active' : ''}`}
              onClick={() => caseForm.setFieldValue('bodyType', option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div className="api-wb-body-actions">
          <button
            type="button"
            className="api-wb-body-action"
            disabled={bodyType !== 'json'}
            onClick={() => guardJsonAction(handleFormatBodyJson, '格式化')}
          >
            <FormatPainterOutlined />
            格式化代码
          </button>
          <button
            type="button"
            className="api-wb-body-action"
            disabled={bodyType !== 'json'}
            onClick={() => guardJsonAction(handleCompressBodyJson, '压缩')}
          >
            <CompressOutlined />
            压缩
          </button>
          {bodyType === 'json'
            ? renderEnvVarPicker({
              pickerKey: 'bodyJson',
              placement: 'bottomLeft',
              onInsert: insertTemplateTextIntoJson,
              trigger: (
                <button type="button" className="api-wb-body-action is-accent">
                  <CodeOutlined />
                  插入变量 {'{{var}}'}
                </button>
              ),
            })
            : null}
          <span className="api-wb-body-action-divider" aria-hidden="true" />
          {bodyType === 'json' ? (
            <span className={`api-wb-body-validity tone-${jsonValid ? 'green' : 'red'}`}>
              {jsonValid ? <CheckCircleFilled /> : <WarningFilled />}
              {jsonValid ? 'JSON Schema 合法' : 'JSON 语法错误'}
            </span>
          ) : null}
        </div>
      </div>

      <Form.Item name="bodyType" hidden>
        <Input />
      </Form.Item>

      {bodyType === 'json' ? (
        <Form.Item
          name="bodyJson"
          className="api-body-editor-form-item"
          validateTrigger={['onChange', 'onBlur']}
          rules={[
            {
              validator: async (_, value) => validateJsonText(value),
            },
          ]}
        >
          <JsonEditor
            ref={bodyJsonEditorRef}
            minHeight={260}
            ariaLabel="请求体 JSON"
            toolbar={null}
            onCursorChange={setCursor}
          />
        </Form.Item>
      ) : null}

      {bodyType === 'raw' ? (
        <Form.Item name="bodyText" label="Body 内容" className="api-body-editor-form-item">
          <Input.TextArea rows={8} placeholder="原始请求体内容" />
        </Form.Item>
      ) : null}

      {bodyType === 'form' ? (
        <Card size="small" className="api-body-placeholder-card">
          <Text type="secondary">`x-www-form-urlencoded` 类型的键值表单下一步再补，这一版先保留类型切换。</Text>
        </Card>
      ) : null}

      {bodyType === 'none' ? (
        <Card size="small" className="api-body-placeholder-card">
          <Text type="secondary">当前选择 `none`，无需填写请求体。</Text>
        </Card>
      ) : null}

      <div className="api-wb-body-status">
        <div className="api-wb-body-status-main">
          {bodyType === 'json' ? (
            jsonValid ? (
              <span className="tone-green">
                <CheckCircleFilled />
                无语法错误
              </span>
            ) : (
              <span className="tone-red">
                <WarningFilled />
                存在语法错误
              </span>
            )
          ) : (
            <span className="is-muted">无需校验</span>
          )}
          <span className="is-muted">大小: {sizeText}</span>
          <span className="is-muted">格式: {bodyType === 'json' ? 'JSON' : '文本'}</span>
          <span className="is-muted">编码: UTF-8</span>
        </div>
        <div className="api-wb-body-status-side">
          {bodyType === 'json' ? (
            <span>行 {cursor.line}, 列 {cursor.column} (光标聚焦)</span>
          ) : null}
          <span className="is-muted">空格: {INDENT_WIDTH}</span>
        </div>
      </div>
    </div>
  )
}
