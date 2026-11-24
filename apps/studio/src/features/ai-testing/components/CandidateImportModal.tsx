import { Alert, Button, Modal, Select } from 'antd'
import type { CandidateChainKind, CurrentImportPreview } from '../api/generationCandidates.contract'

const ROW_WRAP = 'flex flex-wrap items-center gap-2'
const STACK_FIELD = 'flex flex-col gap-1.5'
const STACK = 'flex flex-col gap-2'
const STRONG_LABEL = 'font-semibold text-app-surface-text'

type Props = {
  open: boolean
  kind: CandidateChainKind
  candidateId?: string
  targetId: string
  targetOptions: { value: string; label: string }[]
  targetsLoading: boolean
  targetsError: string | null
  preview: CurrentImportPreview | null
  loading: boolean
  onTargetChange: (value: string) => void
  onPreview: () => void
  onImport: () => void
  onClose: () => void
}

function ConflictCard({ conflict, index }: { conflict: Record<string, unknown>; index: number }) {
  const name = String(conflict.normalizedName || `冲突 ${index + 1}`)
  return <article className="rounded-[8px] border border-app-surface-border bg-app-surface p-3" aria-label={`冲突：${name}`}>
    <div className={ROW_WRAP}>
      <strong className="min-w-0 truncate text-[11.5px] text-app-surface-text" title={name}>{name}</strong>
      <span className="ml-auto shrink-0 rounded-[4px] border border-app-status-warning-border bg-app-status-warning-bg px-1.5 py-0.5 text-[9px] font-semibold text-app-status-warning-text">同名冲突</span>
    </div>
    <div className="mt-2 grid grid-cols-2 gap-2 max-[720px]:grid-cols-1">
      <div className="rounded-[6px] border border-app-status-warning-border bg-app-surface-hover p-2">
        <span className="mb-1 block text-[9.5px] text-app-surface-text-muted">已有用例</span>
        <pre className="m-0 max-h-40 overflow-auto whitespace-pre-wrap break-words text-[10px] leading-[1.5] text-app-surface-text">{JSON.stringify(conflict.existingCase, null, 2)}</pre>
      </div>
      <div className="rounded-[6px] border border-app-accent-border bg-app-accent-surface p-2">
        <span className="mb-1 block text-[9.5px] text-app-surface-text-muted">将导入的用例</span>
        <pre className="m-0 max-h-40 overflow-auto whitespace-pre-wrap break-words text-[10px] leading-[1.5] text-app-surface-text">{JSON.stringify(conflict.generatedCase, null, 2)}</pre>
      </div>
    </div>
  </article>
}

/** 最终阶段的正式导入：侧栏或底栏只放入口，预览、冲突对比和确认都在弹窗内完成。 */
export function CandidateImportModal({
  open, kind, candidateId, targetId, targetOptions, targetsLoading, targetsError, preview, loading,
  onTargetChange, onPreview, onImport, onClose,
}: Props) {
  const targetReady = kind === 'function' || Boolean(targetId)
  const needsTarget = kind !== 'function'

  return <Modal
    open={open}
    title="导入正式用例"
    width="min(880px, calc(100vw - 32px))"
    centered
    destroyOnHidden
    footer={<div className={ROW_WRAP}>
      <span className="text-[10px] text-app-surface-text-muted">导入后可在正式用例库查看</span>
      <span className="ml-auto flex gap-2">
        <Button onClick={onClose}>取消</Button>
        {preview ? <Button loading={loading} onClick={onPreview}>重新预览</Button> : null}
        {preview
          ? <Button type="primary" loading={loading} onClick={onImport}>{preview.requiresConfirmation ? '确认覆盖并导入' : '确认导入'}</Button>
          : <Button type="primary" loading={loading} disabled={!targetReady} onClick={onPreview}>预览导入</Button>}
      </span>
    </div>}
    onCancel={onClose}
    styles={{ body: { maxHeight: 'calc(100vh - 240px)', overflowY: 'auto' } }}
  >
    <div className="flex flex-col gap-4 pt-1">
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-app-surface-text-muted">
        <span className="inline-flex items-center rounded-[5px] border border-app-accent-border bg-app-accent-surface px-1.5 py-0.5 text-[9.5px] font-semibold text-app-accent">最终阶段</span>
        <span>{kind === 'function' ? '按模块归入功能测试集' : '导入到所选正式目标'}</span>
        {candidateId ? <span className="ml-auto font-mono text-[10px]">当前采用 {candidateId.slice(0, 8)}</span> : null}
      </div>

      <section className={STACK_FIELD} aria-label="导入目标">
        <span className="text-[12px] font-semibold text-app-surface-text">导入目标</span>
        {needsTarget ? <>
          <Select
            className="w-full max-w-[420px]"
            aria-label="正式导入目标"
            placeholder="选择正式目标"
            value={targetId || undefined}
            options={targetOptions}
            loading={targetsLoading}
            onChange={onTargetChange}
          />
          {targetsError ? <Alert showIcon type="error" title={targetsError} /> : null}
          {!targetsLoading && !targetsError && targetOptions.length === 0 ? <Alert showIcon type="warning" title="暂无可导入的正式目标" /> : null}
        </> : <div className="flex flex-wrap items-center gap-2 rounded-[7px] border border-app-surface-border bg-app-surface px-3 py-2 text-[11px]">
          <span className={STRONG_LABEL}>功能测试集</span>
          <span className="text-app-surface-text-muted">按模块自动归入，无需选择</span>
        </div>}
      </section>

      {preview ? <section className={STACK} aria-label="导入预览">
        <Alert
          showIcon
          type={preview.requiresConfirmation ? 'warning' : 'info'}
          title={preview.requiresConfirmation ? `有 ${preview.conflicts.length} 个同名冲突，确认后将覆盖同名用例` : '预览完成，没有同名冲突'}
        />
        {preview.conflicts.length ? <div className={STACK}>{preview.conflicts.map((conflict, index) => <ConflictCard key={index} conflict={conflict} index={index} />)}</div> : null}
      </section> : <div className="rounded-[8px] border border-dashed border-app-surface-border px-3 py-4 text-[11px] leading-[1.6] text-app-surface-text-muted">
        先预览将导入的内容和同名冲突；确认后写入正式用例库。
      </div>}
    </div>
  </Modal>
}
