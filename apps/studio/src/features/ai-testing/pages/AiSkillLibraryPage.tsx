import { saveBlob } from '@/shared/utils/download'
import { ActionButton } from '@/shared/components/ActionButton'
import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { Alert, Card, Empty, Popconfirm, Space, Tag, Tooltip, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { skillFolder } from '../api/skills.api'
import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/skill-library.css'
import { useActiveProject } from '@/features/projects/hooks/useActiveProject'
import { api, listItems, type AiSkillLibraryItem, type UploadAiSkillPayload } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'

const { Text } = Typography

function getSkillSpaceId(skill: AiSkillLibraryItem) {
  return skill.skillSpaceId
}

function footerRange(total: number) {
  if (total === 0) return '显示第 0 条 - 第 0 条，共 0 条'
  return `显示第 1 条 - 第 ${total} 条，共 ${total} 条`
}

export function AiSkillLibraryPage({ embedded = false }: { embedded?: boolean }) {
  const queryClient = useQueryClient()
  const { activeProjectId, projectsQuery } = useActiveProject()
  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  const [uploadFiles, setUploadFiles] = useState<File[]>([])
  const skillsQuery = useQuery({
    queryKey: ['aiSkillLibrary', activeProjectId],
    queryFn: () => api.getAiSkillLibraryItems(activeProjectId!),
    enabled: Boolean(activeProjectId),
  })
  const skills = listItems(skillsQuery.data)

  const uploadSkillMutation = useMutation({
    mutationFn: (payload: UploadAiSkillPayload) => api.uploadAiSkill(activeProjectId!, payload),
    onSuccess: () => {
      message.success('Skill 已上传')
      closeUploadModal()
      queryClient.invalidateQueries({ queryKey: ['aiSkillLibrary', activeProjectId] })
    },
  })

  const deleteSkillMutation = useMutation({
    mutationFn: (skillSpaceId: string) => api.deleteAiSkill(activeProjectId!, skillSpaceId),
    onSuccess: () => {
      message.success('Skill 已删除')
      queryClient.invalidateQueries({ queryKey: ['aiSkillLibrary', activeProjectId] })
    },
  })

  const downloadSkillMutation = useMutation({
    mutationFn: (skill: AiSkillLibraryItem) => api.downloadAiSkill(activeProjectId!, getSkillSpaceId(skill)),
    onSuccess: (response, skill) => {
      saveBlob(response.blob, response.filename || `${skill.filename || 'skill'}.zip`)
    },
  })

  function openUploadModal() {
    setUploadFiles([])
    setUploadModalOpen(true)
  }

  function closeUploadModal() {
    setUploadModalOpen(false)
    setUploadFiles([])
  }

  function handleUpload() {
    if (!uploadFiles.length) {
      message.warning('请先选择 Skill 文件夹')
      return
    }

    uploadSkillMutation.mutate({
      files: uploadFiles,
    })
  }

  function handleDeleteSkill(skill: AiSkillLibraryItem) {
    if (skill.isDefault) {
      message.warning('系统默认 Skill 不允许删除')
      return
    }

    deleteSkillMutation.mutate(getSkillSpaceId(skill))
  }

  const content = (
    <>
      <div className="workbench-tabs ai-skill-library-tabs">
        <section className="workbench-panel workbench-board-panel ai-testing-task-panel ai-skill-library-panel">
          <div className="panel-header ai-task-panel-header ai-skill-library-panel-head">
            <Text strong>Skill 列表</Text>
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
                <Empty description="当前项目下暂无 Skill">
                  <ProjectActionButton action="manage" type="primary" operation="create" onClick={openUploadModal}>
                    上传第一个 Skill
                  </ProjectActionButton>
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
                          <Text strong>
                            {skill.filename || '未命名技能'}
                          </Text>
                        </div>
                        <div className="ai-skill-card-footer">
                          <Tag color={isDefaultSkill ? 'blue' : 'default'}>{isDefaultSkill ? '系统默认' : '项目自定义'}</Tag>
                          <Space size={6}>
                            <Tooltip title="下载">
                              <ActionButton
                                type="text"
                                shape="circle"
                                operation="download" iconOnly
                                aria-label="下载 Skill"
                                loading={downloadSkillMutation.isPending && downloadSkillMutation.variables === skill}
                                onClick={() => downloadSkillMutation.mutate(skill)}
                              />
                            </Tooltip>
                            <Popconfirm
                              title="确认删除该 Skill？"
                              disabled={isDefaultSkill}
                              onConfirm={() => handleDeleteSkill(skill)}
                            >
                              <Tooltip title={isDefaultSkill ? '系统默认 Skill 不允许删除' : '删除'}>
                                <span>
                                  <ProjectActionButton action="manage"
                                    danger
                                    type="text"
                                    shape="circle"
                                    operation="delete" iconOnly
                                    aria-label={isDefaultSkill ? '系统默认 Skill 不允许删除' : '删除 Skill'}
                                    disabled={isDefaultSkill}
                                    loading={deleteSkillMutation.isPending && deleteSkillMutation.variables === skillSpaceId}
                                  />
                                </span>
                              </Tooltip>
                            </Popconfirm>
                          </Space>
                        </div>
                      </div>
                    </Card>
                  )
                })}
              </div>
            )}
          </div>

          <div className="table-footer ai-skill-library-footer">
            <Text type="secondary">{footerRange(skills.length)}</Text>

          </div>
        </section>
      </div>

      <ProjectActionModal action="manage"
        mask={{ closable: false }}
        open={uploadModalOpen}
        title="上传 Skill 文件夹"
        okText="上传"
        onCancel={closeUploadModal}
        onOk={handleUpload}
        confirmLoading={uploadSkillMutation.isPending}
        okButtonProps={{ className: 'action-btn-save' }}
        destroyOnHidden
      >
        <input
          aria-label="选择 Skill 文件夹"
          type="file"
          {...{ webkitdirectory: '', directory: '' }}
          multiple
          disabled={uploadSkillMutation.isPending}
          onChange={(event) => {
            const files = Array.from(event.target.files || [])
            try {
              skillFolder(files)
              setUploadFiles(files)
            } catch (error) {
              setUploadFiles([])
              message.error(getErrorMessage(error))
            }
          }}
        />
        <p>{uploadFiles.length ? `已选择 ${uploadFiles.length} 个文件` : '请选择根目录包含 SKILL.md 的技能文件夹'}</p>
        <Text type="secondary">同名自定义技能整体覆盖，不保留旧文件；系统默认技能不可覆盖。</Text>

      </ProjectActionModal>
    </>
  )

  if (embedded) return content

  return (
    <div className="workbench-page ai-testing-page tp-list-surface ai-skill-library-page">
      {content}
    </div>
  )
}
