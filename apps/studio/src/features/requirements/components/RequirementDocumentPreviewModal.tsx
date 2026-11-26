import { RichTextViewer } from '@/shared/components/RichTextEditor'
import { readSignedFileResponse } from '@/shared/api/files'
import { saveBlob } from '@/shared/utils/download'
import {
  DownloadOutlined,
  FileWordOutlined,
} from '@ant-design/icons'
import { Alert, Button, Spin } from 'antd'
import { useMutation } from '@tanstack/react-query'
import { renderAsync } from 'docx-preview'
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useAuthStore } from '@/features/auth/store/auth.store'
import type { Requirement } from '@/features/requirements/types'
import {
  getRequirementDocumentDisplayName,
  isWordRequirementDocument as isWordDocument,
  resolveRequirementDocumentPreviewUrl,
  resolveRequirementDocumentUrl,
} from '@/features/requirements/utils/requirementDocument'
import { api } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import detailStyles from '../styles/requirement-detail.module.css'

async function fetchBlobWithAuth(url: string, token?: string | null) {
  const authorize = () => fetch(url, {
    headers: token
      ? {
          Authorization: `Bearer ${token}`,
          Accept: 'application/json',
        }
      : undefined,
  })
  const response = await authorize()

  if (!response.ok) {
    throw new Error(`文档加载失败（${response.status}）`)
  }

  return (await readSignedFileResponse(response, authorize)).blob()
}

function RequirementDocxPreview({
  requirementId,
  documentUrl,
  previewUrl,
  documentName,
}: {
  requirementId?: string
  documentUrl: string
  previewUrl: string
  documentName: string
}) {
  const token = useAuthStore((state) => state.token)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [previewAttempt, setPreviewAttempt] = useState(0)
  const downloadMutation = useMutation({
    mutationFn: async () => {
      if (requirementId) {
        return api.downloadRequirementDocument(requirementId)
      }

      const sourceUrl = documentUrl || previewUrl
      if (!sourceUrl) {
        throw new Error('暂无可下载文档')
      }

      return {
        blob: await fetchBlobWithAuth(sourceUrl, token),
        filename: documentName,
      }
    },
    onSuccess: (response) => {
      saveBlob(response.blob, response.filename || documentName || 'requirement-document')
    },
    onError: (downloadError) => {
      message.error(getErrorMessage(downloadError))
    },
  })

  useEffect(() => {
    let disposed = false
    const container = containerRef.current

    async function loadDocument() {
      if ((!previewUrl && !requirementId) || !container) return

      setLoading(true)
      setError(null)
      container.innerHTML = ''

      try {
        const blob = requirementId
          ? (await api.downloadRequirementDocument(requirementId)).blob
          : await fetchBlobWithAuth(previewUrl || documentUrl, token)

        if (blob.size === 0) {
          throw new Error('文档内容为空，请下载原文件确认是否上传成功')
        }

        const arrayBuffer = await blob.arrayBuffer()
        if (disposed) return
        const signature = new Uint8Array(arrayBuffer.slice(0, 4))
        const isZipDocument = signature[0] === 0x50 && signature[1] === 0x4b

        if (!isZipDocument) {
          throw new Error('文档内容不是有效的 DOCX 文件，请下载原文件确认')
        }

        await renderAsync(arrayBuffer, container, undefined, {
          className: 'requirement-docx',
          inWrapper: false,
          breakPages: false,
          ignoreWidth: true,
          ignoreHeight: true,
        })

        if (!disposed) {
          setLoading(false)
        }
      } catch (loadError) {
        if (disposed) return
        const nextError = loadError instanceof Error ? loadError.message : '文档预览失败'
        setError(nextError)
        setLoading(false)
      }
    }

    void loadDocument()

    return () => {
      disposed = true
      if (container) {
        container.innerHTML = ''
      }
    }
  }, [documentUrl, previewUrl, requirementId, token, previewAttempt])

  return (
    <div className="requirement-document-preview-shell flex h-full w-full min-h-0 flex-1 overflow-hidden">
      {loading ? (
        <div className="requirement-document-preview-state flex min-h-[220px] flex-col items-center justify-center gap-2.5 text-[13px] text-[var(--testing-text-muted)]">
          <Spin />
          <span>文档预览加载中...</span>
        </div>
      ) : null}
      {error ? (
        <div className="requirement-document-preview-state error flex min-h-[220px] flex-col items-center justify-center gap-2 text-[13px] text-[var(--testing-text-muted)]">
          <span role="alert">{error}</span>
          <Button onClick={() => setPreviewAttempt(attempt => attempt + 1)}>重试预览</Button>
          <Button type="link" loading={downloadMutation.isPending} onClick={() => downloadMutation.mutate()}>
            下载文档：{documentName}
          </Button>
        </div>
      ) : null}
      <div
        ref={containerRef}
        className={`requirement-document-docx-host min-h-0 w-full flex-1 overflow-auto rounded-none border-0 bg-[var(--app-surface)] shadow-none${loading ? ' loading' : ''}${error ? ' hidden' : ''}`}
      />
    </div>
  )
}

function RequirementTextPreview({ previewUrl, richText = false }: { previewUrl: string; richText?: boolean }) {
  const token = useAuthStore((state) => state.token)
  const [loading, setLoading] = useState(false)
  const [content, setContent] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [previewAttempt, setPreviewAttempt] = useState(0)

  useEffect(() => {
    let disposed = false

    async function loadText() {
      if (!previewUrl) {
        setContent('')
        setError(null)
        return
      }

      setLoading(true)
      setError(null)

      try {
        const authorize = () => fetch(previewUrl, {
          headers: token
            ? {
                Authorization: `Bearer ${token}`,
                Accept: 'application/json',
              }
            : undefined,
        })
        const response = await authorize()

        if (!response.ok) {
          throw new Error(`文本加载失败（${response.status}）`)
        }

        const text = await (await readSignedFileResponse(response, authorize)).text()
        if (disposed) return
        setContent(text)
        setLoading(false)
      } catch (loadError) {
        if (disposed) return
        setError(loadError instanceof Error ? loadError.message : '文本预览失败')
        setLoading(false)
      }
    }

    void loadText()

    return () => {
      disposed = true
    }
  }, [previewUrl, token, previewAttempt])

  return (
    <div className="requirement-document-text-host min-h-0 min-w-0 w-full max-w-full flex-1 overflow-auto [&_.rich-text-viewer]:box-border [&_.rich-text-viewer]:min-h-full [&_.rich-text-viewer]:w-full [&_.rich-text-viewer]:p-6">
      {loading ? (
        <div className="requirement-document-preview-state flex min-h-[220px] flex-col items-center justify-center gap-2.5 text-[13px] text-[var(--testing-text-muted)]">
          <Spin />
          <span>文本预览加载中...</span>
        </div>
      ) : null}
      {error ? (
        <div className="requirement-document-preview-state error flex min-h-[220px] flex-col items-center justify-center gap-2 text-[13px] text-[var(--testing-text-muted)]">
          <span role="alert">{error}</span>
          <Button onClick={() => setPreviewAttempt(attempt => attempt + 1)}>重试预览</Button>
        </div>
      ) : null}
      {!loading && !error ? (
        richText ? <RichTextViewer html={content} ariaLabel="需求正文" /> :
        <div className="requirement-document-text-article box-border block min-h-full w-full min-w-0 max-w-full whitespace-pre-wrap break-words bg-[var(--app-surface)] p-6 text-[15px] leading-[1.84] text-[var(--description-text)] [font-family:var(--description-font)]">{content || '暂无源文件内容'}</div>
      ) : null}
    </div>
  )
}

type RequirementDocumentPreviewContentProps = {
  embedded?: boolean
  requirementId?: string
  requirementName?: string
  documentType?: Requirement['documentType']
  documentContent?: string
  documentFilename?: string
  documentDownloadUrl?: string
}

function RequirementPreviewPane({ children }: { children: ReactNode }) {
  return (
    <section className="requirement-document-pane flex min-h-0 min-w-0 flex-col overflow-hidden rounded-[8px] border border-[var(--app-testing-control-disabled-border)] bg-[var(--app-surface)]">
      <div className="requirement-document-pane-body flex min-h-0 min-w-0 flex-1 overflow-hidden bg-[var(--app-surface)]">{children}</div>
    </section>
  )
}

export function RequirementDocumentPreviewContent({
  requirementId,
  requirementName,
  documentType,
  documentContent,
  documentFilename,
  documentDownloadUrl,
  embedded = false,
}: RequirementDocumentPreviewContentProps) {
  const isWord = isWordDocument(documentType)
  const sourceDocumentPath = documentDownloadUrl || (requirementId ? `/v1/requirements/${requirementId}/download` : undefined)
  const documentUrl = useMemo(() => resolveRequirementDocumentUrl(sourceDocumentPath), [sourceDocumentPath])
  const documentName = useMemo(
    () =>
      getRequirementDocumentDisplayName({
        documentType,
        documentFilename,
        requirementName,
      }),
    [documentFilename, documentType, requirementName],
  )
  const previewUrl = useMemo(() => resolveRequirementDocumentPreviewUrl(documentUrl), [documentUrl])
  const documentTypeLabel = isWord ? 'Word 文档' : documentType === 'richtext' ? '富文本需求' : '未配置需求文档'
  const documentText = documentContent?.trim() ?? ''
  const downloadMutation = useMutation({
    mutationFn: () => api.downloadRequirementDocument(requirementId!),
    onSuccess: (response) => {
      saveBlob(response.blob, response.filename || documentName || 'requirement-document')
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  function handleDownload() {
    if (requirementId) {
      downloadMutation.mutate()
      return
    }

    if (documentUrl) {
      window.open(documentUrl, '_blank', 'noopener,noreferrer')
    }
  }

  const documentPreviewContent = (
    <div className={`requirement-document-modal-stage flex h-full w-full min-h-0 min-w-0 max-w-full flex-none overflow-hidden bg-transparent p-0${isWord ? ' docx-mode' : ' text-mode'}`}>
      {isWord && (documentUrl || requirementId) ? (
        <RequirementDocxPreview
          requirementId={requirementId}
          documentUrl={documentUrl}
          previewUrl={previewUrl}
          documentName={documentName}
        />
      ) : !isWord && documentUrl ? (
        <RequirementTextPreview key={previewUrl} previewUrl={previewUrl} richText={documentType === 'richtext'} />
      ) : !isWord && documentText ? (
        <div className="requirement-document-text-host min-h-0 min-w-0 w-full max-w-full flex-1 overflow-auto [&_.rich-text-viewer]:box-border [&_.rich-text-viewer]:min-h-full [&_.rich-text-viewer]:w-full [&_.rich-text-viewer]:p-6">
          <article className="requirement-document-text-article box-border block min-h-full w-full min-w-0 max-w-full whitespace-pre-wrap break-words bg-[var(--app-surface)] p-6 text-[15px] leading-[1.84] text-[var(--description-text)] [font-family:var(--description-font)]">{documentText}</article>
        </div>
      ) : (
        <div className="requirement-document-text-host min-h-0 min-w-0 w-full max-w-full flex-1 overflow-auto [&_.rich-text-viewer]:box-border [&_.rich-text-viewer]:min-h-full [&_.rich-text-viewer]:w-full [&_.rich-text-viewer]:p-6">
          <div className="requirement-document-text-article box-border block min-h-full w-full min-w-0 max-w-full whitespace-pre-wrap break-words bg-[var(--app-surface)] p-6 text-[15px] leading-[1.84] text-[var(--description-text)] [font-family:var(--description-font)]">暂无源文件</div>
        </div>
      )}
    </div>
  )

  return (
    <div className={`requirement-document-modal flex min-h-0 flex-1 flex-col gap-0${embedded ? ' requirement-document-inline' : ''} ${detailStyles.root}`}>
      {!embedded ? <header className="requirement-document-modal-toolbar flex min-h-[72px] items-center justify-between gap-[18px] border-b border-[var(--app-list-row-border)] bg-[var(--app-surface)] px-4 py-3 pr-16 [backdrop-filter:none]">
        <div className="requirement-document-modal-toolbar-main flex min-w-0 flex-1 flex-col gap-1 overflow-hidden">
          {!embedded ? <div className="requirement-document-modal-title-row flex items-center gap-2.5">
            <FileWordOutlined className="requirement-document-modal-title-icon inline-flex text-[21px] text-[var(--app-testing-control-accent)]" />
            <div className="requirement-document-modal-title text-[20px] font-bold leading-[28px] tracking-normal text-[var(--testing-text)]">需求文档</div>
          </div> : null}
          <div className="requirement-document-modal-meta flex w-full min-w-0 items-center justify-start gap-2.5 overflow-hidden whitespace-nowrap text-[13px] text-[var(--testing-text-muted)]">
            <span className="requirement-document-type-chip inline-flex h-6 items-center justify-center rounded-[6px] border border-[var(--app-testing-control-hover-border)] bg-[var(--app-testing-control-hover-bg)] px-2.5 text-xs font-semibold leading-[18px] tracking-[0.02em] text-[var(--app-testing-control-accent)]">{documentTypeLabel}</span>
            <span className="requirement-document-file-name block min-w-0 max-w-[min(52vw,760px)] flex-[0_1_auto] truncate text-[13px] leading-[20px] text-[var(--app-list-header-text)]" title={documentName}>
              {documentName}
            </span>
          </div>
        </div>
        {documentUrl || requirementId ? (
          <Button
            type="link"
            className="requirement-document-download-link inline-flex h-[34px] flex-none items-center gap-2 self-center rounded-[7px] border border-[var(--app-testing-control-selected-border)] bg-[var(--app-surface)] px-[13px] text-[13px] font-semibold text-[var(--app-testing-control-accent)] no-underline shadow-none transition-[transform,border-color,background-color] duration-200 hover:border-[var(--app-testing-control-focus-border)] hover:bg-[var(--app-testing-control-selected-bg)] hover:no-underline"
            loading={downloadMutation.isPending}
            onClick={handleDownload}
          >
            <DownloadOutlined />
            下载原文件
          </Button>
        ) : null}
      </header> : null}
      {downloadMutation.error ? <Alert showIcon type="error" title={getErrorMessage(downloadMutation.error)} /> : null}
      <div className="requirement-document-workspace grid min-h-[520px] h-[calc(100vh-176px)] grid-cols-1 flex-1 overflow-hidden bg-[var(--app-testing-control-disabled-bg)] p-0">
        <RequirementPreviewPane>
          {documentPreviewContent}
        </RequirementPreviewPane>

      </div>
    </div>
  )
}
