import type { ApiCaseFormValues } from '@/features/api-automation/utils/apiCaseEditor'
import type { ApiEnvironment } from '@/features/api-automation/types'
import type { ProjectAction } from '@/features/projects/types'
import type { ListResponse } from '@/shared/api/request'
import type { JsonEditorRef } from '@/shared/components/JsonEditor/JsonEditor'
import type {
  ApiAssertRule,
  ApiCase,
  ApiCaseRunResult,
  ApiExtractRule,
} from '@/services/api'
import type { UseMutationResult, UseQueryResult } from '@tanstack/react-query'
import type { FormInstance, InputRef } from 'antd'
import type { JSX } from 'react'

/*
 * 请求编辑区的三段配置各带一组状态与回调：页签内容拆成子组件后，编辑器和子组件要共用
 * 同一份签名，所以集中放在这里，而不是在三处各抄一遍。
 */

export type EnvironmentProps = {
  environmentPopoverOpen: boolean
  setEnvironmentPopoverOpen: React.Dispatch<React.SetStateAction<boolean>>
  environments: ApiEnvironment[]
  resolvedEnvironmentId: string | undefined
  handleSelectEnvironment: (nextEnvironmentId: string) => void
  switchDefaultEnvironmentMutation: UseMutationResult<string, Error, string, { previousEnvironmentId: string | undefined }>
  projectId: string | undefined
  selectedEnvironment: ApiEnvironment
  environmentsQuery: UseQueryResult<ListResponse<ApiEnvironment>, Error>
}

export type RenderEnvVarPicker = (options: {
  pickerKey: string
  onInsert: (templateText: string) => void
  trigger: React.ReactNode
  placement?: 'bottomRight' | 'bottomLeft' | undefined
}) => JSX.Element

/** Key-Value 行渲染要用的字段级模板插入：输入框引用、模板选择器与插入动作。 */
export type TemplatesProps = {
  setEnvVarInputRef: (fieldKey: string, ref: InputRef | null) => void
  renderEnvVarPicker: RenderEnvVarPicker
  insertTemplateText: (fieldPath: (string | number)[], fieldKey: string, templateText: string) => void
  bodyJsonEditorRef: React.RefObject<JsonEditorRef | null>
  insertTemplateTextIntoJson: (templateText: string) => void
  handleFormatBodyJson: () => void
  handleCompressBodyJson: () => void
}

export type RulesProps = {
  postOperationCount: number
  can: (action: ProjectAction) => boolean
  openCreateAssertRule: () => void
  openCreateExtractRule: () => void
  assertRulesQuery: UseQueryResult<ListResponse<ApiAssertRule>, Error>
  extractRulesQuery: UseQueryResult<ListResponse<ApiExtractRule>, Error>
  assertRules: ApiAssertRule[]
  toggleAssertRuleMutation: UseMutationResult<ApiAssertRule, Error, { assertRuleId: string; enabled: boolean }, unknown>
  openEditAssertRule: (rule: ApiAssertRule) => void
  deleteAssertRuleMutation: UseMutationResult<Record<string, never>, Error, string, unknown>
  extractRules: ApiExtractRule[]
  toggleExtractRuleMutation: UseMutationResult<ApiExtractRule, Error, { extractRuleId: string; enabled: boolean }, unknown>
  openEditExtractRule: (rule: ApiExtractRule) => void
  deleteExtractRuleMutation: UseMutationResult<Record<string, never>, Error, string, unknown>
}

export type ApiCaseEditorProps = {
  caseForm: FormInstance<ApiCaseFormValues>
  isCreatingCase: boolean
  setDraftCaseValues: React.Dispatch<React.SetStateAction<ApiCaseFormValues | null>>
  getCompleteCaseFormValues: () => ApiCaseFormValues
  createCaseMutation: UseMutationResult<ApiCase, Error, ApiCaseFormValues, unknown>
  editingCase: ApiCase | null
  activeCaseId: string
  updateCaseMutation: UseMutationResult<ApiCase, Error, ApiCaseFormValues, unknown>
  pathInputRef: React.RefObject<InputRef | null>
  runApiCaseMutation: UseMutationResult<ApiCaseRunResult, Error, { caseId: string; environmentId: string }, unknown>
  isApiCaseRunInProgress: boolean
  isSelectedCaseReady: boolean
  handleSendRequest: () => Promise<void>
  watchedBodyType: ApiCase['bodyType'] | undefined
  environment: EnvironmentProps
  templates: TemplatesProps
  rules: RulesProps
}
