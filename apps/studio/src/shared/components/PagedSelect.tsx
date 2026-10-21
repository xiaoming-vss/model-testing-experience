import { Alert, Button, Select, Space, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { getErrorMessage } from '@/utils/format'

type Option = { label: string; value: string }
type Props = {
  id?: string
  'aria-label'?: string
  value?: string
  onChange?: (value?: string) => void
  placeholder?: string
  disabled?: boolean
  scopeKey: string
  queryKey: readonly unknown[]
  loadPage: (page: number, keyword: string) => Promise<{ items: Option[]; total: number; page: number }>
}

/** Search and page a remote option set without loading the whole collection. */
export function PagedSelect({ id, 'aria-label': ariaLabel, value, onChange, placeholder, disabled, scopeKey, queryKey, loadPage }: Props) {
  const [open, setOpen] = useState(false)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [keyword, setKeyword] = useState('')
  const [selectedLabel, setSelectedLabel] = useState<Option | null>(null)
  useEffect(() => {
    const timer = setTimeout(() => { setKeyword(search.trim()); setPage(1) }, 250)
    return () => clearTimeout(timer)
  }, [search])
  useEffect(() => { setSearch(''); setKeyword(''); setPage(1); setSelectedLabel(null) }, [scopeKey])
  useEffect(() => { if (disabled) setOpen(false) }, [disabled])
  const query = useQuery({
    queryKey: [...queryKey, scopeKey, keyword, page],
    queryFn: () => loadPage(page, keyword),
    enabled: open && !disabled,
  })
  const current = query.data?.page ?? page
  const total = query.data?.total ?? 0
  const options = query.data?.items ?? []
  return <Select<string> id={id} aria-label={ariaLabel}
    allowClear showSearch={{ filterOption: false, onSearch: setSearch, searchValue: search }}
    value={value} onChange={(next) => onChange?.(next)} placeholder={placeholder} disabled={disabled}
    open={open} onOpenChange={setOpen} loading={query.isFetching} options={options}
    onSelect={(next) => setSelectedLabel(options.find((option) => option.value === next) ?? null)}
    labelRender={(item) => selectedLabel?.value === item.value ? selectedLabel.label : item.label ?? item.value}
    onInputKeyDown={(event) => {
      if (event.key === 'PageDown' && !query.isFetching && current * 20 < total) { event.preventDefault(); setPage(current + 1) }
      if (event.key === 'PageUp' && !query.isFetching && current > 1) { event.preventDefault(); setPage(current - 1) }
    }}
    popupRender={(menu) => <div onMouseDown={(event) => event.preventDefault()}>
      {query.error ? <Alert type="error" title={getErrorMessage(query.error)} action={<Button onClick={() => void query.refetch()}>重试</Button>} /> : menu}
      <Space wrap className="tp-paged-select-footer" style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 4px' }}>
        <Typography.Text type="secondary">共 {total} 项 · 第 {current} 页</Typography.Text>
        <Space size={4}>
          <Button size="small" disabled={query.isFetching || current <= 1} onClick={() => setPage(current - 1)}>上一页</Button>
          <Button size="small" disabled={query.isFetching || current * 20 >= total} onClick={() => setPage(current + 1)}>下一页</Button>
        </Space>
      </Space>
    </div>}
  />
}
