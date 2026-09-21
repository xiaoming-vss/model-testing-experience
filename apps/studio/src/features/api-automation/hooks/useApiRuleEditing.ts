import { type AssertRuleFormValues, type ExtractRuleFormValues } from '@/features/api-automation/utils/detailView'
import {
  api,
  type ApiAssertRule,
  type ApiExtractRule
} from '@/services/api'
import { message } from '@/shared/utils/feedback'
import {
  normalizeAssertRuleId,
  normalizeExtractRuleId
} from '@/utils/format'
import { buildApiAssertRuleUpdatePayload, buildApiExtractRuleUpdatePayload } from '@/utils/updatePayload'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Form } from 'antd'
import { useState } from 'react'
import { EMPTY_ASSERT_RULES, EMPTY_EXTRACT_RULES, sortRulesByOrderNo } from '../utils/apiCaseEditor'

type Options = {
  activeCaseId: string
}

export function useApiRuleEditing({ activeCaseId }: Options) {
  const queryClient = useQueryClient()
  const [assertRuleModalOpen, setAssertRuleModalOpen] = useState(false)

  const [extractRuleModalOpen, setExtractRuleModalOpen] = useState(false)

  const [editingAssertRule, setEditingAssertRule] = useState<ApiAssertRule | null>(null)

  const [editingExtractRule, setEditingExtractRule] = useState<ApiExtractRule | null>(null)

  const [assertRuleForm] = Form.useForm<AssertRuleFormValues>()

  const [extractRuleForm] = Form.useForm<ExtractRuleFormValues>()

  const watchedAssertSource = Form.useWatch('assertSource', assertRuleForm)

  const watchedAssertComparator = Form.useWatch('comparator', assertRuleForm)

  const watchedExtractSource = Form.useWatch('source', extractRuleForm)

  const saveAssertRuleMutation = useMutation({
    mutationFn: (values: AssertRuleFormValues) => {
      if (!activeCaseId) throw new Error('请先保存用例')
      if (editingAssertRule) {
        return api.updateApiAssertRule(
          normalizeAssertRuleId(editingAssertRule),
          buildApiAssertRuleUpdatePayload(editingAssertRule, values),
        )
      }
      return api.createApiAssertRule(activeCaseId, values)
    },
    onSuccess: () => {
      message.success(editingAssertRule ? '断言规则已更新' : '断言规则已创建')
      setAssertRuleModalOpen(false)
      setEditingAssertRule(null)
      assertRuleForm.resetFields()
      queryClient.invalidateQueries({ queryKey: ['apiAssertRules', activeCaseId] })
    },
  })

  const deleteAssertRuleMutation = useMutation({
    mutationFn: (assertRuleId: string) => api.deleteApiAssertRule(assertRuleId),
    onSuccess: () => {
      message.success('断言规则已删除')
      queryClient.invalidateQueries({ queryKey: ['apiAssertRules', activeCaseId] })
    },
  })

  const toggleAssertRuleMutation = useMutation({
    mutationFn: ({ assertRuleId, enabled }: { assertRuleId: string; enabled: boolean }) => api.updateApiAssertRule(assertRuleId, { enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apiAssertRules', activeCaseId] })
    },
  })

  const saveExtractRuleMutation = useMutation({
    mutationFn: (values: ExtractRuleFormValues) => {
      if (!activeCaseId) throw new Error('请先保存用例')
      if (editingExtractRule) {
        return api.updateApiExtractRule(
          normalizeExtractRuleId(editingExtractRule),
          buildApiExtractRuleUpdatePayload(editingExtractRule, values),
        )
      }
      return api.createApiExtractRule(activeCaseId, values)
    },
    onSuccess: () => {
      message.success(editingExtractRule ? '提取规则已更新' : '提取规则已创建')
      setExtractRuleModalOpen(false)
      setEditingExtractRule(null)
      extractRuleForm.resetFields()
      queryClient.invalidateQueries({ queryKey: ['apiExtractRules', activeCaseId] })
    },
  })

  const deleteExtractRuleMutation = useMutation({
    mutationFn: (extractRuleId: string) => api.deleteApiExtractRule(extractRuleId),
    onSuccess: () => {
      message.success('提取规则已删除')
      queryClient.invalidateQueries({ queryKey: ['apiExtractRules', activeCaseId] })
    },
  })

  const toggleExtractRuleMutation = useMutation({
    mutationFn: ({ extractRuleId, enabled }: { extractRuleId: string; enabled: boolean }) => api.updateApiExtractRule(extractRuleId, { enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apiExtractRules', activeCaseId] })
    },
  })

  function openCreateAssertRule() {
    if (!activeCaseId) {
      message.warning('请先保存用例')
      return
    }

    setEditingAssertRule(null)
    setAssertRuleModalOpen(true)
    assertRuleForm.setFieldsValue({
      name: '',
      enabled: true,
      orderNo: assertRules.length + 1,
      assertSource: 'status_code',
      targetExpr: '',
      comparator: 'eq',
      expectedValue: '',
    })
  }

  function openEditAssertRule(rule: ApiAssertRule) {
    setEditingAssertRule(rule)
    setAssertRuleModalOpen(true)
    assertRuleForm.setFieldsValue({
      name: rule.name,
      enabled: rule.enabled,
      orderNo: rule.orderNo,
      assertSource: rule.assertSource,
      targetExpr: rule.targetExpr,
      comparator: rule.comparator,
      expectedValue: rule.expectedValue,
    })
  }

  function openCreateExtractRule() {
    if (!activeCaseId) {
      message.warning('请先保存用例')
      return
    }

    setEditingExtractRule(null)
    setExtractRuleModalOpen(true)
    extractRuleForm.setFieldsValue({
      name: '',
      enabled: true,
      orderNo: extractRules.length + 1,
      source: 'body_jsonpath',
      sourceExpr: '',
      varKey: '',
      defaultValue: '',
    })
  }

  function openEditExtractRule(rule: ApiExtractRule) {
    setEditingExtractRule(rule)
    setExtractRuleModalOpen(true)
    extractRuleForm.setFieldsValue({
      name: rule.name,
      enabled: rule.enabled,
      orderNo: rule.orderNo,
      source: rule.source,
      sourceExpr: rule.sourceExpr,
      varKey: rule.varKey,
      defaultValue: rule.defaultValue,
    })
  }

  const assertRulesQuery = useQuery({
    queryKey: ['apiAssertRules', activeCaseId],
    queryFn: () => api.getApiAssertRules(activeCaseId),
    enabled: Boolean(activeCaseId),
  })

  const extractRulesQuery = useQuery({
    queryKey: ['apiExtractRules', activeCaseId],
    queryFn: () => api.getApiExtractRules(activeCaseId),
    enabled: Boolean(activeCaseId),
  })

  const assertRules = sortRulesByOrderNo(assertRulesQuery.data ?? EMPTY_ASSERT_RULES)
  const extractRules = sortRulesByOrderNo(extractRulesQuery.data ?? EMPTY_EXTRACT_RULES)
  return {
    assertRuleModalOpen,
    setAssertRuleModalOpen,
    extractRuleModalOpen,
    setExtractRuleModalOpen,
    editingAssertRule,
    setEditingAssertRule,
    editingExtractRule,
    setEditingExtractRule,
    assertRuleForm,
    extractRuleForm,
    watchedAssertSource,
    watchedAssertComparator,
    watchedExtractSource,
    saveAssertRuleMutation,
    deleteAssertRuleMutation,
    toggleAssertRuleMutation,
    saveExtractRuleMutation,
    deleteExtractRuleMutation,
    toggleExtractRuleMutation,
    openCreateAssertRule,
    openEditAssertRule,
    openCreateExtractRule,
    openEditExtractRule,
    assertRulesQuery,
    extractRulesQuery,
    assertRules,
    extractRules,
  }
}
