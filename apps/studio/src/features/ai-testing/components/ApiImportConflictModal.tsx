import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { Alert, Collapse } from 'antd'
import type { ApiCaseGenerateTaskRunImportCase, ApiCaseGenerateTaskRunImportConflict } from '../types'
import { getErrorMessage } from '@/utils/format'

type ApiImportConflictModalProps = {
  open: boolean
  conflicts: ApiCaseGenerateTaskRunImportConflict[]
  loading: boolean
  error?: unknown
  onCancel: () => void
  onConfirm: () => void
}

const comparedFields: Array<{ key: keyof ApiCaseGenerateTaskRunImportCase; label: string }> = [
  { key: 'name', label: '名称' },
  { key: 'description', label: '描述' },
  { key: 'enabled', label: '是否启用' },
  { key: 'orderNo', label: '顺序' },
  { key: 'method', label: '请求方法' },
  { key: 'urlTemplate', label: 'URL' },
  { key: 'headers', label: '请求头' },
  { key: 'query', label: '查询参数' },
  { key: 'bodyType', label: '请求体类型' },
  { key: 'bodyJson', label: 'JSON 请求体' },
  { key: 'bodyText', label: '文本请求体' },
  { key: 'timeoutMs', label: '超时' },
  { key: 'continueOnFailure', label: '失败后是否继续' },
  { key: 'extractRules', label: '提取规则' },
  { key: 'assertRules', label: '断言规则' },
]

function formatValue(value: unknown) {
  if (value === undefined || value === null || value === '') return '-'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function CaseComparison({ conflict }: { conflict: ApiCaseGenerateTaskRunImportConflict }) {
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

export function ApiImportConflictModal({
  open,
  conflicts,
  loading,
  error,
  onCancel,
  onConfirm,
}: ApiImportConflictModalProps) {
  return (
    <ProjectActionModal action="write"
      mask={{ closable: false }}
      title="确认覆盖冲突"
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
        description="当前仅支持整批覆盖。确认时后端会重新检查集合，请以下一次响应为准。"
      />
      {error ? <Alert showIcon type="error" title={getErrorMessage(error)} /> : null}
      <div className="api-import-conflict-list">
        <Collapse
          items={conflicts.map((conflict, index) => ({
            key: String(index),
            label: conflict.generatedCase.name || conflict.existingCase.name || conflict.normalizedName,
            children: <CaseComparison conflict={conflict} />,
          }))}
        />
      </div>
    </ProjectActionModal>
  )
}
