import { FlagOutlined, ProfileOutlined } from '@ant-design/icons'
import { AutoComplete, Form, Input, Select } from 'antd'
import type { FormInstance } from 'antd'
import { formatTime, pickCreatedAt, pickUpdatedAt } from '@/utils/format'
import type { FunctionCaseLibraryItem } from '../types'
import type { FunctionCaseFormValues } from '../utils/caseForm'
import { CASE_TYPE_PRESETS } from '../utils/caseTone'
import { FunctionCaseContentEditor } from './FunctionCaseContentEditor'

// 优先级带上等级含义，光看 P2 说不出轻重。取值仍是 P0–P3，只是给下拉一个可读的说法。
const PRIORITY_LABELS: Record<string, string> = {
  P0: 'P0 - 最高',
  P1: 'P1 - 高',
  P2: 'P2 - 中',
  P3: 'P3 - 低',
}

const priorityOptions = Object.entries(PRIORITY_LABELS).map(([value, label]) => ({ label, value }))
const caseTypeOptions = CASE_TYPE_PRESETS.map((value) => ({ label: value, value }))

/**
 * 功能用例正文表单。点开用例直接就是它，没有只读态、没有抽屉。
 * 表单实例与保存动作由调用方持有，弹窗头部与底部动作在 CaseLibraryPage 里。
 */
export function FunctionCaseEditor({
  form,
  isCreate,
  item,
  onSubmit,
}: {
  form: FormInstance<FunctionCaseFormValues>
  isCreate: boolean
  item?: FunctionCaseLibraryItem | null
  onSubmit: (values: FunctionCaseFormValues) => void
}) {
  return (
    <Form<FunctionCaseFormValues>
      form={form}
      layout="vertical"
      requiredMark={false}
      className="case-editor-form bg-transparent p-0"
      onFinish={onSubmit}
    >
      <div className="case-editor-body flex flex-col gap-4">
        <section className="case-editor-name-section">
          <div className="case-editor-name-head mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <span className="case-editor-name-label text-xs font-bold leading-[18px] text-[var(--srf-text)]">
              用例名称
              <em className="case-editor-required not-italic text-[var(--srf-danger)]">*</em>
            </span>
            {isCreate ? null : (
              <span className="case-editor-name-meta text-[11px] leading-[16px] text-[var(--srf-text-muted)]">
                创建时间: {formatTime(pickCreatedAt(item ?? undefined)) || '-'}
                <span className="case-editor-name-meta-sep mx-1.5 text-[var(--srf-card-border)]">・</span>
                更新时间: {formatTime(pickUpdatedAt(item ?? undefined)) || '-'}
              </span>
            )}
          </div>
          <Form.Item
            name="title"
            rules={[{ required: true, message: '请输入用例标题' }]}
          >
            <Input
              className="case-editor-title-input"
              placeholder="例如：用户使用正确账号密码登录成功"
            />
          </Form.Item>
        </section>

        <div className="case-editor-grid grid grid-cols-2 items-stretch gap-4 max-[900.01px]:grid-cols-1">
          <section className="case-editor-section flex flex-col overflow-hidden rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] tone-amber">
            <div className="case-editor-section-head flex flex-wrap items-center justify-between gap-2 px-4 py-3">
              <span className="case-editor-section-title inline-flex items-center gap-2 text-xs font-bold leading-[18px] text-[var(--srf-text)]">
                <FlagOutlined />
                优先级
              </span>
              <span className="case-editor-section-hint text-[11px] leading-[16px] text-[var(--srf-text-muted)]">等级影响执行次序</span>
            </div>
            <div className="case-editor-section-body px-4 pt-3.5 pb-4">
              <Form.Item name="priority">
                <Select allowClear options={priorityOptions} placeholder="请选择优先级" />
              </Form.Item>
            </div>
          </section>

          <section className="case-editor-section flex flex-col overflow-hidden rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] tone-blue">
            <div className="case-editor-section-head flex flex-wrap items-center justify-between gap-2 px-4 py-3">
              <span className="case-editor-section-title inline-flex items-center gap-2 text-xs font-bold leading-[18px] text-[var(--srf-text)]">
                <ProfileOutlined />
                用例类型
              </span>
              <span className="case-editor-section-hint text-[11px] leading-[16px] text-[var(--srf-text-muted)]">测试维度归类</span>
            </div>
            <div className="case-editor-section-body px-4 pt-3.5 pb-4">
              <Form.Item name="caseType">
                <AutoComplete allowClear options={caseTypeOptions} placeholder="请选择或输入用例类型" />
              </Form.Item>
            </div>
          </section>
        </div>

        <FunctionCaseContentEditor />
      </div>
    </Form>
  )
}
