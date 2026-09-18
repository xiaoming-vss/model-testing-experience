import type { Requirement } from '@/features/requirements/types'
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''
const API_PROXY_TARGET = import.meta.env.VITE_API_PROXY_TARGET ?? ''

export function normalizeRequirementDocumentType(documentType?: Requirement['documentType']) {
  if (documentType === 'docx') return 'word'
  return documentType
}

export function isWordRequirementDocument(documentType?: Requirement['documentType']) {
  return normalizeRequirementDocumentType(documentType) === 'word'
}

export function getRequirementDocumentTypeLabel(documentType?: Requirement['documentType']) {
  if (isWordRequirementDocument(documentType)) return 'Word'
  if (documentType === 'text') return '文本'
  return '未配置'
}

export function getRequirementDocumentFileName(documentPath?: string) {
  if (!documentPath) return ''
  const normalized = documentPath.split('?')[0]
  const segments = normalized.split(/[\\/]/)
  return segments[segments.length - 1] || normalized
}

export function getRequirementDocumentDisplayName({
  documentType,
  documentFileName,
  documentFilename,
  requirementName,
}: {
  documentType?: Requirement['documentType']
  documentFileName?: string
  documentFilename?: string
  requirementName?: string
}) {
  if (isWordRequirementDocument(documentType)) {
    return documentFileName || documentFilename || requirementName || '未命名文档'
  }

  return documentFileName || documentFilename || requirementName || '文本内容'
}

export function hasRequirementEnhancedText(requirement?: Pick<Requirement, 'documentContent'>) {
  return Boolean(requirement?.documentContent?.trim())
}

export function hasRequirementDocument(
  document?: Pick<Requirement, 'documentType' | 'documentDownloadUrl' | 'documentFilename'>,
) {
  return Boolean(
    document?.documentType &&
      (document.documentDownloadUrl?.trim() || document.documentFilename?.trim()),
  )
}

export function getRequirementDocumentSummary(
  requirement: Pick<
    Requirement,
    'documentType' | 'documentDownloadUrl' | 'documentFilename'
  >,
) {
  if (isWordRequirementDocument(requirement.documentType)) {
    return requirement.documentFilename || getRequirementDocumentFileName(requirement.documentDownloadUrl) || '已上传 Word 文档'
  }

  if (requirement.documentType === 'text') {
    return requirement.documentFilename || getRequirementDocumentFileName(requirement.documentDownloadUrl) || '已保存文本源文件'
  }

  return '未配置需求文档'
}

export function resolveRequirementDocumentUrl(documentPath?: string) {
  if (!documentPath) return ''
  if (/^https?:\/\//i.test(documentPath)) return documentPath
  if (!API_BASE_URL) return documentPath
  if (documentPath.startsWith('/')) return `${API_BASE_URL}${documentPath}`
  return `${API_BASE_URL}/${documentPath}`
}

export function resolveRequirementDocumentPreviewUrl(documentUrl: string) {
  if (!documentUrl) return ''

  if (!import.meta.env.DEV || !API_PROXY_TARGET) {
    return documentUrl
  }

  try {
    const proxyTarget = new URL(API_PROXY_TARGET)
    const resolvedDocumentUrl = new URL(documentUrl, window.location.origin)
    const isBackendDocument =
      resolvedDocumentUrl.origin === proxyTarget.origin || !/^https?:\/\//i.test(documentUrl)

    if (!isBackendDocument) {
      return documentUrl
    }

    return `/__document_preview_proxy${resolvedDocumentUrl.pathname}${resolvedDocumentUrl.search}`
  } catch {
    return documentUrl
  }
}
