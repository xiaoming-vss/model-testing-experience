import { Alert, Button, Form, Space, Spin } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { useNavigate, useParams } from 'react-router-dom'
import { RequirementDocumentPreviewContent } from '@/features/requirements/components/RequirementDocumentPreviewModal'
import { RequirementDrawer, type RequirementFormValues } from '@/features/requirements/components/RequirementDrawer'
import { RequirementDesignWorkspace } from '@/features/ai-testing/components/RequirementDesignWorkspace'
import type { RequirementReadingNode } from '@/features/ai-testing/components/RequirementGenerationPanorama'
import { requirementsApi } from '@/features/requirements/api/requirements.api'
import { projectsApi } from '@/features/projects/api/projects.api'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { RequirementDetailHeader } from '@/features/requirements/components/RequirementDetailHeader'
import { message } from '@/shared/utils/feedback'
import { canNavigateAway } from '@/shared/utils/unsavedChanges'
import { getErrorMessage } from '@/utils/format'
import '@/shared/styles/surface-tokens.css'
import '@/features/requirements/styles/detail.css'

export function RequirementDetailPage() {
  const { requirementId = '' } = useParams()
  const navigate = useNavigate()
  const documentHydrationSeq = useRef(0)
  const [documentLoading, setDocumentLoading] = useState(false)
  const [documentError, setDocumentError] = useState<string | undefined>()
  const [editing, setEditing] = useState(false)
  const [refreshingGeneration, setRefreshingGeneration] = useState(false)
  const [inspectorHost, setInspectorHost] = useState<HTMLDivElement | null>(null)
  const [readingActionsHost, setReadingActionsHost] = useState<HTMLDivElement | null>(null)
  const [readingNode, setReadingNode] = useState<RequirementReadingNode | null>(null)
  // 阅读态的「退回流程」动作由生成全景提供，用 ref 保存，避免函数身份变化触发重渲染。
  const leaveReadingRef = useRef<(() => void) | null>(null)
  // 画布阅读态会随渲染重复上报同一个产物，值没变时不触发标题栏重渲染。
  const handleReadingNode = useCallback((next: RequirementReadingNode | null) => {
    leaveReadingRef.current = next?.leave ?? null
    setReadingNode(current => {
      if (!next) return current === null ? current : null
      return current?.label === next.label && current.kind === next.kind ? current : { label: next.label, kind: next.kind }
    })
  }, [])
  const handleLeaveReading = useCallback(() => { leaveReadingRef.current?.() }, [])
  const [form] = Form.useForm<RequirementFormValues>()
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['requirement', requirementId],
    queryFn: () => requirementsApi.getRequirement(requirementId), enabled: Boolean(requirementId) })
  const requirement = query.data
  const sprintId = requirement?.sprintId ?? requirement?.sprint_id ?? ''
  const sprint = useQuery({ queryKey: ['sprint', sprintId], queryFn: () => projectsApi.getSprint(sprintId), enabled: Boolean(sprintId) })
  const access = useProjectAccess(sprint.data?.projectId ?? '')
  const canRead = access.can('read')
  const canonicalProjectId = sprint.data?.projectId
  useEffect(() => {
    if (!canRead || !canonicalProjectId || !sprintId) return
    const scope = useWorkbenchStore.getState()
    if (scope.activeProjectId !== canonicalProjectId) scope.setActiveProjectId(canonicalProjectId)
    if (useWorkbenchStore.getState().activeSprintId !== sprintId) useWorkbenchStore.getState().setActiveSprintId(sprintId)
  }, [canRead, canonicalProjectId, sprintId])
  useEffect(() => {
    if (!editing || requirement?.documentType !== 'richtext') return
    const sequence = ++documentHydrationSeq.current
    let cancelled = false
    setDocumentLoading(true)
    setDocumentError(undefined)
    void requirementsApi.downloadRequirementDocument(requirementId)
      .then(response => response.blob.text())
      .then(content => { if (!cancelled && sequence === documentHydrationSeq.current) form.setFieldValue('documentContent', content) })
      .catch(error => { if (!cancelled && sequence === documentHydrationSeq.current) setDocumentError(`需求正文加载失败：${getErrorMessage(error)}`) })
      .finally(() => { if (!cancelled && sequence === documentHydrationSeq.current) setDocumentLoading(false) })
    return () => { cancelled = true }
  }, [editing, requirement?.documentType, requirementId, form])
  const save = useMutation({ mutationFn: async (values: RequirementFormValues) => {
    if (values.documentType === 'richtext') return requirementsApi.replaceRequirementDocument(requirementId, {
      name: values.name, documentType: 'richtext', documentContent: values.documentContent,
      onUploadProgress: values.onUploadProgress,
    })
    if (values.file) return requirementsApi.replaceRequirementDocument(requirementId, { name: values.name, file: values.file, documentType: values.documentType, onUploadProgress: values.onUploadProgress })
    return requirementsApi.updateRequirement(requirementId, { name: values.name })
  }, onSuccess: () => { setEditing(false); void client.invalidateQueries({ queryKey: ['requirement', requirementId] }); void client.invalidateQueries({ queryKey: ['requirementDesign', requirementId] }); void client.invalidateQueries({ queryKey: ['requirementsPool'] }); message.success('需求已更新') } })
  const back = () => { if (canNavigateAway()) navigate('/projects?board=requirements') }
  // 生成全景的刷新入口在需求标题栏，这里直接刷新生成链查询。
  const refreshGeneration = () => {
    setRefreshingGeneration(true)
    void client.invalidateQueries({ queryKey: ['generationChain', requirementId] })
      .finally(() => setRefreshingGeneration(false))
  }
  const retryRead = () => {
    if (query.error) void query.refetch()
    if (sprint.error) void sprint.refetch()
  }
  if (query.isPending) return <Spin />
  if (query.error || sprint.error) return <Alert type="error" title={getErrorMessage(query.error ?? sprint.error)} action={<Space wrap><Button loading={query.isFetching || sprint.isFetching} onClick={retryRead}>重试读取</Button><Button onClick={back}>返回需求列表</Button></Space>} />
  if (!requirement) return <Alert type="warning" title="需求不存在" action={<Button onClick={back}>返回需求列表</Button>} />
  const documentProps = { requirementId, requirementName: requirement.name, documentType: requirement.documentType,
    documentContent: requirement.documentContent, documentFilename: requirement.documentFilename, documentDownloadUrl: requirement.documentDownloadUrl,
    showEnhancedText: false }
  // 下载与编辑只服务需求正文，打开需求文档时才出现在标题栏。
  const readingDocument = readingNode?.kind === 'document'
  return <ProjectAccessScope projectId={sprint.data?.projectId ?? ''} resourceError={query.error}>
    <div className="requirement-detail-page tp-surface">
      <div className="requirement-detail-layout">
        {/* 标题栏与画布共用左侧容器：标题栏是容器内的工具栏，画布紧贴其下。 */}
        <section className="requirement-detail-main">
          <RequirementDetailHeader showDownload={readingDocument} showEdit={readingDocument} requirement={requirement} requirementId={requirementId} readingNode={readingNode} onLeaveReading={handleLeaveReading} readingActionsRef={setReadingActionsHost}
            canWrite={access.can('write')} onRefresh={sprint.data ? refreshGeneration : undefined} refreshing={refreshingGeneration} onBack={back} onEdit={() => {
              setDocumentError(undefined)
              setDocumentLoading(requirement.documentType === 'richtext')
              form.setFieldsValue({ name: requirement.name,
                documentType: requirement.documentType === 'docx' ? 'word' : requirement.documentType ?? 'richtext',
                documentContent: '', documentFilename: requirement.documentFilename,
                documentFileName: requirement.documentFilename, documentDownloadUrl: requirement.documentDownloadUrl,
                file: undefined }); setEditing(true)
            }} />
          {sprint.data ? <RequirementDesignWorkspace key={requirementId} requirementId={requirementId} projectId={sprint.data.projectId ?? ''}
            canWrite={access.can('write')} onReadingNodeChange={handleReadingNode} inspectorHost={inspectorHost} readingActionsHost={readingActionsHost}
            documentPreview={<RequirementDocumentPreviewContent embedded {...documentProps} />} /> : <Spin />}
        </section>
        {/* 阶段侧栏独立成卡片，挂在画布大容器外侧。 */}
        <div className="requirement-detail-side" ref={setInspectorHost} />
      </div>
      <RequirementDrawer title="编辑需求" open={editing} mode="edit" form={form} loading={save.isPending} error={save.error}
        projectId={canonicalProjectId} documentLoading={documentLoading} documentError={documentError}
        onDocumentTypeChange={() => {
          documentHydrationSeq.current += 1
          setDocumentLoading(false)
          setDocumentError(undefined)
          save.reset()
        }}
        onClose={() => setEditing(false)} onFinish={values => save.mutate(values)} />
    </div>
  </ProjectAccessScope>
}
