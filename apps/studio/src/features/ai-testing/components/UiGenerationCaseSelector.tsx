import { Alert, Button, Input, Select, Space, Table, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api, listItems } from '@/services/api'
import { ListPagination } from '@/shared/components/ListPagination'
import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import { getErrorMessage } from '@/utils/format'
import '../styles/ui-generation-case-selector.css'

type SourceCase = { caseId: string; title: string; suiteId: string; suiteName: string }

export function UiGenerationCaseSelector({ requirementId, open, value, onChange, onReady }: {
  requirementId?: string
  open: boolean
  value: string[] | undefined
  onChange: (ids: string[] | undefined) => void
  onReady: (ready: boolean) => void
}) {
  const [suiteIds, setSuiteIds] = useState<string[]>([])
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const query = useQuery({
    queryKey: ['uiGenerationSourceCases', requirementId],
    queryFn: async () => {
      const suites = listItems(await api.getFunctionTestSuites(requirementId!))
      return (await Promise.all(suites.map(async suite => listItems(await api.getFunctionTestCases(suite.suiteId!))
        .filter(item => Boolean(item.caseId)).map(item => ({ caseId: item.caseId!, title: item.title ?? '', suiteId: suite.suiteId!, suiteName: suite.name ?? '' }))))).flat()
    },
    enabled: open && Boolean(requirementId), retry: false,
  })
  useEffect(() => {
    if (query.data && value === undefined) onChange(query.data.map(item => item.caseId))
  }, [query.data, value, onChange])
  useEffect(() => {
    onReady(query.isSuccess && !query.isFetching && Boolean(value?.length) && value!.every(id => query.data?.some(item => item.caseId === id)))
  }, [query.isSuccess, query.isFetching, query.data, value, onReady])
  const suites = useMemo(() => [...new Map((query.data ?? []).map(item => [item.suiteId, { value: item.suiteId, label: item.suiteName }])).values()], [query.data])
  const filtered = useMemo(() => (query.data ?? []).filter(item =>
    (!suiteIds.length || suiteIds.includes(item.suiteId)) && `${item.title} ${item.caseId}`.toLowerCase().includes(search.trim().toLowerCase())), [query.data, suiteIds, search])
  const selected = new Set(value ?? [])
  const visibleSelected = filtered.filter(item => selected.has(item.caseId)).length
  const busy = query.isFetching || query.isError
  return <section className="ui-generation-case-selector" aria-label="来源功能用例">
    <Typography.Text strong>来源功能用例</Typography.Text>
    <Typography.Text type="secondary">默认选中当前需求全部正式功能用例。筛选不改变已选内容，生成时依次审核 JSON、JSON 和 YAML。</Typography.Text>
    <div className="ui-generation-case-filters">
      <Select mode="multiple" allowClear maxTagCount={1} aria-label="按用例集筛选" placeholder="全部用例集" options={suites}
        value={suiteIds} onChange={ids => { setSuiteIds(ids); setPage(1) }} optionFilterProp="label" />
      <Input.Search allowClear aria-label="搜索用例" placeholder="搜索用例标题或编号" value={search}
        onChange={event => { setSearch(event.target.value); setPage(1) }} />
    </div>
    <Space wrap className="ui-generation-case-selection-actions">
      <Typography.Text role="status">已选 {value?.length ?? 0} / {query.data?.length ?? 0} 条</Typography.Text>
      <Button size="small" disabled={busy || !filtered.length || visibleSelected === filtered.length}
        onClick={() => onChange([...new Set([...(value ?? []), ...filtered.map(item => item.caseId)])])}>全选筛选结果</Button>
      <Button size="small" disabled={busy || !visibleSelected}
        onClick={() => { const ids = new Set(filtered.map(item => item.caseId)); onChange((value ?? []).filter(id => !ids.has(id))) }}>取消筛选结果</Button>
      <Button size="small" disabled={busy || !value?.length} onClick={() => onChange([])}>清空选择</Button>
    </Space>
    <Table<SourceCase> size="small" rowKey="caseId" tableLayout="fixed" dataSource={filtered.slice((page - 1) * pageSize, page * pageSize)}
      loading={query.isFetching} pagination={false} scroll={{ y: 216 }}
      locale={{ emptyText: query.error ? '用例读取失败' : !query.data?.length ? '暂无正式功能用例' : '没有符合筛选条件的用例' }}
      rowSelection={{ selectedRowKeys: value ?? [], preserveSelectedRowKeys: true, columnWidth: 40,
        getTitleCheckboxProps: () => ({ 'aria-label': '选择当前页用例', disabled: busy }),
        getCheckboxProps: item => ({ 'aria-label': `选择用例：${item.title}`, disabled: busy }),
        onChange: keys => onChange(keys.map(String)),
      }} columns={[
        { title: '用例名称', dataIndex: 'title', ellipsis: true },
        { title: '用例集', dataIndex: 'suiteName', width: '28%', ellipsis: true },
      ]} />
    <div className="table-footer ui-generation-case-pagination"><ListPagination current={page} pageSize={pageSize} total={filtered.length} loading={query.isFetching}
      onChange={(next, size) => { setPage(next); setPageSize(size) }} /></div>
    {query.error ? <Alert showIcon type="error" title={getErrorMessage(query.error)} action={<Button size="small" onClick={() => { void query.refetch() }}>重新读取</Button>} /> : null}
    {query.isSuccess && value?.some(id => !query.data.some(item => item.caseId === id)) ? <Alert showIcon type="warning"
      title="部分已选用例已删除或移出当前需求，请清空后重新选择" /> : null}
    {query.isSuccess && !query.data.length ? <Alert type="info" title="请先在当前需求下准备正式功能用例"
      description="请先在“功能测试”中审核用例并导入正式测试集，再返回生成 UI 用例。" /> : null}
  </section>
}
