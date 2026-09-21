import {
  assertComparatorLabelMap,
  assertSourceLabelMap,
  bodyTypeOptions,
  extractSourceLabelMap,
  methodOptions
} from '@/features/api-automation/config/collectionConfig'
import {
  buildApiCaseUpdatePayload,
  formatOptionalValue,
  getCaseId,
  type ApiCaseFormValues
} from '@/features/api-automation/utils/apiCaseEditor'
import { Text, validateJsonText } from '@/features/api-automation/utils/detailView'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import {
  type ApiAssertRule,
  type ApiCase,
  type ApiCaseRunResult,
  type ApiExtractRule
} from '@/services/api'
import { JsonEditor, type JsonEditorRef } from '@/shared/components/JsonEditor/JsonEditor'
import { message } from '@/shared/utils/feedback'
import {
  normalizeAssertRuleId,
  normalizeEnvironmentId,
  normalizeExtractRuleId
} from '@/utils/format'
import { CodeOutlined, DownOutlined, InfoCircleOutlined, PlusOutlined, SendOutlined } from '@ant-design/icons'
import type { InputRef } from 'antd'
import { Button, Card, Dropdown, Empty, Form, Input, InputNumber, Popconfirm, Popover, Segmented, Select, Space, Switch, Tabs, Tag, Tooltip } from 'antd'

import type { ApiEnvironment } from '@/features/api-automation/types'
import type { ProjectAction } from '@/features/projects/types'
import type { ListResponse } from '@/shared/api/request'
import type { UseMutationResult, UseQueryResult } from '@tanstack/react-query'
import type { FormInstance } from 'antd'
import type { JSX } from 'react'

type EnvironmentProps = {
  environmentPopoverOpen: boolean
  setEnvironmentPopoverOpen: React.Dispatch<React.SetStateAction<boolean>>
  environments: ApiEnvironment[]
  resolvedEnvironmentId: string | undefined
  handleSelectEnvironment: (nextEnvironmentId: string) => void
  switchDefaultEnvironmentMutation: UseMutationResult<string, Error, string, { previousEnvironmentId: string | undefined }>
  projectId: string | undefined
  selectedEnvironment: ApiEnvironment
  environmentsQuery: UseQueryResult<ListResponse<ApiEnvironment>, Error>
}

type TemplatesProps = {
  setEnvVarInputRef: (fieldKey: string, ref: InputRef | null) => void
  renderEnvVarPicker: ({ pickerKey, onInsert, trigger, }: { pickerKey: string; onInsert: (templateText: string) => void; trigger: React.ReactNode; placement?: "bottomRight" | "bottomLeft" | undefined }) => JSX.Element
  insertTemplateText: (fieldPath: (string | number)[], fieldKey: string, templateText: string) => void
  bodyJsonEditorRef: React.RefObject<JsonEditorRef | null>
  insertTemplateTextIntoJson: (templateText: string) => void
  handleFormatBodyJson: () => void
}

type RulesProps = {
  postOperationCount: number
  can: (action: ProjectAction) => boolean
  openCreateAssertRule: () => void
  openCreateExtractRule: () => void
  assertRulesQuery: UseQueryResult<ListResponse<ApiAssertRule>, Error>
  extractRulesQuery: UseQueryResult<ListResponse<ApiExtractRule>, Error>
  assertRules: ApiAssertRule[]
  toggleAssertRuleMutation: UseMutationResult<ApiAssertRule, Error, { assertRuleId: string; enabled: boolean }, unknown>
  openEditAssertRule: (rule: ApiAssertRule) => void
  deleteAssertRuleMutation: UseMutationResult<Record<string, never>, Error, string, unknown>
  extractRules: ApiExtractRule[]
  toggleExtractRuleMutation: UseMutationResult<ApiExtractRule, Error, { extractRuleId: string; enabled: boolean }, unknown>
  openEditExtractRule: (rule: ApiExtractRule) => void
  deleteExtractRuleMutation: UseMutationResult<Record<string, never>, Error, string, unknown>
}

type Props = {
  caseForm: FormInstance<ApiCaseFormValues>
  isCreatingCase: boolean
  setDraftCaseValues: React.Dispatch<React.SetStateAction<ApiCaseFormValues | null>>
  getCompleteCaseFormValues: () => ApiCaseFormValues
  createCaseMutation: UseMutationResult<ApiCase, Error, ApiCaseFormValues, unknown>
  editingCase: ApiCase | null
  activeCaseId: string
  updateCaseMutation: UseMutationResult<ApiCase, Error, ApiCaseFormValues, unknown>
  pathInputRef: React.RefObject<InputRef | null>
  runApiCaseMutation: UseMutationResult<ApiCaseRunResult, Error, { caseId: string; environmentId: string }, unknown>
  isApiCaseRunInProgress: boolean
  isSelectedCaseReady: boolean
  handleSendRequest: () => Promise<void>
  watchedBodyType: "form" | "json" | "raw" | "none" | undefined
  environment: EnvironmentProps
  templates: TemplatesProps
  rules: RulesProps
}

export function ApiCaseEditor({ caseForm, isCreatingCase, setDraftCaseValues, getCompleteCaseFormValues, createCaseMutation, editingCase, activeCaseId, updateCaseMutation, pathInputRef, runApiCaseMutation, isApiCaseRunInProgress, isSelectedCaseReady, handleSendRequest, watchedBodyType, environment, templates, rules }: Props) {
  const { environmentPopoverOpen, setEnvironmentPopoverOpen, environments, resolvedEnvironmentId, handleSelectEnvironment, switchDefaultEnvironmentMutation, projectId, selectedEnvironment, environmentsQuery } = environment
  const { setEnvVarInputRef, renderEnvVarPicker, insertTemplateText, bodyJsonEditorRef, insertTemplateTextIntoJson, handleFormatBodyJson } = templates
  const { postOperationCount, can, openCreateAssertRule, openCreateExtractRule, assertRulesQuery, extractRulesQuery, assertRules, toggleAssertRuleMutation, openEditAssertRule, deleteAssertRuleMutation, extractRules, toggleExtractRuleMutation, openEditExtractRule, deleteExtractRuleMutation } = rules

  return (
    <Form<ApiCaseFormValues>
      form={caseForm}
      layout="vertical"
      requiredMark={false}
      className="api-case-editor-form"
      onValuesChange={(_changedValues, allValues) => {
        if (isCreatingCase) {
          setDraftCaseValues(allValues as ApiCaseFormValues)
        }
      }}
      onFinish={(values) => {
        const completeValues = {
          ...getCompleteCaseFormValues(),
          ...values,
          headers: values.headers ?? getCompleteCaseFormValues().headers,
          query: values.query ?? getCompleteCaseFormValues().query,
        } satisfies ApiCaseFormValues

        if (isCreatingCase) {
          createCaseMutation.mutate(completeValues)
          return
        }

        if (!editingCase || getCaseId(editingCase) !== activeCaseId) {
          message.warning('用例详情加载中，请稍后再试')
          return
        }

        const payload = buildApiCaseUpdatePayload(editingCase, completeValues)
        if (Object.keys(payload).length === 0) {
          message.info('当前没有需要保存的修改')
          return
        }

        updateCaseMutation.mutate(completeValues)
      }}
    >
      <div className="api-case-editor-sticky-head">
        <Form.Item name="name" label="用例名称" rules={[{ required: true, message: '请输入用例名称' }]}>
          <Input maxLength={120} />
        </Form.Item>

        <div className="api-case-request-shell">
          <div className="api-case-request-caption">
            <span>请求地址</span>
            <span className="api-case-request-env-hint">当前环境</span>
            <Tooltip title="路径不是 http:// 或 https:// 开头时，会自动拼接当前环境 Base URL。">
              <InfoCircleOutlined className="api-case-request-info" />
            </Tooltip>
          </div>
          <div className="api-case-request-bar">
            <Form.Item name="method" className="api-case-method-item" rules={[{ required: true, message: '请选择请求方式' }]}>
              <Select options={methodOptions} classNames={{ popup: { root: 'api-method-dropdown' } }} />
            </Form.Item>
            <div className="api-case-url-group">
              <Popover
                trigger="click"
                placement="bottomLeft"
                open={environmentPopoverOpen}
                onOpenChange={setEnvironmentPopoverOpen}
                overlayClassName="api-case-environment-popover-overlay"
                content={
                  <div className="api-case-environment-popover">
                    <div className="api-case-environment-popover-head">
                      <div className="api-case-environment-popover-title">选择环境 Base URL</div>
                      <div className="api-case-environment-popover-tip">
                        当路径不是 http:// 或 https:// 开头时，会自动拼接当前环境的 Base URL。
                      </div>
                      <div className="api-case-environment-popover-subtitle">选中后会切换为当前启用环境</div>
                    </div>
                    <div className="api-case-environment-option-list">
                      {environments.length === 0 ? (
                        <div className="api-case-environment-empty">当前项目还没有可用环境</div>
                      ) : (
                        environments.map((environment) => {
                          const environmentId = normalizeEnvironmentId(environment)
                          const active = environmentId === resolvedEnvironmentId

                          return (
                            <button
                              key={environmentId}
                              type="button"
                              className={`api-case-environment-option${active ? ' active' : ''}`}
                              onClick={() => handleSelectEnvironment(environmentId)}
                              disabled={switchDefaultEnvironmentMutation.isPending}
                            >
                              <span className="api-case-environment-option-main">
                                <span className="api-case-environment-option-url">{environment.baseUrl}</span>
                                <span className="api-case-environment-option-name">
                                  {environment.name}
                                  {environment.isDefault ? ' · 启用中' : ''}
                                </span>
                              </span>
                              {active ? <span className="api-case-environment-option-badge">当前</span> : null}
                            </button>
                          )
                        })
                      )}
                    </div>
                  </div>
                }
              >
                <button
                  type="button"
                  className={`api-case-base-url-trigger${environmentPopoverOpen ? ' open' : ''}`}
                  disabled={!projectId || environments.length === 0}
                  title={selectedEnvironment?.baseUrl || '未选择环境'}
                >
                  <span className="api-case-base-url-text">
                    {selectedEnvironment?.baseUrl || (environmentsQuery.isLoading ? '加载环境中...' : '未选择环境')}
                  </span>
                  <DownOutlined className="api-case-base-url-arrow" />
                </button>
              </Popover>
              <span className="api-case-url-divider" aria-hidden="true" />
              <Form.Item name="path" className="api-case-path-item" rules={[{ required: true, message: '请输入接口路径' }]}>
                <Input ref={pathInputRef} placeholder="/v1/example" maxLength={1024} />
              </Form.Item>
            </div>
            <div className="api-case-request-actions">
              <Button
                type="primary"
                className="api-case-send-button"
                loading={runApiCaseMutation.isPending || isApiCaseRunInProgress}
                disabled={!isSelectedCaseReady || isApiCaseRunInProgress}
                onClick={handleSendRequest}
                icon={<SendOutlined />}
              >
                发送
              </Button>
              <ProjectActionButton operation="save" action="write"
                className="api-case-save-button"
                loading={createCaseMutation.isPending || updateCaseMutation.isPending}
                disabled={!isSelectedCaseReady}
                onClick={() => caseForm.submit()}
              >
                保存
              </ProjectActionButton>
            </div>
          </div>
        </div>
      </div>

      <Tabs
        className="api-case-editor-tabs"
        items={[
          {
            key: 'query',
            label: '参数',
            children: (
              <>
                <Form.List name="query">
                  {(fields, { remove }) => (
                    <div className="api-kv-block">
                      <div className="api-kv-toolbar">
                        <Text strong>Query 参数</Text>
                      </div>
                      {fields.map((field) => {
                        const { key: fieldKey, ...fieldProps } = field

                        return (
                          <div key={fieldKey} className="api-kv-row">
                            <Form.Item {...fieldProps} name={[field.name, 'enabled']} valuePropName="checked" className="api-kv-check-item">
                              <Switch size="small" />
                            </Form.Item>
                            <Form.Item {...fieldProps} name={[field.name, 'key']} className="api-kv-item">
                              <Input placeholder="参数名" />
                            </Form.Item>
                            <div className="api-kv-item api-kv-value-item">
                              <Space.Compact style={{ width: '100%' }}>
                                <Form.Item {...fieldProps} name={[field.name, 'value']} noStyle>
                                  <Input
                                    ref={(node) => setEnvVarInputRef(`query:${field.key}:value`, node)}
                                    placeholder="参数值"
                                  />
                                </Form.Item>
                                {renderEnvVarPicker({
                                  pickerKey: `query:${field.key}:value`,
                                  onInsert: (templateText) => insertTemplateText(['query', field.name, 'value'], `query:${field.key}:value`, templateText),
                                  trigger: <Button type="text" size="small" className="api-env-var-picker-trigger" icon={<CodeOutlined />} />,
                                })}
                              </Space.Compact>
                            </div>
                            <Tooltip title="删除参数">
                              <ProjectActionButton action="write"
                                danger
                                type="text"
                                shape="circle"
                                className="action-btn-delete"
                                operation="delete" iconOnly
                                aria-label="删除参数"
                                onClick={() => remove(field.name)}
                              />
                            </Tooltip>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </Form.List>
              </>
            ),
          },
          {
            key: 'headers',
            label: '请求头',
            children: (
              <Form.List name="headers">
                {(fields, { remove }) => (
                  <div className="api-kv-block">
                    <div className="api-kv-toolbar">
                      <Text strong>请求头</Text>
                    </div>
                    {fields.map((field) => {
                      const { key: fieldKey, ...fieldProps } = field

                      return (
                        <div key={fieldKey} className="api-kv-row">
                          <Form.Item {...fieldProps} name={[field.name, 'enabled']} valuePropName="checked" className="api-kv-check-item">
                            <Switch size="small" />
                          </Form.Item>
                          <Form.Item {...fieldProps} name={[field.name, 'key']} className="api-kv-item">
                            <Input placeholder="Header 名称" />
                          </Form.Item>
                          <div className="api-kv-item api-kv-value-item">
                            <Space.Compact style={{ width: '100%' }}>
                              <Form.Item {...fieldProps} name={[field.name, 'value']} noStyle>
                                <Input
                                  ref={(node) => setEnvVarInputRef(`headers:${field.key}:value`, node)}
                                  placeholder="Header 值"
                                />
                              </Form.Item>
                              {renderEnvVarPicker({
                                pickerKey: `headers:${field.key}:value`,
                                onInsert: (templateText) => insertTemplateText(['headers', field.name, 'value'], `headers:${field.key}:value`, templateText),
                                trigger: <Button type="text" size="small" className="api-env-var-picker-trigger" icon={<CodeOutlined />} />,
                              })}
                            </Space.Compact>
                          </div>
                          <Tooltip title="删除请求头">
                            <ProjectActionButton action="write"
                              danger
                              type="text"
                              shape="circle"
                              className="action-btn-delete"
                              operation="delete" iconOnly
                              aria-label="删除请求头"
                              onClick={() => remove(field.name)}
                            />
                          </Tooltip>
                        </div>
                      )
                    })}
                  </div>
                )}
              </Form.List>
            ),
          },
          {
            key: 'body',
            label: '请求体',
            children: (
              <>
                <Form.Item name="bodyType" hidden>
                  <Input />
                </Form.Item>
                <div className="api-body-type-block">
                  <Segmented
                    className="api-body-type-segmented"
                    options={bodyTypeOptions}
                    value={watchedBodyType ?? 'none'}
                    onChange={(value) => caseForm.setFieldValue('bodyType', value)}
                  />
                </div>
                {watchedBodyType === 'json' ? (
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
                      toolbar={
                        <div className="json-editor-toolbar-row">
                          <div className="json-editor-toolbar-actions">
                            {renderEnvVarPicker({
                              pickerKey: 'bodyJson',
                              placement: 'bottomLeft',
                              onInsert: insertTemplateTextIntoJson,
                              trigger: (
                                <Button className="json-editor-toolbar-btn" icon={<CodeOutlined />}>
                                  动态值
                                  <DownOutlined />
                                </Button>
                              ),
                            })}
                          </div>
                          <div className="json-editor-toolbar-side">
                            <span className="json-editor-toolbar-type">application/json</span>
                            <Button type="text" className="json-editor-toolbar-link" onClick={handleFormatBodyJson}>
                              格式化
                            </Button>
                          </div>
                        </div>
                      }
                    />
                  </Form.Item>
                ) : null}
                {watchedBodyType === 'raw' ? (
                  <Form.Item name="bodyText" label="Body 内容">
                    <Input.TextArea rows={8} placeholder="原始请求体内容" />
                  </Form.Item>
                ) : null}
                {watchedBodyType === 'form' ? (
                  <Card size="small" className="api-body-placeholder-card">
                    <Text type="secondary">`form` 类型的键值表单下一步再补，这一版先保留类型切换。</Text>
                  </Card>
                ) : null}
                {watchedBodyType === 'none' ? (
                  <Card size="small" className="api-body-placeholder-card">
                    <Text type="secondary">当前选择 `none`，无需填写请求体。</Text>
                  </Card>
                ) : null}
              </>
            ),
          },
          {
            key: 'settings',
            label: '设置',
            children: (
              <div className="api-case-settings-grid">
                <Form.Item name="timeoutMs" label="超时时间(ms)">
                  <InputNumber min={0} step={1000} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="enabled" label="是否启用" valuePropName="checked">
                  <Switch />
                </Form.Item>
                <Form.Item name="continueOnFailure" label="失败后继续" valuePropName="checked">
                  <Switch />
                </Form.Item>
                <Form.Item name="description" label="用例描述" className="api-case-settings-description">
                  <Input.TextArea rows={6} maxLength={512} />
                </Form.Item>
              </div>
            ),
          },
          {
            key: 'post-operations',
            label: `后置操作 (${postOperationCount})`,
            children: activeCaseId ? (
              <div className="api-post-ops-section">
                <div className="api-post-ops-head">
                  <div className="api-post-ops-head-main">
                    <Text strong>后置操作</Text>
                    <div className="api-post-ops-subtitle">统一管理断言与提取变量，提取结果会写回当前所选环境变量。</div>
                  </div>
                </div>

                <Dropdown
                  disabled={!can('write')}
                  trigger={['click']}
                  menu={{
                    items: [
                      { key: 'assert', label: '新增断言' },
                      { key: 'extract', label: '新增提取规则' },
                    ],
                    onClick: ({ key }) => {
                      if (key === 'assert') {
                        openCreateAssertRule()
                        return
                      }
                      openCreateExtractRule()
                    },
                  }}
                >
                  <ProjectActionButton action="write" type="text" className="api-post-ops-add-trigger">
                    <PlusOutlined />
                    <span>添加后置操作</span>
                    <DownOutlined />
                  </ProjectActionButton>
                </Dropdown>

                {assertRulesQuery.isLoading || extractRulesQuery.isLoading ? (
                  <Empty description="后置操作加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : postOperationCount === 0 ? (
                  <Card size="small" className="api-rule-empty-card">
                    <Empty description="还没有后置操作，点击上方添加断言或提取规则" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  </Card>
                ) : (
                  <div className="api-post-ops-group-list">
                    <div className="api-post-ops-group">
                      <div className="api-post-ops-group-title">
                        <span>断言</span>
                        <Tag>{assertRules.length}</Tag>
                      </div>
                      {assertRules.length === 0 ? (
                        <div className="api-post-ops-empty">暂无断言规则</div>
                      ) : (
                        <div className="api-post-ops-items">
                          {assertRules.map((rule) => (
                            <div key={normalizeAssertRuleId(rule)} className="api-post-ops-item">
                              <div className="api-post-ops-item-side">
                                <Tag color="error">断言</Tag>
                                <Switch
                                  size="small"
                                  checked={rule.enabled}
                                  loading={toggleAssertRuleMutation.isPending}
                                  onChange={(checked) =>
                                    toggleAssertRuleMutation.mutate({
                                      assertRuleId: normalizeAssertRuleId(rule),
                                      enabled: checked,
                                    })
                                  }
                                />
                              </div>
                              <div className="api-post-ops-item-main">
                                <div className="api-post-ops-item-title">
                                  <strong>{rule.name}</strong>
                                  <span>#{rule.orderNo ?? '-'}</span>
                                </div>
                                <div className="api-post-ops-item-meta">
                                  <span>{assertSourceLabelMap[rule.assertSource]}</span>
                                  <span>{assertComparatorLabelMap[rule.comparator]}</span>
                                  <span>{formatOptionalValue(rule.targetExpr)}</span>
                                  <span>{formatOptionalValue(rule.expectedValue)}</span>
                                </div>
                              </div>
                              <div className="api-post-ops-item-actions">
                                <ProjectActionButton action="write" type="text" size="small" operation="edit" iconOnly onClick={() => openEditAssertRule(rule)} />
                                <Popconfirm
                                  title="确认删除该断言规则？"
                                  onConfirm={() => deleteAssertRuleMutation.mutate(normalizeAssertRuleId(rule))}
                                >
                                  <ProjectActionButton action="write" danger type="text" size="small" operation="delete" iconOnly loading={deleteAssertRuleMutation.isPending} />
                                </Popconfirm>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="api-post-ops-group">
                      <div className="api-post-ops-group-title">
                        <span>提取规则</span>
                        <Tag>{extractRules.length}</Tag>
                      </div>
                      {extractRules.length === 0 ? (
                        <div className="api-post-ops-empty">暂无提取规则</div>
                      ) : (
                        <div className="api-post-ops-items">
                          {extractRules.map((rule) => (
                            <div key={normalizeExtractRuleId(rule)} className="api-post-ops-item">
                              <div className="api-post-ops-item-side">
                                <Tag color="processing">提取</Tag>
                                <Switch
                                  size="small"
                                  checked={rule.enabled}
                                  loading={toggleExtractRuleMutation.isPending}
                                  onChange={(checked) =>
                                    toggleExtractRuleMutation.mutate({
                                      extractRuleId: normalizeExtractRuleId(rule),
                                      enabled: checked,
                                    })
                                  }
                                />
                              </div>
                              <div className="api-post-ops-item-main">
                                <div className="api-post-ops-item-title">
                                  <strong>{rule.name}</strong>
                                  <span>#{rule.orderNo ?? '-'}</span>
                                </div>
                                <div className="api-post-ops-item-meta">
                                  <span>{extractSourceLabelMap[rule.source]}</span>
                                  <span>{formatOptionalValue(rule.sourceExpr)}</span>
                                  <span>{formatOptionalValue(rule.varKey)}</span>
                                  <span>{formatOptionalValue(rule.defaultValue)}</span>
                                </div>
                              </div>
                              <div className="api-post-ops-item-actions">
                                <ProjectActionButton action="write" type="text" size="small" operation="edit" iconOnly onClick={() => openEditExtractRule(rule)} />
                                <Popconfirm
                                  title="确认删除该提取规则？"
                                  onConfirm={() => deleteExtractRuleMutation.mutate(normalizeExtractRuleId(rule))}
                                >
                                  <ProjectActionButton action="write" danger type="text" size="small" operation="delete" iconOnly loading={deleteExtractRuleMutation.isPending} />
                                </Popconfirm>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <Card size="small" className="api-rule-empty-card">
                <Empty description="请先保存当前用例后再配置后置操作" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              </Card>
            ),
          },
        ]}
      />
    </Form>
  )
}
