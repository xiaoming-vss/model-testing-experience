import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/task-form.css'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { UploadOutlined } from '@ant-design/icons'
import { Alert, Drawer, Form, Input, Segmented, Select, Upload } from 'antd'
import type { FormInstance } from 'antd'
import { useEffect, useState } from 'react'
import type { ApiCaseGenerateTaskSourceType, CreateApiCaseGenerateTaskPayload } from '../types'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'

export type ApiCaseGenerateTaskFormValues = CreateApiCaseGenerateTaskPayload
type SourceContentMode = 'upload' | 'editor'

const sourceTypeOptions: Array<{ label: string; value: ApiCaseGenerateTaskSourceType }> = [
  { label: 'OpenAPI', value: 'openapi' },
  { label: 'Swagger', value: 'swagger' },
]

function isSpecFileName(fileName: string) {
  return /\.(json|yaml|yml)$/i.test(fileName.trim())
}

export function ApiCaseGenerateTaskDrawer({
  title,
  open,
  form,
  loading,
  error,
  sprintOptions,
  requirementOptions,
  onSprintChange,
  onClose,
  onFinish,
}: {
  title: string
  open: boolean
  form: FormInstance<ApiCaseGenerateTaskFormValues>
  loading: boolean
  error: unknown
  sprintOptions: Array<{ label: string; value: string }>
  requirementOptions: Array<{ label: string; value: string }>
  onSprintChange: (value?: string) => void
  onClose: () => void
  onFinish: (values: ApiCaseGenerateTaskFormValues) => void
}) {
  const [sourceContentMode, setSourceContentMode] = useState<SourceContentMode>('editor')
  const [uploadedFileName, setUploadedFileName] = useState('')
  const sourceContentValue = Form.useWatch('sourceContent', form)

  useEffect(() => {
    if (!open) return
    setSourceContentMode('editor')
    setUploadedFileName('')
  }, [open])

  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
      size={640}
      rootClassName="ai-task-generate-drawer"
      destroyOnHidden={false}
      extra={
        <ProjectActionButton operation="save" action="write" type="primary" className="action-btn-save" loading={loading} onClick={() => form.submit()}>
          保存
        </ProjectActionButton>
      }
    >
      {error ? <Alert showIcon type="error" title={getErrorMessage(error)} style={{ marginBottom: 16 }} /> : null}
      <Form<ApiCaseGenerateTaskFormValues> className="ai-task-drawer-form" form={form} layout="vertical" onFinish={onFinish} requiredMark={false}>
        <div className="ai-task-drawer-basic-grid">
          <Form.Item name="name" label="任务名称" rules={[{ required: true, message: '请输入任务名称' }]}>
            <Input maxLength={120} placeholder="例如：登录模块冒烟用例生成" />
          </Form.Item>
          <Form.Item name="sprintId" label="所属迭代" rules={[{ required: true, message: '请选择所属迭代' }]}>
            <Select placeholder="请选择迭代" options={sprintOptions} onChange={onSprintChange} />
          </Form.Item>
          <Form.Item name="requirementId" label="所属需求" rules={[{ required: true, message: '请选择所属需求' }]}>
            <Select placeholder="请选择需求" options={requirementOptions} disabled={requirementOptions.length === 0} />
          </Form.Item>
          <Form.Item name="sourceType" label="来源类型" rules={[{ required: true, message: '请选择来源类型' }]}>
            <Select placeholder="请选择来源类型" options={sourceTypeOptions} />
          </Form.Item>
        </div>
        <Form.Item
          name="sourceContent"
          label="来源内容"
          rules={[{ required: true, message: '请输入来源内容' }]}
        >
          <div className="ai-task-source-content-field">
            <Segmented
              className="ai-task-source-mode"
              value={sourceContentMode}
              options={[
                { label: '上传文件', value: 'upload' },
                { label: '直接输入', value: 'editor' },
              ]}
              onChange={(value) => setSourceContentMode(value as SourceContentMode)}
            />

            {sourceContentMode === 'upload' ? (
              <div className="ai-task-source-upload-box">
                <Upload.Dragger
                  accept=".json,.yaml,.yml"
                  maxCount={1}
                  beforeUpload={(file) => {
                    if (!isSpecFileName(file.name)) {
                      message.error('仅支持 .json / .yaml / .yml 文件')
                      return Upload.LIST_IGNORE
                    }

                    void file
                      .text()
                      .then((text) => {
                        form.setFieldValue('sourceContent', text)
                        setUploadedFileName(file.name)
                        message.success(`已载入文件：${file.name}`)
                      })
                      .catch(() => {
                        message.error('文件读取失败，请重试')
                      })

                    return false
                  }}
                  onRemove={() => {
                    setUploadedFileName('')
                    form.setFieldValue('sourceContent', '')
                    return true
                  }}
                >
                  <p className="ant-upload-drag-icon">
                    <UploadOutlined />
                  </p>
                  <p className="ant-upload-text">点击或拖拽 JSON / YAML 文件到这里</p>
                  <p className="ant-upload-hint">前端会读取文件内容并写入 sourceContent，提交时仍按文本发送给后端。</p>
                </Upload.Dragger>
                <div style={{ marginTop: 8, color: 'var(--ai-text-secondary, var(--app-task-help-text))', fontSize: 12 }}>
                  {uploadedFileName ? `当前文件：${uploadedFileName}` : '尚未选择文件'}
                </div>
              </div>
            ) : (
              <TextCodeEditor
                value={sourceContentValue ?? ''}
                onChange={(value) => form.setFieldValue('sourceContent', value)}
                language="auto"
                height={300}
                minHeight={300}
              />
            )}
          </div>
        </Form.Item>
        <Form.Item
          name="instruction"
          label="生成指令"
          extra="描述希望生成的测试范围、颗粒度或约束。"
          rules={[{ required: true, message: '请输入生成指令' }]}
        >
          <Input.TextArea className="ai-task-instruction-textarea" maxLength={1000} placeholder="例如：只生成登录模块的冒烟测试用例" />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
