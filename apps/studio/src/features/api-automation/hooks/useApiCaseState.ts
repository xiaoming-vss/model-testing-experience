import { useQueryClient } from '@tanstack/react-query'
import type { FormInstance } from 'antd'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type Dispatch, type DragEvent, type SetStateAction } from 'react'
import type { ApiCase } from '@/services/api'
import type { ProjectAction } from '@/domain/projects/types'
import { DRAFT_CASE_ID } from '../config/collectionConfig'
import {
  buildCaseFormValues,
  createDefaultCaseFormValues,
  getCaseId,
  moveArrayItem,
  sortCasesByOrderNo,
  type ApiCaseFormValues,
} from '../utils/apiCaseEditor'
import { useApiCaseEditing } from './useApiCaseEditing'

export function useApiCaseState({
  collectionId,
  cases,
  caseForm,
  queryClient,
  can,
  activeCaseId,
  selectedCaseId,
  setSelectedCaseId,
  selectedCaseDetail,
}: {
  collectionId: string
  cases: ApiCase[]
  caseForm: FormInstance<ApiCaseFormValues>
  queryClient: ReturnType<typeof useQueryClient>
  can: (action: ProjectAction) => boolean
  activeCaseId: string
  selectedCaseId: string
  setSelectedCaseId: Dispatch<SetStateAction<string>>
  selectedCaseDetail: ApiCase | undefined
}) {
  const [editingCase, setEditingCase] = useState<ApiCase | null>(null)
  const [draftCaseValues, setDraftCaseValues] = useState<ApiCaseFormValues | null>(null)
  const [caseSearch, setCaseSearch] = useState('')
  const [caseOrderIds, setCaseOrderIds] = useState<string[]>([])
  const [draggingCaseId, setDraggingCaseId] = useState<string | null>(null)

  const caseOrderRollbackRef = useRef<string[]>([])
  const isCreatingCase = selectedCaseId === DRAFT_CASE_ID
  const effectiveCases = cases

  function getCompleteCaseFormValues() {
    const allValues = caseForm.getFieldsValue(true) as Partial<ApiCaseFormValues>

    return {
      ...createDefaultCaseFormValues(),
      ...allValues,
      headers: allValues.headers ?? [{ enabled: false, key: '', value: '' }],
      query: allValues.query ?? [{ enabled: false, key: '', value: '' }],
    } satisfies ApiCaseFormValues
  }

  const { createCaseMutation, updateCaseMutation, deleteCaseMutation, reorderCasesMutation } = useApiCaseEditing({ setEditingCase, setSelectedCaseId, caseForm, collectionId, caseOrderIds, cases: effectiveCases, setDraftCaseValues, caseOrderRollbackRef, setCaseOrderIds, editingCase, setDraggingCaseId })

  useEffect(() => {
    if (selectedCaseId !== DRAFT_CASE_ID) return

    setEditingCase(null)
    caseForm.setFieldsValue(draftCaseValues ?? createDefaultCaseFormValues())
  }, [caseForm, draftCaseValues, selectedCaseId])

  // 列表接口返回的就是完整用例（含 headers / query / body），先预热详情缓存；
  // 切换用例时不再多发一次详情请求，也不会让迟到的响应覆盖正在编辑的表单。
  useLayoutEffect(() => {
    if (effectiveCases.length === 0) return

    for (const item of effectiveCases) {
      const caseId = getCaseId(item)
      if (!caseId || queryClient.getQueryData(['apiCase', caseId])) continue
      queryClient.setQueryData(['apiCase', caseId], item)
    }
  }, [effectiveCases, queryClient])

  useLayoutEffect(() => {
    if (!activeCaseId || !selectedCaseDetail) return
    // 选中时已经用列表数据同步过编辑态，这里不再重复覆盖。
    if (editingCase && getCaseId(editingCase) === activeCaseId) return

    setEditingCase(selectedCaseDetail)
    caseForm.setFieldsValue(buildCaseFormValues(selectedCaseDetail))
  }, [activeCaseId, caseForm, editingCase, selectedCaseDetail])

  const resetCaseForm = useCallback(() => {
    caseForm.setFieldsValue(createDefaultCaseFormValues())
  }, [caseForm])

  const openCreateDrawer = useCallback(() => {
    const nextDraft = draftCaseValues ?? createDefaultCaseFormValues()
    setDraftCaseValues(nextDraft)
    setSelectedCaseId(DRAFT_CASE_ID)
    setEditingCase(null)
    caseForm.setFieldsValue(nextDraft)
  }, [caseForm, draftCaseValues, setSelectedCaseId])

  const filteredCases = useMemo(() => {
    const keyword = caseSearch.trim().toLowerCase()
    if (!keyword) return effectiveCases

    return effectiveCases.filter((item) =>
      [item.name, item.urlTemplate, item.description, item.method]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(keyword)),
    )
  }, [caseSearch, effectiveCases])

  const orderedByRuleCases = useMemo(() => sortCasesByOrderNo(filteredCases), [filteredCases])

  const draftCase = useMemo<ApiCase | null>(
    () =>
      draftCaseValues
        ? {
          caseId: DRAFT_CASE_ID,
          name: draftCaseValues.name?.trim() || '未保存用例',
          description: draftCaseValues.description,
          method: draftCaseValues.method || 'POST',
          urlTemplate: draftCaseValues.path?.trim() || '/v1/example',
          enabled: draftCaseValues.enabled,
        }
        : null,
    [draftCaseValues],
  )

  useEffect(() => {
    if (reorderCasesMutation.isPending) return

    const nextIds = sortCasesByOrderNo(effectiveCases)
      .map((item) => getCaseId(item))
      .filter(Boolean)

    setCaseOrderIds((current) => {
      if (nextIds.length === 0) return current.length === 0 ? current : []
      if (current.length === 0) return nextIds

      const currentFiltered = current.filter((id) => nextIds.includes(id))
      if (currentFiltered.length === nextIds.length && currentFiltered.every((id, index) => id === nextIds[index])) {
        return currentFiltered
      }

      return nextIds
    })
  }, [effectiveCases, reorderCasesMutation.isPending])

  const orderedCases = useMemo(() => {
    if (caseOrderIds.length === 0) return orderedByRuleCases

    const caseMap = new Map(orderedByRuleCases.map((item) => [getCaseId(item), item]))
    const ordered = caseOrderIds.map((caseId) => caseMap.get(caseId)).filter(Boolean) as ApiCase[]
    const missing = orderedByRuleCases.filter((item) => !caseOrderIds.includes(getCaseId(item)))
    return [...ordered, ...missing]
  }, [caseOrderIds, orderedByRuleCases])

  const sidebarCases = useMemo(() => (draftCase ? [draftCase, ...orderedCases] : orderedCases), [draftCase, orderedCases])
  const selectedCasePreview = useMemo(
    () => orderedCases.find((item) => getCaseId(item) === activeCaseId) ?? effectiveCases.find((item) => getCaseId(item) === activeCaseId) ?? null,
    [activeCaseId, effectiveCases, orderedCases],
  )

  const canReorder = can('write') && caseSearch.trim().length === 0

  // 选中用例后立刻用列表数据填表单，避免绘制出一帧上一条用例的内容。
  useLayoutEffect(() => {
    if (!activeCaseId || selectedCaseId === DRAFT_CASE_ID) return
    if (editingCase && getCaseId(editingCase) === activeCaseId) return
    if (!selectedCasePreview) return

    setEditingCase(selectedCasePreview)
    caseForm.setFieldsValue(buildCaseFormValues(selectedCasePreview))
  }, [activeCaseId, caseForm, editingCase, selectedCaseId, selectedCasePreview])

  useEffect(() => {
    if (sidebarCases.length === 0) {
      if (selectedCaseId) {
        setSelectedCaseId('')
        setEditingCase(null)
        resetCaseForm()
      }
      return
    }

    const exists = sidebarCases.some((item) => getCaseId(item) === selectedCaseId)
    if (!selectedCaseId || !exists) {
      const fallbackCase = sidebarCases[0]
      const fallbackId = getCaseId(fallbackCase)
      setSelectedCaseId(fallbackId)
    }
  }, [resetCaseForm, selectedCaseId, setSelectedCaseId, sidebarCases])

  const handleDiscardDraft = useCallback(() => {
    setDraftCaseValues(null)
    const fallbackCase = filteredCases[0] ?? null
    if (fallbackCase) {
      setSelectedCaseId(getCaseId(fallbackCase))
      return
    }
    setSelectedCaseId('')
    setEditingCase(null)
    resetCaseForm()
  }, [filteredCases, resetCaseForm, setSelectedCaseId])

  const handleCaseDragStart = useCallback((event: DragEvent<HTMLDivElement>, caseId: string) => {
    if (!canReorder || caseId === DRAFT_CASE_ID) return
    setDraggingCaseId(caseId)
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', caseId)
  }, [canReorder])

  const reorderCases = reorderCasesMutation.mutate
  const deleteCase = deleteCaseMutation.mutate
  const handleCaseDrop = useCallback((targetCaseId: string) => {
    if (!draggingCaseId || draggingCaseId === targetCaseId || !canReorder) return
    if (draggingCaseId === DRAFT_CASE_ID || targetCaseId === DRAFT_CASE_ID) return

    const baseOrderIds = (caseOrderIds.length > 0 ? caseOrderIds : orderedCases.map((item) => getCaseId(item)).filter(Boolean)).filter(
      (caseId) => caseId !== DRAFT_CASE_ID,
    )
    const fromIndex = baseOrderIds.indexOf(draggingCaseId)
    const toIndex = baseOrderIds.indexOf(targetCaseId)
    if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return

    const nextOrderIds = moveArrayItem(baseOrderIds, fromIndex, toIndex)
    caseOrderRollbackRef.current = caseOrderIds
    setCaseOrderIds(nextOrderIds)
    reorderCases(nextOrderIds)
  }, [canReorder, caseOrderIds, draggingCaseId, orderedCases, reorderCases])

  const handleDeleteCase = useCallback((caseId: string) => deleteCase(caseId), [deleteCase])
  const handleCaseDragEnd = useCallback(() => setDraggingCaseId(null), [])

  return {
    editingCase,
    setEditingCase,
    draftCaseValues,
    setDraftCaseValues,
    selectedCaseId,
    setSelectedCaseId,
    caseSearch,
    setCaseSearch,
    caseOrderIds,
    setCaseOrderIds,
    draggingCaseId,
    caseOrderRollbackRef,
    isCreatingCase,
    getCompleteCaseFormValues,
    createCaseMutation,
    updateCaseMutation,
    deleteCaseMutation,
    reorderCasesMutation,
    filteredCases,
    orderedCases,
    sidebarCases,
    selectedCasePreview,
    canReorder,
    resetCaseForm,
    openCreateDrawer,
    handleDiscardDraft,
    handleCaseDragStart,
    handleCaseDrop,
    handleCaseDragEnd,
    handleDeleteCase,
  } as const
}
