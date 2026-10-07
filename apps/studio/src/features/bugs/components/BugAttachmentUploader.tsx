import { downloadStoredFile } from '@/shared/api/files'
import { InboxOutlined } from '@ant-design/icons'
import { Upload } from 'antd'
import type { BugAttachment } from '../types'
import { saveBlob } from '@/shared/utils/download'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'

export type BugAttachmentItem = { uid: string; name: string; file: File }

/** Bug 附件选择：受控模式，文件先留在本地状态，提交表单时统一上传。 */
export function BugAttachmentUploader({
  disabled = false,
  items,
  existing = [],
  onChange,
  onRemoveExisting,
}: {
  onRemoveExisting?: (fileId: string) => void
  disabled?: boolean
  existing?: BugAttachment[]
  items: BugAttachmentItem[]
  onChange: (items: BugAttachmentItem[]) => void
}) {
  return (
    <Upload.Dragger
      className="bug-evidence-upload"
      multiple
      disabled={disabled}
      fileList={[
        ...existing.map((item) => ({ uid: item.fileId, name: item.filename, size: item.size, status: 'done' as const })),
        ...items.map(({ uid, name, file }) => ({ uid, name, size: file.size })),
      ]}
      showUploadList={{ showRemoveIcon: (file) => !disabled && (Boolean(onRemoveExisting) || !existing.some((item) => item.fileId === file.uid)),
        showDownloadIcon: (file) => existing.some((item) => item.fileId === file.uid) }}
      onDownload={async (file) => {
        try {
          const { blob } = await downloadStoredFile(file.uid)
          saveBlob(blob, file.name)
        } catch (error) { message.error(getErrorMessage(error)) }
      }}
      beforeUpload={(file, fileList) => {
        // antd 会为每个文件各调一次 beforeUpload；只在最后一个文件时整批收集。
        if (fileList.indexOf(file) === fileList.length - 1) {
          const next = fileList.map((item, index) => ({
            uid: `${Date.now()}-${index}-${item.name}`,
            name: item.name,
            file: item,
          }))
          onChange([...items, ...next])
        }
        return Upload.LIST_IGNORE
      }}
      onRemove={(info) => {
        if (existing.some((item) => item.fileId === info.uid)) onRemoveExisting?.(info.uid)
        else onChange(items.filter((item) => item.uid !== info.uid))
      }}
    >
      <p className="ant-upload-drag-icon">
        <InboxOutlined />
      </p>
      <p className="ant-upload-text">点击或拖拽文件上传</p>
      <p className="ant-upload-hint">支持截图、视频、日志等，大小限制以文件存储配置为准</p>
    </Upload.Dragger>
  )
}
