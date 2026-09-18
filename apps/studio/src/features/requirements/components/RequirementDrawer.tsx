import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { UploadOutlined } from '@ant-design/icons'
import { Alert, Drawer, Form, Input, Select, Upload } from 'antd'
import type { FormInstance, UploadFile } from 'antd'
import { useEffect, useState } from 'react'
import { getRequirementDocumentDisplayName } from '@/features/requirements/utils/requirementDocument'
import type { RequirementCreatePayload, RequirementDocumentType } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'

export type RequirementFormValues = RequirementCreatePayload & {
    sprintId?: string
    documentFileName?: string
    documentFilename?: string
    documentDownloadUrl?: string
  }

const documentTypeOptions: Array<{ label: string; value: RequirementDocumentType }> = [
  { label: '纯文本', value: 'text' },
  { label: 'Word', value: 'word' },
]

function isWordDocument(documentType?: RequirementDocumentType) {
  return documentType === 'word' || documentType === 'docx'
}

function getUploadAccept(documentType?: RequirementDocumentType) {
  if (isWordDocument(documentType)) return '.docx'
  return ''
}

function isAcceptedRequirementFile(fileName: string, documentType?: RequirementDocumentType) {
  const normalizedName = fileName.trim()
  if (isWordDocument(documentType)) return /\.docx$/i.test(normalizedName)
  return false
}

function getUploadHint(documentType?: RequirementDocumentType) {
  if (isWordDocument(documentType)) return '点击或拖拽 DOCX 文件到这里'
  return ''
}

export function RequirementDrawer({
  title,
  open,
  form,
  loading,
  error,
  documentLoading = false,
  onClose,
  mode = 'create',
  sprintOptions,
  onFinish,
}: {
  title: string
  open: boolean
  form: FormInstance
  loading: boolean
  error: unknown
  documentLoading?: boolean
  onClose: () => void
  mode?: 'create' | 'edit'
  sprintOptions?: Array<{ label: string; value: string }>
  onFinish: (values: RequirementFormValues) => void
}) {
  const documentType = Form.useWatch('documentType', form) ?? 'text'
  const [selectedFile, setSelectedFile] = useState<File | undefined>(undefined)
  const [fileList, setFileList] = useState<UploadFile[]>([])

  useEffect(() => {
    if (!open) return
    setSelectedFile(undefined)
    const currentDocumentType = form.getFieldValue('documentType') as RequirementDocumentType | undefined
    const currentDocumentFileName = form.getFieldValue('documentFileName') as string | undefined
    const currentDocumentFilename = form.getFieldValue('documentFilename') as string | undefined
    const currentDocumentDownloadUrl = form.getFieldValue('documentDownloadUrl') as string | undefined

    if (isWordDocument(currentDocumentType) && (currentDocumentDownloadUrl || currentDocumentFilename)) {
      const displayName = getRequirementDocumentDisplayName({
        documentType: currentDocumentType,
        documentFileName: currentDocumentFileName,
        documentFilename: currentDocumentFilename,
      })
      setFileList(
        displayName
          ? [
              {
                uid: 'existing-document',
                name: displayName,
                status: 'done',
              },
            ]
          : [],
      )
      return
    }

    setFileList([])
  }, [form, open])

  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
      size={520}
      extra={
        <ProjectActionButton operation="save" action="write" type="primary" className="action-btn-save" loading={loading || documentLoading} disabled={documentLoading} onClick={() => form.submit()}>
          保存
        </ProjectActionButton>
      }
    >
      {error ? <Alert showIcon type="error" title={getErrorMessage(error)} /> : null}
      <Form<RequirementFormValues>
        form={form}
        layout="vertical"
        onFinish={(values) => {
          if (!isWordDocument(values.documentType)) {
            onFinish({
              ...values,
              documentContent: values.documentContent?.trim() ?? '',
              file: undefined,
            })
            return
          }

          onFinish({
            ...values,
            documentContent: undefined,
            file: selectedFile,
          })
        }}
        requiredMark={false}
      >
        {sprintOptions ? (
          <Form.Item name="sprintId" label="所属迭代" rules={[{ required: true, message: '请选择所属迭代' }]}>
            <Select placeholder="请选择迭代" options={sprintOptions} />
          </Form.Item>
        ) : null}
        <Form.Item name="name" label="需求名称" rules={[{ required: true, message: '请输入需求名称' }]}>
          <Input maxLength={100} />
        </Form.Item>
        <Form.Item name="documentFileName" hidden>
          <Input />
        </Form.Item>
        <Form.Item name="documentFilename" hidden>
          <Input />
        </Form.Item>
        <Form.Item name="documentDownloadUrl" hidden>
          <Input />
        </Form.Item>
        <Form.Item
          name="documentType"
          label="需求文档类型"
          extra={mode === 'edit' ? '文档类型由源文件决定，编辑时不直接切换。' : undefined}
          rules={[{ required: true, message: '请选择需求文档类型' }]}
        >
          <Select
            placeholder="请选择需求文档类型"
            options={documentTypeOptions}
            disabled={mode === 'edit'}
            onChange={(value: RequirementDocumentType) => {
              form.setFieldValue('documentType', value)
              form.setFieldValue('documentContent', '')
              form.setFieldValue('documentFileName', undefined)
              form.setFieldValue('documentFilename', undefined)
              form.setFieldValue('documentDownloadUrl', undefined)
              setSelectedFile(undefined)
              setFileList([])
            }}
          />
        </Form.Item>
        <Form.Item
          name="documentContent"
          label="需求文档"
          extra={
            !isWordDocument(documentType)
              ? mode === 'edit'
                ? '编辑时会读取 TXT 源文件正文，可直接修改并保存。'
                : '请输入纯文本需求正文，后端会保存为 TXT 源文件。'
              : undefined
          }
          rules={[
            {
              validator: async (_, value) => {
                if (!isWordDocument(documentType)) {
                  if (value && String(value).trim()) return
                  throw new Error('请输入需求正文')
                }

                if (selectedFile || (mode === 'edit' && fileList.length > 0)) return
                throw new Error(isWordDocument(documentType) ? '请上传 Word 文件' : '请上传需求文件')
              },
            },
          ]}
        >
          {!isWordDocument(documentType) ? (
            <Input.TextArea
              rows={10}
              maxLength={20000}
              disabled={documentLoading}
              placeholder={documentLoading ? '需求正文加载中...' : '请输入纯文本需求正文'}
            />
          ) : (
            <Upload.Dragger
              accept={getUploadAccept(documentType)}
              maxCount={1}
              fileList={fileList}
              showUploadList={{ showPreviewIcon: false }}
              beforeUpload={(file) => {
                if (!isAcceptedRequirementFile(file.name, documentType)) {
                  message.error(`仅支持 ${getUploadAccept(documentType)} 文件`)
                  return Upload.LIST_IGNORE
                }

                const fileName = file.name.trim()
                form.setFieldValue('documentFileName', fileName)
                if (mode !== 'edit') {
                  form.setFieldValue('documentContent', '')
                }
                setSelectedFile(file)
                setFileList([
                  {
                    uid: `${Date.now()}`,
                    name: fileName,
                    status: 'done',
                    originFileObj: file,
                  },
                ])
                void form.validateFields(['documentContent'])
                return false
              }}
              onRemove={() => {
                form.setFieldValue('documentContent', '')
                form.setFieldValue('documentFileName', undefined)
                form.setFieldValue('documentFilename', undefined)
                form.setFieldValue('documentDownloadUrl', undefined)
                setSelectedFile(undefined)
                setFileList([])
                void form.validateFields(['documentContent'])
                return true
              }}
            >
              <p className="ant-upload-drag-icon">
                <UploadOutlined />
              </p>
              <p className="ant-upload-text">{getUploadHint(documentType)}</p>
            </Upload.Dragger>
          )}
        </Form.Item>
      </Form>
    </Drawer>
  )
}
