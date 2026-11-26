import { RequestJsonValidity } from '@/shared/components/request-editor/RequestJsonValidity'
import requestStyles from '@/shared/components/request-editor/request-editor.module.css'
import { RequestBodyStatus } from '@/shared/components/request-editor/RequestBodyStatus'
import { RequestBodyToolbar, requestBodyVariableClass } from '@/shared/components/request-editor/RequestBodyToolbar'
import { bodyTypeOptions } from '@/features/api-automation/config/collectionConfig'
import type { TemplatesProps } from '@/features/api-automation/components/apiCaseEditorProps'
import { validateJsonText } from '@/features/api-automation/utils/detailView'
import type { ApiCaseFormValues } from '@/features/api-automation/utils/apiCaseEditor'
import { JsonEditor, type JsonEditorCursor } from '@/shared/components/JsonEditor/JsonEditor'
import { FormBodyEditor } from './FormBodyEditor'
import { isJsonText as isJsonTextValid } from '@/shared/utils/value'
import {
  KV_EMPTY_CLASS,
  KV_EMPTY_HINT_CLASS,
  KV_EMPTY_ICON_CLASS,
  KV_EMPTY_TEXT_CLASS,
  KV_EMPTY_TITLE_CLASS,
  KV_SECTION_HINT_CLASS,
} from '@/shared/ui/keyValueTable'
import { message } from '@/shared/utils/feedback'
import { ApiOutlined, CodeOutlined } from '@ant-design/icons'
import { Form, Input } from 'antd'
import { useEffect, useMemo, useState } from 'react'

import type { ApiCase } from '@/services/api'

type Props = {
  bodyType: NonNullable<ApiCase['bodyType']>
  templates: TemplatesProps
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
  // 语法结论和字节数只用于状态条：停止输入后再算，避免大请求体每敲一个字都 JSON.parse + 编码。
  const [stableBodyJson, setStableBodyJson] = useState(bodyJson)
  useEffect(() => {
    const timer = window.setTimeout(() => setStableBodyJson(bodyJson), 150)
    return () => window.clearTimeout(timer)
  }, [bodyJson])
  const jsonValid = useMemo(() => isJsonTextValid(stableBodyJson), [stableBodyJson])

  function guardJsonAction(action: () => void, actionLabel: string) {
    // 动作用当前文本重新校验，不依赖防抖后的状态。
    if (!isJsonTextValid(bodyJson)) {
      message.warning(`${actionLabel}已跳过：当前请求体不是合法 JSON`)
      return
    }
    action()
  }

  return (
    <div className={`${requestStyles.body} -mx-4 flex min-w-0 flex-col`} data-tab-motion-scope>
      <div className="api-wb-body-head px-4 pb-2 pt-1">
        <div className="text-[12px] font-semibold leading-[18px] text-[var(--srf-text)]">请求体</div>
        <p className={KV_SECTION_HINT_CLASS}>
          请求体随用例保存，支持 {'{{变量}}'} 模板和 JSON 语法校验。
        </p>
      </div>
      <RequestBodyToolbar options={bodyTypeOptions} value={bodyType} onChange={value => caseForm.setFieldValue('bodyType', value)}
        json={bodyType === 'json'} onFormat={() => guardJsonAction(handleFormatBodyJson, '格式化')}
        onCompress={() => guardJsonAction(handleCompressBodyJson, '压缩')}
        variableControl={bodyType === 'json' ? renderEnvVarPicker({
          pickerKey: 'bodyJson', placement: 'bottomLeft', onInsert: insertTemplateTextIntoJson,
          trigger: <button type="button" className={requestBodyVariableClass}><CodeOutlined />插入变量 {'{{var}}'}</button>,
        }) : null}
        validity={bodyType === 'json' ? <RequestJsonValidity valid={jsonValid} /> : null} />

      <Form.Item name="bodyType" hidden>
        <Input />
      </Form.Item>

      <div data-tab-motion-panel>
      {bodyType === 'json' ? (
        <Form.Item
          name="bodyJson"
          className="api-body-editor-form-item"
          style={{ marginBottom: 0 }}
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
        <Form.Item name="bodyText" label="Body 内容" className="api-body-editor-form-item" style={{ marginBottom: 0 }}>
          <Input.TextArea rows={8} placeholder="原始请求体内容" />
        </Form.Item>
      ) : null}

      {bodyType === 'form' ? (
        <Form.Item
          name="bodyJson"
          className="api-body-editor-form-item"
          style={{ marginBottom: 0 }}
          validateTrigger={['onChange', 'onBlur']}
          rules={[{
            validator: async (_, value) => {
              if (!value?.trim()) return
              let parsed: unknown
              try {
                parsed = JSON.parse(value)
              } catch {
                throw new Error('表单请求体必须是合法 JSON 对象')
              }
              if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
                throw new Error('表单请求体必须是 JSON 对象')
              }
            },
          }]}
        >
          <FormBodyEditor />
        </Form.Item>
      ) : null}

      {bodyType === 'none' ? (
        <div className={`mx-4 my-3 ${KV_EMPTY_CLASS}`}>
          <ApiOutlined className={KV_EMPTY_ICON_CLASS} aria-hidden />
          <div className={KV_EMPTY_TEXT_CLASS}>
            <strong className={KV_EMPTY_TITLE_CLASS}>当前请求没有请求体</strong>
            <span className={KV_EMPTY_HINT_CLASS}>切换到 JSON 或 raw 即可编辑请求体内容。</span>
          </div>
        </div>
      ) : null}

      </div>
      <RequestBodyStatus json={bodyType === 'json'} valid={jsonValid} value={stableBodyJson}
        cursor={<span className="font-mono">行 {cursor.line}, 列 {cursor.column} (光标聚焦)</span>} />
    </div>
  )
}
