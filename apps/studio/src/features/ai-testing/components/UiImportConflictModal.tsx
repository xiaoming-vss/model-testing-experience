import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { Alert, Collapse, Descriptions, Table, Tag, Typography } from 'antd'
import type {
  UiCaseGenerateTaskRunImportCase,
  UiCaseGenerateTaskRunImportConflict,
  UiCaseGenerateTaskRunImportStep,
} from '../types'
import { uiCaseStepFieldNames } from '../utils/uiCaseCandidate'

const { Text } = Typography

type UiImportConflictModalProps = {
  open: boolean
  conflicts: UiCaseGenerateTaskRunImportConflict[]
  loading: boolean
  errorMessage?: string
  conflictsChanged?: boolean
  confirmDisabled?: boolean
  onCancel: () => void
  onConfirm: () => void
}

const stepFieldLabels: Record<(typeof uiCaseStepFieldNames)[number], string> = {
  orderNo: '排序号',
  stepName: '步骤名称',
  keyword: '关键字',
  locatorType: '定位类型',
  locatorValue: '定位值',
  operationValue: '操作值',
  continueOnFailure: '失败策略',
  enabled: '启用状态',
}

const knownStepFields = uiCaseStepFieldNames.map((key) => ({ key, label: stepFieldLabels[key] }))

const knownStepFieldNames = new Set<string>(knownStepFields.map(({ key }) => key))

function hasOwn(record: object, key: PropertyKey) {
  return Object.prototype.hasOwnProperty.call(record, key)
}

function renderRawValue(value: unknown) {
  if (value === null) return <Text code>null</Text>
  if (value === '') return <Text type="secondary">（空字符串）</Text>
  if (typeof value === 'boolean') return <Tag color={value ? 'success' : 'default'}>{value ? 'true' : 'false'}</Tag>
  if (typeof value === 'string' || typeof value === 'number') return <span className="ui-import-conflict-text">{String(value)}</span>
  return <pre className="ui-import-conflict-json">{JSON.stringify(value, null, 2)}</pre>
}

function renderField(record: object, key: PropertyKey, booleanLabels?: [string, string]) {
  if (!hasOwn(record, key)) return <Text type="secondary">（缺失）</Text>
  const value = (record as Record<PropertyKey, unknown>)[key]
  if (booleanLabels && typeof value === 'boolean') {
    return <Tag color={value ? 'success' : 'default'}>{value ? booleanLabels[0] : booleanLabels[1]}</Tag>
  }
  return renderRawValue(value)
}

function otherStepFields(step: UiCaseGenerateTaskRunImportStep) {
  return Object.fromEntries(Object.entries(step).filter(([key]) => key !== '__rowKey' && !knownStepFieldNames.has(key)))
}

function CaseDetails({ title, value }: { title: string; value: UiCaseGenerateTaskRunImportCase }) {
  return (
    <section className="ui-import-conflict-side" aria-label={title}>
      <h4>{title}</h4>
      <Descriptions
        size="small"
        column={1}
        items={[
          { key: 'name', label: '名称', children: renderField(value, 'name') },
          { key: 'enabled', label: '启用状态', children: renderField(value, 'enabled', ['启用', '禁用']) },
          { key: 'orderNo', label: '排序号', children: renderField(value, 'orderNo') },
        ]}
      />
      <Table<UiCaseGenerateTaskRunImportStep & { __rowKey: number }>
        size="small"
        pagination={false}
        scroll={{ x: 1120 }}
        rowKey="__rowKey"
        dataSource={(Array.isArray(value.stepsJson) ? value.stepsJson : []).map((step, index) => ({ ...step, __rowKey: index }))}
        locale={{ emptyText: '无步骤' }}
        columns={[
          ...knownStepFields.map(({ key, label }) => ({
            title: label,
            key: String(key),
            width: key === 'locatorValue' || key === 'operationValue' ? 190 : 120,
            render: (_: unknown, step: UiCaseGenerateTaskRunImportStep) => renderField(
              step,
              key,
              key === 'enabled'
                ? ['启用', '禁用']
                : key === 'continueOnFailure'
                  ? ['失败后继续', '失败即停止']
                  : undefined,
            ),
          })),
          {
            title: '其他字段',
            key: 'extraFields',
            width: 220,
            render: (_: unknown, step: UiCaseGenerateTaskRunImportStep) => {
              const extra = otherStepFields(step)
              return Object.keys(extra).length
                ? <pre className="ui-import-conflict-json">{JSON.stringify(extra, null, 2)}</pre>
                : <Text type="secondary">（无）</Text>
            },
          },
        ]}
      />
      <Collapse
        ghost
        items={[{
          key: 'raw',
          label: '完整原始 stepsJson',
          children: <pre className="ui-import-conflict-json">{JSON.stringify(value.stepsJson, null, 2)}</pre>,
        }]}
      />
    </section>
  )
}

export function UiImportConflictModal({
  open,
  conflicts,
  loading,
  errorMessage,
  conflictsChanged,
  confirmDisabled,
  onCancel,
  onConfirm,
}: UiImportConflictModalProps) {
  return (
    <ProjectActionModal action="write"
      mask={{ closable: false }}
      title="确认覆盖 UI 用例冲突"
      open={open}
      width={1400}
      okText="整批确认覆盖"
      cancelText="取消覆盖"
      confirmLoading={loading}
      okButtonProps={{ disabled: loading || confirmDisabled }}
      cancelButtonProps={{ disabled: loading }}
      onCancel={onCancel}
      onOk={onConfirm}
      styles={{ body: { maxHeight: 'calc(100vh - 220px)', overflow: 'auto' } }}
      destroyOnHidden
    >
      <Alert
        showIcon
        type="warning"
        title={`发现 ${conflicts.length} 个同名用例冲突`}
        description="当前仅预览冲突，不会写入正式资产。确认后将重新检查：同名用例原位覆盖，非冲突候选同时新增；任一操作失败则整批回滚。"
        style={{ marginBottom: 12 }}
      />
      {conflictsChanged ? (
        <Alert showIcon type="info" title="冲突已变化，请重新检查后再次确认" style={{ marginBottom: 12 }} />
      ) : null}
      {errorMessage ? <Alert showIcon type="error" title={errorMessage} style={{ marginBottom: 12 }} /> : null}
      <Collapse
        defaultActiveKey={conflicts.length ? ['0'] : []}
        items={conflicts.map((conflict, index) => ({
          key: String(index),
          label: `${index + 1}. ${String(conflict.generatedCase.name ?? conflict.existingCase.name ?? '未命名')} · 规范化：${conflict.normalizedName}`,
          children: (
            <div className="ui-import-conflict-comparison">
              <CaseDetails title="现有正式用例" value={conflict.existingCase} />
              <CaseDetails title="已批准候选用例" value={conflict.generatedCase} />
            </div>
          ),
        }))}
      />
    </ProjectActionModal>
  )
}
