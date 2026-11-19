import { InterfaceFieldLabel } from './InterfaceFieldLabel'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Checkbox, Input, Tooltip } from 'antd'
import type { InterfaceRow } from '../types'

type Props = {
  rows: InterfaceRow[]
  readOnly: boolean
  onChange: (rows: InterfaceRow[]) => void
}

const PRESETS: InterfaceRow[] = [
  {
    enabled: true,
    name: 'Authorization',
    type: 'string',
    required: true,
    example: 'Bearer {access_token}',
    description: '访问令牌',
  },
  {
    enabled: true,
    name: 'Content-Type',
    type: 'string',
    required: false,
    example: 'application/json',
    description: '请求体类型',
  },
]

export function InterfaceHeadersPanel({ rows, readOnly, onChange }: Props) {
  function update(index: number, patch: Partial<InterfaceRow>) {
    onChange(rows.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)))
  }

  function inject(preset: InterfaceRow) {
    if (rows.some(row => row.name.toLowerCase() === preset.name.toLowerCase())) return
    onChange([...rows, preset])
  }

  return (
    <div className="if-param-group flex min-w-0 flex-col max-[760.01px]:overflow-x-auto">
      <div className="if-param-group-head mb-2 flex min-w-0 flex-wrap items-center gap-2">
        <InterfaceFieldLabel>请求头</InterfaceFieldLabel>
        <span className="if-field-hint text-[11px] leading-[18px] text-[var(--srf-text-muted)]">请求头会随接口定义保存；导入时由文档字段覆盖。</span>
        {readOnly ? null : (
          <div className="if-quick-inject ms-auto inline-flex items-center gap-[5px] text-[11px] text-[var(--srf-text-muted)]">
            <span>快捷注入</span>
            {PRESETS.map(preset => (
              <Button
                key={preset.name}
                size="small"
                className="if-quick-pill"
                onClick={() => inject(preset)}
              >
                + {preset.name}
              </Button>
            ))}
          </div>
        )}
      </div>
      <table className="if-kv-table w-full table-fixed overflow-hidden rounded-[var(--srf-radius-control)] border border-separate border-spacing-0 border-[var(--srf-card-border)] max-[760.01px]:min-w-[720px] [&_tbody_tr:last-child_td]:border-b-0">
        <thead>
          <tr>
            <th className="if-col-enabled h-[34px] w-12 border-b border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-2 py-1.5 text-center text-[11px] font-semibold text-[var(--srf-list-header-text)]">启用</th>
            <th className="h-[34px] border-b border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-2 py-1.5 text-left text-[11px] font-semibold text-[var(--srf-list-header-text)]">Header Key</th>
            <th className="h-[34px] border-b border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-2 py-1.5 text-left text-[11px] font-semibold text-[var(--srf-list-header-text)]">Header Value</th>
            <th className="h-[34px] border-b border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-2 py-1.5 text-left text-[11px] font-semibold text-[var(--srf-list-header-text)]">说明</th>
            <th className="if-col-action h-[34px] w-[42px] border-b border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-2 py-1.5 text-left text-[11px] font-semibold text-[var(--srf-list-header-text)]" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`header-${index}`}>
              <td className="border-b border-[var(--srf-divider)] px-1.5 py-[5px] text-center align-middle">
                <Checkbox
                  checked={row.enabled}
                  disabled={readOnly}
                  aria-label={`启用请求头${row.name || index + 1}`}
                  onChange={event => update(index, { enabled: event.target.checked })}
                />
              </td>
              <td className="border-b border-[var(--srf-divider)] px-1.5 py-[5px] align-middle">
                <Input
                  value={row.name}
                  disabled={readOnly}
                  placeholder="Header Key"
                  aria-label={`Header Key ${index + 1}`}
                  onChange={event => update(index, { name: event.target.value })}
                />
              </td>
              <td className="border-b border-[var(--srf-divider)] px-1.5 py-[5px] align-middle">
                <Input
                  value={row.example}
                  disabled={readOnly}
                  placeholder="Header Value"
                  aria-label={`Header Value ${index + 1}`}
                  onChange={event => update(index, { example: event.target.value })}
                />
              </td>
              <td className="border-b border-[var(--srf-divider)] px-1.5 py-[5px] align-middle">
                <Input
                  value={row.description}
                  disabled={readOnly}
                  placeholder="说明"
                  aria-label={`请求头说明${index + 1}`}
                  onChange={event => update(index, { description: event.target.value })}
                />
              </td>
              <td className="border-b border-[var(--srf-divider)] px-1.5 py-[5px] align-middle">
                {readOnly ? null : (
                  <Tooltip title="删除">
                    <Button
                      type="text"
                      size="small"
                      danger
                      aria-label={`删除请求头${row.name || index + 1}`}
                      icon={<DeleteOutlined />}
                      onClick={() => onChange(rows.filter((_, rowIndex) => rowIndex !== index))}
                    />
                  </Tooltip>
                )}
              </td>
            </tr>
          ))}
          {!rows.length ? (
            <tr>
              <td colSpan={5} className="if-empty-row h-[50px] px-1.5 py-[5px] text-center text-[12px] text-[var(--srf-text-muted)]">还没有请求头</td>
            </tr>
          ) : null}
        </tbody>
      </table>
      {readOnly ? null : (
        <Button
          className="if-add-row mt-2 self-start"
          size="small"
          icon={<PlusOutlined />}
          onClick={() =>
            onChange([
              ...rows,
              {
                enabled: true,
                name: '',
                type: 'string',
                required: false,
                example: '',
                description: '',
              },
            ])
          }
        >
          添加请求头
        </Button>
      )}
    </div>
  )
}
