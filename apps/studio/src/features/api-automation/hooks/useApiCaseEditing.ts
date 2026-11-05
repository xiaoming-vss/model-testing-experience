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

  // create/update 的响应本身就是完整用例，直接用响应 + 提交值合并，
  // 不再保存后补一次详情请求。
  function resolveCompleteCaseAfterSave(savedCase: ApiCase, submittedValues: ApiCaseFormValues, previousCase?: ApiCase | null) {
    return mergeDefinedApiCaseFields(mergeApiCaseWithFormValues(previousCase ?? savedCase, submittedValues), savedCase)
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
      const completeCase = resolveCompleteCaseAfterSave(createdCase, values)

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
      const completeCase = resolveCompleteCaseAfterSave(updatedCase, values, editingCase)

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
    // 一次拖拽只提交一条批量排序请求；响应即完整的新顺序，直接写入缓存，不再整表重拉。
    mutationFn: (nextOrderIds: string[]) => api.reorderApiCases(collectionId, nextOrderIds),
    onSuccess: (result) => {
      message.success('用例顺序已更新')
      queryClient.setQueryData(['apiCases', collectionId], result)
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
