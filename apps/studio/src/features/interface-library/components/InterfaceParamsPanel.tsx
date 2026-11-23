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

  const enabled = rows.filter(row => row.enabled && row.name.trim()).length

  return (
    <div className="if-param-group flex min-w-0 flex-col">
      <div className={KV_SECTION_HEAD_CLASS}>
        <div className="min-w-0">
          <InterfaceFieldLabel>{title}</InterfaceFieldLabel>
          <p className={KV_SECTION_HINT_CLASS}>{hint}</p>
        </div>
        <span className={KV_SECTION_COUNT_CLASS}>
          {rows.length} 个参数 · {enabled} 个启用
        </span>
      </div>

      {rows.length ? (
        <div className={KV_TABLE_WRAP_CLASS}>
          <table className={`if-kv-table ${KV_TABLE_CLASS} max-[760.01px]:min-w-[720px]`}>
            <thead>
              <tr>
                <th className={`if-col-enabled ${KV_HEAD_CELL_CENTER_CLASS} w-12`}>启用</th>
                <th className={KV_HEAD_CELL_CLASS}>参数名</th>
                <th className={`if-col-type ${KV_HEAD_CELL_CLASS} w-[106px]`}>类型</th>
                <th className={`if-col-required ${KV_HEAD_CELL_CENTER_CLASS} w-[52px]`}>必填</th>
                <th className={KV_HEAD_CELL_CLASS}>示例值</th>
                <th className={KV_HEAD_CELL_CLASS}>说明</th>
                <th className={`if-col-action ${KV_HEAD_CELL_ACTION_CLASS} w-[42px]`} />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${location}-${index}`}>
                  <td className={KV_BODY_CELL_CENTER_CLASS}>
                    <Checkbox
                      checked={row.enabled}
                      disabled={readOnly}
                      aria-label={`启用参数${row.name || index + 1}`}
                      onChange={event => update(index, { enabled: event.target.checked })}
                    />
                  </td>
                  <td className={KV_BODY_CELL_CLASS}>
                    <Input
                      value={row.name}
                      disabled={readOnly}
                      placeholder="参数名"
                      aria-label={`参数名${index + 1}`}
                      onChange={event => update(index, { name: event.target.value })}
                    />
                  </td>
                  <td className={KV_BODY_CELL_CLASS}>
                    <Select
                      value={row.type}
                      disabled={readOnly}
                      aria-label={`参数类型${index + 1}`}
                      options={ROW_TYPES.map(type => ({ label: type, value: type }))}
                      onChange={value => update(index, { type: value })}
                    />
                  </td>
                  <td className={KV_BODY_CELL_CENTER_CLASS}>
                    <Checkbox
                      checked={location === 'path' ? true : row.required}
                      disabled={readOnly || location === 'path'}
                      aria-label={`参数必填${index + 1}`}
                      onChange={event => update(index, { required: event.target.checked })}
                    />
                  </td>
                  <td className={KV_BODY_CELL_CLASS}>
                    <Input
                      value={row.example}
                      disabled={readOnly}
                      placeholder="示例值"
                      aria-label={`参数示例值${index + 1}`}
                      onChange={event => update(index, { example: event.target.value })}
                    />
                  </td>
                  <td className={KV_BODY_CELL_CLASS}>
                    <Input
                      value={row.description}
                      disabled={readOnly}
                      placeholder="说明"
                      aria-label={`参数说明${index + 1}`}
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
                          aria-label={`删除参数${row.name || index + 1}`}
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
            <strong className={KV_EMPTY_TITLE_CLASS}>
              {location === 'path' ? '路径中没有占位符参数' : '还没有 Query 参数'}
            </strong>
            <span className={KV_EMPTY_HINT_CLASS}>
              {location === 'path'
                ? '在路径中使用 {id} 会自动生成 Path 参数。'
                : '添加后可在生成用例时作为查询条件。'}
            </span>
          </div>
        </div>
      )}

      {!readOnly && location === 'query' ? (
        <Button
          className="if-add-row mt-2 w-full"
          type="dashed"
          icon={<PlusOutlined />}
          onClick={() => onChange([...rows, blankRow()])}
        >
          添加参数
        </Button>
      ) : null}
    </div>
  )
}
