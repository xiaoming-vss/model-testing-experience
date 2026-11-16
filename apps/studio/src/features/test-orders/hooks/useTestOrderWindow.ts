import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, listItems } from '@/services/api'
import type { TestOrderEntryFilters } from '../types'

type Filters = { keyword: string; status: string; onlyMine: boolean; actor?: string }

/** List windows carry summaries; the selected identity independently loads its detail. */
export function useTestOrderWindow(orderId: string | undefined, initialEntryId: string | null, filters: Filters) {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(initialEntryId)
  const [focus, setFocus] = useState(initialEntryId ?? '')
  /**
   * 列表优先：没有 entryId 时进入测试单只展示清单，不再自动打开「首条待执行」。
   * resume 只用于自动前进和跨页定位，初始列表请求必须为 false。
   */
  const [resume, setResume] = useState(false)
  const scope = JSON.stringify([orderId, filters.keyword, filters.status, filters.onlyMine, filters.actor])
  const scopeRef = useRef(scope)
  const selectedRef = useRef(selectedEntryId)
  useEffect(() => { selectedRef.current = selectedEntryId }, [selectedEntryId])
  useEffect(() => {
    if (scopeRef.current === scope) return
    scopeRef.current = scope
    setPage(1); setFocus(''); setResume(false); setSelectedEntryId(null)
  }, [scope])
  const link = JSON.stringify([orderId, initialEntryId])
  const linkRef = useRef(link)
  useEffect(() => {
    if (linkRef.current === link) return
    linkRef.current = link
    setPage(1); setFocus(initialEntryId ?? ''); setResume(false); setSelectedEntryId(initialEntryId)
  }, [link, initialEntryId])
  const params: TestOrderEntryFilters = {
    page, pageSize, keyword: filters.keyword, status: filters.status,
    onlyMine: filters.onlyMine, focusEntryId: focus, resume,
  }
  const entriesQuery = useQuery({
    queryKey: ['testOrderEntries', orderId, 'page', filters.actor, params],
    queryFn: () => api.getTestOrderEntries(orderId!, params),
    enabled: Boolean(orderId),
    placeholderData: (previous, previousQuery) => {
      const prior = previousQuery?.queryKey[4] as TestOrderEntryFilters | undefined
      return previousQuery?.queryKey[1] === orderId && previousQuery?.queryKey[3] === filters.actor
        && prior?.keyword === params.keyword && prior?.status === params.status && prior?.onlyMine === params.onlyMine
        ? previous : undefined
    },
    refetchOnWindowFocus: true,
  })
  const entries = listItems(entriesQuery.data)
  const currentPage = entriesQuery.data?.page ?? page
  const total = entriesQuery.data?.total ?? 0
  useEffect(() => {
    if (entriesQuery.isSuccess && !entriesQuery.isPlaceholderData && !focus && !resume && currentPage !== page) {
      setPage(currentPage)
    }
  }, [entriesQuery.isSuccess, entriesQuery.isPlaceholderData, focus, resume, currentPage, page])
  const detailQuery = useQuery({
    queryKey: ['testOrderEntry', orderId, selectedEntryId],
    queryFn: () => api.getTestOrderEntry(orderId!, selectedEntryId!),
    enabled: Boolean(orderId && selectedEntryId),
    refetchOnWindowFocus: true,
  })
  function selectEntry(id: string | null) {
    setSelectedEntryId(id); setPage(currentPage); setFocus(''); setResume(false)
  }
  function clearDeletedSelection(id: string) {
    if (selectedRef.current !== id) return
    setSelectedEntryId(null); setFocus(''); setResume(false)
  }
  function changePage(next: number, size = pageSize) {
    setPage(size === pageSize ? next : 1); setPageSize(size)
    setFocus(''); setResume(false); setSelectedEntryId(null)
  }
  /** 继续执行 / 深链定位：后端按 focusEntryId 反查条目所在页，不要求它当前在列表页上。 */
  function focusEntry(id: string) {
    setPage(1); setFocus(id); setResume(false); setSelectedEntryId(id)
  }
  /** 详情上下条跨页时按页取首/末条，保持全量列表顺序，而不是只找下一条待执行。 */
  async function moveToPageEntry(direction: 1 | -1) {
    const from = selectedRef.current
    if (!orderId || !from) return false
    const targetPage = direction > 0 ? currentPage + 1 : currentPage - 1
    if (targetPage < 1 || targetPage > Math.ceil(total / pageSize)) return false
    const before = scope
    try {
      const data = await api.getTestOrderEntries(orderId, {
        page: targetPage, pageSize, keyword: filters.keyword, status: filters.status,
        onlyMine: filters.onlyMine,
      })
      if (before !== scopeRef.current || selectedRef.current !== from) return false
      const items = listItems(data)
      const target = direction > 0 ? items[0] : items.at(-1)
      if (!target?.entryId) return false
      setPage(data.page ?? targetPage); setFocus(''); setResume(false); setSelectedEntryId(target.entryId)
      return true
    } catch (error) {
      if (before === scopeRef.current && selectedRef.current === from) throw error
      return false
    }
  }
  async function advance(fromEntryId: string) {
    if (!orderId || selectedRef.current !== fromEntryId || scopeRef.current !== scope) return
    const before = scope
    try {
      const next = await api.getTestOrderEntries(orderId, {
        page: currentPage, pageSize, keyword: filters.keyword, status: filters.status,
        onlyMine: filters.onlyMine, resume: true, afterEntryId: fromEntryId,
      })
      if (before !== scopeRef.current || selectedRef.current !== fromEntryId || !next.preferredEntryId) return
      setPage(next.page); setFocus(next.preferredEntryId); setResume(false); setSelectedEntryId(next.preferredEntryId)
    } catch (error) {
      if (before === scopeRef.current && selectedRef.current === fromEntryId) throw error
    }
  }
  return { entriesQuery, detailQuery, entries, currentPage, pageSize, total, selectedEntryId,
    selected: detailQuery.data, selectEntry, focusEntry, clearDeletedSelection, changePage,
    moveToPageEntry, advance }
}
