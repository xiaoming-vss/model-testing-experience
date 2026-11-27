import { Button, Dropdown, Modal, type MenuProps } from 'antd'
import { DownOutlined, LoadingOutlined, MoreOutlined } from '@ant-design/icons'
import type { CandidateSummary } from '../api/generationCandidates.contract'

type Props = {
  candidate: CandidateSummary
  continueLabel: string
  canAdopt: boolean
  canContinue: boolean
  canEdit: boolean
  canRevise: boolean
  canDispose: boolean
  loading: boolean
  editing: boolean
  revisionOpen: boolean
  revisionDirty: boolean
  currentActive: boolean
  onAdopt: (continueAfter?: boolean) => void
  onEdit: () => void
  onSave: () => void
  onCancelEdit: () => void
  onRevise: () => void
  onDispose: (action: 'reject' | 'delete') => void
}

export function CandidateStageActions({
  candidate, continueLabel, canAdopt, canContinue, canEdit, canRevise, canDispose,
  loading, editing, revisionOpen, revisionDirty, currentActive, onAdopt, onEdit, onSave, onCancelEdit, onRevise, onDispose,
}: Props) {
  const disposeItems: MenuProps['items'] = canDispose
    ? [...(candidate.disposition === 'available' ? [{ key: 'reject', label: '拒绝候选' }] : []), { key: 'delete', label: '删除候选', danger: true }]
    : []
  const menuItems: MenuProps['items'] = [
    ...(canContinue ? [{ key: 'continue', label: continueLabel, disabled: loading || revisionOpen || revisionDirty || !candidate.currentAttemptId }] : []),
    ...(disposeItems.length ? [{ type: 'divider' as const }, ...disposeItems] : []),
  ]
  function handleMenu({ key }: { key: string }) {
    if (key === 'continue') { onAdopt(true); return }
    if (key === 'reject') Modal.confirm({ title: '拒绝这个候选？', okText: '确定', cancelText: '取消', onOk: () => onDispose('reject') })
    if (key === 'delete') Modal.confirm({ title: '删除这个候选？', content: '删除后不可恢复；当前采用内容不受影响。', okText: '确定', cancelText: '取消', onOk: () => onDispose('delete') })
  }
  return <>
    <div className="gc-candidate-dock-head">
      <span className="gc-candidate-dock-label">候选 {candidate.candidateId.slice(0, 8)}</span>
      <span className="gc-candidate-dock-hint">{candidate.isCurrent ? '当前采用内容' : '采用后替换当前内容'}</span>
    </div>
    {editing ? <>
      <Button className="gc-candidate-primary" type="primary" block loading={loading} onClick={onSave}>保存{candidate.frozenAt || candidate.isCurrent || candidate.disposition !== 'available' ? '为新候选' : '候选'}</Button>
      <Button block onClick={onCancelEdit}>取消编辑</Button>
    </> : <>
      {canAdopt ? menuItems.length ? <div className="gc-candidate-split flex min-h-9 overflow-hidden rounded-lg border border-[var(--button-primary-border)] bg-[var(--button-primary-bg)]">
        <button type="button" className="gc-candidate-split-main inline-flex min-w-0 flex-1 cursor-pointer items-center justify-center gap-1.5 border-0 bg-transparent px-3 text-[13px] font-semibold text-[var(--button-primary-text)] transition-colors enabled:hover:bg-[var(--button-primary-hover-bg)] disabled:cursor-not-allowed disabled:text-[var(--button-disabled-text)] focus-visible:outline-2 focus-visible:outline-offset-[-3px] focus-visible:outline-[var(--button-focus)]" disabled={loading || revisionOpen || revisionDirty || !candidate.currentAttemptId} aria-busy={loading} onClick={() => onAdopt()}>
          {loading ? <LoadingOutlined aria-hidden /> : null}采用
        </button>
        <Dropdown trigger={['click']} placement="topRight" disabled={loading || revisionOpen || revisionDirty} menu={{ items: menuItems, onClick: handleMenu }}>
          <button type="button" className="gc-candidate-split-caret inline-flex w-9 flex-none cursor-pointer items-center justify-center border-0 border-l border-[var(--button-primary-border)] bg-transparent text-[11px] text-[var(--button-primary-text)] transition-colors enabled:hover:bg-[var(--button-primary-hover-bg)] disabled:cursor-not-allowed disabled:text-[var(--button-disabled-text)] focus-visible:outline-2 focus-visible:outline-offset-[-3px] focus-visible:outline-[var(--button-focus)]" aria-label="更多操作" title="更多操作" aria-haspopup="menu"><DownOutlined aria-hidden /></button>
        </Dropdown>
      </div> : <Button className="gc-candidate-primary" type="primary" block autoInsertSpace={false} loading={loading} disabled={revisionOpen || revisionDirty || !candidate.currentAttemptId} onClick={() => onAdopt()}>采用</Button>
        : disposeItems.length ? <div className="gc-candidate-primary-row"><Dropdown trigger={['click']} placement="topRight" menu={{ items: menuItems, onClick: handleMenu }}><Button className="gc-candidate-more-wide" icon={<MoreOutlined />} block disabled={loading || revisionOpen || revisionDirty}>更多操作</Button></Dropdown></div> : null}
      {canEdit || canRevise ? <div className="gc-candidate-secondary-row">
        {canEdit ? <Button block autoInsertSpace={false} disabled={revisionOpen || revisionDirty} onClick={onEdit}>编辑</Button> : null}
        {canRevise ? <Button block disabled={loading || currentActive} onClick={onRevise}>继续优化</Button> : null}
      </div> : null}
    </>}
  </>
}
