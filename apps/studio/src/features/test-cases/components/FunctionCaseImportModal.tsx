import { UploadOutlined } from '@ant-design/icons'
import { Segmented, Upload } from 'antd'
import { ProjectActionModal } from '@/domain/projects/components/ProjectActionModal'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { cx } from '@/shared/utils/cx'
import { isJsonFileName, type CaseImportMode } from '@/shared/utils/caseImport'
import { message } from '@/shared/utils/feedback'
import type { CaseLibraryPageModel } from '../hooks/useCaseLibraryPage'

export function FunctionCaseImportModal({ page }: { page: CaseLibraryPageModel }) {
  const {
    caseImportOpen,
    caseImportMode,
    setCaseImportMode,
    setImportJsonFile,
    importJsonText,
    setImportJsonText,
    importFunctionCasesMutation,
    closeCaseImportModal,
    handleImportFunctionCases,
  } = page

  return (
    <ProjectActionModal
      action="execute"
      mask={{ closable: false }}
      open={caseImportOpen}
      title="用例导入"
      width={860}
      okText="开始导入"
      cancelText="取消"
      onCancel={closeCaseImportModal}
      confirmLoading={importFunctionCasesMutation.isPending}
      okButtonProps={{ className: 'action-btn-save' }}
      onOk={handleImportFunctionCases}
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
            { label: '上传 JSON', value: 'upload' },
            { label: '直接输入', value: 'editor' },
          ]}
          onChange={(value) => setCaseImportMode(value as CaseImportMode)}
        />
        {caseImportMode === 'upload' ? (
          <div className="flex min-h-0 w-full max-w-full flex-1 flex-col gap-2.5">
            <Upload.Dragger
              accept=".json"
              maxCount={1}
              beforeUpload={(file) => {
                if (!isJsonFileName(file.name)) {
                  message.error('仅支持 .json 文件')
                  return Upload.LIST_IGNORE
                }
                setImportJsonFile(file)
                return false
              }}
              onRemove={() => {
                setImportJsonFile(null)
                return true
              }}
            >
              <p className="ant-upload-drag-icon">
                <UploadOutlined />
              </p>
              <p className="ant-upload-text">点击或拖拽 JSON 文件到这里</p>
              <p className="ant-upload-hint">
                仅支持 .json，导入时会自动绑定到左栏选中的测试集。
              </p>
            </Upload.Dragger>
          </div>
        ) : (
          <div className="flex min-h-0 w-full max-w-full flex-1 flex-col gap-2.5">
            <div className="text-xs leading-[18px] text-[var(--tp-text-secondary)]">
              直接粘贴 JSON 内容，提交时前端会将文本包装成 `.json` 文件上传。
            </div>
            <TextCodeEditor
              value={importJsonText}
              onChange={setImportJsonText}
              language="json"
              height="clamp(240px, 48vh, 420px)"
            />
          </div>
        )}
      </div>
    </ProjectActionModal>
  )
}
