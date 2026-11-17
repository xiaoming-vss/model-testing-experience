import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Input, InputNumber, Select, Tooltip } from 'antd'
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

function updateAt<T>(items: T[], index: number, next: T): T[] {
  return items.map((item, itemIndex) => itemIndex === index ? next : item)
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
  return <label className="grid gap-1 text-xs text-app-surface-text-muted">
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

function HeaderRows({
  stepIndex,
  rows,
  disabled,
  onChange,
}: {
  stepIndex: number
  rows: PerfHeaderRow[]
  disabled?: boolean
  onChange: (rows: PerfHeaderRow[]) => void
}) {
  return <div className="grid gap-2">
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs font-semibold text-app-surface-text">请求头</span>
      <Button size="small" icon={<PlusOutlined />} disabled={disabled} onClick={() => onChange([...rows, createPerfHeaderRow()])}>添加</Button>
    </div>
    {rows.length === 0 ? <div className="text-xs text-app-surface-text-muted">暂无请求头</div> : rows.map((row, index) => (
      <div key={row.id} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] items-center gap-2">
        <Input
          aria-label={`步骤 ${stepIndex + 1} 请求头 ${index + 1} 名称`}
          size="small"
          placeholder="Header"
          value={row.name}
          disabled={disabled}
          onChange={event => onChange(updateAt(rows, index, { ...row, name: event.target.value }))}
        />
        <Input
          aria-label={`步骤 ${stepIndex + 1} 请求头 ${index + 1} 值`}
          size="small"
          placeholder="Value"
          value={row.value}
          disabled={disabled}
          onChange={event => onChange(updateAt(rows, index, { ...row, value: event.target.value }))}
        />
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
      </div>
    ))}
  </div>
}

function CheckRows({
  stepIndex,
  rows,
  disabled,
  onChange,
}: {
  stepIndex: number
  rows: PerfCheckRow[]
  disabled?: boolean
  onChange: (rows: PerfCheckRow[]) => void
}) {
  const update = (index: number, patch: Partial<PerfCheckRow>) => onChange(updateAt(rows, index, { ...rows[index], ...patch }))
  return <div className="grid gap-2">
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs font-semibold text-app-surface-text">响应校验</span>
      <Button size="small" icon={<PlusOutlined />} disabled={disabled} onClick={() => onChange([...rows, createPerfCheckRow()])}>添加</Button>
    </div>
    {rows.length === 0 ? <div className="text-xs text-app-surface-text-muted">暂无校验</div> : rows.map((row, index) => {
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
          <Tooltip title="删除校验">
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
  stepIndex,
  rows,
  disabled,
  onChange,
}: {
  stepIndex: number
  rows: PerfExtractRow[]
  disabled?: boolean
  onChange: (rows: PerfExtractRow[]) => void
}) {
  const update = (index: number, patch: Partial<PerfExtractRow>) => onChange(updateAt(rows, index, { ...rows[index], ...patch }))
  return <div className="grid gap-2">
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs font-semibold text-app-surface-text">提取变量</span>
      <Button size="small" icon={<PlusOutlined />} disabled={disabled} onClick={() => onChange([...rows, createPerfExtractRow()])}>添加</Button>
    </div>
    {rows.length === 0 ? <div className="text-xs text-app-surface-text-muted">暂无提取变量</div> : rows.map((row, index) => (
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
        <Tooltip title="删除提取变量">
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

export function PerfStepFields({
  step,
  stepIndex,
  variables,
  disabled = false,
  onChange,
}: {
  step: PerfStepFormValues
  stepIndex: number
  variables: string[]
  disabled?: boolean
  onChange: (patch: Partial<PerfStepFormValues>) => void
}) {
  return <div className="grid gap-4">
    <div className="grid grid-cols-1 gap-3 md:grid-cols-12">
      <label className="grid gap-1 text-xs text-app-surface-text-muted md:col-span-4">
        <span>步骤名称<span className="text-app-request-error-text"> *</span></span>
        <Input
          aria-label={`步骤 ${stepIndex + 1} 名称`}
          value={step.name}
          disabled={disabled}
          onChange={event => onChange({ name: event.target.value })}
        />
      </label>
      <label className="grid gap-1 text-xs text-app-surface-text-muted md:col-span-3">
        <span>请求方法</span>
        <Select
          aria-label={`步骤 ${stepIndex + 1} 请求方法`}
          value={step.method}
          disabled={disabled}
          options={(['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'] satisfies PerfHttpMethod[]).map(method => ({ value: method, label: method }))}
          onChange={method => onChange({ method })}
        />
      </label>
      <label className="grid gap-1 text-xs text-app-surface-text-muted md:col-span-5">
        <span>请求路径<span className="text-app-request-error-text"> *</span></span>
        <Input
          aria-label={`步骤 ${stepIndex + 1} 请求路径`}
          value={step.path}
          disabled={disabled}
          onChange={event => onChange({ path: event.target.value })}
        />
      </label>
      <label className="grid gap-1 text-xs text-app-surface-text-muted md:col-span-4">
        <span>失败后</span>
        <Select
          aria-label={`步骤 ${stepIndex + 1} 失败后`}
          value={step.onFailure}
          disabled={disabled}
          options={[
            { value: 'abort_iteration', label: '终止本次迭代' },
            { value: 'continue', label: '继续下一步' },
            { value: 'abort_test', label: '终止整个测试' },
          ]}
          onChange={onFailure => onChange({ onFailure })}
        />
      </label>
      <div className="md:col-span-2">
        <NumericInput
          label="思考时间（ms）"
          value={step.thinkTimeMs}
          disabled={disabled}
          onChange={thinkTimeMs => onChange({ thinkTimeMs })}
        />
      </div>
    </div>

    <div className="flex flex-wrap items-center gap-1.5 text-xs text-app-surface-text-muted">
      <span>可用变量：</span>
      {variables.length === 0
        ? <span>前面步骤提取的变量会在这里出现</span>
        : variables.map(name => <button
          key={name}
          type="button"
          className="rounded-md border border-app-accent-border bg-app-accent-surface px-1.5 py-0.5 font-mono text-[11px] text-app-accent"
          title="插入到请求路径"
          disabled={disabled}
          onClick={() => onChange({ path: `${step.path}{{var.${name}}}` })}
        >{`{{var.${name}}}`}</button>)}
      <span>· 仅当前用例 / 当前 VU / 当前迭代内有效</span>
    </div>

    <HeaderRows
      stepIndex={stepIndex}
      rows={step.headers}
      disabled={disabled}
      onChange={headers => onChange({ headers })}
    />

    <div className="grid gap-2">
      <span className="text-xs font-semibold text-app-surface-text">请求体</span>
      <div className="flex flex-wrap gap-1">
        {([['none', '无'], ['json', 'JSON'], ['text', '文本']] as const).map(([mode, label]) => (
          <Button
            key={mode}
            size="small"
            type={step.bodyMode === mode ? 'primary' : 'default'}
            disabled={disabled}
            onClick={() => onChange({ bodyMode: mode })}
          >{label}</Button>
        ))}
      </div>
      {step.bodyMode !== 'none' ? <Input.TextArea
        aria-label={`步骤 ${stepIndex + 1} 请求体`}
        className="font-mono text-xs"
        autoSize={{ minRows: 4, maxRows: 10 }}
        value={step.bodyText}
        disabled={disabled}
        onChange={event => onChange({ bodyText: event.target.value })}
      /> : null}
    </div>

    <CheckRows
      stepIndex={stepIndex}
      rows={step.checks}
      disabled={disabled}
      onChange={checks => onChange({ checks })}
    />

    <ExtractRows
      stepIndex={stepIndex}
      rows={step.extract}
      disabled={disabled}
      onChange={extract => onChange({ extract })}
    />
  </div>
}
