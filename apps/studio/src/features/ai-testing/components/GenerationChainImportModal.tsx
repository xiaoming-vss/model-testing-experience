import { Alert, Button, Modal, Select, Spin, Tag } from 'antd'
import { CheckCircleFilled, ImportOutlined, LinkOutlined } from '@ant-design/icons'
import type { GenerationChainWorkspace } from '../hooks/useRequirementGenerationChain'
import type { GenerationChainImportRecord, GenerationChainImportTarget } from '../api/generationChain.api'
import chainStyles from '../styles/generation-chain.module.css'

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
    return <span className="gc-import-source is-danger inline-flex items-center gap-[5px] text-[11px] text-[var(--app-profile-danger-text)]">当前正式来源已删除</span>
  }
  if (!target.effectiveImport) {
    return <span className="gc-import-source is-muted inline-flex items-center gap-[5px] text-[11px] text-[var(--app-surface-text-muted)]">尚未从生成链导入</span>
  }
  return <span className="gc-import-source inline-flex items-center gap-[5px] text-[11px] text-[var(--app-result-success-text)] [&_small]:text-[var(--app-surface-text-muted)]">
    <CheckCircleFilled /> 当前正式来源 {target.effectiveImport.versionLabel || '历史版本'}
    <small>{formatTime(target.effectiveImport.importedAt)} · 变更 {target.effectiveImport.changedCaseCount} 条</small>
    {target.effectiveImport.mixedSource ? <Tag color="warning">混合来源</Tag> : null}
  </span>
}

function RecordDetails({ record }: { record: GenerationChainImportRecord }) {
  return <div className="gc-import-record grid grid-cols-3 gap-1.5 border-t border-[var(--app-surface-divider)] pt-[7px] [&>.ant-alert]:col-span-full [&>div]:flex [&>div:not(.gc-import-case-ids)]:flex-col [&>div:not(.gc-import-case-ids)]:gap-px [&_b]:text-[11px] [&_b]:text-[var(--app-surface-text)] [&_span]:text-[10px] [&_span]:text-[var(--app-surface-text-muted)]">
    <div><span>来源版本</span><b>{record.versionLabel || record.versionId}</b></div>
    <div><span>变更用例</span><b>{record.changedCaseCount} / {record.targetCaseCount}</b></div>
    <div><span>导入时间</span><b>{formatTime(record.importedAt) || '—'}</b></div>
    {record.mixedSource ? <Alert showIcon type="warning" title="本次只覆盖部分用例，正式目标仍保留旧来源用例。" /> : null}
    {record.changedCaseIds.length ? <div className="gc-import-case-ids col-span-full flex flex-row flex-wrap items-center gap-1">
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
    rootClassName={chainStyles.scope}
    className="generation-chain-import-modal"
    title={<div className="gc-import-title flex items-center justify-between gap-3">
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="gc-kicker mb-1 block text-[11px] uppercase tracking-[0.08em] text-[var(--gc-muted)]">正式资产导入</span>
        <strong className="text-[16px] text-[var(--app-surface-text)]">导入 {label || '当前版本'}</strong>
      </div>
      <Tag color="blue"><ImportOutlined /> 版本级来源</Tag>
    </div>}
    footer={<div className="gc-import-footer flex justify-end gap-2 [&>*]:min-w-[92px]">
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
    {importOptions.isPending ? <div className="gc-import-loading grid min-h-[180px] place-items-center"><Spin /></div> : null}
    {importOptions.error ? <Alert showIcon type="error" title="导入信息读取失败"
      description={String(importOptions.error)} /> : null}
    {options ? <>
      <div className="gc-import-version grid grid-cols-2 gap-2 rounded-[10px] border border-[var(--app-surface-border)] bg-[var(--app-surface-hover)] px-3 py-2.5 [&>div]:flex [&>div]:flex-col [&>div]:gap-0.5 [&_b]:text-[13px] [&_b]:text-[var(--app-surface-text)] [&_span]:text-[11px] [&_span]:text-[var(--app-surface-text-muted)]">
        <div><span>叶子版本</span><b>{options.versionLabel} · {stage?.label ?? options.leafStage}</b></div>
        <div><span>发布状态</span><b>{selectedVersion?.imported ? '已导入过正式资产' : '尚未导入'}</b></div>
      </div>

      {options.parents.length ? <section className="gc-import-section mt-3.5 flex flex-col gap-2">
        <h4 className="m-0 flex items-center gap-[5px] text-[12px] text-[var(--app-surface-text)]"><LinkOutlined /> 关联阶段</h4>
        <div className="gc-import-parents flex flex-wrap gap-1.5">
          {options.parents.map(parent => <span className="gc-import-parent grid min-w-[140px] grid-cols-[auto_auto] gap-x-1.5 gap-y-px rounded-[8px] border border-[var(--app-surface-border)] bg-[var(--app-surface-hover)] px-[9px] py-[7px] [&_b]:font-mono [&_b]:text-[11px] [&_b]:font-semibold [&_b]:text-[var(--app-accent)] [&_em]:col-span-full [&_em]:overflow-hidden [&_em]:text-ellipsis [&_em]:whitespace-nowrap [&_em]:text-[10px] [&_em]:not-italic [&_em]:text-[var(--app-surface-text-muted)] [&_small]:text-[10px] [&_small]:text-[var(--app-surface-text-muted)]" key={parent.versionId}>
            <small>{parent.stageLabel || parent.stage}</small>
            <b>{parent.label}</b>
            <em>{parent.summary}</em>
          </span>)}
        </div>
      </section> : null}

      <section className="gc-import-section mt-3.5 flex flex-col gap-2">
        <h4 className="m-0 flex items-center gap-[5px] text-[12px] text-[var(--app-surface-text)]">目标正式资产</h4>
        {options.targetRequired ? <>
          <Select
            className="gc-import-target-select w-[min(420px,100%)]"
            value={target?.targetId}
            placeholder={options.targets.length ? '选择正式目标' : '当前需求下还没有可导入的正式目标'}
            options={options.targets.map(item => ({
              value: item.targetId,
              label: `${item.name} · ${item.caseCount} 条用例`,
            }))}
            onChange={setImportTargetId}
            disabled={!options.targets.length || hasConflicts}
          />
          {target ? <div className="gc-import-target-card flex flex-col gap-[7px] rounded-[10px] border border-[var(--app-surface-border)] bg-[var(--app-surface-hover)] px-3 py-2.5 [&>div:first-child]:flex [&>div:first-child]:items-baseline [&>div:first-child]:gap-2 [&>div:first-child_span]:text-[11px] [&>div:first-child_span]:text-[var(--app-surface-text-muted)] [&_strong]:text-[12px] [&_strong]:text-[var(--app-surface-text)]">
            <div><strong>{target.name}</strong><span>{target.caseCount} 条正式用例</span></div>
            <SourceSummary target={target} />
            {target.effectiveImport ? <RecordDetails record={target.effectiveImport} /> : null}
          </div> : <p className="gc-import-hint m-0 text-[11px] text-[var(--app-surface-text-muted)]">请先在对应正式测试页面创建集合或测试集。</p>}
          {!options.targets.length ? <Alert showIcon type="warning" title="没有可用的正式目标"
            description="先创建 API 集合或 UI 测试集，再回到这里导入版本。" /> : null}
        </> : <div className="gc-import-target-card flex flex-col gap-[7px] rounded-[10px] border border-[var(--app-surface-border)] bg-[var(--app-surface-hover)] px-3 py-2.5 [&>div:first-child]:flex [&>div:first-child]:items-baseline [&>div:first-child]:gap-2 [&>div:first-child_span]:text-[11px] [&>div:first-child_span]:text-[var(--app-surface-text-muted)] [&_strong]:text-[12px] [&_strong]:text-[var(--app-surface-text)]">
          <div><strong>按模块自动归属功能测试集</strong><span>沿用现有冲突预览和用例编号规则</span></div>
          {options.targets.length ? <div className="gc-import-function-targets flex flex-col gap-[5px] [&>div]:flex [&>div]:items-center [&>div]:gap-[7px] [&>div]:border-t [&>div]:border-[var(--app-surface-divider)] [&>div]:pt-[5px] [&_.gc-import-source]:ml-auto [&_b]:text-[11px] [&_b]:text-[var(--app-surface-text)] [&_small]:text-[10px] [&_small]:text-[var(--app-surface-text-muted)]">
            {options.targets.map(item => <div key={item.targetId}>
              <b>{item.name}</b>
              <small>{item.caseCount} 条</small>
              <SourceSummary target={item} />
            </div>)}
          </div> : <p className="gc-import-hint m-0 text-[11px] text-[var(--app-surface-text-muted)]">导入时会按生成结果的模块名自动创建功能测试集。</p>}
        </div>}
      </section>

      {hasConflicts ? <section className="gc-import-section mt-3.5 flex flex-col gap-2">
        <Alert showIcon type="warning" title={`发现 ${importConflicts.length} 个同名正式用例`}
          description="确认后将覆盖同名用例；未出现在本次版本里的旧用例会保留，并标记为混合来源。" />
        <div className="gc-import-conflicts flex max-h-[140px] flex-col gap-[5px] overflow-auto [&>div]:flex [&>div]:items-center [&>div]:gap-1.5 [&>div]:text-[11px] [&>div]:text-[var(--app-surface-text-muted)]">
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
