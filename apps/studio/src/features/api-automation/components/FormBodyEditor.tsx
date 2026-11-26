import { useEffect, useRef, useState } from 'react'
import { ApiOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Input, Tooltip } from 'antd'
import {
  KV_BODY_CELL_CLASS,
  KV_EMPTY_CLASS,
  KV_EMPTY_HINT_CLASS,
  KV_EMPTY_ICON_CLASS,
  KV_EMPTY_TEXT_CLASS,
  KV_EMPTY_TITLE_CLASS,
  KV_HEAD_CELL_ACTION_CLASS,
  KV_HEAD_CELL_CLASS,
  KV_SECTION_HINT_CLASS,
  KV_TABLE_CLASS,
  KV_TABLE_WRAP_CLASS,
} from '@/shared/ui/keyValueTable'

type FormRow = { key: string; value: string }

function parseRows(value?: string): FormRow[] {
  try {
    const parsed: unknown = JSON.parse(value || '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return []
    return Object.entries(parsed).map(([key, item]) => ({
      key,
      value: typeof item === 'string' ? item : JSON.stringify(item),
    }))
  } catch {
    return []
  }
}

function serializeRows(rows: FormRow[]) {
  return JSON.stringify(Object.fromEntries(rows.map((row) => [row.key.trim(), row.value])))
}

/** x-www-form-urlencoded body editor; the form value stays a JSON object string. */
export function FormBodyEditor({ value, onChange }: { value?: string; onChange?: (value: string) => void }) {
  const [rows, setRows] = useState<FormRow[]>(() => parseRows(value))
  const lastEmitted = useRef(value ?? '')
  useEffect(() => {
    if (value !== lastEmitted.current) {
      setRows(parseRows(value))
      lastEmitted.current = value ?? ''
    }
  }, [value])

  function commit(next: FormRow[]) {
    setRows(next)
    const serialized = serializeRows(next.filter((row) => row.key.trim()))
    lastEmitted.current = serialized
    onChange?.(serialized)
  }

  function update(index: number, patch: Partial<FormRow>) {
    commit(rows.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)))
  }

  return <div className="api-form-body flex min-w-0 flex-col px-4 py-3">
    <p className={KV_SECTION_HINT_CLASS}>表单字段以 JSON 对象保存，沿用请求体的 {'{{变量}}'} 模板。</p>
    {rows.length ? <div className={KV_TABLE_WRAP_CLASS}>
      <table className={`api-form-table ${KV_TABLE_CLASS}`}>
        <thead><tr>
          <th className={KV_HEAD_CELL_CLASS}>字段名</th>
          <th className={KV_HEAD_CELL_CLASS}>值</th>
          <th className={`${KV_HEAD_CELL_ACTION_CLASS} w-[42px]`} />
        </tr></thead>
        <tbody>{rows.map((row, index) => <tr key={index}>
          <td className={KV_BODY_CELL_CLASS}><Input value={row.key} placeholder="字段名"
            aria-label={`表单字段名${index + 1}`} onChange={(event) => update(index, { key: event.target.value })} /></td>
          <td className={KV_BODY_CELL_CLASS}><Input value={row.value} placeholder="值"
            aria-label={`表单字段值${index + 1}`} onChange={(event) => update(index, { value: event.target.value })} /></td>
          <td className={KV_BODY_CELL_CLASS}>
            <Tooltip title="删除"><Button type="text" size="small" danger icon={<DeleteOutlined />}
              aria-label={`删除表单字段${row.key || index + 1}`}
              onClick={() => commit(rows.filter((_, rowIndex) => rowIndex !== index))} /></Tooltip>
          </td>
        </tr>)}</tbody>
      </table>
    </div> : <div className={KV_EMPTY_CLASS}>
      <ApiOutlined className={KV_EMPTY_ICON_CLASS} aria-hidden />
      <div className={KV_EMPTY_TEXT_CLASS}>
        <strong className={KV_EMPTY_TITLE_CLASS}>还没有表单字段</strong>
        <span className={KV_EMPTY_HINT_CLASS}>添加字段后按 x-www-form-urlencoded 提交。</span>
      </div>
    </div>}
    <Button className="mt-2 w-full" type="dashed" icon={<PlusOutlined />}
      onClick={() => setRows([...rows, { key: '', value: '' }])}>添加字段</Button>
  </div>
}
