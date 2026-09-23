import {
  assertComparatorLabelMap,
  assertSourceLabelMap,
  extractSourceLabelMap,
  methodOptions,
  methodTone
} from '@/features/api-automation/config/collectionConfig'
import type { ApiCaseEditorProps } from '@/features/api-automation/components/apiCaseEditorProps'
import { ApiCaseBodyPanel } from '@/features/api-automation/components/ApiCaseBodyPanel'
import { ApiCaseHeadersPanel } from '@/features/api-automation/components/ApiCaseHeadersPanel'
import {
  buildApiCaseUpdatePayload,
  formatOptionalValue,
  getCaseId,
  type ApiCaseFormValues
} from '@/features/api-automation/utils/apiCaseEditor'
import { Text } from '@/features/api-automation/utils/detailView'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { message } from '@/shared/utils/feedback'
import {
  normalizeAssertRuleId,
  normalizeEnvironmentId,
  normalizeExtractRuleId
} from '@/utils/format'
import { CodeOutlined, DownOutlined, InfoCircleOutlined, PlusOutlined, SendOutlined } from '@ant-design/icons'
import { Button, Card, Checkbox, Dropdown, Empty, Form, Input, InputNumber, Popconfirm, Popover, Select, Space, Switch, Tabs, Tag, Tooltip } from 'antd'
import { useState } from 'react'

/** 顶部一行只读元信息与页签计数都要看当前表单值，草稿态下这些值还没落库。 */
function countFilledRows(rows?: Array<{ key?: string; value?: string }>) {
  return (rows ?? []).filter((row) => (row?.key ?? '').trim() || (row?.value ?? '').trim()).length
}

/** 请求头页签的工具条提示：设计稿把「已启用 / 总数」标在页签行右侧。 */
function countEnabledRows(rows?: Array<{ enabled?: boolean; key?: string; value?: string }>) {
  return (rows ?? []).filter((row) => row.enabled !== false && ((row.key ?? '').trim() || (row.value ?? '').trim())).length
}

export function ApiCaseEditor({ caseForm, isCreatingCase, setDraftCaseValues, getCompleteCaseFormValues, createCaseMutation, editingCase, activeCaseId, updateCaseMutation, pathInputRef, runApiCaseMutation, isApiCaseRunInProgress, isSelectedCaseReady, handleSendRequest, watchedBodyType, environment, templates, rules }: ApiCaseEditorProps) {
  const { environmentPopoverOpen, setEnvironmentPopoverOpen, environments, resolvedEnvironmentId, handleSelectEnvironment, switchDefaultEnvironmentMutation, projectId, selectedEnvironment, environmentsQuery } = environment
  const { setEnvVarInputRef, renderEnvVarPicker, insertTemplateText } = templates
  const { postOperationCount, can, openCreateAssertRule, openCreateExtractRule, assertRulesQuery, extractRulesQuery, assertRules, toggleAssertRuleMutation, openEditAssertRule, deleteAssertRuleMutation, extractRules, toggleExtractRuleMutation, openEditExtractRule, deleteExtractRuleMutation } = rules

  const [activeTabKey, setActiveTabKey] = useState('query')
  const watchedMethod = Form.useWatch('method', caseForm)
  const watchedEnabled = Form.useWatch('enabled', caseForm)
  const watchedTimeoutMs = Form.useWatch('timeoutMs', caseForm)
  const watchedQuery = Form.useWatch('query', caseForm)
  const watchedHeaders = Form.useWatch('headers', caseForm)
  const queryCount = countFilledRows(watchedQuery)
  const headerCount = countFilledRows(watchedHeaders)
  const enabledHeaderCount = countEnabledRows(watchedHeaders)

  /* `useWatch` 对没挂载的 Form.Item 返回 undefined：请求体与设置两个页签只有被打开时才挂载，
     所以首屏的请求体类型 / 超时 / 启用状态要回落到已加载的用例记录上。 */
  const bodyType = watchedBodyType ?? editingCase?.bodyType ?? editingCase?.body_type ?? 'none'
  const caseTimeoutMs = watchedTimeoutMs ?? editingCase?.timeoutMs ?? editingCase?.timeout_ms
  const caseEnabled = watchedEnabled ?? editingCase?.enabled ?? true

  return (
    <Form<ApiCaseFormValues>
      form={caseForm}
      layout="vertical"
      requiredMark={false}
      className="api-wb-form"
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
      <div className="api-wb-editor-head">
        <div className="api-wb-case-head">
          <div className="api-wb-case-name">
            <Form.Item name="name" label="用例名称" className="api-wb-case-name-item" rules={[{ required: true, message: '请输入用例名称' }]}>
              <Input maxLength={120} placeholder="请输入用例名称" />
            </Form.Item>
          </div>
          <div className="api-wb-case-meta">
            <span className="api-wb-case-meta-item">
              请求方式 <strong>{watchedMethod ?? editingCase?.method ?? '-'}</strong>
            </span>
            <span className="api-wb-case-meta-item">
              超时 <strong>{caseTimeoutMs ? `${caseTimeoutMs} ms` : '默认'}</strong>
            </span>
            <span className="api-wb-case-meta-item">
              后置操作 <strong>{postOperationCount}</strong>
            </span>
            <span className={`api-wb-case-state tone-${caseEnabled ? 'green' : 'slate'}`}>
              {caseEnabled ? '启用中' : '已禁用'}
            </span>
          </div>
        </div>

        <div className={`api-wb-request tone-${methodTone(watchedMethod ?? editingCase?.method ?? 'GET')}`}>
          <div className="api-wb-request-bar">
            <Form.Item name="method" className="api-wb-method" rules={[{ required: true, message: '请选择请求方式' }]}>
              <Select options={methodOptions} classNames={{ popup: { root: 'api-method-dropdown' } }} />
            </Form.Item>
            <div className="api-wb-url-group">
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
                  className={`api-wb-base-url${environmentPopoverOpen ? ' open' : ''}`}
                  disabled={!projectId || environments.length === 0}
                  title={selectedEnvironment?.baseUrl || '未选择环境'}
                >
                  <span className="api-wb-base-url-dot" aria-hidden="true" />
                  <span className="api-wb-base-url-text">
                    {selectedEnvironment?.baseUrl || (environmentsQuery.isLoading ? '加载环境中...' : '未选择环境')}
                  </span>
                  <DownOutlined className="api-wb-base-url-arrow" />
                </button>
              </Popover>
              <span className="api-wb-url-divider" aria-hidden="true" />
              <Form.Item name="path" className="api-wb-path" rules={[{ required: true, message: '请输入接口路径' }]}>
                <Input ref={pathInputRef} placeholder="/v1/example" maxLength={1024} />
              </Form.Item>
              <Tooltip title="路径不是 http:// 或 https:// 开头时，会自动拼接当前环境 Base URL。">
                <InfoCircleOutlined className="api-wb-url-info" />
              </Tooltip>
            </div>
            <div className="api-wb-request-actions">
              <Button
                type="primary"
                className="api-wb-send"
                loading={runApiCaseMutation.isPending || isApiCaseRunInProgress}
                disabled={!isSelectedCaseReady || isApiCaseRunInProgress}
                onClick={handleSendRequest}
                icon={<SendOutlined />}
              >
                发送
              </Button>
              <ProjectActionButton operation="save" action="write"
                className="api-wb-save"
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
        className="api-wb-tabs"
        activeKey={activeTabKey}
        onChange={setActiveTabKey}
        tabBarExtraContent={activeTabKey === 'headers' ? (
          <span className="api-wb-tabs-extra">
            已启用请求头: <strong>{enabledHeaderCount}</strong> / {headerCount}
          </span>
        ) : activeTabKey === 'body' ? (
          <span className="api-wb-tabs-extra">
            Content-Type:{' '}
            <span className="api-wb-tabs-extra-code">
              {bodyType === 'json' ? 'application/json' : bodyType === 'form' ? 'application/x-www-form-urlencoded' : '—'}
            </span>
          </span>
        ) : undefined}
        items={[
          {
            key: 'query',
            label: <TabLabel label="参数" count={queryCount} />,
            children: (
              <>
                <Form.List name="query">
                  {(fields, { remove }) => (
                    <div className="api-wb-kv-block">
                      <div className="api-wb-kv-toolbar">
                        <Text strong>Query 参数</Text>
                      </div>
                      {fields.map((field) => {
                        const { key: fieldKey, ...fieldProps } = field

                        return (
                          <div key={fieldKey} className="api-wb-kv-row">
                            <Form.Item {...fieldProps} name={[field.name, 'enabled']} valuePropName="checked" className="api-wb-kv-check">
                              <Checkbox aria-label="启用该参数" />
                            </Form.Item>
                            <Form.Item {...fieldProps} name={[field.name, 'key']} className="api-wb-kv-item">
                              <Input placeholder="参数名" />
                            </Form.Item>
                            <div className="api-wb-kv-item api-wb-kv-value">
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
            label: <TabLabel label="请求头" count={headerCount} />,
            children: <ApiCaseHeadersPanel headers={watchedHeaders ?? []} templates={templates} />,
          },
          {
            key: 'body',
            label: <TabLabel label="请求体" dot={bodyType !== 'none'} />,
            children: <ApiCaseBodyPanel bodyType={bodyType} templates={templates} />,
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
            label: <TabLabel label="后置操作" count={postOperationCount} />,
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

/** 页签标题：计数徽标与「有请求体」圆点，都是设计稿画在页签上的状态。 */
function TabLabel({ label, count = 0, dot = false }: { label: string; count?: number; dot?: boolean }) {
  return (
    <span className="api-wb-tab-label">
      {label}
      {count > 0 ? <span className="api-wb-tab-count">{count}</span> : null}
      {dot ? <span className="api-wb-tab-dot" aria-hidden="true" /> : null}
    </span>
  )
}
