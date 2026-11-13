import { useMemo, useState } from 'react'
import { Collapse, Empty, Input, Tag, Tabs } from 'antd'
import type { ReactNode } from 'react'
import { MaterialBlockContent, type MaterialBlock } from './ReadableRequirementMaterial'
import { toRecord, toRecordArray } from '@/shared/utils/value'
import { toDisplayText } from '../utils/functionalOutput'
import '@/features/ai-testing/styles/traceable-points.css'

type Props = { content: string; onChange?: (content: string) => void; tree?: ReactNode; materialContent?: string }

export function TraceablePointsView({ content, onChange, tree, materialContent }: Props) {
  const [selected, setSelected] = useState<string>()
  const [treeActive, setTreeActive] = useState(false)
  const artifact = useMemo(() => {
    try { return toRecord(JSON.parse(content)) } catch { return undefined }
  }, [content])
  const material = useMemo(() => {
    try { return toRecord(JSON.parse(materialContent || '')) } catch { return undefined }
  }, [materialContent])
  const blocks = toRecordArray(material?.materialBlocks)
  const sources = toRecordArray(material?.sources)
  const points = toRecordArray(artifact?.testPoints)
  const gaps = toRecordArray(artifact?.coverageGaps)
  const issues = toRecordArray(artifact?.reviewIssues)
  const grouped = new Map<string, Map<string, Record<string, unknown>[]>>()
  for (const point of points) {
    const module = toDisplayText(point.module) || '未分组功能项'
    const dimension = toDisplayText(point.dimension) || '未分组场景'
    const scenes = grouped.get(module) ?? new Map<string, Record<string, unknown>[]>()
    scenes.set(dimension, [...(scenes.get(dimension) ?? []), point])
    grouped.set(module, scenes)
  }
  if (artifact?.artifactType !== 'traceable_test_points') return <Empty description="测试点格式无效，请重新生成" />
  const review = toDisplayText(artifact.reviewStatus)
  const reviewLabel = ({ independent_reviewed: '独立审查通过', independent_review_failed: '独立审查未通过', self_review_only: '仅完成自审' } as Record<string, string>)[review] || '审查状态未知'
  const updateName = (id: string, name: string) => {
    if (!onChange) return
    const next = { ...artifact, reviewStatus: 'self_review_only', testPoints: points.map(point => point.id === id ? { ...point, name } : point) }
    onChange(JSON.stringify(next, null, 2))
  }
  return <div className={`ai-traceable-points${treeActive ? ' is-tree-active' : ''}`}>
    <div className="ai-traceable-points-summary"><span>测试点 {points.length} 项</span><span>覆盖缺口 {gaps.length} 项</span><Tag color={review === 'independent_reviewed' ? 'green' : 'orange'}>{reviewLabel}</Tag></div>
    {tree ? <Tabs items={[{ key: 'details', label: '测试点详情', children: null }, { key: 'tree', label: '树图', children: tree }]} onChange={key => setTreeActive(key === 'tree')} /> : null}
    {!treeActive && <>{points.length ? [...grouped.entries()].map(([module, scenes]) => <section className="ai-traceable-points-module" key={module}>
      <h3>{module}</h3>
      {[...scenes.entries()].map(([dimension, entries]) => <div key={dimension} className="ai-traceable-points-scene"><h4>{dimension} <span>{entries.length}</span></h4>
        {entries.map((point, index) => {
          const id = toDisplayText(point.id) || String(index)
          const refs = ['materialBlockIds', 'testObjectIds', 'impactAreaIds', 'riskIds', 'materialQuestionIds', 'scopeQuestionIds']
          return <article className="ai-traceable-points-item" key={id}>
            <div><span className="ai-traceable-points-id">{id}</span>{onChange ? <Input aria-label={`测试点 ${id}`} value={toDisplayText(point.name)} onChange={event => updateName(id, event.target.value)} /> : <strong>{toDisplayText(point.name)}</strong>}</div>
            <button type="button" aria-expanded={selected === id} onClick={() => setSelected(selected === id ? undefined : id)}>查看关联</button>
            {selected === id ? <dl>{refs.map(field => {
              const values = Array.isArray(point[field]) ? point[field].map(toDisplayText).filter(Boolean) : []
              return values.length ? <div key={field}><dt>{({ materialBlockIds: '材料块', testObjectIds: '测试对象', impactAreaIds: '影响范围', riskIds: '风险', materialQuestionIds: '材料问题', scopeQuestionIds: '分析问题' } as Record<string, string>)[field]}</dt><dd>{values.join('、')}</dd></div> : null
            })}{Array.isArray(point.materialBlockIds) ? point.materialBlockIds.map(id => {
              const block = blocks.find(item => item.id === id)
              if (!block) return null
              const source = sources.find(item => item.id === block.sourceId)
              return <div className="ai-traceable-points-evidence" key={String(id)}><strong>{toDisplayText(source?.name)} · {toDisplayText(block.locator)}</strong><MaterialBlockContent block={block as MaterialBlock} /></div>
            }) : null}</dl> : null}
          </article>
        })}</div>)}
    </section>) : <Empty description="暂无测试点" />}
    {issues.length ? <section className="ai-traceable-points-module"><h3>未解决的审查问题</h3>{issues.map((issue, index) => <article className="ai-traceable-points-item" key={index}><strong>{toDisplayText(issue.targetId) || '遗漏项'}</strong><p>{toDisplayText(issue.issue)}</p><p>{toDisplayText(issue.suggestion)}</p></article>)}</section> : null}
    <section className="ai-traceable-points-module"><h3>覆盖缺口</h3>{gaps.length ? <Collapse items={gaps.map((gap, index) => ({ key: toDisplayText(gap.id) || String(index), label: toDisplayText(gap.description), children: <p>{toDisplayText(gap.blockedCoverage)}</p> }))} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未记录覆盖缺口" />}</section></>}
  </div>
}
