import { bodyTypeOptions } from '@/features/api-automation/config/collectionConfig'
import type { TemplatesProps } from '@/features/api-automation/components/apiCaseEditorProps'
import { Text, validateJsonText } from '@/features/api-automation/utils/detailView'
import type { ApiCaseFormValues } from '@/features/api-automation/utils/apiCaseEditor'
import { JsonEditor, type JsonEditorCursor } from '@/shared/components/JsonEditor/JsonEditor'
import { message } from '@/shared/utils/feedback'
import { CheckCircleFilled, CodeOutlined, CompressOutlined, FormatPainterOutlined, WarningFilled } from '@ant-design/icons'
import { Card, Form, Input } from 'antd'
import { useEffect, useMemo, useState } from 'react'

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
  // 语法结论和字节数只用于状态条：停止输入后再算，避免大请求体每敲一个字都 JSON.parse + 编码。
  const [stableBodyJson, setStableBodyJson] = useState(bodyJson)
  useEffect(() => {
    const timer = window.setTimeout(() => setStableBodyJson(bodyJson), 150)
    return () => window.clearTimeout(timer)
  }, [bodyJson])
  const jsonValid = useMemo(() => isJsonTextValid(stableBodyJson), [stableBodyJson])
  const sizeText = useMemo(() => formatByteSize(new TextEncoder().encode(stableBodyJson).length), [stableBodyJson])

  function guardJsonAction(action: () => void, actionLabel: string) {
    // 动作用当前文本重新校验，不依赖防抖后的状态。
    if (!isJsonTextValid(bodyJson)) {
      message.warning(`${actionLabel}已跳过：当前请求体不是合法 JSON`)
      return
    }
    action()
  }

  return (
    <div className="api-wb-body-panel -mx-4 flex min-w-0 flex-col" data-tab-motion-scope>
      <div className="api-wb-body-bar flex flex-wrap items-center justify-between gap-2 border-b border-[var(--srf-card-border)] bg-[var(--srf-hover)] px-4 py-1">
        <div className="api-wb-body-types flex flex-wrap items-center gap-1" role="tablist" data-tab-motion-scoped aria-label="请求体类型">
          {bodyTypeOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              role="tab"
              aria-selected={option.value === bodyType}
              className={`api-wb-body-type cursor-pointer rounded-[4px] border-0 px-2 py-1 text-[12px] leading-4 transition-colors hover:text-[var(--srf-text)]${option.value === bodyType ? ' active bg-[var(--srf-card)] font-semibold text-[var(--srf-accent)]' : ' bg-transparent text-[var(--srf-text-secondary)]'}`}
              onClick={() => caseForm.setFieldValue('bodyType', option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div className="api-wb-body-actions flex flex-wrap items-center gap-1">
          <button
            type="button"
            className="api-wb-body-action inline-flex cursor-pointer items-center gap-1 rounded-[4px] border-0 bg-[var(--srf-chip)] px-2 py-1 text-[12px] leading-4 text-[var(--srf-text)] transition-colors hover:bg-[var(--srf-accent-soft)] disabled:cursor-not-allowed disabled:opacity-45 [&_.anticon]:text-[var(--srf-text-muted)]"
            disabled={bodyType !== 'json'}
            onClick={() => guardJsonAction(handleFormatBodyJson, '格式化')}
          >
            <FormatPainterOutlined />
            格式化代码
          </button>
          <button
            type="button"
            className="api-wb-body-action inline-flex cursor-pointer items-center gap-1 rounded-[4px] border-0 bg-[var(--srf-chip)] px-2 py-1 text-[12px] leading-4 text-[var(--srf-text)] transition-colors hover:bg-[var(--srf-accent-soft)] disabled:cursor-not-allowed disabled:opacity-45 [&_.anticon]:text-[var(--srf-text-muted)]"
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
                <button type="button" className="api-wb-body-action is-accent inline-flex cursor-pointer items-center gap-1 rounded-[4px] border-0 bg-transparent px-2 py-1 text-[12px] leading-4 text-[var(--srf-accent)] transition-colors hover:bg-[var(--srf-accent-soft)] disabled:cursor-not-allowed disabled:opacity-45 [&_.anticon]:text-[var(--srf-accent)]">
                  <CodeOutlined />
                  插入变量 {'{{var}}'}
                </button>
              ),
            })
            : null}
          <span className="api-wb-body-action-divider h-3 w-px bg-[var(--srf-card-border)]" aria-hidden="true" />
          {bodyType === 'json' ? (
            <span className={`api-wb-body-validity inline-flex items-center gap-1 whitespace-nowrap rounded-[4px] border border-[var(--srf-tone-border)] bg-[var(--srf-tone-bg)] px-2 py-1 text-[11px] font-semibold leading-4 text-[var(--srf-tone-text)] tone-${jsonValid ? 'green' : 'red'}`}>
              {jsonValid ? <CheckCircleFilled /> : <WarningFilled />}
              {jsonValid ? 'JSON Schema 合法' : 'JSON 语法错误'}
            </span>
          ) : null}
        </div>
      </div>

      <Form.Item name="bodyType" hidden>
        <Input />
      </Form.Item>

      <div data-tab-motion-panel>
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

      </div>
      <div className="api-wb-body-status flex flex-wrap items-center justify-between gap-2 border-t border-[var(--srf-divider)] bg-[var(--srf-hover)] px-4 py-1 text-[11px] leading-[18px] text-[var(--srf-text-secondary)]">
        <div className="api-wb-body-status-main flex flex-wrap items-center gap-3">
          {bodyType === 'json' ? (
            jsonValid ? (
              <span className="tone-green inline-flex items-center gap-1 font-mono font-medium text-[var(--srf-tone-text)]">
                <CheckCircleFilled />
                无语法错误
              </span>
            ) : (
              <span className="tone-red inline-flex items-center gap-1 font-mono font-medium text-[var(--srf-tone-text)]">
                <WarningFilled />
                存在语法错误
              </span>
            )
          ) : (
            <span className="is-muted text-[var(--srf-text-muted)]">无需校验</span>
          )}
          <span className="is-muted text-[var(--srf-text-muted)]">大小: {sizeText}</span>
          <span className="is-muted text-[var(--srf-text-muted)]">格式: {bodyType === 'json' ? 'JSON' : '文本'}</span>
          <span className="is-muted text-[var(--srf-text-muted)]">编码: UTF-8</span>
        </div>
        <div className="api-wb-body-status-side flex flex-wrap items-center gap-3">
          {bodyType === 'json' ? (
            <span className="font-mono">行 {cursor.line}, 列 {cursor.column} (光标聚焦)</span>
          ) : null}
          <span className="is-muted text-[var(--srf-text-muted)]">空格: {INDENT_WIDTH}</span>
        </div>
      </div>
    </div>
  )
}
