import { EditOutlined } from '@ant-design/icons'
import { Modal, Popconfirm, Space } from 'antd'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { FunctionCaseEditor } from './FunctionCaseEditor'
import type { FunctionCaseFormValues } from '../utils/caseForm'
import { normalizeFunctionTestCaseId } from '@/utils/format'
import caseLibraryStyles from '../styles/case-library.module.css'
import type { CaseLibraryPageModel } from '../hooks/useCaseLibraryPage'

export function CaseEditorModal({ page }: { page: CaseLibraryPageModel }) {
  const {
    editorTarget,
    caseForm,
    saveCaseMutation,
    deleteCaseMutation,
    closeCaseEditor,
  } = page

  if (!editorTarget) return null

  // 弹窗头部：用例身份（序号 / UID）与这次在做什么。新建时还没有编号，显示「未保存」。
  const editingCaseId = editorTarget.mode === 'edit' ? normalizeFunctionTestCaseId(editorTarget.item) : ''
  const editingOrderNo = editorTarget.mode === 'edit' ? editorTarget.item.orderNo : undefined
  const caseEditorHeader = (
    <div className="case-editor-head flex items-start gap-3">
      <span className="case-editor-head-icon inline-flex h-7 w-7 flex-none items-center justify-center rounded-[8px] border border-[var(--srf-accent-border)] bg-[var(--srf-accent-soft)] text-[14px] text-[var(--srf-accent)]">
        <EditOutlined />
      </span>
      <div className="case-editor-head-copy flex min-w-0 flex-col gap-0.5">
        <div className="case-editor-head-title flex min-w-0 flex-wrap items-center gap-2">
          <span className="case-editor-head-name text-[15px] font-bold leading-[22px] text-[var(--srf-text)]">
            {editorTarget.mode === 'create' ? '新建用例' : '编辑用例'}
          </span>
          {editingOrderNo ? (
            <span className="case-editor-head-badge rounded-[4px] bg-[var(--srf-chip)] px-1.5 py-0.5 font-mono text-[10px] leading-[16px] text-[var(--srf-text-secondary)]" title="该测试集内的用例序号">
              TC-{String(editingOrderNo).padStart(4, '0')}
            </span>
          ) : null}
          {editingCaseId ? (
            <span className="case-editor-head-uid font-mono text-[11px] leading-[16px] text-[var(--srf-text-muted)]">UID: {editingCaseId.slice(0, 8)}</span>
          ) : (
            <span className="case-editor-head-badge rounded-[4px] bg-[var(--srf-chip)] px-1.5 py-0.5 font-mono text-[10px] leading-[16px] text-[var(--srf-text-secondary)]">未保存</span>
          )}
        </div>
        <p className="case-editor-head-subtitle m-0 text-[11px] leading-[16px] text-[var(--srf-text-secondary)]">
          {editorTarget.mode === 'create'
            ? '填写用例的执行规范与验证结果'
            : '修改并完善当前测试用例的执行规范及验证结果'}
        </p>
      </div>
    </div>
  )

  return (
    <Modal
      open
      centered
      width={1040}
      maskClosable={false}
      className={`case-library-case-modal tp-surface ${caseLibraryStyles.root}`}
      title={caseEditorHeader}
      onCancel={closeCaseEditor}
      footer={
        <div className="case-editor-footer flex w-full flex-wrap items-center justify-between gap-2">
          {/* 删除是危险动作，按设计稿收在底部最左侧，和右侧的确认动作分开。 */}
          {editorTarget.mode === 'edit' ? (
            <Popconfirm
              title="确认删除该用例？"
              description="删除后不可恢复。"
              okText="确认删除"
              okButtonProps={{ danger: true }}
              onConfirm={() =>
                deleteCaseMutation.mutate(normalizeFunctionTestCaseId(editorTarget.item))
              }
            >
              <ProjectActionButton
                action="write"
                danger
                type="text"
                className="action-btn-delete"
                operation="delete"
                disabled={saveCaseMutation.isPending}
                loading={deleteCaseMutation.isPending}
              >
                删除用例
              </ProjectActionButton>
            </Popconfirm>
          ) : null}
          <Space size={8} className="case-editor-footer-main items-center">
            <ProjectActionButton
              action="write"
              disabled={saveCaseMutation.isPending}
              onClick={closeCaseEditor}
            >
              取消
            </ProjectActionButton>
            <ProjectActionButton
              action="write"
              type="primary"
              className="action-btn-save"
              operation="save"
              loading={saveCaseMutation.isPending}
              onClick={() => caseForm.submit()}
            >
              保存变更
            </ProjectActionButton>
          </Space>
        </div>
      }
    >
      <FunctionCaseEditor
        form={caseForm}
        isCreate={editorTarget.mode === 'create'}
        item={editorTarget.mode === 'edit' ? editorTarget.item : null}
        onSubmit={(values) =>
          // orderNo 这类字段没有对应的表单项，只能从表单全量取值里补回来。
          saveCaseMutation.mutate({
            ...(caseForm.getFieldsValue(true) as FunctionCaseFormValues),
            ...values,
          })
        }
      />
    </Modal>
  )
}
