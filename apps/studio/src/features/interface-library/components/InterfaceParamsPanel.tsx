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
    <div className="if-param-group">
      <div className="if-param-group-head">
        <span className="if-field-label">{title}</span>
        <span className="if-field-hint">{hint}</span>
      </div>
      <table className="if-kv-table">
        <thead>
          <tr>
            <th className="if-col-enabled">启用</th>
            <th>参数名</th>
            <th className="if-col-type">类型</th>
            <th className="if-col-required">必填</th>
            <th>示例值</th>
            <th>说明</th>
            <th className="if-col-action" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${location}-${index}`}>
              <td>
                <Checkbox
                  checked={row.enabled}
                  disabled={readOnly}
                  aria-label={`启用参数${row.name || index + 1}`}
                  onChange={event => update(index, { enabled: event.target.checked })}
                />
              </td>
              <td>
                <Input
                  value={row.name}
                  disabled={readOnly}
                  placeholder="参数名"
                  aria-label={`参数名${index + 1}`}
                  onChange={event => update(index, { name: event.target.value })}
                />
              </td>
              <td>
                <Select
                  value={row.type}
                  disabled={readOnly}
                  aria-label={`参数类型${index + 1}`}
                  options={ROW_TYPES.map(type => ({ label: type, value: type }))}
                  onChange={value => update(index, { type: value })}
                />
              </td>
              <td>
                <Checkbox
                  checked={location === 'path' ? true : row.required}
                  disabled={readOnly || location === 'path'}
                  aria-label={`参数必填${index + 1}`}
                  onChange={event => update(index, { required: event.target.checked })}
                />
              </td>
              <td>
                <Input
                  value={row.example}
                  disabled={readOnly}
                  placeholder="示例值"
                  aria-label={`参数示例值${index + 1}`}
                  onChange={event => update(index, { example: event.target.value })}
                />
              </td>
              <td>
                <Input
                  value={row.description}
                  disabled={readOnly}
                  placeholder="说明"
                  aria-label={`参数说明${index + 1}`}
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
              <td colSpan={7} className="if-empty-row">还没有参数</td>
            </tr>
          ) : null}
        </tbody>
      </table>
      {readOnly ? null : (
        <Button
          className="if-add-row"
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
