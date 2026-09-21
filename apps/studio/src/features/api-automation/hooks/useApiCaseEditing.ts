import {
  buildApiCaseUpdatePayload,
  buildCaseFormValues,
  getCaseId,
  mergeApiCaseWithFormValues,
  mergeDefinedApiCaseFields,
  serializeCaseValues,
  sortCasesByOrderNo,
  type ApiCaseFormValues
} from '@/features/api-automation/utils/apiCaseEditor'
import {
  api,
  type ApiCase
} from '@/services/api'
import { message } from '@/shared/utils/feedback'
import {
  getErrorMessage
} from '@/utils/format'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { FormInstance } from 'antd'

type Options = {
  setEditingCase: React.Dispatch<React.SetStateAction<ApiCase | null>>
  setSelectedCaseId: React.Dispatch<React.SetStateAction<string>>
  caseForm: FormInstance<ApiCaseFormValues>
  collectionId: string
  caseOrderIds: string[]
  cases: ApiCase[]
  setDraftCaseValues: React.Dispatch<React.SetStateAction<ApiCaseFormValues | null>>
  caseOrderRollbackRef: React.RefObject<string[]>
  setCaseOrderIds: React.Dispatch<React.SetStateAction<string[]>>
  editingCase: ApiCase | null
  setDraggingCaseId: React.Dispatch<React.SetStateAction<string | null>>
}

export function useApiCaseEditing({ setEditingCase, setSelectedCaseId, caseForm, collectionId, caseOrderIds, cases, setDraftCaseValues, caseOrderRollbackRef, setCaseOrderIds, editingCase, setDraggingCaseId }: Options) {
  const queryClient = useQueryClient()
  function syncCaseDetailState(apiCase: ApiCase) {
    const caseId = getCaseId(apiCase)
    setEditingCase(apiCase)
    setSelectedCaseId(caseId)
    caseForm.setFieldsValue(buildCaseFormValues(apiCase))
    queryClient.setQueryData(['apiCase', caseId], apiCase)
  }

  async function resolveCompleteCaseAfterSave(savedCase: ApiCase, submittedValues: ApiCaseFormValues, previousCase?: ApiCase | null) {
    const caseId = getCaseId(savedCase)
    const optimisticCase = mergeDefinedApiCaseFields(mergeApiCaseWithFormValues(previousCase ?? savedCase, submittedValues), savedCase)

    if (!caseId) return optimisticCase

    try {
      return await api.getApiCase(caseId)
    } catch {
      return optimisticCase
    }
  }

  const createCaseMutation = useMutation({
    mutationFn: (values: ApiCaseFormValues) =>
      api.createApiCase(collectionId, {
        ...serializeCaseValues(values),
        orderNo: 1,
      }),
    onSuccess: async (createdCase, values) => {
      const createdCaseId = getCaseId(createdCase)
      const currentOrderIds = (caseOrderIds.length > 0 ? caseOrderIds : sortCasesByOrderNo(cases).map((item) => getCaseId(item))).filter(Boolean)
      const nextOrderIds = [createdCaseId, ...currentOrderIds.filter((id) => id !== createdCaseId)]
      const completeCase = await resolveCompleteCaseAfterSave(createdCase, values)

      message.success('用例已创建')
      setDraftCaseValues(null)
      syncCaseDetailState(completeCase)
      caseOrderRollbackRef.current = caseOrderIds
      setCaseOrderIds(nextOrderIds)
      reorderCasesMutation.mutate(nextOrderIds)

      queryClient.invalidateQueries({ queryKey: ['apiCases', collectionId] })
    },
  })

  const updateCaseMutation = useMutation({
    mutationFn: (values: ApiCaseFormValues) => {
      const payload = buildApiCaseUpdatePayload(editingCase!, values)
      if (Object.keys(payload).length === 0) {
        return Promise.resolve(editingCase!)
      }

      return api.updateApiCase(getCaseId(editingCase!), payload)
    },
    onSuccess: async (updatedCase, values) => {
      const completeCase = await resolveCompleteCaseAfterSave(updatedCase, values, editingCase)

      message.success('用例已更新')
      syncCaseDetailState(completeCase)
      queryClient.invalidateQueries({ queryKey: ['apiCases', collectionId] })
    },
  })

  const deleteCaseMutation = useMutation({
    mutationFn: (caseId: string) => api.deleteApiCase(caseId),
    onSuccess: (_, caseId) => {
      message.success('用例已删除')
      setCaseOrderIds((current) => current.filter((id) => id !== caseId))
      setSelectedCaseId((current) => (current === caseId ? '' : current))
      queryClient.removeQueries({ queryKey: ['apiCase', caseId], exact: true })
      queryClient.invalidateQueries({ queryKey: ['apiCases', collectionId] })
    },
  })

  const reorderCasesMutation = useMutation({
    mutationFn: async (nextOrderIds: string[]) => {
      const caseMap = new Map(cases.map((item) => [getCaseId(item), item]))

      await Promise.all(
        nextOrderIds.map((caseId, index) => {
          const targetCase = caseMap.get(caseId)
          const nextOrderNo = index + 1

          if (targetCase?.orderNo === nextOrderNo) return Promise.resolve()
          return api.updateApiCase(caseId, { orderNo: nextOrderNo })
        }),
      )
    },
    onSuccess: () => {
      message.success('用例顺序已更新')
      queryClient.invalidateQueries({ queryKey: ['apiCases', collectionId] })
    },
    onError: (error) => {
      setCaseOrderIds(caseOrderRollbackRef.current)
      message.error(getErrorMessage(error))
    },
    onSettled: () => {
      caseOrderRollbackRef.current = []
      setDraggingCaseId(null)
    },
  })
  return { createCaseMutation, updateCaseMutation, deleteCaseMutation, reorderCasesMutation }
}
