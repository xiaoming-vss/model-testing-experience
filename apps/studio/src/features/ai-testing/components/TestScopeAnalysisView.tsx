import { useMemo, useState } from 'react'
import { Tag } from 'antd'
import {
  ArtifactBreakdown,
  ArtifactDetailTitle,
  ArtifactDivider,
  ArtifactEmpty,
  ArtifactEvidence,
  ArtifactEvidenceItem,
  ArtifactEvidenceMissing,
  ArtifactField,
  ArtifactHeader,
  ArtifactKicker,
  ArtifactListRow,
  ArtifactRefChips,
  ArtifactSplit,
  ArtifactStat,
  ArtifactTabs,
} from '@/shared/components/ArtifactView'
import miscArtifactStyles from '../styles/artifact-misc.module.css'
import { cx } from '@/shared/utils/cx'
import { toRecord, toRecordArray } from '@/shared/utils/value'
import { toDisplayText } from '../utils/functionalOutput'
import { MaterialBlockContent, type MaterialBlock } from './ReadableRequirementMaterial'

const categories = [
  { key: 'testObjects', label: '测试对象', hint: '识别需要关注的业务对象与操作' },
  { key: 'impactAreas', label: '影响范围', hint: '从变更出发，梳理已知业务关联和影响' },
  { key: 'risks', label: '风险', hint: '可能影响业务判断或测试覆盖的因素' },
  { key: 'openQuestions', label: '待确认', hint: '材料未明确、需要进一步确认的事项' },
] as const

type Category = (typeof categories)[number]['key']

const status: Record<string, { label: string; color: string }> = {
  confirmed: { label: '明确', color: 'green' },
  inferred: { label: '推测', color: 'blue' },
  unconfirmed: { label: '待确认', color: 'orange' },
}

function refIds(record: Record<string, unknown>, field: string) {
  return Array.isArray(record[field]) ? record[field].map(toDisplayText).filter(Boolean) : []
}

function entryId(entry: Record<string, unknown>, index: number) {
  return toDisplayText(entry.id) || String(index + 1)
}

function entryTitle(category: Category, entry: Record<string, unknown>) {
  const value = category === 'testObjects'
    ? entry.name
    : category === 'impactAreas'
      ? entry.area
      : category === 'risks'
        ? entry.description
        : entry.question
  return toDisplayText(value) || '未命名'
}

export function TestScopeAnalysisView({ analysis, materialContent }: {
  analysis: Record<string, unknown>
  materialContent?: string
}) {
  const [active, setActive] = useState<Category>('testObjects')
  const [selected, setSelected] = useState<Partial<Record<Category, number>>>({})

  const material = useMemo(() => {
    try { return toRecord(JSON.parse(materialContent || '')) } catch { return undefined }
  }, [materialContent])

  const blocks = toRecordArray(material?.materialBlocks)
  const sources = toRecordArray(material?.sources)
  const materialQuestions = toRecordArray(material?.questions)
  const blockById = useMemo(() => new Map(blocks.map(block => [toDisplayText(block.id), block])), [blocks])
  const sourceById = useMemo(() => new Map(sources.map(source => [toDisplayText(source.id), source])), [sources])
  const questionById = useMemo(() => new Map(materialQuestions.map(question => [toDisplayText(question.id), toDisplayText(question.question)])), [materialQuestions])

  const objects = toRecordArray(analysis.testObjects)
  const areas = toRecordArray(analysis.impactAreas)
  const risks = toRecordArray(analysis.risks)
  const objectNameById = useMemo(() => new Map(objects.map((entry, index) => [entryId(entry, index), entryTitle('testObjects', entry)])), [objects])
  const areaNameById = useMemo(() => new Map(areas.map((entry, index) => [entryId(entry, index), entryTitle('impactAreas', entry)])), [areas])
  const riskNameById = useMemo(() => new Map(risks.map((entry, index) => [entryId(entry, index), entryTitle('risks', entry)])), [risks])

  const entries = toRecordArray(analysis[active])
  const activeIndex = Math.min(selected[active] ?? 0, Math.max(entries.length - 1, 0))
  const activeEntry = entries[activeIndex]
  const current = categories.find(category => category.key === active)!
  const activeStatus = activeEntry ? status[toDisplayText(activeEntry.basisStatus)] : undefined

  const breakdown = { confirmed: 0, inferred: 0, unconfirmed: 0 }
  entries.forEach((entry) => {
    const key = toDisplayText(entry.basisStatus)
    if (key in breakdown) breakdown[key as keyof typeof breakdown] += 1
  })

  const questionRelated = {
    objects: new Set(entries.flatMap(entry => refIds(entry, 'testObjectIds'))).size,
    areas: new Set(entries.flatMap(entry => refIds(entry, 'impactAreaIds'))).size,
    risks: new Set(entries.flatMap(entry => refIds(entry, 'riskIds'))).size,
  }

  const select = (index: number) => setSelected(currentValue => ({ ...currentValue, [active]: index }))
  const sourceBlockIds = activeEntry ? refIds(activeEntry, 'sourceBlockIds') : []

  return <div className={cx('flex h-full min-h-0 flex-col bg-app-surface', miscArtifactStyles.testScopeRoot)}>
    <ArtifactTabs
      ariaLabel="测试范围风险分析"
      active={active}
      onChange={setActive}
      tabs={categories.map((category) => {
        const count = toRecordArray(analysis[category.key]).length
        return {
          key: category.key,
          label: category.label,
          count,
          tone: category.key === 'openQuestions' && count ? 'warn' : undefined,
        }
      })}
    />
    <div className="flex min-h-0 flex-1 flex-col gap-2.5 px-3 pb-3 pt-2.5 max-narrow:overflow-auto" role="tabpanel" aria-label={current.label}>
      <ArtifactHeader hint={current.hint} hintClassName="max-narrow:hidden">
        <ArtifactStat label={current.label} value={entries.length} />
        <ArtifactDivider />
        {active === 'openQuestions'
          ? <ArtifactBreakdown items={[
            { label: '涉及测试对象', value: questionRelated.objects },
            { label: '影响范围', value: questionRelated.areas },
            { label: '风险', value: questionRelated.risks },
          ]} />
          : <ArtifactBreakdown items={[
            { label: '明确', value: breakdown.confirmed, dot: 'ok' },
            { label: '推测', value: breakdown.inferred, dot: 'accent' },
            { label: '待确认', value: breakdown.unconfirmed, dot: 'warn' },
          ]} />}
      </ArtifactHeader>
      {entries.length ? <ArtifactSplit
        listLabel={`${current.label}列表`}
        detailLabel={`${current.label}详情`}
        list={entries.map((entry, index) => {
          const entryStatus = status[toDisplayText(entry.basisStatus)]
          return <ArtifactListRow
            key={`${entryId(entry, index)}-${index}`}
            id={entryId(entry, index)}
            title={entryTitle(active, entry)}
            active={index === activeIndex}
            onClick={() => select(index)}
          >
            {entryStatus ? <Tag color={entryStatus.color}>{entryStatus.label}</Tag> : null}
          </ArtifactListRow>
        })}
        detail={activeEntry ? <>
          <ArtifactKicker badge={current.label}>
            <span>{entryId(activeEntry, activeIndex)}</span>
            {activeStatus ? <Tag color={activeStatus.color}>{activeStatus.label}</Tag> : null}
          </ArtifactKicker>
          <ArtifactDetailTitle>{entryTitle(active, activeEntry)}</ArtifactDetailTitle>
          {active === 'testObjects' ? <>
            <ArtifactField className="mt-3" label="类型" value={toDisplayText(activeEntry.type)} />
            <ArtifactField className="mt-3" label="描述" value={toDisplayText(activeEntry.description)} />
          </> : null}
          {active === 'impactAreas' ? <>
            <ArtifactField className="mt-3" label="影响" value={toDisplayText(activeEntry.impact)} />
            <ArtifactRefChips className="mt-4" title="关联测试对象" values={refIds(activeEntry, 'testObjectIds')} resolve={id => objectNameById.get(id)} />
          </> : null}
          {active === 'risks' ? <>
            <ArtifactRefChips className="mt-4" title="关联测试对象" values={refIds(activeEntry, 'testObjectIds')} resolve={id => objectNameById.get(id)} />
            <ArtifactRefChips className="mt-4" title="关联影响范围" values={refIds(activeEntry, 'impactAreaIds')} resolve={id => areaNameById.get(id)} />
          </> : null}
          {active === 'openQuestions' ? <>
            <ArtifactRefChips className="mt-4" title="关联测试对象" values={refIds(activeEntry, 'testObjectIds')} resolve={id => objectNameById.get(id)} />
            <ArtifactRefChips className="mt-4" title="关联影响范围" values={refIds(activeEntry, 'impactAreaIds')} resolve={id => areaNameById.get(id)} />
            <ArtifactRefChips className="mt-4" title="关联风险" values={refIds(activeEntry, 'riskIds')} resolve={id => riskNameById.get(id)} />
            <ArtifactRefChips className="mt-4" title="来源问题" values={refIds(activeEntry, 'sourceQuestionIds')} resolve={id => questionById.get(id)} />
          </> : null}
          <ArtifactEvidence title="材料依据" count={sourceBlockIds.length} className="mt-4">
            {sourceBlockIds.map((id) => {
              const block = blockById.get(id)
              if (!block) return <ArtifactEvidenceMissing key={id}>{id}：未找到对应材料</ArtifactEvidenceMissing>
              const source = sourceById.get(toDisplayText(block.sourceId))
              return <ArtifactEvidenceItem key={id} source={toDisplayText(source?.name) || '来源未找到'} locator={toDisplayText(block.locator)}>
                <MaterialBlockContent block={block as MaterialBlock} />
              </ArtifactEvidenceItem>
            })}
          </ArtifactEvidence>
        </> : null}
      /> : <ArtifactEmpty description={`暂无${current.label}`} />}
    </div>
  </div>
}
