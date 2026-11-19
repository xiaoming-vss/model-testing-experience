import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { isYamlFileName, type CaseImportMode } from '../utils/detailView'

export function useApiCaseImport({ collectionId }: { collectionId: string }) {
  const queryClient = useQueryClient()
  const [caseImportModalOpen, setCaseImportModalOpen] = useState(false)
  const [caseImportMode, setCaseImportMode] = useState<CaseImportMode>('upload')
  const [importYamlFile, setImportYamlFile] = useState<File | null>(null)
  const [importYamlText, setImportYamlText] = useState('')

  const importApiCasesMutation = useMutation({
    mutationFn: ({ file, filename }: { file: Blob; filename: string }) => api.importApiCases(collectionId, file, filename),
    onSuccess: (result) => {
      message.success(
        `导入成功：${result.importedCaseCount ?? 0} 条用例，${result.importedExtractRuleCount ?? 0} 条提取规则，${result.importedAssertRuleCount ?? 0} 条断言规则`,
      )
      setCaseImportModalOpen(false)
      setCaseImportMode('upload')
      setImportYamlFile(null)
      setImportYamlText('')
      queryClient.invalidateQueries({ queryKey: ['apiCases', collectionId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  function openCaseImportModal() {
    setCaseImportModalOpen(true)
  }

  function closeCaseImportModal() {
    if (importApiCasesMutation.isPending) return
    setCaseImportModalOpen(false)
    setCaseImportMode('upload')
    setImportYamlFile(null)
    setImportYamlText('')
  }

  function handleImportApiCases() {
    if (!collectionId) return

    if (caseImportMode === 'upload') {
      if (!importYamlFile) {
        message.warning('请上传 YAML 文件')
        return
      }
      if (!isYamlFileName(importYamlFile.name)) {
        message.warning('仅支持 .yaml 或 .yml 文件')
        return
      }

      importApiCasesMutation.mutate({
        file: importYamlFile,
        filename: importYamlFile.name,
      })
      return
    }

    const yamlContent = importYamlText.trim()
    if (!yamlContent) {
      message.warning('请输入 YAML 内容')
      return
    }

    const generatedFileName = `collection-${collectionId || 'cases'}.yaml`
    importApiCasesMutation.mutate({
      file: new File([yamlContent], generatedFileName, { type: 'application/x-yaml' }),
      filename: generatedFileName,
    })
  }

  return {
    caseImportModalOpen,
    setCaseImportModalOpen,
    caseImportMode,
    setCaseImportMode,
    importYamlFile,
    setImportYamlFile,
    importYamlText,
    setImportYamlText,
    importApiCasesMutation,
    openCaseImportModal,
    closeCaseImportModal,
    handleImportApiCases,
  } as const
}
