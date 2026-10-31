/* eslint-disable react-refresh/only-export-components -- standalone prototype entry */
import { useEffect, useState } from 'react'
import { Button, Form, Modal } from 'antd'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { requirementsApi } from '@/features/requirements/api/requirements.api'
import { saveBlob } from '@/shared/utils/download'
import { RequirementDrawer, type RequirementFormValues } from '@/features/requirements/components/RequirementDrawer'
import { RequirementDocumentPreviewModal } from '@/features/requirements/components/RequirementDocumentPreviewModal'
import { RequirementDesignConfigurationModal } from '@/features/ai-testing/components/RequirementDesignConfigurationModal'
import { RequirementCodeRiskPanel } from '@/features/ai-testing/components/RequirementCodeRiskPanel'
import { useRequirementCodeRiskWorkspace } from '@/features/ai-testing/hooks/useRequirementCodeRiskWorkspace'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import 'antd/dist/reset.css'
import '@/app/styles/index.css'
import '@/shared/styles/surface-tokens.css'
import '@/shared/styles/list-table.css'
import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/task-detail-v2.css'
import '@/features/ai-testing/styles/requirement-design.css'
import '@/features/ai-testing/styles/requirement-generation-chain.css'
import '@/features/ai-testing/styles/functional-artifact-modal.css'
import '@/features/ai-testing/styles/functional-candidate-workbench.css'
import '@/features/ai-testing/styles/requirement-analysis.css'
import '@/features/ai-testing/styles/case-name-tree.css'
import '@/features/ai-testing/styles/run-result.css'
import '@/features/ai-testing/styles/api-config-result.css'
import { QueryProvider } from '@/app/providers/QueryProvider'
import { ThemeProvider } from '@/app/providers/ThemeProvider'
import { useRequirementGenerationChain } from '@/features/ai-testing/hooks/useRequirementGenerationChain'
import { GenerationChainModal } from '@/features/ai-testing/components/GenerationChainModal'
import type { GenerationChainKind } from '@/features/ai-testing/api/generationChain.api'

const params = new URLSearchParams(location.search)
const requirementId = params.get('requirementId') || ''
const projectId = params.get('projectId') || ''
const kind = (params.get('kind') || '') as GenerationChainKind
const stage = params.get('stage') || ''
const initialVersion = params.get('version') || ''
const initialDiff = params.get('diff') === '1'
const view = params.get('view') || 'stage'
const intent = params.get('intent') || ''
const closeViewer = () => parent.postMessage({ type: 'prototype-close' }, location.origin)
function Preview() {
  const workspace = useRequirementGenerationChain({ requirementId, projectId, enabled: Boolean(requirementId && projectId) })
  useEffect(() => { if (kind && stage) workspace.openStage(kind, stage) }, [kind, stage, workspace.openStage])
  useEffect(() => { if (workspace.stage && initialVersion) workspace.setVersionKey(initialVersion) }, [workspace.stage, workspace.setVersionKey])
  useEffect(() => { if (intent === 'revise' && workspace.stage?.draft) workspace.setRevisionOpen(true) }, [workspace.stage, workspace.setRevisionOpen])
  useEffect(() => { if (initialDiff && workspace.comparisonId) { workspace.setMode('raw'); workspace.setDiffOpen(true) } }, [workspace.comparisonId, workspace.setMode, workspace.setDiffOpen])
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (event.origin !== location.origin || event.source !== parent) return
      if (event.data?.type === 'prototype-version' && typeof event.data.version === 'string') { workspace.setVersionKey(event.data.version); workspace.setDiffOpen(false) }
      if (event.data?.type === 'prototype-diff') { workspace.setMode('raw'); workspace.setDiffOpen(true) }
      if (event.data?.type === 'prototype-revise') workspace.setRevisionOpen(true)
    }
    window.addEventListener('message', listener)
    return () => window.removeEventListener('message', listener)
  }, [workspace.setVersionKey, workspace.setDiffOpen, workspace.setMode, workspace.setRevisionOpen])
  const close = () => { workspace.closeStage(); closeViewer() }
  return <><style>{`
    html,body,#root{background:transparent!important;margin:0;height:100%}
    .gc-version-buttons{display:none!important}
  `}</style><GenerationChainModal workspace={workspace} requirementId={requirementId} projectId={projectId} open={Boolean(workspace.selected)} onClose={close} onOpenLegacy={(next) => { parent.postMessage({type:'prototype-configure',kind:next},location.origin) }} />{workspace.personalLlm.dialog}</>
}
function DocumentView() {
  const query = useQuery({queryKey: ['requirement', requirementId], queryFn: () => requirementsApi.getRequirement(requirementId)})
  const r = query.data
  if (!r) return <Modal open title="需求文档" onCancel={closeViewer} footer={null}>正在加载需求文档…</Modal>
  return <RequirementDocumentPreviewModal open onClose={closeViewer} requirementId={requirementId} requirementName={r.name} documentType={r.documentType} documentContent={r.documentContent} documentFilename={r.documentFilename} documentDownloadUrl={r.documentDownloadUrl} />
}
function RiskView() {
  const workspace=useRequirementCodeRiskWorkspace(requirementId,projectId,true)
  const access=useProjectAccess(projectId)
  return <Modal open centered title="代码风险分析" width="min(2000px, calc(100vw - 56px))" onCancel={closeViewer} footer={<Button onClick={closeViewer}>关闭</Button>}><RequirementCodeRiskPanel workspace={workspace} canWrite={access.can('write')} /></Modal>
}
function EditView() {
  const [form] = Form.useForm<RequirementFormValues>()
  const [documentLoading, setDocumentLoading] = useState(false)
  const [documentError, setDocumentError] = useState<string>()
  const query = useQuery({queryKey:['requirement',requirementId],queryFn:()=>requirementsApi.getRequirement(requirementId)})
  const r = query.data
  useEffect(() => {if(!r)return;form.setFieldsValue({name:r.name,documentType:r.documentType === 'docx' ? 'word' : r.documentType ?? 'text',documentContent:'',documentFilename:r.documentFilename,documentFileName:r.documentFilename,documentDownloadUrl:r.documentDownloadUrl,file:undefined});if(['text','richtext'].includes(r.documentType ?? '')) {setDocumentLoading(true);setDocumentError(undefined);void requirementsApi.downloadRequirementDocument(requirementId).then(x=>x.blob.text()).then(text=>form.setFieldValue('documentContent',text)).catch(()=>setDocumentError('需求正文加载失败，请关闭后重试。')).finally(()=>setDocumentLoading(false))}},[r,form])
  const save=useMutation({mutationFn:async(values:RequirementFormValues)=>{if(values.documentType==='richtext')return requirementsApi.replaceRequirementDocument(requirementId,{name:values.name,documentType:'richtext',documentContent:values.documentContent,onUploadProgress:values.onUploadProgress});if(values.file)return requirementsApi.replaceRequirementDocument(requirementId,{name:values.name,file:values.file,documentType:values.documentType,onUploadProgress:values.onUploadProgress});return requirementsApi.updateRequirement(requirementId,{name:values.name,...(values.documentType==='text'?{documentContent:values.documentContent??'',documentType:'text'}:{})})},onSuccess:closeViewer})
  if(!r)return <Modal open title="编辑需求" onCancel={closeViewer} footer={null}>正在加载…</Modal>
  return <RequirementDrawer title="编辑需求" open mode="edit" form={form} loading={save.isPending} error={save.error} documentLoading={documentLoading} documentError={documentError} projectId={projectId} onClose={closeViewer} onFinish={values=>save.mutate(values)} />
}
function DownloadView() {
  useEffect(() => { void requirementsApi.downloadRequirementDocument(requirementId).then(r => {saveBlob(r.blob,r.filename || '需求文档'); closeViewer()}).catch(() => {closeViewer(); parent.postMessage({type:'prototype-error', message:'下载失败，请在平台页面重试'},location.origin)}) }, [])
  return <Modal open title="下载原文件" footer={null} onCancel={closeViewer}>正在准备文件…</Modal>
}
function Viewer() {
  if (view === 'edit') return <EditView />
  if (view === 'download') return <DownloadView />
  if (view === 'document') return <DocumentView />
  if (view === 'risk') return <RiskView />
  if (view === 'setup') return <RequirementDesignConfigurationModal requirementId={requirementId} kind={kind} tasks={[]} onClose={closeViewer} onSaved={closeViewer} />
  return <Preview />
}
createRoot(document.getElementById('root')!).render(<QueryProvider><ThemeProvider><BrowserRouter><ProjectAccessScope projectId={projectId}><Viewer /></ProjectAccessScope></BrowserRouter></ThemeProvider></QueryProvider>)
