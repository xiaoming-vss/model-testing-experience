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
    <div className="if-param-group">
      <div className="if-param-group-head">
        <span className="if-field-label">请求头</span>
        <span className="if-field-hint">请求头会随接口定义保存；导入时由文档字段覆盖。</span>
        {readOnly ? null : (
          <div className="if-quick-inject">
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
      <table className="if-kv-table">
        <thead>
          <tr>
            <th className="if-col-enabled">启用</th>
            <th>Header Key</th>
            <th>Header Value</th>
            <th>说明</th>
            <th className="if-col-action" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`header-${index}`}>
              <td>
                <Checkbox
                  checked={row.enabled}
                  disabled={readOnly}
                  aria-label={`启用请求头${row.name || index + 1}`}
                  onChange={event => update(index, { enabled: event.target.checked })}
                />
              </td>
              <td>
                <Input
                  value={row.name}
                  disabled={readOnly}
                  placeholder="Header Key"
                  aria-label={`Header Key ${index + 1}`}
                  onChange={event => update(index, { name: event.target.value })}
                />
              </td>
              <td>
                <Input
                  value={row.example}
                  disabled={readOnly}
                  placeholder="Header Value"
                  aria-label={`Header Value ${index + 1}`}
                  onChange={event => update(index, { example: event.target.value })}
                />
              </td>
              <td>
                <Input
                  value={row.description}
                  disabled={readOnly}
                  placeholder="说明"
                  aria-label={`请求头说明${index + 1}`}
                  onChange={event => update(index, { description: event.target.value })}
                />
              </td>
              <td>
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
              <td colSpan={5} className="if-empty-row">还没有请求头</td>
            </tr>
          ) : null}
        </tbody>
      </table>
      {readOnly ? null : (
        <Button
          className="if-add-row"
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
