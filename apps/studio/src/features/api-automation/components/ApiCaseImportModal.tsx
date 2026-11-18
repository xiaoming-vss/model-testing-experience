import { isYamlFileName, type CaseImportMode } from '@/features/api-automation/utils/detailView'
import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { message } from '@/shared/utils/feedback'
import { cx } from '@/shared/utils/cx'
import { UploadOutlined } from '@ant-design/icons'
import { Segmented, Upload } from 'antd'

import type { ApiCollectionImportResult } from '@/features/api-automation/types'
import type { UseMutationResult } from '@tanstack/react-query'

type Props = {
  caseImportModalOpen: boolean
  closeCaseImportModal: () => void
  importApiCasesMutation: UseMutationResult<ApiCollectionImportResult, Error, { file: Blob; filename: string }, unknown>
  handleImportApiCases: () => void
  caseImportMode: CaseImportMode
  setCaseImportMode: React.Dispatch<React.SetStateAction<CaseImportMode>>
  setImportYamlFile: React.Dispatch<React.SetStateAction<File | null>>
  importYamlText: string
  setImportYamlText: React.Dispatch<React.SetStateAction<string>>
}

export function ApiCaseImportModal({ caseImportModalOpen, closeCaseImportModal, importApiCasesMutation, handleImportApiCases, caseImportMode, setCaseImportMode, setImportYamlFile, importYamlText, setImportYamlText }: Props) {
  return (
    <ProjectActionModal action="execute"
      mask={{ closable: false }}
      open={caseImportModalOpen}
      title="用例导入"
      width={860}
      okText="开始导入"
      onCancel={closeCaseImportModal}
      confirmLoading={importApiCasesMutation.isPending}
      okButtonProps={{ className: 'action-btn-save' }}
      onOk={handleImportApiCases}
      rootClassName={cx('api-case-import-modal-root')}
      className="api-case-import-modal-shell"
      style={{ maxWidth: 'calc(100vw - 32px)' }}
      classNames={{
        container: 'flex max-h-[calc(100vh-40px)] flex-col overflow-hidden',
        body: 'min-h-0 flex-1 overflow-hidden',
      }}
      destroyOnHidden
    >
      <div className="flex max-h-[calc(100vh-148px)] w-full min-w-0 flex-col gap-3">
        <Segmented
          className="w-full"
          value={caseImportMode}
          options={[
            { label: '上传 YAML', value: 'upload' },
            { label: '直接输入', value: 'editor' },
          ]}
          onChange={(value) => setCaseImportMode(value as CaseImportMode)}
        />
        {caseImportMode === 'upload' ? (
          <div className="flex min-h-0 w-full max-w-full flex-1 flex-col gap-2.5">
            <Upload.Dragger
              accept=".yaml,.yml"
              maxCount={1}
              beforeUpload={(file) => {
                if (!isYamlFileName(file.name)) {
                  message.error('仅支持 .yaml 或 .yml 文件')
                  return Upload.LIST_IGNORE
                }
                setImportYamlFile(file)
                return false
              }}
              onRemove={() => {
                setImportYamlFile(null)
                return true
              }}
            >
              <p className="ant-upload-drag-icon">
                <UploadOutlined />
              </p>
              <p className="ant-upload-text">点击或拖拽 YAML 文件到这里</p>
              <p className="ant-upload-hint">仅支持 .yaml / .yml，导入时会自动绑定到当前 Collection。</p>
            </Upload.Dragger>
            <div className="text-xs leading-[18px] text-[var(--tp-text-secondary)]">后端会直接解析 YAML，前端不做字段预解析。</div>
          </div>
        ) : (
          <div className="flex min-h-0 w-full max-w-full flex-1 flex-col gap-2.5">
            <div className="text-xs leading-[18px] text-[var(--tp-text-secondary)]">直接粘贴 YAML 内容，提交时前端会将文本包装成 `.yaml` 文件上传。</div>
            <TextCodeEditor value={importYamlText} onChange={setImportYamlText} language="yaml" height="clamp(240px, 48vh, 420px)" />
          </div>
        )}
      </div>
    </ProjectActionModal>
  )
}
