import { useState, type ReactNode } from 'react'
import { FileTextOutlined } from '@ant-design/icons'
import { Empty, Input, Select } from 'antd'

type AnalysisEntry = {
  key: string
  title: string
  code?: string
  searchText: string
  status?: 'ready' | 'blocked' | 'unknown'
  badge?: ReactNode
  content: ReactNode
}

export function AnalysisContentBrowser({ title, entries, filterStatus = false, compact = false }: {
  title: string
  entries: AnalysisEntry[]
  compact?: boolean
  filterStatus?: boolean
}) {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [selectedKey, setSelectedKey] = useState<string>()
  const visible = entries.filter((entry) => (
    `${entry.code ?? ''} ${entry.title} ${entry.searchText}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()) &&
    (status === 'all' || entry.status === status)
  ))
  const selected = visible.find((entry) => entry.key === selectedKey) ?? visible[0]

  return (
    <div className={`ai-analysis-browser${compact ? ' ai-analysis-browser-rules' : ''}`}>
      <nav className="ai-analysis-directory" aria-label={`${title}目录`}>
        <div className="ai-analysis-directory-tools">
          <strong>{title}<span>{visible.length} / {entries.length}</span></strong>
          <Input.Search aria-label={`搜索${title}`} placeholder={`搜索${title}`} allowClear value={query} onChange={(event) => setQuery(event.target.value)} />
          {filterStatus && <Select aria-label="场景生成状态" value={status} onChange={setStatus} options={[
            { value: 'all', label: '全部状态' }, { value: 'ready', label: '可生成测试点' },
            { value: 'blocked', label: '暂不可生成测试点' }, { value: 'unknown', label: '生成就绪状态未明确' },
          ]} />}
        </div>
        <div className="ai-analysis-directory-list">
          {visible.map((entry) => <button key={entry.key} type="button" title={compact ? [entry.code, entry.title].filter(Boolean).join(' ') : undefined} aria-label={[entry.code, entry.title].filter(Boolean).join(' ')} aria-current={entry.key === selected?.key ? 'true' : undefined} onClick={() => setSelectedKey(entry.key)}>
            {compact && <FileTextOutlined className="ai-analysis-directory-icon" aria-hidden />}
            {!compact && entry.code && <span className="ai-analysis-entry-code">{entry.code}</span>}
            <span className="ai-analysis-entry-title">{entry.title}</span>
            {compact && entry.code && <span className="ai-analysis-entry-code">{entry.code}</span>}
          </button>)}
          {!visible.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的条目" />}
        </div>
      </nav>
      <article className="ai-analysis-detail" aria-label={`${title}详情`} key={selected?.key}>
        {selected ? <>
          <header><h3>{selected.code && <span>{selected.code}</span>}{selected.title}</h3>{selected.badge}</header>
          <div className="ai-analysis-detail-fields">{selected.content}</div>
        </> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请调整搜索或筛选条件" />}
      </article>
    </div>
  )
}