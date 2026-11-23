import { InterfaceFieldLabel } from './InterfaceFieldLabel'
import { ApiOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons'
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
    <div className="if-param-group flex min-w-0 flex-col">
      <div className={KV_SECTION_HEAD_CLASS}>
        <div className="min-w-0">
          <InterfaceFieldLabel>请求头</InterfaceFieldLabel>
          <p className={KV_SECTION_HINT_CLASS}>请求头会随接口定义保存；导入时由文档字段覆盖。</p>
        </div>
        <div className="flex flex-none flex-wrap items-center gap-2">
          <span className={KV_SECTION_COUNT_CLASS}>{rows.length} 个请求头</span>
          {readOnly ? null : (
            <div className="if-quick-inject inline-flex items-center gap-[5px] text-[11px] text-[var(--srf-text-muted)]">
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
      </div>

      {rows.length ? (
        <div className={KV_TABLE_WRAP_CLASS}>
          <table className={`if-kv-table ${KV_TABLE_CLASS} max-[760.01px]:min-w-[720px]`}>
            <thead>
              <tr>
                <th className={`if-col-enabled ${KV_HEAD_CELL_CENTER_CLASS} w-12`}>启用</th>
                <th className={KV_HEAD_CELL_CLASS}>Header Key</th>
                <th className={KV_HEAD_CELL_CLASS}>Header Value</th>
                <th className={KV_HEAD_CELL_CLASS}>说明</th>
                <th className={`if-col-action ${KV_HEAD_CELL_ACTION_CLASS} w-[42px]`} />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`header-${index}`}>
                  <td className={KV_BODY_CELL_CENTER_CLASS}>
                    <Checkbox
                      checked={row.enabled}
                      disabled={readOnly}
                      aria-label={`启用请求头${row.name || index + 1}`}
                      onChange={event => update(index, { enabled: event.target.checked })}
                    />
                  </td>
                  <td className={KV_BODY_CELL_CLASS}>
                    <Input
                      value={row.name}
                      disabled={readOnly}
                      placeholder="Header Key"
                      aria-label={`Header Key ${index + 1}`}
                      onChange={event => update(index, { name: event.target.value })}
                    />
                  </td>
                  <td className={KV_BODY_CELL_CLASS}>
                    <Input
                      value={row.example}
                      disabled={readOnly}
                      placeholder="Header Value"
                      aria-label={`Header Value ${index + 1}`}
                      onChange={event => update(index, { example: event.target.value })}
                    />
                  </td>
                  <td className={KV_BODY_CELL_CLASS}>
                    <Input
                      value={row.description}
                      disabled={readOnly}
                      placeholder="说明"
                      aria-label={`请求头说明${index + 1}`}
                      onChange={event => update(index, { description: event.target.value })}
                    />
                  </td>
                  <td className={KV_BODY_CELL_CLASS}>
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
            </tbody>
          </table>
        </div>
      ) : (
        <div className={KV_EMPTY_CLASS}>
          <ApiOutlined className={KV_EMPTY_ICON_CLASS} aria-hidden />
          <div className={KV_EMPTY_TEXT_CLASS}>
            <strong className={KV_EMPTY_TITLE_CLASS}>还没有请求头</strong>
            <span className={KV_EMPTY_HINT_CLASS}>可添加 Authorization、Content-Type 等请求头，生成用例时会随请求带入。</span>
          </div>
        </div>
      )}

      {readOnly ? null : (
        <Button
          className="if-add-row mt-2 w-full"
          type="dashed"
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
