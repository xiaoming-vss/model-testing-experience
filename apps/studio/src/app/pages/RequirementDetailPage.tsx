import { Alert, Button, Form, Space, Spin } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { RequirementDocumentPreviewContent } from '@/features/requirements/components/RequirementDocumentPreviewModal'
import { RequirementDrawer, type RequirementFormValues } from '@/features/requirements/components/RequirementDrawer'
import { RequirementDesignWorkspace, type RequirementWorkspaceTab } from '@/features/ai-testing/components/RequirementDesignWorkspace'
import { requirementsApi } from '@/features/requirements/api/requirements.api'
import { projectsApi } from '@/features/projects/api/projects.api'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { RequirementDetailHeader } from '@/features/requirements/components/RequirementDetailHeader'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import '@/shared/styles/surface-tokens.css'
import '@/features/requirements/styles/detail.css'

export function RequirementDetailPage() {
  const { requirementId = '' } = useParams()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const requestedTab = params.get('tab')
  const activeTab: RequirementWorkspaceTab = requestedTab === 'design' ? 'requirement_analysis'
    : requestedTab === 'requirement_analysis' || requestedTab === 'function' || requestedTab === 'api' || requestedTab === 'ui' || requestedTab === 'codeRisk'
      ? requestedTab : 'content'
  const changeTab = (tab: RequirementWorkspaceTab) => {
    const updated = new URLSearchParams(params)
    updated.set('tab', tab)
    setParams(updated)
  }
  const documentHydrationSeq = useRef(0)
  const [documentLoading, setDocumentLoading] = useState(false)
  const [documentError, setDocumentError] = useState<string | undefined>()
  const [editing, setEditing] = useState(false)
  const [actionsContainer, setActionsContainer] = useState<HTMLDivElement | null>(null)
  const [tabsContainer, setTabsContainer] = useState<HTMLDivElement | null>(null)
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
    if (!editing || !['text', 'richtext'].includes(requirement?.documentType ?? '')) return
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
    return requirementsApi.updateRequirement(requirementId, { name: values.name,
      ...(values.documentType === 'text' ? { documentContent: values.documentContent ?? '', documentType: 'text' } : {}) })
  }, onSuccess: () => { setEditing(false); void client.invalidateQueries({ queryKey: ['requirement', requirementId] }); void client.invalidateQueries({ queryKey: ['requirementDesign', requirementId] }); void client.invalidateQueries({ queryKey: ['requirementsPool'] }); message.success('需求已更新') } })
  const back = () => navigate('/projects?board=requirements')
  const retryRead = () => {
    if (query.error) void query.refetch()
    if (sprint.error) void sprint.refetch()
  }
  if (query.isPending) return <Spin />
  if (query.error || sprint.error) return <Alert type="error" title={getErrorMessage(query.error ?? sprint.error)} action={<Space wrap><Button loading={query.isFetching || sprint.isFetching} onClick={retryRead}>重试读取</Button><Button onClick={back}>返回需求列表</Button></Space>} />
  if (!requirement) return <Alert type="warning" title="需求不存在" action={<Button onClick={back}>返回需求列表</Button>} />
  const documentProps = { requirementId, requirementName: requirement.name, documentType: requirement.documentType,
    documentContent: requirement.documentContent, documentFilename: requirement.documentFilename, documentDownloadUrl: requirement.documentDownloadUrl }
  return <ProjectAccessScope projectId={sprint.data?.projectId ?? ''} resourceError={query.error}>
    <div className="requirement-detail-page tp-surface">
      <div className="requirement-detail-tabs" ref={setTabsContainer} />
      <div className="requirement-detail-container tp-board tp-list-panel">
      <RequirementDetailHeader showDownload={activeTab === 'content'} showEdit={activeTab === 'content'} workspaceActionsRef={setActionsContainer} requirement={requirement} requirementId={requirementId}
        canWrite={access.can('write')} onBack={back} onEdit={() => {
          setDocumentError(undefined)
          setDocumentLoading(requirement.documentType === 'richtext' || requirement.documentType === 'text')
          form.setFieldsValue({ name: requirement.name,
            documentType: requirement.documentType === 'docx' ? 'word' : requirement.documentType ?? 'text',
            documentContent: '', documentFilename: requirement.documentFilename,
            documentFileName: requirement.documentFilename, documentDownloadUrl: requirement.documentDownloadUrl,
            file: undefined }); setEditing(true)
        }} />
      <section className="requirement-detail-main">
        {sprint.data ? <RequirementDesignWorkspace key={requirementId} requirementId={requirementId} projectId={sprint.data.projectId ?? ''} documentHash={requirement.documentHash}
          activeTab={activeTab} onTabChange={changeTab} tabsContainer={tabsContainer} actionsContainer={actionsContainer}
          document={<RequirementDocumentPreviewContent key={requirement.documentHash} embedded {...documentProps} />}
          canWrite={access.can('write')} canExecute={access.can('execute')} canReview={access.can('review')} /> : <Spin />}
      </section>
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
