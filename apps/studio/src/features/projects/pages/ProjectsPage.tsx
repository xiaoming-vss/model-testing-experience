import { footerRange } from '@/shared/utils/pagination'
import { ActionButton } from '@/shared/components/ActionButton'
import { AppIcon } from '@/shared/icons'
import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { ProjectMembersModal } from '../components/ProjectMembersModal'
import { roleLabels, useProjectAccess } from '../hooks/useProjectAccess'
import { SettingOutlined, UserOutlined, BranchesOutlined, CheckCircleOutlined, FileTextOutlined, LinkOutlined, RocketOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Drawer,
  Divider,
  Empty,
  Form,
  Input,
  Pagination,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { type BindingDepth, ZentaoBindingModal, ZentaoBindingSummary } from '@/features/base-services/components/ZentaoBindingPanel'
import { GitlabBindingModal, GitlabBindingSummary } from '@/features/base-services/components/GitlabBindingPanel'
import { RequirementCodeBindingModal } from '@/features/base-services/components/RequirementCodeBindingModal'
import { useActiveProject } from '@/features/projects/hooks/useActiveProject'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { useSprintBoundaryRefresh } from '@/features/projects/hooks/useSprintBoundaryRefresh'
import { RequirementDocumentPreviewModal } from '@/features/requirements/components/RequirementDocumentPreviewModal'
import { RequirementDrawer, type RequirementFormValues } from '@/features/requirements/components/RequirementDrawer'
import {
  getRequirementDocumentSummary,
  getRequirementDocumentTypeLabel,
  hasRequirementDocument,
  normalizeRequirementDocumentType,
} from '@/features/requirements/utils/requirementDocument'
import { SprintDrawer } from '@/features/projects/components/SprintDrawer'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { api, listItems, type Project, type Requirement, type Sprint } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import {
  formatTime,
  getErrorMessage,
  normalizeProjectId,
  normalizeRequirementId,
  normalizeSprintId,
  pickCreatedAt,
  pickEndTime,
  pickStartTime,
  statusTag,
} from '@/utils/format'
import {
  buildProjectUpdatePayload,
  buildRequirementMetadataUpdatePayload,
  buildSprintCreatePayload,
  buildSprintUpdatePayload,
} from '@/utils/updatePayload'

const { Text, Title } = Typography

type RequirementPoolItem = Requirement & {
  sprintName: string
  sprintIdForCreate: string
}

type PaginationState = {
  projectId?: string
  page: number
}

type RequirementViewState = {
  projectId?: string
  page: number
}

type ZentaoBindingTargetState = {
  targetType: 'project' | 'sprint' | 'requirement'
  resourceId: string
  parentProjectId?: string
  parentSprintId?: string
  depth: BindingDepth
  title: string
}

function toPickerValue(value?: string) {
  if (!value) return undefined
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed : undefined
}

export function ProjectsPage() {
  const [membersOpen, setMembersOpen] = useState(false)
  const [settingsProjectId, setSettingsProjectId] = useState<string | null>(null)
  const { project: accessProject, can } = useProjectAccess()
  const [deleteProjectId, setDeleteProjectId] = useState<string | null>(null)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const projectModalOpen = useWorkbenchStore((state) => state.projectModalOpen)
  const editingProject = useWorkbenchStore((state) => state.editingProject)
  const openProjectModal = useWorkbenchStore((state) => state.openProjectModal)
  const closeProjectModal = useWorkbenchStore((state) => state.closeProjectModal)
  const [sprintDrawerOpen, setSprintDrawerOpen] = useState(false)
  const [editingSprint, setEditingSprint] = useState<Sprint | null>(null)
  const [requirementDrawerOpen, setRequirementDrawerOpen] = useState(false)
  const [editingRequirement, setEditingRequirement] = useState<RequirementPoolItem | null>(null)
  const [requirementDocumentLoading, setRequirementDocumentLoading] = useState(false)
  const [activeBoard, setActiveBoard] = useState<'sprints' | 'requirements'>('sprints')
  const [zentaoBindingTarget, setZentaoBindingTarget] = useState<ZentaoBindingTargetState | null>(null)
  const [gitlabBindingOpen, setGitlabBindingOpen] = useState(false)
  const [codeBindingRequirement, setCodeBindingRequirement] = useState<RequirementPoolItem | null>(null)
  const [sprintPagination, setSprintPagination] = useState<PaginationState>({ page: 1 })
  const [sprintPageSize, setSprintPageSize] = useState(10)
  const [requirementView, setRequirementView] = useState<RequirementViewState>({ page: 1 })
  const [requirementPageSize, setRequirementPageSize] = useState(10)
  const [previewRequirement, setPreviewRequirement] = useState<RequirementPoolItem | null>(null)
  const [projectForm] = Form.useForm()
  const [sprintForm] = Form.useForm()
  const [requirementForm] = Form.useForm<RequirementFormValues>()
  const requirementEditHydrationSeq = useRef(0)
  const { activeProjectId, projects, projectsQuery, setActiveProjectId } = useActiveProject()
  const { activeSprintId, selectSprint: selectGlobalSprint } = useActiveSprint()
  const activeProject = useMemo(
    () => projects.find((project) => normalizeProjectId(project) === activeProjectId),
    [activeProjectId, projects],
  )
  const sprintPage = sprintPagination.projectId === activeProjectId ? sprintPagination.page : 1
  const requirementPage = requirementView.projectId === activeProjectId ? requirementView.page : 1
  const selectedRequirementSprintId = activeSprintId

  useEffect(() => {
    setRequirementView({ projectId: activeProjectId, page: 1 })
  }, [activeProjectId, selectedRequirementSprintId])

  useEffect(() => {
    if (projectModalOpen) {
      projectForm.setFieldsValue(editingProject ?? { name: '', description: '' })
    }
  }, [editingProject, projectForm, projectModalOpen])

  const sprintsQuery = useQuery({
    queryKey: ['sprints', activeProjectId],
    queryFn: () => api.getSprints(activeProjectId!),
    enabled: Boolean(activeProjectId),
  })
  const sprints = listItems(sprintsQuery.data)
  useSprintBoundaryRefresh({ sprints, enabled: Boolean(activeProjectId), refresh: sprintsQuery.refetch })
  const sprintOptions = sprints.map((sprint) => ({ label: sprint.name, value: normalizeSprintId(sprint) }))
  const sprintIds = sprintOptions.map((option) => option.value).join(',')

  const requirementsQuery = useQuery({
    queryKey: ['requirementsPool', activeProjectId, sprintIds],
    queryFn: async () => {
      if (sprints.length === 0) return []
      const requirementGroups = await Promise.all(
        sprints.map(async (sprint) => {
          const sprintId = normalizeSprintId(sprint)
          const requirements = await api.getRequirements(sprintId)
          return requirements.map((requirement) => ({
            ...requirement,
            sprintName: sprint.name,
            sprintIdForCreate: sprintId,
          }))
        }),
      )
      return requirementGroups.flat()
    },
    enabled: Boolean(activeProjectId) && !sprintsQuery.isLoading,
  })
  const requirements = listItems(requirementsQuery.data)
  const filteredRequirements = !selectedRequirementSprintId
    ? requirements
    : requirements.filter((requirement) => requirement.sprintIdForCreate === selectedRequirementSprintId)
  const visibleSprints = sprints.slice((sprintPage - 1) * sprintPageSize, sprintPage * sprintPageSize)
  const visibleRequirements = filteredRequirements.slice(
    (requirementPage - 1) * requirementPageSize,
    requirementPage * requirementPageSize,
  )

  const saveProjectMutation = useMutation({
    mutationFn: (values: Pick<Project, 'name' | 'description'>) =>
      editingProject
        ? api.updateProject(normalizeProjectId(editingProject), buildProjectUpdatePayload(editingProject, values))
        : api.createProject(values),
    onSuccess: (project) => {
      message.success(editingProject ? '项目已更新' : '项目已创建')
      closeProjectModal()
      projectForm.resetFields()
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      if (!editingProject && project) setActiveProjectId(normalizeProjectId(project))
    },
  })

  const deleteProjectMutation = useMutation({
    mutationFn: api.deleteProject,
    onSuccess: () => {
      message.success('项目已删除')
      setActiveProjectId(undefined)
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  const saveSprintMutation = useMutation({
    mutationFn: (values: Parameters<typeof buildSprintCreatePayload>[0]) => {
      if (editingSprint) {
        return api.updateSprint(normalizeSprintId(editingSprint), buildSprintUpdatePayload(editingSprint, values))
      }
      return api.createSprint(activeProjectId!, buildSprintCreatePayload(values))
    },
    onSuccess: () => {
      message.success(editingSprint ? '迭代已更新' : '迭代已创建')
      closeSprintDrawer()
      queryClient.invalidateQueries({ queryKey: ['sprints', activeProjectId] })
      queryClient.invalidateQueries({ queryKey: ['requirementsPool', activeProjectId] })
    },
  })

  const deleteSprintMutation = useMutation({
    mutationFn: api.deleteSprint,
    onSuccess: () => {
      message.success('迭代已删除')
      queryClient.invalidateQueries({ queryKey: ['sprints', activeProjectId] })
      queryClient.invalidateQueries({ queryKey: ['requirementsPool', activeProjectId] })
    },
  })

  const saveRequirementMutation = useMutation({
    mutationFn: async (values: RequirementFormValues) => {
      if (editingRequirement) {
        const requirementId = normalizeRequirementId(editingRequirement)
        const metadataPayload = buildRequirementMetadataUpdatePayload(editingRequirement, values)
        const normalizedDocumentType = normalizeRequirementDocumentType(values.documentType)

        let updatedRequirement: Requirement | undefined
        if (values.file) {
          updatedRequirement = await api.replaceRequirementDocument(requirementId, {
            documentType: normalizedDocumentType,
            file: values.file,
          })
        }

        if (normalizedDocumentType === 'text') {
          updatedRequirement = await api.updateRequirement(requirementId, {
            ...metadataPayload,
            documentType: 'text',
            documentContent: values.documentContent?.trim() ?? '',
          })
        } else if (Object.keys(metadataPayload).length > 0) {
          updatedRequirement = await api.updateRequirement(requirementId, metadataPayload)
        }

        return updatedRequirement ?? editingRequirement
      }

      return api.createRequirement(values.sprintId!, {
        name: values.name,
        documentType: normalizeRequirementDocumentType(values.documentType) ?? 'text',
        documentContent: values.file ? undefined : values.documentContent,
        file: values.file,
      })
    },
    onSuccess: () => {
      message.success(editingRequirement ? '需求已更新' : '需求已创建')
      closeRequirementDrawer()
      queryClient.invalidateQueries({ queryKey: ['requirementsPool', activeProjectId] })
    },
  })

  const deleteRequirementMutation = useMutation({
    mutationFn: api.deleteRequirement,
    onSuccess: () => {
      message.success('需求已删除')
      queryClient.invalidateQueries({ queryKey: ['requirementsPool', activeProjectId] })
    },
  })

  function openSprintDrawer(sprint?: Sprint) {
    setEditingSprint(sprint ?? null)
    sprintForm.setFieldsValue(
      sprint
        ? {
            name: sprint.name,
            description: sprint.description,
            startTime: toPickerValue(pickStartTime(sprint)),
            endTime: toPickerValue(pickEndTime(sprint)),
          }
        : {
            name: '',
            description: '',
            startTime: undefined,
            endTime: undefined,
          },
    )
    setSprintDrawerOpen(true)
  }

  function closeSprintDrawer() {
    setSprintDrawerOpen(false)
    setEditingSprint(null)
    sprintForm.resetFields()
  }

  async function hydrateRequirementTextDocument(requirement: RequirementPoolItem, sequence: number) {
    setRequirementDocumentLoading(true)

    try {
      const response = await api.downloadRequirementDocument(normalizeRequirementId(requirement))
      const documentContent = await response.blob.text()

      if (requirementEditHydrationSeq.current !== sequence) return
      requirementForm.setFieldValue('documentContent', documentContent)
      void requirementForm.validateFields(['documentContent'])
    } catch (loadError) {
      if (requirementEditHydrationSeq.current !== sequence) return
      message.error(`需求正文加载失败：${getErrorMessage(loadError)}`)
    } finally {
      if (requirementEditHydrationSeq.current === sequence) {
        setRequirementDocumentLoading(false)
      }
    }
  }

  function openRequirementDrawer(requirement?: RequirementPoolItem) {
    const sequence = requirementEditHydrationSeq.current + 1
    requirementEditHydrationSeq.current = sequence
    const normalizedDocumentType = normalizeRequirementDocumentType(requirement?.documentType) ?? 'text'

    setEditingRequirement(requirement ?? null)
    requirementForm.setFieldsValue(
      requirement
        ? {
            sprintId: requirement.sprintIdForCreate,
            name: requirement.name,
            documentType: normalizedDocumentType,
            documentContent: '',
            file: undefined,
            documentFileName: requirement.documentFilename,
            documentFilename: requirement.documentFilename,
            documentDownloadUrl: requirement.documentDownloadUrl,
          }
        : {
            sprintId: selectedRequirementSprintId ?? sprintOptions[0]?.value,
            name: '',
            documentType: 'text',
            documentContent: '',
            file: undefined,
            documentFileName: undefined,
            documentFilename: undefined,
            documentDownloadUrl: undefined,
          },
    )
    setRequirementDrawerOpen(true)

    if (requirement && normalizedDocumentType === 'text') {
      void hydrateRequirementTextDocument(requirement, sequence)
    } else {
      setRequirementDocumentLoading(false)
    }
  }

  function closeRequirementDrawer() {
    requirementEditHydrationSeq.current += 1
    setRequirementDocumentLoading(false)
    setRequirementDrawerOpen(false)
    setEditingRequirement(null)
    requirementForm.resetFields()
  }

  function openSprintDetail(sprintId: string) {
    if (!activeProjectId) return
    navigate(`/projects/${activeProjectId}/sprints/${sprintId}`)
  }

  function openZentaoBinding(target: ZentaoBindingTargetState) {
    setZentaoBindingTarget(target)
  }

  const requirementColumns: TableProps<RequirementPoolItem>['columns'] = [
    {
      title: '需求名称',
      dataIndex: 'name',
      key: 'name',
      width: '28%',
      ellipsis: true,
      render: (name: RequirementPoolItem['name'], requirement) => (
        <Space size={0} className="project-requirement-list-name">
          <Tooltip title={name}>
            <Text
              ellipsis
              onClick={(event) => {
                event.stopPropagation()
                if (hasRequirementDocument(requirement)) {
                  setPreviewRequirement(requirement)
                  return
                }
                openRequirementDrawer(requirement)
              }}
            >
              {name}
            </Text>
          </Tooltip>
        </Space>
      ),
    },
    {
      title: '所属迭代',
      dataIndex: 'sprintName',
      key: 'sprintName',
      width: 150,
      render: (sprintName: RequirementPoolItem['sprintName']) => (
        <Tag className="project-requirement-list-tag" color="blue">
          {sprintName}
        </Tag>
      ),
    },
    {
      title: '文档类型',
      key: 'documentType',
      width: 130,
      render: (_, requirement) => (
        <Tag color={normalizeRequirementDocumentType(requirement.documentType) === 'word' ? 'purple' : requirement.documentType === 'text' ? 'blue' : 'cyan'}>
          {getRequirementDocumentTypeLabel(requirement.documentType)}
        </Tag>
      ),
    },
    {
      title: '绑定信息',
      key: 'bindingInfo',
      width: '24%',
      ellipsis: true,
      render: (_, requirement) => (
        <div className="project-requirement-list-binding-info">
          <ZentaoBindingSummary targetType="requirement" resourceId={normalizeRequirementId(requirement)} />
        </div>
      ),
    },
    {
      title: '文档摘要',
      key: 'documentSummary',
      width: 150,
      render: (_, requirement) =>
        hasRequirementDocument(requirement) ? (
          <Button
            type="link"
            className="project-requirement-document-link"
            title={getRequirementDocumentSummary(requirement)}
            onClick={(event) => {
              event.stopPropagation()
              setPreviewRequirement(requirement)
            }}
          >
            查看文档
          </Button>
        ) : (
          <Tooltip title={getRequirementDocumentSummary(requirement)}>
            <Text type="secondary" ellipsis>
              {getRequirementDocumentSummary(requirement)}
            </Text>
          </Tooltip>
        ),
    },
    {
      title: '创建时间',
      key: 'createdAt',
      width: 180,
      render: (_, requirement) => <Text type="secondary">{formatTime(pickCreatedAt(requirement))}</Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 190,
      align: 'right',
      render: (_, requirement) => (
        <Space
          size={6}
          className="project-requirement-list-actions"
          onClick={(event) => event.stopPropagation()}
          onMouseDown={(event) => event.stopPropagation()}
        >
          <Tooltip title="编辑需求">
            <ProjectActionButton action="write"
              type="text"
              shape="circle"
              className="action-btn-update"
              operation="edit" iconOnly
              aria-label="编辑需求"
              onClick={() => openRequirementDrawer(requirement)}
            />
          </Tooltip>
          <Tooltip title="禅道绑定">
            <ProjectActionButton action="manage"
              type="text"
              shape="circle"
              className="action-btn-read"
              icon={<LinkOutlined />}
              aria-label="绑定禅道需求 Story"
              onClick={() =>
                openZentaoBinding({
                  targetType: 'requirement',
                  resourceId: normalizeRequirementId(requirement),
                  parentProjectId: activeProjectId,
                  parentSprintId: requirement.sprintIdForCreate,
                  depth: 'story',
                  title: `绑定禅道需求 Story · ${requirement.name}`,
                })
              }
            />
          </Tooltip>
          <Tooltip title="代码绑定">
            <ProjectActionButton action="manage"
              type="text"
              shape="circle"
              className="action-btn-read"
              icon={<BranchesOutlined />}
              aria-label="代码绑定"
              onClick={() => setCodeBindingRequirement(requirement)}
            />
          </Tooltip>
          <Popconfirm title="确认删除该需求？" onConfirm={() => deleteRequirementMutation.mutate(normalizeRequirementId(requirement))}>
            <Tooltip title="删除需求">
              <ProjectActionButton action="write"
                danger
                type="text"
                shape="circle"
                className="action-btn-delete"
                operation="delete" iconOnly
                aria-label="删除需求"
                loading={deleteRequirementMutation.isPending && deleteRequirementMutation.variables === normalizeRequirementId(requirement)}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="workbench-page project-overview-page">
      {projectsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(projectsQuery.error)} /> : null}

      {!projectsQuery.isLoading && projects.length === 0 ? (
        <div className="workbench-empty">
          <Empty description="暂无项目，请先新建项目">
            <ActionButton type="primary" className="action-btn-create" operation="create" onClick={() => openProjectModal()}>
              新建项目
            </ActionButton>
          </Empty>
        </div>
      ) : (
        <>
          <section className="workbench-project-toolbar">
            <div>
              <Space align="center" size={10}><Title level={4} style={{ margin: 0 }}>{activeProject?.name || '项目概览'}</Title>{accessProject?.role ? <Tag>{roleLabels[accessProject.role]}</Tag> : null}</Space>
              <div className="zentao-binding-toolbar-line">
                <Text type="secondary" className="project-description-text">
                  项目描述：{activeProject?.description || '暂无描述'}
                </Text>
              </div>
            </div>
            <Space size={8} className="project-actions">
              <Button className="action-btn-read" icon={<UserOutlined />} disabled={!activeProjectId} onClick={() => setMembersOpen(true)}>项目成员</Button>
              <ProjectActionButton action="manage" className="action-btn-update" icon={<SettingOutlined />} disabled={!activeProject} onClick={() => activeProjectId && setSettingsProjectId(activeProjectId)}>项目设置</ProjectActionButton>
            </Space>
          </section>

          <div className="workbench-tabs">
            <div className="workbench-board-switcher">
              <Segmented
                value={activeBoard}
                onChange={(value) => setActiveBoard(value as 'sprints' | 'requirements')}
                options={[
                  { label: '迭代', value: 'sprints', icon: <AppIcon name="sprint" /> },
                  { label: '需求', value: 'requirements', icon: <AppIcon name="requirement" /> },
                ]}
              />
            </div>

            <section className="workbench-panel workbench-board-panel">
              {activeBoard === 'sprints' ? (
                <>
                  <div className="panel-header">
                    <Text strong>迭代列表</Text>
                    <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" disabled={!activeProjectId} onClick={() => openSprintDrawer()}>
                      新建迭代
                    </ProjectActionButton>
                  </div>
                  {sprintsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(sprintsQuery.error)} /> : null}
                  <div className="table-body-scroll sprint-card-scroll">
                    {sprintsQuery.isLoading ? <div className="sprint-card-loading"><Empty description="迭代加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} /></div> : null}
                    {!sprintsQuery.isLoading && visibleSprints.length === 0 ? <Empty description="暂无迭代" /> : null}
                    {!sprintsQuery.isLoading && visibleSprints.length > 0 ? (
                        <div className="sprint-card-grid sprint-card-grid-workbench">
                        {visibleSprints.map((sprint) => (
                          <Card
                            key={normalizeSprintId(sprint)}
                            hoverable
                            className="sprint-card"
                            styles={{ body: { padding: 20 } }}
                            onClick={() => openSprintDetail(normalizeSprintId(sprint))}
                          >
                            <div className="sprint-card-head">
                              <div className="sprint-card-title-wrap">
                                <Space size={10}>
                                  {sprint.status === 'completed' ? (
                                    <CheckCircleOutlined className="sprint-icon done" />
                                  ) : (
                                    <RocketOutlined className="sprint-icon running" />
                                  )}
                                  <div className="sprint-card-title" title={sprint.name}>
                                    {sprint.name}
                                  </div>
                                </Space>
                              </div>
                              <div className="sprint-card-status">{statusTag(sprint.status)}</div>
                            </div>
                            <div className="sprint-card-meta">
                              <span className="sprint-card-label">开始时间</span>
                              <span className="sprint-card-value project-time-text">{formatTime(pickStartTime(sprint))}</span>
                            </div>
                            <div className="sprint-card-meta">
                              <span className="sprint-card-label">结束时间</span>
                              <span className="sprint-card-value project-time-text">{formatTime(pickEndTime(sprint))}</span>
                            </div>
                            <div className="sprint-card-binding-line">
                              <ZentaoBindingSummary targetType="sprint" resourceId={normalizeSprintId(sprint)} />
                            </div>
                            <div className="sprint-card-description project-description-text" title={sprint.description || '暂无迭代描述'}>
                              {sprint.description || '暂无迭代描述'}
                            </div>
                            <div className="sprint-card-actions">
                                <Tooltip title="编辑迭代">
                                  <ProjectActionButton action="write"
                                    type="text"
                                    shape="circle"
                                    className="action-btn-update"
                                    operation="edit" iconOnly
                                    aria-label="编辑迭代"
                                    onClick={(event) => {
                                      event.stopPropagation()
                                      openSprintDrawer(sprint)
                                    }}
                                  />
                                </Tooltip>
                                <Tooltip title="禅道绑定">
                                  <ProjectActionButton action="manage"
                                    type="text"
                                    shape="circle"
                                    className="action-btn-read"
                                    icon={<LinkOutlined />}
                                    aria-label="绑定禅道执行"
                                    onClick={(event) => {
                                      event.stopPropagation()
                                      openZentaoBinding({
                                        targetType: 'sprint',
                                        resourceId: normalizeSprintId(sprint),
                                        parentProjectId: activeProjectId,
                                        depth: 'execution',
                                        title: `绑定禅道执行 · ${sprint.name}`,
                                      })
                                    }}
                                  />
                                </Tooltip>
                                <Popconfirm title="确认删除该迭代？" onConfirm={() => deleteSprintMutation.mutate(normalizeSprintId(sprint))}>
                                  <Tooltip title="删除迭代">
                                    <ProjectActionButton action="write"
                                      danger
                                      type="text"
                                      shape="circle"
                                      className="action-btn-delete"
                                      operation="delete" iconOnly
                                      aria-label="删除迭代"
                                      loading={deleteSprintMutation.isPending}
                                      onClick={(event) => event.stopPropagation()}
                                    />
                                  </Tooltip>
                                </Popconfirm>
                                <Tooltip title="查看迭代详情">
                                  <Button
                                    type="text"
                                    shape="circle"
                                    className="action-btn-read"
                                    icon={<FileTextOutlined />}
                                    aria-label="查看迭代详情"
                                    onClick={(event) => {
                                      event.stopPropagation()
                                      openSprintDetail(normalizeSprintId(sprint))
                                    }}
                                  />
                                </Tooltip>
                            </div>
                          </Card>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="table-footer">
                    <Text type="secondary">{footerRange(sprints.length, sprintPage, sprintPageSize)}</Text>
                    <Pagination
                      current={sprintPage}
                      pageSize={sprintPageSize}
                      total={sprints.length}
                      showSizeChanger
                      pageSizeOptions={['10', '20', '50']}
                      onChange={(page, pageSize) => {
                        setSprintPagination({ projectId: activeProjectId, page })
                        setSprintPageSize(pageSize)
                      }}
                    />
                  </div>
                </>
              ) : (
                <>
                  <div className="panel-header">
                    <div className="requirement-panel-head">
                      <Text strong>需求列表</Text>
                      <div className="requirement-filter-bar">
                        <span className="requirement-filter-label">迭代范围</span>
                        <div className="requirement-filter-control">
                          <Select
                            className="requirement-filter-select"
                            loading={sprintsQuery.isLoading}
                            value={selectedRequirementSprintId}
                            placeholder="筛选迭代"
                            allowClear
                            options={sprintOptions}
                            onChange={(value) => {
                              selectGlobalSprint(value)
                            }}
                            variant="borderless"
                            disabled={sprints.length === 0}
                          />
                        </div>
                      </div>
                    </div>
                    <ProjectActionButton action="write"
                      type="primary"
                      className="action-btn-create"
                      operation="create"
                      disabled={!activeProjectId || sprints.length === 0}
                      onClick={() => openRequirementDrawer()}
                    >
                      新建需求
                    </ProjectActionButton>
                  </div>
                  {requirementsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(requirementsQuery.error)} /> : null}
                  <div className="table-body-scroll sprint-card-scroll">
                    {sprintsQuery.isLoading || requirementsQuery.isLoading ? (
                      <div className="sprint-card-loading">
                        <Empty description="需求加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                      </div>
                    ) : null}
                    {!sprintsQuery.isLoading && !requirementsQuery.isLoading && sprints.length === 0 ? (
                      <Empty description="请先创建迭代，再添加需求" />
                    ) : null}
                    {!sprintsQuery.isLoading && !requirementsQuery.isLoading && sprints.length > 0 && visibleRequirements.length === 0 ? (
                      <Empty description="暂无需求" />
                    ) : null}
                    {!sprintsQuery.isLoading && !requirementsQuery.isLoading && visibleRequirements.length > 0 ? (
                      <Table<RequirementPoolItem>
                        className="project-requirement-list-table"
                        columns={requirementColumns}
                        dataSource={visibleRequirements}
                        rowKey={(requirement) => normalizeRequirementId(requirement)}
                        pagination={false}
                      />
                    ) : null}
                  </div>
                  <div className="table-footer">
                    <Text type="secondary">{footerRange(filteredRequirements.length, requirementPage, requirementPageSize)}</Text>
                    <Pagination
                      current={requirementPage}
                      pageSize={requirementPageSize}
                      total={filteredRequirements.length}
                      showSizeChanger
                      pageSizeOptions={['10', '20', '30', '50']}
                      onChange={(page, pageSize) => {
                        setRequirementView({
                          projectId: activeProjectId,
                          page,
                        })
                        setRequirementPageSize(pageSize)
                      }}
                    />
                  </div>
                </>
              )}
            </section>
          </div>
        </>
      )}

      <Drawer title="项目设置" className="project-settings-drawer" size={480} open={Boolean(settingsProjectId && settingsProjectId === activeProjectId && activeProject && can('manage'))} onClose={() => setSettingsProjectId(null)}>
        {activeProject && settingsProjectId === activeProjectId && can('manage') ? <>
          <Title level={5}>基本信息</Title>
          <Card size="small">
            <div className="project-settings-row">
              <div className="project-settings-copy"><Text type="secondary">项目名称</Text><div><Text strong>{activeProject.name}</Text></div></div>
              <ProjectActionButton action="manage" operation="edit" onClick={() => { setSettingsProjectId(null); openProjectModal(activeProject) }}>编辑</ProjectActionButton>
            </div>
            <div style={{ marginTop: 12 }}><Text type="secondary">{activeProject.description || '暂无描述'}</Text></div>
          </Card>
          <Title level={5} style={{ marginTop: 24 }}>外部绑定</Title>
          <Card size="small">
            <div className="project-settings-row">
              <Space size={10}><AppIcon name="zentao" size={32} /><Text strong>禅道</Text></Space>
              <ProjectActionButton action="manage" icon={<LinkOutlined />} onClick={() => { setSettingsProjectId(null); if (activeProjectId) openZentaoBinding({ targetType: 'project', resourceId: activeProjectId, depth: 'project', title: `绑定禅道项目 · ${activeProject.name}` }) }}>配置</ProjectActionButton>
            </div>
            {activeProjectId ? <ZentaoBindingSummary targetType="project" resourceId={activeProjectId} variant="settings" /> : null}
            <Divider style={{ margin: '16px 0' }} />
            <div className="project-settings-row">
              <Space size={10}><AppIcon name="gitlab" size={32} /><Text strong>GitLab</Text></Space>
              <ProjectActionButton action="manage" icon={<LinkOutlined />} onClick={() => { setSettingsProjectId(null); setGitlabBindingOpen(true) }}>配置</ProjectActionButton>
            </div>
            {activeProjectId ? <GitlabBindingSummary projectId={activeProjectId} variant="settings" /> : null}
          </Card>
          <Divider style={{ margin: '32px 0 20px' }} />
          <div className="project-settings-row">
            <Text type="secondary">项目操作</Text>
            <ProjectActionButton action="manage" danger operation="delete" onClick={() => { setSettingsProjectId(null); if (activeProjectId) setDeleteProjectId(activeProjectId) }}>删除项目</ProjectActionButton>
          </div>
        </> : null}
      </Drawer>

      <ProjectActionModal action="manage" projectId={deleteProjectId ?? undefined} title="确认删除当前项目？" open={Boolean(deleteProjectId)} okText="删除项目" cancelText="取消" okButtonProps={{ danger: true }} confirmLoading={deleteProjectMutation.isPending} onCancel={() => setDeleteProjectId(null)} onOk={() => { if (deleteProjectId) deleteProjectMutation.mutate(deleteProjectId, { onSuccess: () => setDeleteProjectId(null) }) }}>
        <Text>确认删除该项目？</Text>
      </ProjectActionModal>
      {membersOpen && activeProjectId ? <ProjectMembersModal key={activeProjectId} projectId={activeProjectId} onClose={() => setMembersOpen(false)} /> : null}
      <ProjectActionModal action={editingProject ? 'manage' : undefined}
        title={editingProject ? '编辑项目' : '新建项目'}
        open={projectModalOpen}
        onCancel={closeProjectModal}
        onOk={() => projectForm.submit()}
        confirmLoading={saveProjectMutation.isPending}
      >
        {saveProjectMutation.error ? <Alert showIcon type="error" title={getErrorMessage(saveProjectMutation.error)} /> : null}
        <Form form={projectForm} layout="vertical" onFinish={(values) => saveProjectMutation.mutate(values)} requiredMark={false}>
          <Form.Item name="name" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item name="description" label="项目描述">
            <Input.TextArea maxLength={256} rows={4} />
          </Form.Item>
        </Form>
      </ProjectActionModal>

      <SprintDrawer
        title={editingSprint ? '编辑迭代' : '新建迭代'}
        open={sprintDrawerOpen}
        form={sprintForm}
        loading={saveSprintMutation.isPending}
        error={saveSprintMutation.error}
        onClose={closeSprintDrawer}
        onFinish={(values) => saveSprintMutation.mutate(values)}
      />

      <RequirementDrawer
        title={editingRequirement ? '编辑需求' : '新建需求'}
        open={requirementDrawerOpen}
        form={requirementForm}
        loading={saveRequirementMutation.isPending}
        error={saveRequirementMutation.error}
        documentLoading={requirementDocumentLoading}
        mode={editingRequirement ? 'edit' : 'create'}
        sprintOptions={editingRequirement ? undefined : sprintOptions}
        onClose={closeRequirementDrawer}
        onFinish={(values) => saveRequirementMutation.mutate(values)}
      />

      {gitlabBindingOpen && activeProjectId ? (
        <GitlabBindingModal
          open
          onClose={() => setGitlabBindingOpen(false)}
          projectId={activeProjectId}
          projectName={activeProject?.name}
          requirementNameResolver={(requirementId) => {
            const requirement = requirements.find((item) => normalizeRequirementId(item) === requirementId)
            return requirement?.name
          }}
        />
      ) : null}

      {codeBindingRequirement && activeProjectId ? (
        <RequirementCodeBindingModal
          open
          onClose={() => setCodeBindingRequirement(null)}
          projectId={activeProjectId}
          requirementId={normalizeRequirementId(codeBindingRequirement)}
          requirementName={codeBindingRequirement.name}
        />
      ) : null}

      {zentaoBindingTarget ? (
        <ZentaoBindingModal
          open
          onClose={() => setZentaoBindingTarget(null)}
          projectId={zentaoBindingTarget.parentProjectId ?? (zentaoBindingTarget.targetType === 'project' ? zentaoBindingTarget.resourceId : activeProjectId ?? '')}
          targetType={zentaoBindingTarget.targetType}
          resourceId={zentaoBindingTarget.resourceId}
          parentProjectId={zentaoBindingTarget.parentProjectId}
          parentSprintId={zentaoBindingTarget.parentSprintId}
          depth={zentaoBindingTarget.depth}
          title={zentaoBindingTarget.title}
        />
      ) : null}

      <RequirementDocumentPreviewModal
        open={Boolean(previewRequirement)}
        onClose={() => setPreviewRequirement(null)}
        requirementName={previewRequirement?.name}
        documentType={previewRequirement?.documentType}
        documentContent={previewRequirement?.documentContent}
        documentFilename={previewRequirement?.documentFilename}
        documentDownloadUrl={previewRequirement?.documentDownloadUrl}
        requirementId={previewRequirement ? normalizeRequirementId(previewRequirement) : undefined}
      />
    </div>
  )
}
