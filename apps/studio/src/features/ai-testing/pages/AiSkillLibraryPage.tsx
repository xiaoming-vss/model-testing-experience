import { saveBlob } from '@/shared/utils/download'
import { ActionButton } from '@/shared/components/ActionButton'
import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { UploadOutlined } from '@ant-design/icons'
import { Alert, Card, Empty, Pagination, Popconfirm, Space, Tag, Tooltip, Typography, Upload } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import '@/features/ai-testing/styles/index.css'
import { useActiveProject } from '@/features/projects/hooks/useActiveProject'
import { api, listItems, type AiSkillLibraryItem, type UploadAiSkillPayload } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'

const { Text } = Typography

function getSkillSpaceId(skill: AiSkillLibraryItem) {
  return skill.skillSpaceId
}

function isSkillArchiveFile(fileName: string) {
  return /\.(zip|tar)$/i.test(fileName.trim())
}

function footerRange(total: number) {
  if (total === 0) return '显示第 0 条 - 第 0 条，共 0 条'
  return `显示第 1 条 - 第 ${total} 条，共 ${total} 条`
}

export function AiSkillLibraryPage({ embedded = false }: { embedded?: boolean }) {
  const queryClient = useQueryClient()
  const { activeProjectId, projectsQuery } = useActiveProject()
  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const skillsQuery = useQuery({
    queryKey: ['aiSkillLibrary', activeProjectId],
    queryFn: () => api.getAiSkillLibraryItems(activeProjectId!),
    enabled: Boolean(activeProjectId),
  })
  const skills = listItems(skillsQuery.data)

  const uploadSkillMutation = useMutation({
    mutationFn: (payload: UploadAiSkillPayload) => api.uploadAiSkill(activeProjectId!, payload),
    onSuccess: () => {
      message.success('Skill 包已上传')
      closeUploadModal()
      queryClient.invalidateQueries({ queryKey: ['aiSkillLibrary', activeProjectId] })
    },
  })

  const deleteSkillMutation = useMutation({
    mutationFn: (skillSpaceId: string) => api.deleteAiSkill(activeProjectId!, skillSpaceId),
    onSuccess: () => {
      message.success('Skill 包已删除')
      queryClient.invalidateQueries({ queryKey: ['aiSkillLibrary', activeProjectId] })
    },
  })

  const downloadSkillMutation = useMutation({
    mutationFn: (skill: AiSkillLibraryItem) => api.downloadAiSkill(activeProjectId!, getSkillSpaceId(skill)),
    onSuccess: (response, skill) => {
      saveBlob(response.blob, response.filename || skill.filename || 'skill-package')
    },
  })

  function openUploadModal() {
    setUploadFile(null)
    setUploadModalOpen(true)
  }

  function closeUploadModal() {
    setUploadModalOpen(false)
    setUploadFile(null)
  }

  function handleUpload() {
    if (!uploadFile) {
      message.warning('请先选择 Skill 压缩包')
      return
    }

    uploadSkillMutation.mutate({
      file: uploadFile,
    })
  }

  function handleDeleteSkill(skill: AiSkillLibraryItem) {
    if (skill.isDefault) {
      message.warning('默认 Skill 不允许删除')
      return
    }

    deleteSkillMutation.mutate(getSkillSpaceId(skill))
  }

  const content = (
    <>
      <div className="workbench-tabs ai-skill-library-tabs">
        <section className="workbench-panel workbench-board-panel ai-testing-task-panel ai-skill-library-panel">
          <div className="panel-header ai-task-panel-header ai-skill-library-panel-head">
            <Text strong>Skill 包列表</Text>
            <Space wrap size={8}>
              <ActionButton operation="refresh" onClick={() => skillsQuery.refetch()} disabled={!activeProjectId}>
                刷新
              </ActionButton>
              <ProjectActionButton action="manage" type="primary" className="action-btn-create" operation="create" disabled={!activeProjectId} onClick={openUploadModal}>
                上传 Skill
              </ProjectActionButton>
            </Space>
          </div>

          {projectsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(projectsQuery.error)} style={{ margin: '12px 18px 0' }} /> : null}
          {skillsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(skillsQuery.error)} style={{ margin: '12px 18px 0' }} /> : null}
          {uploadSkillMutation.error ? <Alert showIcon type="error" title={getErrorMessage(uploadSkillMutation.error)} style={{ margin: '12px 18px 0' }} /> : null}
          {deleteSkillMutation.error ? <Alert showIcon type="error" title={getErrorMessage(deleteSkillMutation.error)} style={{ margin: '12px 18px 0' }} /> : null}
          {downloadSkillMutation.error ? <Alert showIcon type="error" title={getErrorMessage(downloadSkillMutation.error)} style={{ margin: '12px 18px 0' }} /> : null}

          <div className="table-body-scroll ai-testing-card-scroll ai-skill-library-body">
            {!activeProjectId ? (
              <div className="sprint-card-loading ai-testing-empty-shell ai-skill-library-empty">
                <Empty description="请先选择项目，再进入 Skill库" />
              </div>
            ) : skillsQuery.isLoading ? (
              <div className="sprint-card-loading ai-testing-empty-shell ai-skill-library-empty">
                <Empty description="Skill库加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
              </div>
            ) : skills.length === 0 ? (
              <div className="ai-testing-empty-shell ai-skill-library-empty">
                <Empty description="当前项目下暂无 Skill 包">
                  <ActionButton type="primary" operation="create" onClick={openUploadModal}>
                    上传第一个 Skill
                  </ActionButton>
                </Empty>
              </div>
            ) : (
              <div className="ai-skill-library-grid">
                {skills.map((skill) => {
                  const skillSpaceId = getSkillSpaceId(skill)
                  const isDefaultSkill = Boolean(skill.isDefault)
                  return (
                    <Card key={skillSpaceId} className="ai-skill-card" hoverable>
                      <div className="ai-skill-card-head">
                        <div className="ai-skill-card-title">
                          <Text strong ellipsis={{ tooltip: skill.filename }}>
                            {skill.filename || '未命名 Skill 包'}
                          </Text>
                          {isDefaultSkill ? <Tag color="blue">默认</Tag> : null}
                        </div>
                        <Space size={6}>
                          <Tooltip title="下载">
                            <ActionButton
                              type="text"
                              shape="circle"
                              operation="download" iconOnly
                              aria-label="下载 Skill 包"
                              loading={downloadSkillMutation.isPending && downloadSkillMutation.variables === skill}
                              onClick={() => downloadSkillMutation.mutate(skill)}
                            />
                          </Tooltip>
                          <Popconfirm
                            title="确认删除该 Skill 包？"
                            disabled={isDefaultSkill}
                            onConfirm={() => handleDeleteSkill(skill)}
                          >
                            <Tooltip title={isDefaultSkill ? '默认 Skill 不允许删除' : '删除'}>
                              <span>
                                <ProjectActionButton action="manage"
                                  danger
                                  type="text"
                                  shape="circle"
                                  operation="delete" iconOnly
                                  aria-label={isDefaultSkill ? '默认 Skill 不允许删除' : '删除 Skill 包'}
                                  disabled={isDefaultSkill}
                                  loading={deleteSkillMutation.isPending && deleteSkillMutation.variables === skillSpaceId}
                                />
                              </span>
                            </Tooltip>
                          </Popconfirm>
                        </Space>
                      </div>
                    </Card>
                  )
                })}
              </div>
            )}
          </div>

          <div className="table-footer ai-skill-library-footer">
            <Text type="secondary">{footerRange(skills.length)}</Text>
            <Pagination current={1} pageSize={18} total={skills.length} showSizeChanger pageSizeOptions={['18']} disabled />
          </div>
        </section>
      </div>

      <ProjectActionModal action="manage"
        mask={{ closable: false }}
        open={uploadModalOpen}
        title="上传 Skill 包"
        okText="上传"
        onCancel={closeUploadModal}
        onOk={handleUpload}
        confirmLoading={uploadSkillMutation.isPending}
        okButtonProps={{ className: 'action-btn-save' }}
        destroyOnHidden
      >
        <Upload.Dragger
          accept=".zip,.tar"
          maxCount={1}
          beforeUpload={(file) => {
            if (!isSkillArchiveFile(file.name)) {
              message.error('仅支持 .zip / .tar 文件')
              return Upload.LIST_IGNORE
            }
            setUploadFile(file)
            return false
          }}
          onRemove={() => {
            setUploadFile(null)
            return true
          }}
        >
          <p className="ant-upload-drag-icon">
            <UploadOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽 Skill 压缩包到这里</p>
          <p className="ant-upload-hint">同项目下同名文件会由后端覆盖并自动递增版本号。</p>
        </Upload.Dragger>
      </ProjectActionModal>
    </>
  )

  if (embedded) return content

  return (
    <div className="workbench-page ai-testing-page ai-skill-library-page">
      {content}
    </div>
  )
}
