import { FileTextOutlined, LockOutlined, RightOutlined, TableOutlined, WarningOutlined } from '@ant-design/icons'
import { useState } from 'react'
import { cx } from '@/shared/utils/cx'
import type { ScopeEntryView, ScopeMaterialBlockView } from '../../utils/testScopeAnalysis'
import { MaterialBlockContent } from '../ReadableRequirementMaterial'
import {
  EVIDENCE_BODY,
  EVIDENCE_CARD,
  EVIDENCE_DOC,
  EVIDENCE_DOC_META,
  EVIDENCE_DOC_TITLE,
  EVIDENCE_EMPTY,
  EVIDENCE_HEAD,
  EVIDENCE_HEAD_BUTTON,
  EVIDENCE_INDEX,
  EVIDENCE_ITEM,
  EVIDENCE_KIND,
  EVIDENCE_LOCATOR,
  EVIDENCE_MISSING,
  EVIDENCE_SUMMARY,
  SECTION,
  SECTION_COUNT,
  SECTION_HEAD,
  SECTION_NOTE,
  SECTION_TITLE,
} from './testScopeClasses'
import styles from '../../styles/test-scope.module.css'

type EvidenceItem = { key: string; id: string; block?: ScopeMaterialBlockView; index: number }
type EvidenceGroup = { key: string; sourceName: string; sourceType: string; items: EvidenceItem[] }

const KIND_LABEL: Record<string, string> = {
  section: '章节',
  paragraph: '段落',
  list: '列表',
  table: '表格',
  image: '图片',
}

const SOURCE_TYPE_LABEL: Record<string, string> = {
  document: '需求文档',
  richtext: '富文本',
  image: '图片',
  user_confirmation: '用户确认',
}

function safeId(value: string) {
  return value.replace(/[^a-zA-Z0-9_-]/g, '-')
}

function blockSummary(block: ScopeMaterialBlockView) {
  const { kind, content } = block
  if (kind === 'table' && Array.isArray(content.rows)) {
    const rows = content.rows.filter((row): row is unknown[] => Array.isArray(row))
    const columns = rows.reduce((max, row) => Math.max(max, row.length), 0)
    return columns ? `${rows.length} 行 × ${columns} 列` : `${rows.length} 行`
  }
  if (kind === 'list' && Array.isArray(content.items)) return `${content.items.length} 项`
  if (kind === 'image') return '图片材料'
  return ''
}

function groupEvidence(entry: ScopeEntryView, blockById: Map<string, ScopeMaterialBlockView>) {
  const groups: EvidenceGroup[] = []
  const groupByKey = new Map<string, EvidenceGroup>()
  entry.sourceBlockIds.forEach((id, index) => {
    const block = blockById.get(id)
    const key = block ? (block.sourceId || block.sourceName) : '__missing__'
    let group = groupByKey.get(key)
    if (!group) {
      group = {
        key,
        sourceName: block?.sourceName || '未找到来源',
        sourceType: block?.sourceType || '',
        items: [],
      }
      groupByKey.set(key, group)
      groups.push(group)
    }
    group.items.push({ key: `${id}-${index}`, id, block, index })
  })
  return groups
}

function EvidenceDocument({ group, expanded, onToggle }: {
  group: EvidenceGroup
  expanded: Set<string>
  onToggle: (key: string) => void
}) {
  return <div className={EVIDENCE_CARD}>
    <div className={EVIDENCE_DOC}>
      <FileTextOutlined className="mt-0.5 shrink-0 text-[14px] text-app-surface-text-muted" aria-hidden="true" />
      <div className="min-w-0 basis-0 grow">
        <strong className={EVIDENCE_DOC_TITLE}>{group.sourceName}</strong>
        <span className={EVIDENCE_DOC_META}>{group.key === '__missing__' ? '材料引用不可用' : `${SOURCE_TYPE_LABEL[group.sourceType] || '来源材料'} · ${group.items.length} 个材料块`}</span>
      </div>
      {group.key !== '__missing__' ? <span className="inline-flex h-5 shrink-0 items-center gap-1 rounded-[4px] border border-app-surface-border px-1.5 text-[10px] text-app-surface-text-muted"><LockOutlined aria-hidden="true" />冻结</span> : null}
    </div>
    {group.items.map((item) => {
      if (!item.block) {
        return <div className={EVIDENCE_ITEM} key={item.key}>
          <div className={EVIDENCE_HEAD}>
            <span className={EVIDENCE_INDEX}>[{String(item.index + 1).padStart(2, '0')}]</span>
            <span className={EVIDENCE_LOCATOR}>{item.id}</span>
            <span className={EVIDENCE_KIND}>未收录</span>
          </div>
          <div className={EVIDENCE_MISSING}><WarningOutlined aria-hidden="true" />未找到该材料块，请重新生成或检查材料引用。</div>
        </div>
      }

      const block = item.block
      const summary = blockSummary(block)
      const kind = KIND_LABEL[block.kind] || '材料'
      const bodyId = `scope-evidence-${safeId(block.id)}`
      if (block.kind === 'table') {
        const open = expanded.has(block.id)
        return <div className={EVIDENCE_ITEM} key={item.key}>
          <button
            type="button"
            className={EVIDENCE_HEAD_BUTTON}
            aria-expanded={open}
            aria-controls={bodyId}
            onClick={() => onToggle(block.id)}
          >
            <span className={EVIDENCE_INDEX}>[{String(item.index + 1).padStart(2, '0')}]</span>
            <span className={EVIDENCE_LOCATOR}>{block.locator}</span>
            <span className={cx(EVIDENCE_SUMMARY, 'inline-flex items-center gap-1')}><TableOutlined aria-hidden="true" />{summary || '表格'}</span>
            <RightOutlined className={cx('shrink-0 text-[10px] text-app-surface-text-muted transition-transform', open && 'rotate-90')} aria-hidden="true" />
          </button>
          <div id={bodyId} hidden={!open} className={EVIDENCE_BODY}>
            <div className={styles.evidenceContent}><MaterialBlockContent block={block} /></div>
          </div>
        </div>
      }

      return <div className={EVIDENCE_ITEM} key={item.key}>
        <div className={EVIDENCE_HEAD}>
          <span className={EVIDENCE_INDEX}>[{String(item.index + 1).padStart(2, '0')}]</span>
          <span className={EVIDENCE_LOCATOR}>{block.locator}</span>
          <span className={EVIDENCE_KIND}>{kind}</span>
          {summary ? <span className={EVIDENCE_SUMMARY}>{summary}</span> : null}
        </div>
        <div className={EVIDENCE_BODY}>
          <div className={styles.evidenceContent}><MaterialBlockContent block={block} /></div>
        </div>
      </div>
    })}
  </div>
}

export function TestScopeEvidence({ entry, blockById }: {
  entry: ScopeEntryView
  blockById: Map<string, ScopeMaterialBlockView>
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const groups = groupEvidence(entry, blockById)
  const toggle = (key: string) => setExpanded((current) => {
    const next = new Set(current)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return next
  })

  return <section className={SECTION} aria-label="材料依据">
    <div className={SECTION_HEAD}>
      <h2 className={SECTION_TITLE}>材料依据</h2>
      <span className={SECTION_COUNT}>{entry.sourceBlockIds.length}</span>
      <span className={SECTION_NOTE}><LockOutlined aria-hidden="true" />冻结于本次分析</span>
    </div>
    {groups.length
      ? groups.map((group) => <EvidenceDocument key={group.key} group={group} expanded={expanded} onToggle={toggle} />)
      : <p className={EVIDENCE_EMPTY}>当前条目没有可引用的材料依据。</p>}
  </section>
}
