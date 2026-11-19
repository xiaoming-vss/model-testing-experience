import { InterfaceFieldLabel } from './InterfaceFieldLabel'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Checkbox, Input, Select, Tooltip } from 'antd'
import type { InterfaceRow } from '../types'
import { blankRow, ROW_TYPES } from '../utils/interfaceForm'

type Props = {
  title: string
  hint: string
  location: 'path' | 'query'
  rows: InterfaceRow[]
  readOnly: boolean
  onChange: (rows: InterfaceRow[]) => void
}

export function InterfaceParamsPanel({ title, hint, location, rows, readOnly, onChange }: Props) {
  function update(index: number, patch: Partial<InterfaceRow>) {
    onChange(rows.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)))
  }

  return (
    <div className="if-param-group flex min-w-0 flex-col max-[760.01px]:overflow-x-auto">
      <div className="if-param-group-head mb-2 flex min-w-0 flex-wrap items-center gap-2">
        <InterfaceFieldLabel>{title}</InterfaceFieldLabel>
        <span className="if-field-hint text-[11px] leading-[18px] text-[var(--srf-text-muted)]">{hint}</span>
      </div>
      <table className="if-kv-table w-full table-fixed overflow-hidden rounded-[var(--srf-radius-control)] border border-separate border-spacing-0 border-[var(--srf-card-border)] max-[760.01px]:min-w-[720px] [&_tbody_tr:last-child_td]:border-b-0">
        <thead>
          <tr>
            <th className="if-col-enabled h-[34px] w-12 border-b border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-2 py-1.5 text-center text-[11px] font-semibold text-[var(--srf-list-header-text)]">启用</th>
            <th className="h-[34px] border-b border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-2 py-1.5 text-left text-[11px] font-semibold text-[var(--srf-list-header-text)]">参数名</th>
            <th className="if-col-type h-[34px] w-[106px] border-b border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-2 py-1.5 text-left text-[11px] font-semibold text-[var(--srf-list-header-text)]">类型</th>
            <th className="if-col-required h-[34px] w-[52px] border-b border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-2 py-1.5 text-center text-[11px] font-semibold text-[var(--srf-list-header-text)]">必填</th>
            <th className="h-[34px] border-b border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-2 py-1.5 text-left text-[11px] font-semibold text-[var(--srf-list-header-text)]">示例值</th>
            <th className="h-[34px] border-b border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-2 py-1.5 text-left text-[11px] font-semibold text-[var(--srf-list-header-text)]">说明</th>
            <th className="if-col-action h-[34px] w-[42px] border-b border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-2 py-1.5 text-left text-[11px] font-semibold text-[var(--srf-list-header-text)]" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${location}-${index}`}>
              <td className="border-b border-[var(--srf-divider)] px-1.5 py-[5px] text-center align-middle">
                <Checkbox
                  checked={row.enabled}
                  disabled={readOnly}
                  aria-label={`启用参数${row.name || index + 1}`}
                  onChange={event => update(index, { enabled: event.target.checked })}
                />
              </td>
              <td className="border-b border-[var(--srf-divider)] px-1.5 py-[5px] align-middle">
                <Input
                  value={row.name}
                  disabled={readOnly}
                  placeholder="参数名"
                  aria-label={`参数名${index + 1}`}
                  onChange={event => update(index, { name: event.target.value })}
                />
              </td>
              <td className="border-b border-[var(--srf-divider)] px-1.5 py-[5px] align-middle">
                <Select
                  value={row.type}
                  disabled={readOnly}
                  aria-label={`参数类型${index + 1}`}
                  options={ROW_TYPES.map(type => ({ label: type, value: type }))}
                  onChange={value => update(index, { type: value })}
                />
              </td>
              <td className="border-b border-[var(--srf-divider)] px-1.5 py-[5px] text-center align-middle">
                <Checkbox
                  checked={location === 'path' ? true : row.required}
                  disabled={readOnly || location === 'path'}
                  aria-label={`参数必填${index + 1}`}
                  onChange={event => update(index, { required: event.target.checked })}
                />
              </td>
              <td className="border-b border-[var(--srf-divider)] px-1.5 py-[5px] align-middle">
                <Input
                  value={row.example}
                  disabled={readOnly}
                  placeholder="示例值"
                  aria-label={`参数示例值${index + 1}`}
                  onChange={event => update(index, { example: event.target.value })}
                />
              </td>
              <td className="border-b border-[var(--srf-divider)] px-1.5 py-[5px] align-middle">
                <Input
                  value={row.description}
                  disabled={readOnly}
                  placeholder="说明"
                  aria-label={`参数说明${index + 1}`}
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
                      aria-label={`删除参数${row.name || index + 1}`}
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
              <td colSpan={7} className="if-empty-row h-[50px] px-1.5 py-[5px] text-center text-[12px] text-[var(--srf-text-muted)]">还没有参数</td>
            </tr>
          ) : null}
        </tbody>
      </table>
      {readOnly ? null : (
        <Button
          className="if-add-row mt-2 self-start"
          size="small"
          icon={<PlusOutlined />}
          onClick={() => onChange([...rows, blankRow()])}
        >
          添加参数
        </Button>
      )}
    </div>
  )
}
