import type { FormInstance, InputRef } from 'antd'
import { useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import type { JsonEditorRef } from '@/shared/components/JsonEditor/JsonEditor'
import {
  ENV_VAR_TOKEN_PREFIX,
  ENV_VAR_TOKEN_SUFFIX,
  builtinTemplateFunctions,
  type EnvVarPickerMode,
} from '../config/collectionConfig'
import type { ApiCaseFormValues } from '../utils/apiCaseEditor'

export function useApiEnvVarPicker({
  caseForm,
  resolvedEnvironmentId,
  environmentVars,
  environmentVarsQuery,
  bodyJsonEditorRef,
}: {
  caseForm: FormInstance<ApiCaseFormValues>
  resolvedEnvironmentId?: string
  environmentVars: Array<{ varKey: string; description?: string }>
  environmentVarsQuery: { isLoading: boolean }
  bodyJsonEditorRef: RefObject<JsonEditorRef | null>
}) {
  const [envVarPickerOpenKey, setEnvVarPickerOpenKey] = useState<string | null>(null)
  const [envVarPickerMode, setEnvVarPickerMode] = useState<EnvVarPickerMode>('environment')
  const [envVarPickerSearch, setEnvVarPickerSearch] = useState('')
  const [envVarPickerSelectedKey, setEnvVarPickerSelectedKey] = useState<string>('')
  const [envVarPickerInsertHandler, setEnvVarPickerInsertHandler] = useState<((templateText: string) => void) | null>(null)
  const envVarInputRefs = useRef<Record<string, InputRef | null>>({})

  const filteredEnvironmentVars = useMemo(() => {
    const keyword = envVarPickerSearch.trim().toLowerCase()
    if (!keyword) return environmentVars
    return environmentVars.filter((item) => item.varKey.toLowerCase().includes(keyword))
  }, [envVarPickerSearch, environmentVars])
  const filteredBuiltinTemplateFunctions = useMemo(() => {
    const keyword = envVarPickerSearch.trim().toLowerCase()
    if (!keyword) return builtinTemplateFunctions
    return builtinTemplateFunctions.filter((item) =>
      [item.label, item.token, item.description, item.example].filter(Boolean).some((field) => field!.toLowerCase().includes(keyword)),
    )
  }, [envVarPickerSearch])

  useEffect(() => {
    if (!envVarPickerOpenKey) return
    if (envVarPickerMode === 'builtin') {
      if (filteredBuiltinTemplateFunctions.some((item) => item.token === envVarPickerSelectedKey)) return
      setEnvVarPickerSelectedKey(filteredBuiltinTemplateFunctions[0]?.token ?? '')
      return
    }

    const environmentTokens = filteredEnvironmentVars.map((item) => formatEnvironmentToken(item.varKey))
    if (environmentTokens.includes(envVarPickerSelectedKey)) return
    setEnvVarPickerSelectedKey(environmentTokens[0] ?? '')
  }, [envVarPickerMode, envVarPickerOpenKey, envVarPickerSelectedKey, filteredBuiltinTemplateFunctions, filteredEnvironmentVars])

  function formatEnvironmentToken(varKey: string) {
    return `${ENV_VAR_TOKEN_PREFIX}${varKey}${ENV_VAR_TOKEN_SUFFIX}`
  }

  function setEnvVarInputRef(fieldKey: string, ref: InputRef | null) {
    if (!ref) {
      delete envVarInputRefs.current[fieldKey]
      return
    }
    envVarInputRefs.current[fieldKey] = ref
  }

  function openEnvVarPicker(fieldKey: string, onInsert: (templateText: string) => void) {
    const defaultMode: EnvVarPickerMode = resolvedEnvironmentId ? 'environment' : 'builtin'
    setEnvVarPickerOpenKey(fieldKey)
    setEnvVarPickerInsertHandler(() => onInsert)
    setEnvVarPickerMode(defaultMode)
    setEnvVarPickerSearch('')
    setEnvVarPickerSelectedKey(
      defaultMode === 'environment' ? formatEnvironmentToken(environmentVars[0]?.varKey ?? '') : builtinTemplateFunctions[0]?.token ?? '',
    )
  }

  function closeEnvVarPicker() {
    setEnvVarPickerOpenKey(null)
    setEnvVarPickerInsertHandler(null)
    setEnvVarPickerMode('environment')
    setEnvVarPickerSearch('')
    setEnvVarPickerSelectedKey('')
  }

  function insertTemplateText(fieldPath: Array<string | number>, fieldKey: string, templateText: string) {
    const currentValue = String(caseForm.getFieldValue(fieldPath as never) ?? '')
    const inputRef = envVarInputRefs.current[fieldKey]
    const inputElement = inputRef?.input ?? null

    if (inputElement) {
      const selectionStart = inputElement.selectionStart ?? currentValue.length
      const selectionEnd = inputElement.selectionEnd ?? selectionStart
      const nextValue = `${currentValue.slice(0, selectionStart)}${templateText}${currentValue.slice(selectionEnd)}`
      caseForm.setFieldValue(fieldPath as never, nextValue)

      requestAnimationFrame(() => {
        inputElement.focus()
        const caretPosition = selectionStart + templateText.length
        inputElement.setSelectionRange?.(caretPosition, caretPosition)
      })
    } else {
      caseForm.setFieldValue(fieldPath as never, `${currentValue}${templateText}`)
    }

    closeEnvVarPicker()
  }

  function insertTemplateTextIntoJson(templateText: string) {
    bodyJsonEditorRef.current?.insertText(templateText)
    closeEnvVarPicker()
  }

  function handleFormatBodyJson() {
    bodyJsonEditorRef.current?.formatDocument()
  }

  function handleCompressBodyJson() {
    bodyJsonEditorRef.current?.compressDocument()
  }

  function renderEnvVarPicker({
    pickerKey,
    onInsert,
    trigger,
  }: {
    pickerKey: string
    onInsert: (templateText: string) => void
    trigger: ReactNode
    placement?: 'bottomRight' | 'bottomLeft'
  }) {
    return (
      <span
        className="api-env-var-picker-trigger-wrap inline-flex"
        onClick={(event) => {
          event.preventDefault()
          event.stopPropagation()
          openEnvVarPicker(pickerKey, onInsert)
        }}
      >
        {trigger}
      </span>
    )
  }

  return {
    envVarPickerOpenKey,
    envVarPickerMode,
    setEnvVarPickerMode,
    envVarPickerSearch,
    setEnvVarPickerSearch,
    envVarPickerSelectedKey,
    setEnvVarPickerSelectedKey,
    envVarPickerInsertHandler,
    filteredEnvironmentVars,
    filteredBuiltinTemplateFunctions,
    setEnvVarInputRef,
    closeEnvVarPicker,
    insertTemplateText,
    insertTemplateTextIntoJson,
    handleFormatBodyJson,
    handleCompressBodyJson,
    renderEnvVarPicker,
    formatEnvironmentToken,
    environmentVarsQuery,
    resolvedEnvironmentId,
    environmentVars,
  } as const
}
