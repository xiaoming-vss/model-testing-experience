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
  const [resume, setResume] = useState(!initialEntryId)
  const [edge, setEdge] = useState<'first' | 'last'>('first')
  const scope = JSON.stringify([orderId, filters.keyword, filters.status, filters.onlyMine, filters.actor])
  const scopeRef = useRef(scope)
  const selectedRef = useRef(selectedEntryId)
  useEffect(() => { selectedRef.current = selectedEntryId }, [selectedEntryId])
  useEffect(() => {
    if (scopeRef.current === scope) return
    scopeRef.current = scope
    setPage(1); setFocus(''); setResume(true); setSelectedEntryId(null); setEdge('first')
  }, [scope])
  const link = JSON.stringify([orderId, initialEntryId])
  const linkRef = useRef(link)
  useEffect(() => {
    if (linkRef.current === link) return
    linkRef.current = link
    setPage(1); setFocus(initialEntryId ?? ''); setResume(!initialEntryId); setSelectedEntryId(initialEntryId)
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
    if (!entriesQuery.isSuccess || entriesQuery.isPlaceholderData || selectedEntryId) return
    const items = listItems(entriesQuery.data)
    const preferred = edge === 'last' ? items.at(-1)?.entryId : entriesQuery.data.preferredEntryId || items[0]?.entryId
    setSelectedEntryId(preferred ?? null)
  }, [entriesQuery.isSuccess, entriesQuery.isPlaceholderData, entriesQuery.data, selectedEntryId, edge])
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
  function changePage(next: number, size = pageSize, nextEdge: 'first' | 'last' = 'first') {
    setPage(size === pageSize ? next : 1); setPageSize(size)
    setFocus(''); setResume(false); setSelectedEntryId(null); setEdge(nextEdge)
  }
  function moveSelection(offset: number) {
    const index = entries.findIndex((entry) => entry.entryId === selectedEntryId)
    if (index < 0) return
    const next = entries[index + offset]
    if (next) selectEntry(next.entryId ?? null)
    else if (offset > 0 && currentPage * pageSize < total) changePage(currentPage + 1)
    else if (offset < 0 && currentPage > 1) changePage(currentPage - 1, pageSize, 'last')
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
    selected: detailQuery.data, selectEntry, clearDeletedSelection, changePage, moveSelection, advance }
}
