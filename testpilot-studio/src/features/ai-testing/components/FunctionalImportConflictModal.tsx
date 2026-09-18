import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { Alert, Collapse } from 'antd'
import type {
  FunctionalCaseGenerateTaskRunImportCase,
  FunctionalCaseGenerateTaskRunImportConflict,
} from '../types'
import { getErrorMessage } from '@/utils/format'

type FunctionalImportConflictModalProps = {
  open: boolean
  conflicts: FunctionalCaseGenerateTaskRunImportConflict[]
  loading: boolean
  error?: unknown
  onCancel: () => void
  onConfirm: () => void
}

const comparedFields: Array<{ key: keyof FunctionalCaseGenerateTaskRunImportCase; label: string }> = [
  { key: 'module', label: '模块' },
  { key: 'title', label: '标题' },
  { key: 'preconditions', label: '前置条件' },
  { key: 'steps', label: '步骤' },
  { key: 'expectedResults', label: '预期结果' },
  { key: 'priority', label: '优先级' },
  { key: 'caseType', label: '用例类型' },
]

function formatValue(value: unknown) {
  if (value === undefined || value === null || value === '') return '-'
  return String(value)
}

function CaseComparison({ conflict }: { conflict: FunctionalCaseGenerateTaskRunImportConflict }) {
  return (
    <div className="api-import-conflict-comparison">
      <div className="api-import-conflict-heading">字段</div>
      <div className="api-import-conflict-heading">当前正式用例</div>
      <div className="api-import-conflict-heading">已批准候选用例</div>
      {comparedFields.map(({ key, label }) => (
        <div className="api-import-conflict-row" key={key}>
          <div className="api-import-conflict-label">{label}</div>
          <pre className="api-import-conflict-value">{formatValue(conflict.existingCase[key])}</pre>
          <pre className="api-import-conflict-value">{formatValue(conflict.generatedCase[key])}</pre>
        </div>
      ))}
    </div>
  )
}

export function FunctionalImportConflictModal({
  open,
  conflicts,
  loading,
  error,
  onCancel,
  onConfirm,
}: FunctionalImportConflictModalProps) {
  return (
    <ProjectActionModal action="write"
      mask={{ closable: false }}
      title="确认覆盖功能用例冲突"
      open={open}
      onCancel={onCancel}
      onOk={onConfirm}
      okText="整批确认覆盖"
      cancelText="取消覆盖"
      confirmLoading={loading}
      width="min(1200px, calc(100vw - 48px))"
      destroyOnHidden
    >
      <Alert
        showIcon
        type="warning"
        title={`发现 ${conflicts.length} 个同名用例冲突`}
        description="本次仅展示冲突，不会写入正式资产。确认后将重新检查并整批覆盖。"
      />
      {error ? <Alert showIcon type="error" title={getErrorMessage(error)} /> : null}
      <Collapse
        defaultActiveKey={conflicts.map((_, index) => String(index))}
        items={conflicts.map((conflict, index) => ({
          key: String(index),
          label: conflict.generatedCase.title || conflict.existingCase.title || conflict.normalizedName,
          children: <CaseComparison conflict={conflict} />,
        }))}
      />
    </ProjectActionModal>
  )
}
