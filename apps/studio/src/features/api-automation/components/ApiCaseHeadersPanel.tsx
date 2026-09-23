import { headerQuickInjectPresets } from '@/features/api-automation/config/collectionConfig'
import type { TemplatesProps } from '@/features/api-automation/components/apiCaseEditorProps'
import type { ApiCaseFormValues } from '@/features/api-automation/utils/apiCaseEditor'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { message } from '@/shared/utils/feedback'
import {
  ClearOutlined,
  CodeOutlined,
  CopyOutlined,
  DeleteOutlined,
} from '@ant-design/icons'
import { Button, Checkbox, Form, Input, Modal, Tooltip } from 'antd'
import { useState } from 'react'

export type ApiCaseHeaderRow = { enabled?: boolean; key?: string; value?: string }

type Props = {
  headers: ApiCaseHeaderRow[]
  templates: TemplatesProps
}

function isBlankRow(row: ApiCaseHeaderRow) {
  return !(row.key ?? '').trim() && !(row.value ?? '').trim()
}

/** 请求头面板：快捷注入与批量工具，加上一张与设计稿同构的键值表。 */
export function ApiCaseHeadersPanel({ headers, templates }: Props) {
  const { setEnvVarInputRef, renderEnvVarPicker, insertTemplateText } = templates
  const caseForm = Form.useFormInstance<ApiCaseFormValues>()
  const [draftRow, setDraftRow] = useState({ key: '', value: '' })
  const [rawEditorOpen, setRawEditorOpen] = useState(false)
  const [rawEditorText, setRawEditorText] = useState('')

  const filledRows = headers.filter((row) => !isBlankRow(row))
  const enabledCount = filledRows.filter((row) => row.enabled !== false).length

  function applyHeaderRows(rows: ApiCaseHeaderRow[]) {
    caseForm.setFieldValue('headers', rows)
  }

  function handleRawEditorConfirm() {
    const rows = rawEditorText
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const separatorIndex = line.indexOf(':')
        if (separatorIndex < 0) return { enabled: true, key: line, value: '' }

        return {
          enabled: true,
          key: line.slice(0, separatorIndex).trim(),
          value: line.slice(separatorIndex + 1).trim(),
        }
      })
      .filter((row) => row.key)

    applyHeaderRows(rows)
    setRawEditorOpen(false)
  }

  return (
    <Form.List name="headers">
      {(fields, { add, remove }) => (
        <div className="api-wb-hdr-panel">
          <div className="api-wb-hdr-toolbar">
            <div className="api-wb-hdr-toolbar-main">
              <span className="api-wb-hdr-toolbar-label">快捷注入:</span>
              {headerQuickInjectPresets.map((preset) => (
                <button
                  key={preset.key}
                  type="button"
                  className="api-wb-hdr-preset"
                  onClick={() => add({ enabled: true, key: preset.key, value: preset.value })}
                >
                  <span className="api-wb-hdr-preset-plus">+</span>
                  {preset.label}
                </button>
              ))}
            </div>
            <div className="api-wb-hdr-toolbar-side">
              <button
                type="button"
                className="api-wb-hdr-tool"
                onClick={() => {
                  setRawEditorText(filledRows.map((row) => `${row.key ?? ''}: ${row.value ?? ''}`).join('\n'))
                  setRawEditorOpen(true)
                }}
              >
                <CodeOutlined />
                批量编辑 / 格式转换 (RAW)
              </button>
              <span className="api-wb-hdr-tool-divider" aria-hidden="true" />
              <button
                type="button"
                className="api-wb-hdr-tool is-danger"
                disabled={filledRows.length === enabledCount}
                onClick={() => applyHeaderRows(filledRows.filter((row) => row.enabled !== false))}
              >
                <ClearOutlined />
                清空未启用
              </button>
            </div>
          </div>

          <div className="api-wb-hdr-table-wrap">
            <table className="api-wb-hdr-table">
              <colgroup>
                <col className="api-wb-hdr-col-check" />
                <col className="api-wb-hdr-col-key" />
                <col className="api-wb-hdr-col-value" />
                <col className="api-wb-hdr-col-actions" />
              </colgroup>
              <thead>
                <tr>
                  <th className="api-wb-hdr-cell-check">
                    <Checkbox
                      aria-label="全选 / 反选请求头"
                      checked={filledRows.length > 0 && enabledCount === filledRows.length}
                      disabled={filledRows.length === 0}
                      onChange={(event) => {
                        const nextEnabled = event.target.checked
                        applyHeaderRows(headers.map((row) => ({ ...row, enabled: nextEnabled })))
                      }}
                    />
                  </th>
                  <th>请求头名称 (Header Key)</th>
                  <th>请求头值 (Header Value)</th>
                  <th className="api-wb-hdr-cell-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                {fields.map((field, index) => {
                  const row = headers[index] ?? {}
                  const { key: fieldKey, ...fieldProps } = field

                  return (
                    <tr key={fieldKey} className="api-wb-hdr-row">
                      <td className="api-wb-hdr-cell-check">
                        <Form.Item {...fieldProps} name={[field.name, 'enabled']} valuePropName="checked" noStyle>
                          <Checkbox aria-label="启用该请求头" />
                        </Form.Item>
                      </td>
                      <td>
                        <Form.Item {...fieldProps} name={[field.name, 'key']} noStyle>
                          <Input className="api-wb-hdr-input is-key" placeholder="Header 名称" />
                        </Form.Item>
                      </td>
                      <td>
                        <div className="api-wb-hdr-value-cell">
                          <Form.Item {...fieldProps} name={[field.name, 'value']} noStyle>
                            <Input
                              className="api-wb-hdr-input"
                              ref={(node) => setEnvVarInputRef(`headers:${field.key}:value`, node)}
                              placeholder="Header 值"
                            />
                          </Form.Item>
                          {renderEnvVarPicker({
                            pickerKey: `headers:${field.key}:value`,
                            onInsert: (templateText) => insertTemplateText(['headers', field.name, 'value'], `headers:${field.key}:value`, templateText),
                            trigger: (
                              <Tooltip title="插入动态值">
                                <Button type="text" size="small" className="api-env-var-picker-trigger" icon={<CodeOutlined />} />
                              </Tooltip>
                            ),
                          })}
                        </div>
                      </td>
                      <td className="api-wb-hdr-cell-actions">
                        <div className="api-wb-hdr-row-actions">
                          <Tooltip title="复制当前行">
                            <Button
                              type="text"
                              size="small"
                              aria-label="复制请求头"
                              icon={<CopyOutlined />}
                              disabled={isBlankRow(row)}
                              onClick={() => add({ enabled: row.enabled !== false, key: row.key ?? '', value: row.value ?? '' })}
                            />
                          </Tooltip>
                          <Tooltip title="删除请求头">
                            <ProjectActionButton action="write"
                              danger
                              type="text"
                              shape="circle"
                              size="small"
                              className="action-btn-delete"
                              operation="delete" iconOnly
                              aria-label="删除请求头"
                              icon={<DeleteOutlined />}
                              onClick={() => remove(field.name)}
                            />
                          </Tooltip>
                        </div>
                      </td>
                    </tr>
                  )
                })}
                <tr className="api-wb-hdr-row is-draft">
                  <td className="api-wb-hdr-cell-check">
                    <Checkbox aria-label="启用新请求头" disabled />
                  </td>
                  <td>
                    <Input
                      className="api-wb-hdr-input is-draft"
                      placeholder="添加新的请求头 (键)..."
                      value={draftRow.key}
                      onChange={(event) => setDraftRow((prev) => ({ ...prev, key: event.target.value }))}
                      onPressEnter={() => {
                        if (!isBlankRow(draftRow)) {
                          add({ enabled: true, key: draftRow.key, value: draftRow.value })
                          setDraftRow({ key: '', value: '' })
                        }
                      }}
                    />
                  </td>
                  <td>
                    <Input
                      className="api-wb-hdr-input is-draft"
                      placeholder="值 (支持 {{变量}} 语法)..."
                      value={draftRow.value}
                      onChange={(event) => setDraftRow((prev) => ({ ...prev, value: event.target.value }))}
                      onPressEnter={() => {
                        if (!isBlankRow(draftRow)) {
                          add({ enabled: true, key: draftRow.key, value: draftRow.value })
                          setDraftRow({ key: '', value: '' })
                        }
                      }}
                    />
                  </td>
                  <td className="api-wb-hdr-cell-actions">
                    <span className="api-wb-hdr-draft-hint">回车添加</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <Modal
            open={rawEditorOpen}
            title="批量编辑请求头"
            okText="应用"
            cancelText="取消"
            onCancel={() => setRawEditorOpen(false)}
            onOk={() => {
              if (!rawEditorText.trim()) {
                message.warning('批量编辑内容为空，已保留原有请求头')
                setRawEditorOpen(false)
                return
              }
              handleRawEditorConfirm()
            }}
          >
            <p className="api-wb-hdr-raw-tip">每行一个请求头，格式为「名称: 值」；应用后按输入顺序替换当前请求头。</p>
            <Input.TextArea
              rows={8}
              aria-label="请求头批量编辑内容"
              value={rawEditorText}
              onChange={(event) => setRawEditorText(event.target.value)}
              placeholder={'Content-Type: application/json\nAuthorization: Bearer {{token}}'}
            />
          </Modal>
        </div>
      )}
    </Form.List>
  )
}
