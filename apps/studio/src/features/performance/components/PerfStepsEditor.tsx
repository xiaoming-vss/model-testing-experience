import { useMemo, useRef, useState } from 'react'
import {
  ArrowDownOutlined,
  ArrowLeftOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  CopyOutlined,
  CodeOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import { Button, Dropdown, Input, InputNumber, Modal, Popconfirm, Select, Space, Tabs, Tag, Tooltip } from 'antd'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { message } from '@/shared/utils/feedback'
import requestStyles from '@/shared/components/request-editor/request-editor.module.css'
import { RequestJsonValidity } from '@/shared/components/request-editor/RequestJsonValidity'
import { RequestBodyStatus } from '@/shared/components/request-editor/RequestBodyStatus'
import { RequestHeaderToolbar } from '@/shared/components/request-editor/RequestHeaderToolbar'
import { requestHeaderPresets } from '@/shared/components/request-editor/requestHeaderPresets'
import { RequestBodyToolbar, requestBodyVariableClass } from '@/shared/components/request-editor/RequestBodyToolbar'
import { JsonEditor, type JsonEditorCursor, type JsonEditorRef } from '@/shared/components/JsonEditor/JsonEditor'
import {
  createPerfCheckRow,
  createPerfExtractRow,
  createPerfHeaderRow,
  type PerfCheckOp,
  type PerfCheckRow,
  type PerfCheckType,
  type PerfExtractRow,
  type PerfExtractSource,
  type PerfHeaderRow,
  type PerfHttpMethod,
  type PerfStepFormValues,
} from '../utils/perfCaseForm'

const fieldLabelClass = 'grid gap-1 text-xs text-app-surface-text-muted'

const CHECK_TYPE_OPTIONS: { value: PerfCheckType; label: string }[] = [
  { value: 'status', label: '状态码' },
  { value: 'json', label: 'JSON 路径' },
  { value: 'header', label: '响应头' },
  { value: 'body', label: '响应体' },
]

const CHECK_OP_OPTIONS: { value: PerfCheckOp; label: string }[] = [
  { value: 'eq', label: '等于' },
  { value: 'ne', label: '不等于' },
  { value: 'exists', label: '存在' },
  { value: 'contains', label: '包含' },
  { value: 'regex', label: '正则' },
  { value: 'in', label: '属于' },
  { value: 'gte', label: '大于等于' },
  { value: 'lte', label: '小于等于' },
]

const STATUS_CHECK_OPS: PerfCheckOp[] = ['eq', 'ne', 'gte', 'lte']

const METHOD_OPTIONS = (['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'] satisfies PerfHttpMethod[])
  .map(method => ({ value: method, label: method }))

const BODY_MODES = [{ value: 'none', label: 'none' }, { value: 'json', label: 'JSON' }, { value: 'text', label: 'raw' }] as const

function updateAt<T>(items: T[], index: number, next: T): T[] {
  return items.map((item, itemIndex) => itemIndex === index ? next : item)
}

function isJsonText(value: string) {
  if (!value.trim()) return true
  try {
    JSON.parse(value)
    return true
  } catch {
    return false
  }
}

function NumericInput({
  label,
  value,
  min = 0,
  disabled,
  onChange,
}: {
  label: string
  value: number
  min?: number
  disabled?: boolean
  onChange: (value: number) => void
}) {
  return <label className={fieldLabelClass}>
    <span>{label}</span>
    <InputNumber
      aria-label={label}
      className="w-full"
      min={min}
      precision={0}
      value={value}
      disabled={disabled}
      onChange={next => onChange(typeof next === 'number' ? next : value)}
    />
  </label>
}

function CountBadge({ count }: { count: number }) {
  return <span className="inline-grid h-4 min-w-4 place-items-center rounded-full bg-app-surface-hover px-1 font-mono text-[9px] text-app-surface-text-muted">{count}</span>
}

function TabLabel({ label, count, dot }: { label: string; count?: number; dot?: boolean }) {
  return <span className="inline-flex items-center gap-1.5">
    {label}
    {count !== undefined && count > 0 ? <CountBadge count={count} /> : null}
    {dot ? <span className="h-1 w-1 rounded-full bg-app-accent" /> : null}
  </span>
}

function RequestHeadersPanel({
  stepIndex,
  rows,
  variables,
  disabled,
  onChange,
}: {
  stepIndex: number
  rows: PerfHeaderRow[]
  variables: string[]
  disabled?: boolean
  onChange: (rows: PerfHeaderRow[]) => void
}) {
  const [rawOpen, setRawOpen] = useState(false)
  const [rawText, setRawText] = useState('')
  const [draft, setDraft] = useState({ name: '', value: '' })
  const update = (index: number, patch: Partial<PerfHeaderRow>) =>
    onChange(updateAt(rows, index, { ...rows[index], ...patch }))

  function addHeader(preset?: { name: string; value: string }) {
    onChange([...rows, { ...createPerfHeaderRow(), ...preset }])
  }

  return <div className="flex min-w-0 flex-col">
    <RequestHeaderToolbar presets={requestHeaderPresets} disabled={disabled}
      onAdd={preset => addHeader({ name: preset.key, value: preset.value })}
      actions={<button type="button" disabled={disabled} className="inline-flex cursor-pointer items-center gap-1 rounded-[4px] border-0 bg-transparent px-2 py-1 text-[11px] leading-4 text-[var(--srf-text-secondary)] transition-colors hover:bg-[var(--srf-card)] hover:text-[var(--srf-accent-strong)] disabled:cursor-not-allowed disabled:opacity-45" onClick={() => {
        setRawText(rows.map(row => `${row.name}: ${row.value}`).join('\n'))
        setRawOpen(true)
      }}><CodeOutlined aria-hidden="true" />批量编辑 / 格式转换 (RAW)</button>} />

    <table className={`${requestStyles.headerTable} w-full table-fixed border-collapse`}>
      <colgroup>
        <col className="w-[26%]" />
        <col />
        <col className="w-[84px]" />
      </colgroup>
      <thead>
        <tr>
          <th>请求头名称 (Header Key)</th>
          <th>请求头值 (Header Value)</th>
          <th className="text-right">操作</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => <tr key={row.id} className="group hover:bg-[var(--srf-hover)]">
          <td>
            <Input
              aria-label={`步骤 ${stepIndex + 1} 请求头 ${index + 1} 名称`}
              className={`${requestStyles.headerInput} ${requestStyles.headerInputKey}`}
              placeholder="Header"
              value={row.name}
              disabled={disabled}
              onChange={event => update(index, { name: event.target.value })}
            />
          </td>
          <td>
            <div className="flex items-center gap-1">
            <Input
              aria-label={`步骤 ${stepIndex + 1} 请求头 ${index + 1} 值`}
              className={requestStyles.headerInput}
              placeholder="Value"
              value={row.value}
              disabled={disabled}
              onChange={event => update(index, { value: event.target.value })}
            />
            <Dropdown disabled={disabled || variables.length === 0} trigger={['click']} menu={{
              items: variables.map(name => ({ key: name, label: `{{var.${name}}}` })),
              onClick: ({ key }) => update(index, { value: `${row.value}{{var.${key}}}` }),
            }}><Button type="text" size="small" aria-label={`请求头 ${index + 1} 插入变量`} icon={<CodeOutlined />} disabled={disabled || variables.length === 0} /></Dropdown>
            </div>
          </td>
          <td className="text-right">
            <Tooltip title="复制请求头">
              <Button type="text" size="small" aria-label={`复制步骤 ${stepIndex + 1} 请求头 ${index + 1}`} icon={<CopyOutlined />}
                disabled={disabled} onClick={() => addHeader({ name: row.name, value: row.value })} />
            </Tooltip>
            <Tooltip title="删除请求头">
              <Button
                type="text"
                size="small"
                danger
                aria-label={`删除步骤 ${stepIndex + 1} 请求头 ${index + 1}`}
                icon={<DeleteOutlined />}
                disabled={disabled}
                onClick={() => onChange(rows.filter((_, rowIndex) => rowIndex !== index))}
              />
            </Tooltip>
          </td>
        </tr>)}
        <tr className="bg-[var(--srf-hover)]">
          <td><Input aria-label="添加请求头名称" className={`${requestStyles.headerInput} ${requestStyles.headerInputDraft}`} placeholder="添加新的请求头 (键)..." value={draft.name} disabled={disabled} onChange={event => setDraft({ ...draft, name: event.target.value })} onPressEnter={() => { if (draft.name.trim() || draft.value.trim()) { addHeader(draft); setDraft({ name: '', value: '' }) } }} /></td>
          <td><Input aria-label="添加请求头值" className={`${requestStyles.headerInput} ${requestStyles.headerInputDraft}`} placeholder="值 (支持 {{变量}} 语法)..." value={draft.value} disabled={disabled} onChange={event => setDraft({ ...draft, value: event.target.value })} onPressEnter={() => { if (draft.name.trim() || draft.value.trim()) { addHeader(draft); setDraft({ name: '', value: '' }) } }} /></td>
          <td className="px-1 text-right text-[11px] text-[var(--srf-text-muted)]">回车添加</td>
        </tr>
      </tbody>
    </table>

    <Modal title="批量编辑请求头" open={rawOpen} okText="应用" cancelText="取消" onCancel={() => setRawOpen(false)} onOk={() => {
      if (!rawText.trim()) { message.warning('批量编辑内容为空，已保留原有请求头'); setRawOpen(false); return }
      onChange(rawText.split('\n').map(line => line.trim()).filter(Boolean).map(line => {
        const separator = line.indexOf(':')
        return { ...createPerfHeaderRow(), name: (separator < 0 ? line : line.slice(0, separator)).trim(), value: separator < 0 ? '' : line.slice(separator + 1).trim() }
      }).filter(row => row.name))
      setRawOpen(false)
    }}>
      <p>每行一个请求头，格式为「名称: 值」；应用后按输入顺序替换当前请求头。</p>
      <Input.TextArea rows={8} aria-label="请求头批量编辑内容" value={rawText} onChange={event => setRawText(event.target.value)} />
    </Modal>
  </div>
}

function CheckRows({
  title = '断言',
  stepIndex,
  rows,
  disabled,
  onChange,
}: {
  title?: string
  stepIndex: number
  rows: PerfCheckRow[]
  disabled?: boolean
  onChange: (rows: PerfCheckRow[]) => void
}) {
  const update = (index: number, patch: Partial<PerfCheckRow>) => onChange(updateAt(rows, index, { ...rows[index], ...patch }))
  return <div className="grid gap-2">
    <div className="flex items-center justify-between gap-2">
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-app-surface-text">
        {title}<CountBadge count={rows.length} />
      </span>
      <Button size="small" icon={<PlusOutlined />} disabled={disabled} onClick={() => onChange([...rows, createPerfCheckRow()])}>添加</Button>
    </div>
    {rows.length === 0 ? <div className="rounded-lg border border-dashed border-app-surface-border px-3 py-4 text-center text-xs text-app-surface-text-muted">暂无断言</div> : rows.map((row, index) => {
      const needsPattern = row.op === 'regex' || row.op === 'contains'
      return <div key={row.id} className="grid gap-2 rounded-lg border border-app-surface-border bg-app-surface-hover p-2">
        <div className="flex flex-wrap items-center gap-2">
          <Select
            aria-label={`步骤 ${stepIndex + 1} 校验 ${index + 1} 类型`}
            size="small"
            className="w-32"
            value={row.type}
            disabled={disabled}
            options={CHECK_TYPE_OPTIONS}
            onChange={type => update(index, {
              type,
              op: type === 'status' && !STATUS_CHECK_OPS.includes(row.op) ? 'eq' : row.op,
              path: '',
              name: '',
            })}
          />
          <Select
            aria-label={`步骤 ${stepIndex + 1} 校验 ${index + 1} 操作符`}
            size="small"
            className="w-28"
            value={row.op}
            disabled={disabled}
            options={row.type === 'status'
              ? CHECK_OP_OPTIONS.filter(option => STATUS_CHECK_OPS.includes(option.value))
              : CHECK_OP_OPTIONS}
            onChange={op => update(index, { op })}
          />
          {row.type === 'json' ? <Input
            aria-label={`步骤 ${stepIndex + 1} 校验 ${index + 1} JSON 路径`}
            size="small"
            className="min-w-40 flex-1"
            placeholder="data.token"
            value={row.path}
            disabled={disabled}
            onChange={event => update(index, { path: event.target.value })}
          /> : null}
          {row.type === 'header' ? <Input
            aria-label={`步骤 ${stepIndex + 1} 校验 ${index + 1} 响应头名称`}
            size="small"
            className="min-w-40 flex-1"
            placeholder="Content-Type"
            value={row.name}
            disabled={disabled}
            onChange={event => update(index, { name: event.target.value })}
          /> : null}
          {needsPattern ? <Input
            aria-label={`步骤 ${stepIndex + 1} 校验 ${index + 1} 匹配内容`}
            size="small"
            className="min-w-40 flex-1"
            placeholder="匹配内容"
            value={row.pattern}
            disabled={disabled}
            onChange={event => update(index, { pattern: event.target.value })}
          /> : null}
          {!needsPattern && row.op !== 'exists' ? <Input
            aria-label={`步骤 ${stepIndex + 1} 校验 ${index + 1} 校验值`}
            size="small"
            className="min-w-28 flex-1"
            placeholder={row.type === 'status' ? '200' : '校验值'}
            value={row.value}
            disabled={disabled}
            onChange={event => update(index, { value: event.target.value })}
          /> : null}
          <Tooltip title="删除断言">
            <Button
              type="text"
              size="small"
              danger
              aria-label={`删除步骤 ${stepIndex + 1} 校验 ${index + 1}`}
              icon={<DeleteOutlined />}
              disabled={disabled}
              onClick={() => onChange(rows.filter((_, rowIndex) => rowIndex !== index))}
            />
          </Tooltip>
        </div>
      </div>
    })}
  </div>
}

function ExtractRows({
  title = '提取规则',
  stepIndex,
  rows,
  disabled,
  onChange,
}: {
  title?: string
  stepIndex: number
  rows: PerfExtractRow[]
  disabled?: boolean
  onChange: (rows: PerfExtractRow[]) => void
}) {
  const update = (index: number, patch: Partial<PerfExtractRow>) => onChange(updateAt(rows, index, { ...rows[index], ...patch }))
  return <div className="grid gap-2">
    <div className="flex items-center justify-between gap-2">
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-app-surface-text">
        {title}<CountBadge count={rows.length} />
      </span>
      <Button size="small" icon={<PlusOutlined />} disabled={disabled} onClick={() => onChange([...rows, createPerfExtractRow()])}>添加</Button>
    </div>
    {rows.length === 0 ? <div className="rounded-lg border border-dashed border-app-surface-border px-3 py-4 text-center text-xs text-app-surface-text-muted">暂无提取规则</div> : rows.map((row, index) => (
      <div key={row.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-app-surface-border bg-app-surface-hover p-2">
        <Input
          aria-label={`步骤 ${stepIndex + 1} 提取 ${index + 1} 变量名`}
          size="small"
          className="w-32"
          placeholder="token"
          value={row.name}
          disabled={disabled}
          onChange={event => update(index, { name: event.target.value })}
        />
        <Select
          aria-label={`步骤 ${stepIndex + 1} 提取 ${index + 1} 来源`}
          size="small"
          className="w-28"
          value={row.source}
          disabled={disabled}
          options={[
            { value: 'json', label: 'JSON 响应' },
            { value: 'header', label: '响应头' },
            { value: 'regex', label: '正则' },
          ] satisfies { value: PerfExtractSource; label: string }[]}
          onChange={source => update(index, { source })}
        />
        {row.source === 'regex' ? <>
          <Input
            aria-label={`步骤 ${stepIndex + 1} 提取 ${index + 1} 正则`}
            size="small"
            className="min-w-40 flex-1"
            placeholder="正则表达式"
            value={row.pattern}
            disabled={disabled}
            onChange={event => update(index, { pattern: event.target.value })}
          />
          <label className="grid w-20 gap-1 text-xs text-app-surface-text-muted">
            <span>分组</span>
            <InputNumber
              aria-label={`步骤 ${stepIndex + 1} 提取 ${index + 1} 分组`}
              className="w-full"
              min={0}
              precision={0}
              value={row.group}
              disabled={disabled}
              onChange={group => update(index, { group: typeof group === 'number' ? group : row.group })}
            />
          </label>
        </> : <Input
          aria-label={`步骤 ${stepIndex + 1} 提取 ${index + 1} 路径`}
          size="small"
          className="min-w-40 flex-1"
          placeholder={row.source === 'header' ? '响应头名称' : 'data.token'}
          value={row.path}
          disabled={disabled}
          onChange={event => update(index, { path: event.target.value })}
        />}
        <Tooltip title="删除提取规则">
          <Button
            type="text"
            size="small"
            danger
            aria-label={`删除步骤 ${stepIndex + 1} 提取 ${index + 1}`}
            icon={<DeleteOutlined />}
            disabled={disabled}
            onClick={() => onChange(rows.filter((_, rowIndex) => rowIndex !== index))}
          />
        </Tooltip>
      </div>
    ))}
  </div>
}

export function PerfStepEditor({
  className,
  step,
  stepIndex,
  stepCount,
  variables,
  projectId,
  environmentName,
  environmentBaseUrl,
  canWrite,
  dirty,
  saving,
  errors,
  errorsAlert,
  onBack,
  onMove,
  onDelete,
  onCancel,
  onSave,
  onChange,
}: {
  className?: string
  step: PerfStepFormValues
  stepIndex: number
  stepCount: number
  variables: string[]
  projectId?: string
  environmentName?: string
  environmentBaseUrl?: string
  canWrite: boolean
  dirty: boolean
  saving: boolean
  errors: string[]
  errorsAlert: React.ReactNode
  onBack: () => void
  onMove: (offset: 1 | -1) => void
  onDelete: () => void
  onCancel: () => void
  onSave: () => void
  onChange: (patch: Partial<PerfStepFormValues>) => void
}) {
  const [activeTab, setActiveTab] = useState('headers')
  const bodyEditorRef = useRef<JsonEditorRef>(null)
  const [bodyCursor, setBodyCursor] = useState<JsonEditorCursor>({ line: 1, column: 1 })
  const bodyHasContent = step.bodyMode !== 'none'
  const postCount = step.checks.length + step.extract.length
  const jsonInvalid = useMemo(
    () => step.bodyMode === 'json' && !isJsonText(step.bodyText),
    [step.bodyMode, step.bodyText],
  )

  function formatBody() {
    try {
      onChange({ bodyText: JSON.stringify(JSON.parse(step.bodyText || '{}'), null, 2) })
    } catch {
      message.warning('当前请求体不是合法 JSON，无法格式化')
    }
  }

  function compressBody() {
    try {
      onChange({ bodyText: JSON.stringify(JSON.parse(step.bodyText || '{}')) })
    } catch {
      message.warning('当前请求体不是合法 JSON，无法压缩')
    }
  }

  const tabs = [
    {
      key: 'headers',
      label: <TabLabel label="请求头" count={step.headers.length} />,
      children: <RequestHeadersPanel
        stepIndex={stepIndex}
        rows={step.headers}
        variables={variables}
        disabled={!canWrite}
        onChange={headers => onChange({ headers })}
      />,
    },
    {
      key: 'body',
      label: <TabLabel label="请求体" dot={bodyHasContent} />,
      children: <div className={`${requestStyles.body} flex min-w-0 flex-col`} data-tab-motion-scope>
        <RequestBodyToolbar options={BODY_MODES} value={step.bodyMode} onChange={bodyMode => onChange({ bodyMode })}
          disabled={!canWrite} json={step.bodyMode === 'json'} onFormat={formatBody} onCompress={compressBody}
          variableControl={step.bodyMode === 'json' ? <Dropdown disabled={!canWrite || variables.length === 0} trigger={['click']} menu={{
            items: variables.map(name => ({ key: name, label: `{{var.${name}}}` })),
            onClick: ({ key }) => bodyEditorRef.current?.insertText(`{{var.${key}}}`),
          }}><button type="button" className={requestBodyVariableClass} disabled={!canWrite || variables.length === 0}><CodeOutlined aria-hidden="true" />插入变量 {'{{var}}'}</button></Dropdown> : null}
          validity={step.bodyMode === 'json' ? <RequestJsonValidity valid={!jsonInvalid} /> : null} />
        <div data-tab-motion-panel>
          {step.bodyMode === 'none' ? <div className="px-4 py-8 text-center text-xs text-app-surface-text-muted">当前请求没有请求体</div>
            : step.bodyMode === 'json' ? <JsonEditor ref={bodyEditorRef} value={step.bodyText} onChange={bodyText => onChange({ bodyText })} readOnly={!canWrite} minHeight={260} toolbar={null} onCursorChange={setBodyCursor} ariaLabel={`步骤 ${stepIndex + 1} 请求体`} />
              : <Input.TextArea aria-label={`步骤 ${stepIndex + 1} 请求体`} className="font-mono text-xs" autoSize={{ minRows: 8, maxRows: 18 }} value={step.bodyText} disabled={!canWrite} onChange={event => onChange({ bodyText: event.target.value })} />}
        </div>
        <RequestBodyStatus json={step.bodyMode === 'json'} valid={!jsonInvalid} value={step.bodyMode === 'none' ? '' : step.bodyText} cursor={<span className="font-mono">行 {bodyCursor.line}, 列 {bodyCursor.column} (光标聚焦)</span>} />
      </div>,
    },
    {
      key: 'post',
      label: <TabLabel label="后置操作" count={postCount} />,
      children: <div className="grid gap-4 px-4 pt-3 pb-4">
        <div>
          <div className="text-xs font-bold text-app-surface-text">后置操作</div>
          <div className="mt-0.5 text-[11px] text-app-surface-text-muted">统一管理断言与提取规则，提取结果供后续步骤使用。</div>
        </div>
        <CheckRows
          title="断言"
          stepIndex={stepIndex}
          rows={step.checks}
          disabled={!canWrite}
          onChange={checks => onChange({ checks })}
        />
        <ExtractRows
          title="提取规则"
          stepIndex={stepIndex}
          rows={step.extract}
          disabled={!canWrite}
          onChange={extract => onChange({ extract })}
        />
      </div>,
    },
    {
      key: 'settings',
      label: '设置',
      children: <div className="grid gap-3 px-4 pt-3 pb-4 md:grid-cols-2">
        <label className={fieldLabelClass}>
          <span>预期状态码（留空接受所有 2xx）</span>
          <Select mode="tags" value={step.expectedStatuses.map(String)} disabled={!canWrite}
            tokenSeparators={[',']} placeholder="例如 200, 202"
            onChange={(values: string[]) => onChange({ expectedStatuses: values.map(Number) })} />
        </label>
        <label className={fieldLabelClass}>
          <span>失败后</span>
          <Select
            aria-label={`步骤 ${stepIndex + 1} 失败后`}
            value={step.onFailure}
            disabled={!canWrite}
            options={[
              { value: 'abort_iteration', label: '终止本次迭代' },
              { value: 'continue', label: '继续下一步' },
              { value: 'abort_test', label: '终止整个测试' },
            ]}
            onChange={onFailure => onChange({ onFailure })}
          />
        </label>
        <NumericInput
          label="思考时间（ms）"
          value={step.thinkTimeMs}
          disabled={!canWrite}
          onChange={thinkTimeMs => onChange({ thinkTimeMs })}
        />
        <div className="text-[11px] text-app-surface-text-muted md:col-span-2">
          失败策略只影响当前步骤；思考时间作用于本步骤结束后、下一步骤开始前。
        </div>
      </div>,
    },
  ]

  const tabBarExtraContent = activeTab === 'headers'
    ? <span className="text-[11px] text-app-surface-text-muted">已配置 {step.headers.length} 个</span>
    : activeTab === 'body'
      ? <span className="text-[11px] text-app-surface-text-muted">Content-Type: <span className="font-mono">{step.bodyMode === 'json' ? 'application/json' : step.bodyMode === 'text' ? 'text/plain' : '—'}</span></span>
      : activeTab === 'post'
        ? <span className="text-[11px] text-app-surface-text-muted">断言 {step.checks.length} · 提取 {step.extract.length}</span>
        : null

  return <div className={`flex h-full min-h-0 flex-col overflow-hidden rounded-[var(--app-panel-radius)] border border-app-surface-border bg-app-surface ${className ?? ''}`}>
    <div className="flex-none">
      <div className="flex flex-wrap items-center gap-3 px-4 py-2.5">
        <Button type="text" size="small" icon={<ArrowLeftOutlined />} aria-label="返回用例" onClick={onBack} />
        <label className="flex items-center gap-2 text-xs text-app-surface-text-muted">
          <span className="shrink-0 whitespace-nowrap">步骤名称<span className="text-app-request-error-text"> *</span></span>
          <Input
            className="w-[260px]"
            aria-label={`步骤 ${stepIndex + 1} 名称`}
            value={step.name}
            status={step.name.trim() ? undefined : 'error'}
            disabled={!canWrite}
            onChange={event => onChange({ name: event.target.value })}
          />
        </label>
        {dirty ? <Tag color="warning" className="m-0">有未保存修改</Tag> : null}
        <Space size={4} className="ml-auto" wrap>
          <Tooltip title="上移接口">
            <Button size="small" type="text" icon={<ArrowUpOutlined />} aria-label="上移接口" disabled={!canWrite || stepIndex === 0} onClick={() => onMove(-1)} />
          </Tooltip>
          <Tooltip title="下移接口">
            <Button size="small" type="text" icon={<ArrowDownOutlined />} aria-label="下移接口" disabled={!canWrite || stepIndex === stepCount - 1} onClick={() => onMove(1)} />
          </Tooltip>
          <Popconfirm
            title="删除这个接口？"
            okText="删除"
            cancelText="取消"
            disabled={!canWrite}
            onConfirm={onDelete}
          >
            <Tooltip title="删除接口">
              <Button size="small" type="text" danger icon={<DeleteOutlined />} aria-label="删除接口" disabled={!canWrite} />
            </Tooltip>
          </Popconfirm>
          <Button size="small" onClick={onCancel} disabled={!dirty}>取消</Button>
        </Space>
      </div>

      <div className="flex flex-wrap items-center gap-2 bg-app-surface-hover px-4 py-2.5">
        <Select
          aria-label={`步骤 ${stepIndex + 1} 请求方法`}
          className="w-[108px] shrink-0"
          value={step.method}
          disabled={!canWrite}
          options={METHOD_OPTIONS}
          onChange={method => onChange({ method })}
        />
        <div className="flex min-w-0 flex-1 items-stretch overflow-hidden rounded-lg border border-app-surface-border bg-app-surface focus-within:border-app-accent-border focus-within:shadow-[0_0_0_3px_var(--app-accent-surface)]">
          <span
            className="inline-flex max-w-[240px] shrink-0 items-center gap-1.5 border-r border-app-surface-border bg-app-surface-hover px-2.5 font-mono text-[11px] text-app-surface-text-muted"
            title={environmentBaseUrl ? `运行环境：${environmentName ?? ''} ${environmentBaseUrl}` : '未选择运行环境'}
          >
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${environmentBaseUrl ? 'bg-[var(--srf-result-passed)]' : 'bg-[var(--srf-result-skipped)]'}`} aria-hidden="true" />
            <span className="truncate">{environmentBaseUrl || '未选择运行环境'}</span>
          </span>
          <Input
            variant="borderless"
            aria-label={`步骤 ${stepIndex + 1} 请求路径`}
            className="min-w-0 flex-1 font-mono text-[11.5px]"
            value={step.path}
            disabled={!canWrite}
            onChange={event => onChange({ path: event.target.value })}
          />
          <Tooltip title="相对路径会拼接运行环境的 baseUrl；支持 {{env.变量}} 和 {{var.变量}} 占位符">
            <span className="grid w-8 shrink-0 cursor-help place-items-center text-app-surface-text-muted"><InfoCircleOutlined /></span>
          </Tooltip>
          <Dropdown
            disabled={!canWrite || variables.length === 0}
            trigger={['click']}
            menu={{
              items: variables.map(name => ({ key: name, label: `{{var.${name}}}` })),
              onClick: ({ key }) => onChange({ path: `${step.path}{{var.${key}}}` }),
            }}
          >
            <Button
              type="text"
              size="small"
              aria-label="插入提取变量"
              title={variables.length
                ? '插入前序步骤提取的变量；仅当前用例 / 当前 VU / 当前迭代内有效'
                : '前面步骤还没有提取变量'}
              disabled={!canWrite || variables.length === 0}
              className="mx-1 shrink-0 px-1 font-mono text-[10px] text-app-surface-text-muted"
            >
              {'{ }'}
            </Button>
          </Dropdown>
        </div>
        <ProjectActionButton
          action="write"
          projectId={projectId}
          type="primary"
          className="shrink-0"
          operation="save"
          icon={<SaveOutlined />}
          disabled={!dirty || errors.length > 0 || saving || !canWrite}
          loading={saving}
          onClick={onSave}
        >
          保存用例
        </ProjectActionButton>
      </div>
    </div>

    {errorsAlert ? <div className="flex-none border-b border-[var(--app-surface-divider)] px-4 py-3">{errorsAlert}</div> : null}

    <Tabs
      className="flex min-h-0 flex-1 flex-col pt-1 [&>.ant-tabs-nav]:px-4 [&>.ant-tabs-nav_.ant-tabs-tab]:px-2 [&>.ant-tabs-nav_.ant-tabs-tab+.ant-tabs-tab]:ml-1 [&_.ant-tabs-content-holder]:min-h-0 [&_.ant-tabs-content-holder]:flex-1 [&_.ant-tabs-content-holder]:overflow-auto [&_.ant-tabs-nav]:mb-0 [&_.ant-tabs-nav]:flex-none [&>.ant-tabs-nav_.shared-tab-motion-indicator]:[clip-path:inset(7px_0_round_8px)]"
      activeKey={activeTab}
      onChange={setActiveTab}
      tabBarExtraContent={tabBarExtraContent}
      items={tabs}
    />
  </div>
}
