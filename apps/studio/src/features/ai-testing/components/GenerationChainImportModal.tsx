import { Alert, Button, Modal, Select, Spin, Tag } from 'antd'
import { CheckCircleFilled, ImportOutlined, LinkOutlined } from '@ant-design/icons'
import type { GenerationChainWorkspace } from '../hooks/useRequirementGenerationChain'
import type { GenerationChainImportRecord, GenerationChainImportTarget } from '../api/generationChain.api'

function formatTime(value?: string | null) {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return ''
  return parsed.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function conflictName(conflict: Record<string, unknown>) {
  return String(conflict.normalizedName ?? conflict.name ?? '同名正式用例')
}

function conflictCaseName(value: unknown) {
  if (!value || typeof value !== 'object') return ''
  const item = value as Record<string, unknown>
  return String(item.title ?? item.name ?? '')
}

function SourceSummary({ target }: { target: GenerationChainImportTarget }) {
  if (target.sourceDeleted) {
    return <span className="gc-import-source is-danger">当前正式来源已删除</span>
  }
  if (!target.effectiveImport) {
    return <span className="gc-import-source is-muted">尚未从生成链导入</span>
  }
  return <span className="gc-import-source">
    <CheckCircleFilled /> 当前正式来源 {target.effectiveImport.versionLabel || '历史版本'}
    <small>{formatTime(target.effectiveImport.importedAt)} · 变更 {target.effectiveImport.changedCaseCount} 条</small>
    {target.effectiveImport.mixedSource ? <Tag color="warning">混合来源</Tag> : null}
  </span>
}

function RecordDetails({ record }: { record: GenerationChainImportRecord }) {
  return <div className="gc-import-record">
    <div><span>来源版本</span><b>{record.versionLabel || record.versionId}</b></div>
    <div><span>变更用例</span><b>{record.changedCaseCount} / {record.targetCaseCount}</b></div>
    <div><span>导入时间</span><b>{formatTime(record.importedAt) || '—'}</b></div>
    {record.mixedSource ? <Alert showIcon type="warning" title="本次只覆盖部分用例，正式目标仍保留旧来源用例。" /> : null}
    {record.changedCaseIds.length ? <div className="gc-import-case-ids">
      <span>变更用例</span>
      {record.changedCaseIds.slice(0, 12).map(caseId => <code key={caseId}>{caseId}</code>)}
      {record.changedCaseIds.length > 12 ? <small>等 {record.changedCaseIds.length} 条</small> : null}
    </div> : null}
  </div>
}

export function GenerationChainImportModal({ workspace, open, onClose }: {
  workspace: GenerationChainWorkspace
  open: boolean
  onClose: () => void
}) {
  const {
    selectedVersion, stage, importOptions, importTargetId, setImportTargetId, importConflicts,
    importVersion, importableVersionId,
  } = workspace
  const options = importOptions.data
  const target = options?.targets.find(item => item.targetId === importTargetId)
  const canImport = Boolean(
    importableVersionId
    && options
    && (!options.targetRequired || target)
    && !importVersion.isPending,
  )
  const hasConflicts = importConflicts.length > 0
  const label = selectedVersion?.label ?? options?.versionLabel ?? ''

  return <Modal
    open={open}
    onCancel={onClose}
    width={760}
    centered
    destroyOnHidden
    className="generation-chain-import-modal"
    title={<div className="gc-import-title">
      <div>
        <span className="gc-kicker">正式资产导入</span>
        <strong>导入 {label || '当前版本'}</strong>
      </div>
      <Tag color="blue"><ImportOutlined /> 版本级来源</Tag>
    </div>}
    footer={<div className="gc-import-footer">
      <Button onClick={onClose}>取消</Button>
      <Button
        type="primary"
        loading={importVersion.isPending}
        disabled={!canImport}
        onClick={() => importVersion.mutate(hasConflicts)}
      >
        {hasConflicts ? '确认覆盖并导入' : '导入此版本'}
      </Button>
    </div>}
  >
    {importOptions.isPending ? <div className="gc-import-loading"><Spin /></div> : null}
    {importOptions.error ? <Alert showIcon type="error" title="导入信息读取失败"
      description={String(importOptions.error)} /> : null}
    {options ? <>
      <div className="gc-import-version">
        <div><span>叶子版本</span><b>{options.versionLabel} · {stage?.label ?? options.leafStage}</b></div>
        <div><span>发布状态</span><b>{selectedVersion?.imported ? '已导入过正式资产' : '尚未导入'}</b></div>
      </div>

      <section className="gc-import-section">
        <h4><LinkOutlined /> 完整父链</h4>
        {options.parents.length ? <div className="gc-import-parents">
          {options.parents.map(parent => <span className="gc-import-parent" key={parent.versionId}>
            <small>{parent.stageLabel || parent.stage}</small>
            <b>{parent.label}</b>
            <em>{parent.summary}</em>
          </span>)}
        </div> : <p className="gc-import-hint">该链路只有当前叶子阶段，无上游 AI 版本。</p>}
      </section>

      <section className="gc-import-section">
        <h4>目标正式资产</h4>
        {options.targetRequired ? <>
          <Select
            className="gc-import-target-select"
            value={target?.targetId}
            placeholder={options.targets.length ? '选择正式目标' : '当前需求下还没有可导入的正式目标'}
            options={options.targets.map(item => ({
              value: item.targetId,
              label: `${item.name} · ${item.caseCount} 条用例`,
            }))}
            onChange={setImportTargetId}
            disabled={!options.targets.length || hasConflicts}
          />
          {target ? <div className="gc-import-target-card">
            <div><strong>{target.name}</strong><span>{target.caseCount} 条正式用例</span></div>
            <SourceSummary target={target} />
            {target.effectiveImport ? <RecordDetails record={target.effectiveImport} /> : null}
          </div> : <p className="gc-import-hint">请先在对应正式测试页面创建集合或测试集。</p>}
          {!options.targets.length ? <Alert showIcon type="warning" title="没有可用的正式目标"
            description="先创建 API 集合或 UI 测试集，再回到这里导入版本。" /> : null}
        </> : <div className="gc-import-target-card">
          <div><strong>按模块自动归属功能测试集</strong><span>沿用现有冲突预览和用例编号规则</span></div>
          {options.targets.length ? <div className="gc-import-function-targets">
            {options.targets.map(item => <div key={item.targetId}>
              <b>{item.name}</b>
              <small>{item.caseCount} 条</small>
              <SourceSummary target={item} />
            </div>)}
          </div> : <p className="gc-import-hint">导入时会按生成结果的模块名自动创建功能测试集。</p>}
        </div>}
      </section>

      {hasConflicts ? <section className="gc-import-section">
        <Alert showIcon type="warning" title={`发现 ${importConflicts.length} 个同名正式用例`}
          description="确认后将覆盖同名用例；未出现在本次版本里的旧用例会保留，并标记为混合来源。" />
        <div className="gc-import-conflicts">
          {importConflicts.map((conflict, index) => {
            const existingName = conflictCaseName(conflict.existingCase)
            const generatedName = conflictCaseName(conflict.generatedCase)
            return <div key={`${conflictName(conflict)}-${index}`}>
              <Tag color="orange">{conflictName(conflict)}</Tag>
              <span>{existingName || '现有用例'} → {generatedName || '本次版本用例'}</span>
            </div>
          })}
        </div>
      </section> : null}

      {!hasConflicts ? <Alert showIcon type="info" title="导入会更新正式资产，但不会删除未出现在本版本中的旧用例。"
        description="正式资产保留版本来源指针；删除该版本后，来源记录会消失并显示“来源已删除”。" /> : null}
    </> : null}
  </Modal>
}
