import { isYamlFileName, type CaseImportMode } from '@/features/api-automation/utils/detailView'
import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { message } from '@/shared/utils/feedback'
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
      rootClassName="api-case-import-modal-root"
      className="api-case-import-modal-shell"
      destroyOnHidden
    >
      <div className="api-case-import-modal">
        <Segmented
          className="api-case-import-mode"
          value={caseImportMode}
          options={[
            { label: '上传 YAML', value: 'upload' },
            { label: '直接输入', value: 'editor' },
          ]}
          onChange={(value) => setCaseImportMode(value as CaseImportMode)}
        />
        {caseImportMode === 'upload' ? (
          <div className="api-case-import-upload">
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
            <div className="api-case-import-hint">后端会直接解析 YAML，前端不做字段预解析。</div>
          </div>
        ) : (
          <div className="api-case-import-editor">
            <div className="api-case-import-hint">直接粘贴 YAML 内容，提交时前端会将文本包装成 `.yaml` 文件上传。</div>
            <TextCodeEditor value={importYamlText} onChange={setImportYamlText} language="yaml" minHeight={280} />
          </div>
        )}
      </div>
    </ProjectActionModal>
  )
}
