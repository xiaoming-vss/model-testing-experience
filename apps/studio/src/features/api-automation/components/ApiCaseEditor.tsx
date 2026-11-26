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
  buildCaseFormValues,
  formatOptionalValue,
  getCaseId,
  stringifyKeyValuePairs,
  type ApiCaseFormValues
} from '@/features/api-automation/utils/apiCaseEditor'
import { Text } from '@/features/api-automation/utils/detailView'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import {
  KV_BODY_CELL_CENTER_CLASS,
  KV_BODY_CELL_CLASS,
  KV_EMPTY_CLASS,
  KV_EMPTY_HINT_CLASS,
  KV_EMPTY_ICON_CLASS,
  KV_EMPTY_TEXT_CLASS,
  KV_EMPTY_TITLE_CLASS,
  KV_HEAD_CELL_ACTION_CLASS,
  KV_HEAD_CELL_CENTER_CLASS,
  KV_HEAD_CELL_CLASS,
  KV_SECTION_COUNT_CLASS,
  KV_SECTION_HEAD_CLASS,
  KV_SECTION_HINT_CLASS,
  KV_TABLE_CLASS,
  KV_TABLE_WRAP_CLASS,
} from '@/shared/ui/keyValueTable'
import { message } from '@/shared/utils/feedback'
import {
  formatTime,
  normalizeAssertRuleId,
  normalizeEnvironmentId,
  normalizeExtractRuleId
} from '@/utils/format'
import titleStyles from '@/shared/styles/editor-title-input.module.css'
import { ApiOutlined, CodeOutlined, CopyOutlined, DownOutlined, FileTextOutlined, InfoCircleOutlined, PlusOutlined, SaveOutlined, SendOutlined } from '@ant-design/icons'
import { Alert, Button, Checkbox, Dropdown, Empty, Form, Input, InputNumber, Popconfirm, Popover, Select, Switch, Tabs, Tag, Tooltip } from 'antd'
import { useEffect, useState } from 'react'
import styles from '../styles/api-detail-rules.module.css'

/** 顶部一行只读元信息与页签计数都要看当前表单值，草稿态下这些值还没落库。 */
function countFilledRows(rows?: Array<{ key?: string; value?: string }>) {
  return (rows ?? []).filter((row) => (row?.key ?? '').trim() || (row?.value ?? '').trim()).length
}

/** 请求头页签的工具条提示：设计稿把「已启用 / 总数」标在页签行右侧。 */
function countEnabledRows(rows?: Array<{ enabled?: boolean; key?: string; value?: string }>) {
  return (rows ?? []).filter((row) => row.enabled !== false && ((row.key ?? '').trim() || (row.value ?? '').trim())).length
}

/** 比较表单值与用例持久化值；键值对按提交格式序列化，避免空行造成误判。 */
function normalizeCaseFormValues(values?: Partial<ApiCaseFormValues>) {
  return JSON.stringify({
    name: values?.name ?? '',
    method: values?.method ?? 'POST',
    path: values?.path ?? '',
    description: values?.description ?? '',
    headers: stringifyKeyValuePairs(values?.headers),
    query: stringifyKeyValuePairs(values?.query),
    bodyType: values?.bodyType ?? 'none',
    bodyJson: values?.bodyJson ?? '',
    bodyText: values?.bodyText ?? '',
    timeoutMs: values?.timeoutMs ?? 0,
    enabled: values?.enabled ?? true,
    continueOnFailure: values?.continueOnFailure ?? false,
  })
}

export function ApiCaseEditor({ caseForm, isCreatingCase, setDraftCaseValues, getCompleteCaseFormValues, createCaseMutation, editingCase, activeCaseId, updateCaseMutation, pathInputRef, runApiCaseMutation, isApiCaseRunInProgress, isSelectedCaseReady, selectedCaseInvalidated, handleSendRequest, collectionName, environment, templates, rules }: ApiCaseEditorProps) {
  const { environmentPopoverOpen, setEnvironmentPopoverOpen, environments, resolvedEnvironmentId, handleSelectEnvironment, switchDefaultEnvironmentMutation, projectId, selectedEnvironment, environmentsQuery } = environment
  const { setEnvVarInputRef, renderEnvVarPicker, insertTemplateText } = templates
  const { postOperationCount, can, openCreateAssertRule, openCreateExtractRule, assertRulesQuery, extractRulesQuery, assertRules, toggleAssertRuleMutation, openEditAssertRule, deleteAssertRuleMutation, extractRules, toggleExtractRuleMutation, openEditExtractRule, deleteExtractRuleMutation } = rules

  const [activeTabKey, setActiveTabKey] = useState('query')
  const [caseDirty, setCaseDirty] = useState(false)
  const watchedName = Form.useWatch('name', caseForm)
  const watchedMethod = Form.useWatch('method', caseForm)
  const watchedPath = Form.useWatch('path', caseForm)
  const watchedEnabled = Form.useWatch('enabled', caseForm)
  const watchedTimeoutMs = Form.useWatch('timeoutMs', caseForm)
  const watchedQuery = Form.useWatch('query', caseForm)
  const watchedHeaders = Form.useWatch('headers', caseForm)
  const watchedBodyType = Form.useWatch('bodyType', caseForm)
  const watchedDescription = Form.useWatch('description', caseForm)
  const watchedValues = Form.useWatch([], { form: caseForm, preserve: true })
  const queryCount = countFilledRows(watchedQuery)
  const enabledQueryCount = countEnabledRows(watchedQuery)
  const headerCount = countFilledRows(watchedHeaders)
  const saving = createCaseMutation.isPending || updateCaseMutation.isPending

  /* 已有用例直接比较表单当前值与持久化值，避免 setFieldValue / 用例切换时的时序问题；
     新建用例还没有持久化基线，沿用本地 dirty 标记。 */
  const savedFormValues = editingCase ? buildCaseFormValues(editingCase) : undefined
  const dirty = isCreatingCase
    ? caseDirty
    : savedFormValues && watchedValues
      ? normalizeCaseFormValues(watchedValues) !== normalizeCaseFormValues(savedFormValues)
      : false

  /* 切换用例后表单会被整体替换；草稿的本地 dirty 标记随之复位。 */
  useEffect(() => { setCaseDirty(false) }, [activeCaseId])

  /* `useWatch` 对没挂载的 Form.Item 返回 undefined：请求体与设置两个页签只有被打开时才挂载，
     所以首屏的请求体类型 / 超时 / 启用状态要回落到已加载的用例记录上。 */
  const bodyType = watchedBodyType ?? editingCase?.bodyType ?? 'none'
  const caseTimeoutMs = watchedTimeoutMs ?? editingCase?.timeoutMs
  const caseEnabled = watchedEnabled ?? editingCase?.enabled ?? true
  const caseName = watchedName ?? editingCase?.name ?? ''
  const caseUpdatedAt = editingCase?.updatedAt
  const stateLabel = saving ? '保存中…' : isCreatingCase ? (dirty ? '有未保存的修改' : '新建用例') : dirty ? '有未保存的修改' : '已保存'
  const stateDot = saving
    ? 'bg-[var(--srf-accent)]'
    : isCreatingCase && !dirty
      ? 'bg-[var(--srf-text-muted)]'
      : dirty
        ? 'bg-[var(--app-status-warning-text)]'
        : 'bg-[var(--srf-result-passed)]'

  function markSaved() {
    setCaseDirty(false)
  }

  async function copyRequestUrl() {
    const path = String(watchedPath ?? editingCase?.urlTemplate ?? '')
    const baseUrl = selectedEnvironment?.baseUrl ?? ''
    const address = /^https?:\/\//i.test(path.trim()) || !baseUrl
      ? path
      : `${baseUrl.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`

    try {
      await navigator.clipboard.writeText(address)
      message.success('请求地址已复制')
    } catch {
      message.error('复制失败，请手动选择路径')
    }
  }

  return (
    <Form<ApiCaseFormValues>
      form={caseForm}
      layout="vertical"
      requiredMark={false}
      className="api-wb-form flex flex-col"
      onFieldsChange={() => {
        if (isCreatingCase) setCaseDirty(true)
      }}
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
          createCaseMutation.mutate(completeValues, { onSuccess: markSaved })
          return
        }

        if (!editingCase || getCaseId(editingCase) !== activeCaseId) {
          message.warning('用例详情加载中，请稍后再试')
          return
        }

        const payload = buildApiCaseUpdatePayload(editingCase, completeValues)
        if (Object.keys(payload).length === 0) {
          markSaved()
          message.info('当前没有需要保存的修改')
          return
        }

        updateCaseMutation.mutate(completeValues, { onSuccess: markSaved })
      }}
    >
      {selectedCaseInvalidated ? (
        <Alert
          showIcon
          type="warning"
          className="mx-4 mt-3"
          title="该用例已失效，不能运行"
          description="恢复有效后可继续发送和执行；已有运行记录不受影响。"
        />
      ) : null}
      <div className="api-wb-editor-head flex-none">
        <div className="api-wb-case-head flex flex-col gap-1 px-4 pb-2 pt-3">
          <div className="api-wb-case-title-row flex min-w-0 flex-wrap items-center gap-2">
            <div className="min-w-0 max-w-full flex-none" style={{ width: `${Math.min(520, Math.max(240, caseName.length * 24 + 56))}px` }}>
              <Form.Item name="name" noStyle rules={[{ required: true, message: '请输入用例名称' }]}>
                <Input className={titleStyles.titleInput} maxLength={120} placeholder="请输入用例名称" aria-label="用例名称" />
              </Form.Item>
            </div>
            <span className="api-wb-case-save-state inline-flex items-center gap-1.5 text-[11px] leading-[18px] text-[var(--srf-text-muted)]" role="status" aria-live="polite">
              <i className={`h-1.5 w-1.5 flex-none rounded-full ${stateDot}`} aria-hidden />
              {stateLabel}
            </span>
            <span className={`api-wb-case-state tp-tone-tag tone-${caseEnabled ? 'green' : 'slate'}`}>
              {caseEnabled ? '启用中' : '已禁用'}
            </span>
            {isCreatingCase ? <span className="tp-tone-tag tone-slate">草稿</span> : null}
          </div>
          <div className="api-wb-case-meta flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] leading-[18px] text-[var(--srf-text-muted)]">
            {collectionName ? <><span>所属测试集 {collectionName}</span><span aria-hidden>·</span></> : null}
            <span>{caseUpdatedAt ? `更新于 ${formatTime(caseUpdatedAt)}` : '尚未保存'}</span>
            <span aria-hidden>·</span>
            <span>超时 {caseTimeoutMs ? `${caseTimeoutMs} ms` : '默认'}</span>
            <span aria-hidden>·</span>
            <span>后置操作 {postOperationCount}</span>
          </div>
        </div>

        <div className={`api-wb-request border-b border-[var(--srf-divider)] px-4 pb-[13px] pt-1 tone-${methodTone(watchedMethod ?? editingCase?.method ?? 'GET')}`}>
          <div className="api-wb-request-bar flex flex-wrap items-center gap-2">
            <Form.Item name="method" className="api-wb-method w-[110px] flex-none" rules={[{ required: true, message: '请选择请求方式' }]}>
              <Select options={methodOptions} classNames={{ popup: { root: `api-method-dropdown ${styles.scope}` } }} />
            </Form.Item>
            <div className="api-wb-url-group flex min-w-0 flex-[1_1_420px] items-center gap-0 overflow-hidden rounded-[var(--srf-radius-control)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] focus-within:border-[var(--srf-accent)] focus-within:shadow-[0_0_0_3px_var(--srf-accent-soft)]">
              <Popover
                trigger="click"
                placement="bottomLeft"
                open={environmentPopoverOpen}
                onOpenChange={setEnvironmentPopoverOpen}
                overlayClassName={`api-case-environment-popover-overlay ${styles.scope}`}
                content={
                  <div className="api-case-environment-popover w-[min(520px,calc(100vw-48px))] bg-[var(--tp-bg-elevated,var(--app-surface))]">
                    <div className="api-case-environment-popover-head border-b border-[var(--tp-border-soft)] px-4 pt-3.5 pb-2.5">
                      <div className="api-case-environment-popover-title text-[14px] font-bold leading-5 text-[var(--tp-text)]">选择环境 Base URL</div>
                      <div className="api-case-environment-popover-tip mt-1.5 text-[12px] leading-[18px] text-[var(--tp-text-secondary)]">
                        当路径不是 http:// 或 https:// 开头时，会自动拼接当前环境的 Base URL。
                      </div>
                      <div className="api-case-environment-popover-subtitle mt-1 text-[12px] leading-[18px] text-[var(--tp-text-secondary)]">选中后会切换为当前启用环境</div>
                    </div>
                    <div className="api-case-environment-option-list flex max-h-[260px] flex-col gap-1 overflow-auto p-2">
                      {environments.length === 0 ? (
                        <div className="api-case-environment-empty px-3 py-5 text-center text-[13px] leading-5 text-[var(--tp-text-secondary)]">当前项目还没有可用环境</div>
                      ) : (
                        environments.map((environment) => {
                          const environmentId = normalizeEnvironmentId(environment)
                          const active = environmentId === resolvedEnvironmentId

                          return (
                            <button
                              key={environmentId}
                              type="button"
                              className={`api-case-environment-option flex w-full cursor-pointer items-center justify-between gap-3 rounded-[10px] border px-3 py-2.5 text-[var(--tp-text)] transition-colors hover:bg-[var(--app-environment-option-hover)] disabled:cursor-not-allowed disabled:opacity-70${active ? ' active border-[var(--app-environment-option-border-selected)] bg-[var(--app-environment-option-selected)]' : ' border-transparent bg-transparent'}`}
                              onClick={() => handleSelectEnvironment(environmentId)}
                              disabled={switchDefaultEnvironmentMutation.isPending}
                            >
                              <span className="api-case-environment-option-main flex min-w-0 flex-[1_1_auto] flex-col gap-0.5">
                                <span className="api-case-environment-option-url block min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-left text-[14px] font-semibold leading-[22px]">{environment.baseUrl}</span>
                                <span className="api-case-environment-option-name min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[12px] leading-[18px] text-[var(--tp-text-secondary)]">
                                  {environment.name}
                                  {environment.isDefault ? ' · 启用中' : ''}
                                </span>
                              </span>
                              {active ? <span className="api-case-environment-option-badge flex-none rounded-full bg-[var(--app-environment-current-bg)] px-2 py-0.5 text-[12px] font-semibold leading-[18px] text-[var(--app-environment-current-text)]">当前</span> : null}
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
                  className={`api-wb-base-url inline-flex h-8 max-w-[260px] flex-none cursor-pointer items-center gap-1.5 border-0 border-r border-r-[var(--srf-card-border)] bg-[var(--srf-hover)] px-2.5 py-0 font-mono text-[11px] text-[var(--srf-text-secondary)] disabled:cursor-not-allowed disabled:opacity-70${environmentPopoverOpen ? ' open' : ''}`}
                  disabled={!projectId || environments.length === 0}
                  title={selectedEnvironment?.baseUrl || '未选择环境'}
                >
                  <span className="api-wb-base-url-dot h-1.5 w-1.5 flex-none rounded-full bg-[var(--srf-result-passed)]" aria-hidden="true" />
                  <span className="api-wb-base-url-text overflow-hidden text-ellipsis whitespace-nowrap">
                    {selectedEnvironment?.baseUrl || (environmentsQuery.isLoading ? '加载环境中...' : '未选择环境')}
                  </span>
                  <DownOutlined className="api-wb-base-url-arrow flex-none text-[10px] text-[var(--srf-text-muted)]" />
                </button>
              </Popover>
              <span className="api-wb-url-divider hidden" aria-hidden="true" />
              <Form.Item name="path" className="api-wb-path min-w-0 flex-[1_1_auto] px-1" rules={[{ required: true, message: '请输入接口路径' }]}>
                <Input ref={pathInputRef} placeholder="/v1/example" maxLength={1024} />
              </Form.Item>
              <Tooltip title="路径不是 http:// 或 https:// 开头时，会自动拼接当前环境 Base URL。">
                <InfoCircleOutlined className="api-wb-url-info flex-none cursor-help px-2 text-[var(--srf-text-muted)]" />
              </Tooltip>
              <Tooltip title="复制请求地址">
                <Button
                  type="text"
                  size="small"
                  className="api-wb-copy-url mr-1 flex-none self-center"
                  aria-label="复制请求地址"
                  icon={<CopyOutlined />}
                  onClick={() => void copyRequestUrl()}
                />
              </Tooltip>
            </div>
            <div className="api-wb-request-actions flex flex-wrap items-center gap-2">
              <Button
                type="primary"
                className="api-wb-send"
                loading={runApiCaseMutation.isPending || isApiCaseRunInProgress}
                disabled={!isSelectedCaseReady || isApiCaseRunInProgress || selectedCaseInvalidated}
                onClick={handleSendRequest}
                icon={<SendOutlined />}
              >
                发送
              </Button>
              <ProjectActionButton operation="save" action="write"
                className="api-wb-save"
                icon={<SaveOutlined />}
                loading={saving}
                disabled={!isSelectedCaseReady}
                onClick={() => caseForm.submit()}
              >
                {dirty ? '保存更改' : '保存'}
              </ProjectActionButton>
            </div>
          </div>
        </div>
      </div>

      <Tabs
        className="api-wb-tabs px-4 [&>.ant-tabs-nav_.shared-tab-motion-indicator]:[clip-path:inset(3px_0_round_8px)]"
        activeKey={activeTabKey}
        onChange={setActiveTabKey}
        tabBarExtraContent={activeTabKey === 'body' ? (
          <span className="api-wb-tabs-extra">
            Content-Type:{' '}
            <span className="api-wb-tabs-extra-code rounded-[4px] bg-[var(--srf-chip)] px-1.5 py-px font-mono text-[var(--srf-chip-text)]">
              {bodyType === 'json' ? 'application/json' : bodyType === 'form' ? 'application/x-www-form-urlencoded' : '—'}
            </span>
          </span>
        ) : undefined}
        items={[
          {
            key: 'query',
            label: <TabLabel label="参数" count={queryCount} />,
            children: (
              <Form.List name="query">
                {(fields, { add, remove }) => (
                  <div className="api-wb-query-panel flex flex-col gap-4">
                    <section className="flex min-w-0 flex-col">
                      <div className={KV_SECTION_HEAD_CLASS}>
                        <div className="min-w-0">
                          <Text strong>Query 参数</Text>
                          <p className={KV_SECTION_HINT_CLASS}>
                            发送请求时会把启用的参数拼到 URL 查询串。
                          </p>
                        </div>
                        <span className={KV_SECTION_COUNT_CLASS}>
                          {queryCount} 个参数 · {enabledQueryCount} 个启用
                        </span>
                      </div>

                      {fields.length ? (
                        <div className={KV_TABLE_WRAP_CLASS}>
                          <table className={`api-wb-kv-table ${KV_TABLE_CLASS} max-[760.01px]:min-w-[620px]`}>
                            <thead>
                              <tr>
                                <th className={`${KV_HEAD_CELL_CENTER_CLASS} w-12`}>启用</th>
                                <th className={KV_HEAD_CELL_CLASS}>参数名</th>
                                <th className={KV_HEAD_CELL_CLASS}>参数值</th>
                                <th className={`${KV_HEAD_CELL_ACTION_CLASS} w-[52px]`} />
                              </tr>
                            </thead>
                            <tbody>
                              {fields.map((field, index) => {
                                const { key: fieldKey, ...fieldProps } = field

                                return (
                                  <tr key={fieldKey}>
                                    <td className={KV_BODY_CELL_CENTER_CLASS}>
                                      <Form.Item {...fieldProps} name={[field.name, 'enabled']} valuePropName="checked" className="api-wb-kv-check flex justify-center">
                                        <Checkbox aria-label={`启用参数${index + 1}`} />
                                      </Form.Item>
                                    </td>
                                    <td className={KV_BODY_CELL_CLASS}>
                                      <Form.Item {...fieldProps} name={[field.name, 'key']} className="api-wb-kv-item">
                                        <Input placeholder="参数名" aria-label={`参数名${index + 1}`} />
                                      </Form.Item>
                                    </td>
                                    <td className={KV_BODY_CELL_CLASS}>
                                      <div className="api-wb-kv-item flex items-center gap-1">
                                        <Form.Item {...fieldProps} name={[field.name, 'value']} noStyle>
                                          <Input
                                            ref={(node) => setEnvVarInputRef(`query:${field.key}:value`, node)}
                                            placeholder="参数值"
                                            aria-label={`参数值${index + 1}`}
                                          />
                                        </Form.Item>
                                        {renderEnvVarPicker({
                                          pickerKey: `query:${field.key}:value`,
                                          onInsert: (templateText) => insertTemplateText(['query', field.name, 'value'], `query:${field.key}:value`, templateText),
                                          trigger: <Button type="text" size="small" className="api-env-var-picker-trigger" style={{ width: 28, height: 28, padding: 0, borderRadius: 8 }} aria-label="插入环境变量" icon={<CodeOutlined />} />,
                                        })}
                                      </div>
                                    </td>
                                    <td className={KV_BODY_CELL_CLASS}>
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
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <div className={`api-wb-query-empty ${KV_EMPTY_CLASS}`}>
                          <ApiOutlined className={KV_EMPTY_ICON_CLASS} aria-hidden />
                          <div className={KV_EMPTY_TEXT_CLASS}>
                            <strong className={KV_EMPTY_TITLE_CLASS}>还没有 Query 参数</strong>
                            <span className={KV_EMPTY_HINT_CLASS}>点击下方按钮添加，发送请求时会作为查询条件。</span>
                          </div>
                        </div>
                      )}

                      <Button
                        className="api-wb-add-query mt-2 w-full"
                        type="dashed"
                        icon={<PlusOutlined />}
                        onClick={() => add({ enabled: true, key: '', value: '' })}
                      >
                        添加参数
                      </Button>
                    </section>

                    <section className="api-wb-case-description rounded-[var(--srf-radius-control)] border border-[var(--srf-card-border)] bg-[color-mix(in_srgb,var(--srf-hover)_42%,var(--srf-card))] px-3.5 py-3">
                      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold text-[var(--srf-text-secondary)]">
                        <FileTextOutlined aria-hidden />
                        用例说明
                      </div>
                      <p className="m-0 text-[12px] leading-5 text-[var(--srf-text-secondary)]">
                        {watchedDescription || editingCase?.description || '暂无说明'}
                      </p>
                    </section>
                  </div>
                )}
              </Form.List>
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
              <div className="api-case-settings-card rounded-[var(--srf-radius-control)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] p-4">
                <div className="api-case-settings-grid grid grid-cols-2 gap-x-4 gap-y-3 max-narrow:grid-cols-1">
                  <Form.Item name="timeoutMs" label="超时时间(ms)">
                    <InputNumber min={0} step={1000} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name="enabled" label="是否启用" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <Form.Item name="continueOnFailure" label="失败后继续" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <div />
                  <Form.Item name="description" label="用例描述" className="api-case-settings-description col-span-full max-narrow:col-span-1">
                    <Input.TextArea rows={6} maxLength={512} placeholder="补充这个用例验证的场景" />
                  </Form.Item>
                </div>
              </div>
            ),
          },
          {
            key: 'post-operations',
            label: <TabLabel label="后置操作" count={postOperationCount} />,
            children: activeCaseId ? (
              <div className="api-post-ops-section flex flex-col gap-3">
                <div className="api-post-ops-head flex flex-wrap items-start justify-between gap-2">
                  <div className="api-post-ops-head-main min-w-0">
                    <Text strong>后置操作</Text>
                    <div className="api-post-ops-subtitle mt-1 text-[11px] leading-[18px] text-[var(--srf-text-muted)]">统一管理断言与提取变量，提取结果会写回当前所选环境变量。</div>
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
                    <ProjectActionButton
                      action="write"
                      type="dashed"
                      className="api-post-ops-add-trigger"
                      icon={<PlusOutlined />}
                    >
                      添加后置操作
                    </ProjectActionButton>
                  </Dropdown>
                </div>

                {assertRulesQuery.isLoading || extractRulesQuery.isLoading ? (
                  <Empty description="后置操作加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : postOperationCount === 0 ? (
                  <div className={`api-rule-empty ${KV_EMPTY_CLASS}`}>
                    <ApiOutlined className={KV_EMPTY_ICON_CLASS} aria-hidden />
                    <div className={KV_EMPTY_TEXT_CLASS}>
                      <strong className={KV_EMPTY_TITLE_CLASS}>还没有后置操作</strong>
                      <span className={KV_EMPTY_HINT_CLASS}>点击右上方按钮添加断言或提取规则。</span>
                    </div>
                  </div>
                ) : (
                  <div className="api-post-ops-group-list flex flex-col gap-3.5">
                    <div className="api-post-ops-group rounded-[var(--srf-radius-control)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] p-3">
                      <div className="api-post-ops-group-title mb-2.5 flex items-center gap-2 text-[13px] font-semibold leading-5 text-[var(--srf-text)]">
                        <span>断言</span>
                        <Tag>{assertRules.length}</Tag>
                      </div>
                      {assertRules.length === 0 ? (
                        <div className="api-post-ops-empty px-0 pt-2 pb-0.5 text-[12px] leading-[18px] text-[var(--srf-text-muted)]">暂无断言规则</div>
                      ) : (
                        <div className="api-post-ops-items flex flex-col gap-2">
                          {assertRules.map((rule) => (
                            <div key={normalizeAssertRuleId(rule)} className="api-post-ops-item grid min-w-0 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-[var(--srf-radius-control)] border border-[var(--srf-card-border)] bg-[var(--srf-hover)] p-2.5 px-3 max-narrow:grid-cols-1 max-narrow:items-start">
                              <div className="api-post-ops-item-side flex items-center gap-2">
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
                              <div className="api-post-ops-item-main flex min-w-0 flex-col gap-1">
                                <div className="api-post-ops-item-title flex min-w-0 items-center gap-2 text-[13px] leading-5 text-[var(--srf-text)]">
                                  <strong className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">{rule.name}</strong>
                                  <span className="text-[12px] text-[var(--srf-text-muted)]">#{rule.orderNo ?? '-'}</span>
                                </div>
                                <div className="api-post-ops-item-meta flex flex-wrap gap-x-3 gap-y-2 text-[12px] leading-[18px] text-[var(--srf-text-muted)]">
                                  <span>{assertSourceLabelMap[rule.assertSource]}</span>
                                  <span>{assertComparatorLabelMap[rule.comparator]}</span>
                                  <span>{formatOptionalValue(rule.targetExpr)}</span>
                                  <span>{formatOptionalValue(rule.expectedValue)}</span>
                                </div>
                              </div>
                              <div className="api-post-ops-item-actions flex items-center gap-1 max-narrow:w-full max-narrow:justify-end">
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

                    <div className="api-post-ops-group rounded-[var(--srf-radius-control)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] p-3">
                      <div className="api-post-ops-group-title mb-2.5 flex items-center gap-2 text-[13px] font-semibold leading-5 text-[var(--srf-text)]">
                        <span>提取规则</span>
                        <Tag>{extractRules.length}</Tag>
                      </div>
                      {extractRules.length === 0 ? (
                        <div className="api-post-ops-empty px-0 pt-2 pb-0.5 text-[12px] leading-[18px] text-[var(--srf-text-muted)]">暂无提取规则</div>
                      ) : (
                        <div className="api-post-ops-items flex flex-col gap-2">
                          {extractRules.map((rule) => (
                            <div key={normalizeExtractRuleId(rule)} className="api-post-ops-item grid min-w-0 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-[var(--srf-radius-control)] border border-[var(--srf-card-border)] bg-[var(--srf-hover)] p-2.5 px-3 max-narrow:grid-cols-1 max-narrow:items-start">
                              <div className="api-post-ops-item-side flex items-center gap-2">
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
                              <div className="api-post-ops-item-main flex min-w-0 flex-col gap-1">
                                <div className="api-post-ops-item-title flex min-w-0 items-center gap-2 text-[13px] leading-5 text-[var(--srf-text)]">
                                  <strong className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">{rule.name}</strong>
                                  <span className="text-[12px] text-[var(--srf-text-muted)]">#{rule.orderNo ?? '-'}</span>
                                </div>
                                <div className="api-post-ops-item-meta flex flex-wrap gap-x-3 gap-y-2 text-[12px] leading-[18px] text-[var(--srf-text-muted)]">
                                  <span>{extractSourceLabelMap[rule.source]}</span>
                                  <span>{formatOptionalValue(rule.sourceExpr)}</span>
                                  <span>{formatOptionalValue(rule.varKey)}</span>
                                  <span>{formatOptionalValue(rule.defaultValue)}</span>
                                </div>
                              </div>
                              <div className="api-post-ops-item-actions flex items-center gap-1 max-narrow:w-full max-narrow:justify-end">
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
              <div className={`api-rule-empty ${KV_EMPTY_CLASS}`}>
                <ApiOutlined className={KV_EMPTY_ICON_CLASS} aria-hidden />
                <div className={KV_EMPTY_TEXT_CLASS}>
                  <strong className={KV_EMPTY_TITLE_CLASS}>请先保存当前用例</strong>
                  <span className={KV_EMPTY_HINT_CLASS}>保存后才能为这条用例配置断言与提取规则。</span>
                </div>
              </div>
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
    <span className="api-wb-tab-label inline-flex items-center gap-1.5">
      {label}
      {count > 0 ? <span className="api-wb-tab-count rounded-full bg-[var(--srf-chip)] px-[5px] font-mono text-[10px] leading-4 text-[var(--srf-text-secondary)]">{count}</span> : null}
      {dot ? <span className="api-wb-tab-dot h-1.5 w-1.5 rounded-full bg-[var(--srf-result-passed)]" aria-hidden="true" /> : null}
    </span>
  )
}
