import { toRecord, toRecordArray } from '@/shared/utils/value'
import { toDisplayText } from './functionalOutput'

export const TRACEABLE_REF_FIELDS = [
  { field: 'materialBlockIds', label: '材料块' },
  { field: 'testObjectIds', label: '测试对象' },
  { field: 'impactAreaIds', label: '影响范围' },
  { field: 'riskIds', label: '风险' },
  { field: 'materialQuestionIds', label: '材料问题' },
  { field: 'scopeQuestionIds', label: '分析问题' },
] as const

export type TraceableRefField = (typeof TRACEABLE_REF_FIELDS)[number]['field']
export type TraceableRefs = Record<TraceableRefField, string[]>

export type TraceablePoint = {
  /** 产物内 ID 仅用于内部关联和搜索，不在界面显示。 */
  id: string
  rawId: string
  name: string
  module: string
  scene: string
  moduleId: string
  sceneId: string
  derived: boolean
  point: Record<string, unknown>
  refs: TraceableRefs
  refCount: number
}

export type TraceableScene = {
  id: string
  title: string
  moduleId: string
  points: TraceablePoint[]
}

export type TraceableModule = {
  id: string
  title: string
  scenes: TraceableScene[]
  points: TraceablePoint[]
}

export type TraceableGap = {
  id: string
  description: string
  blockedCoverage: string
  gap: Record<string, unknown>
  refs: TraceableRefs
  relatedPointIds: string[]
  relatedSceneIds: string[]
}

export type TraceableIssue = {
  index: number
  kind: string
  targetType: string
  targetId: string
  issue: string
  suggestion: string
  pointId?: string
  gapId?: string
  sceneId?: string
}

export type TraceablePointsModel = {
  artifact: Record<string, unknown>
  modules: TraceableModule[]
  points: TraceablePoint[]
  pointById: Map<string, TraceablePoint>
  sceneById: Map<string, TraceableScene>
  gaps: TraceableGap[]
  issues: TraceableIssue[]
  blocks: Record<string, unknown>[]
  blockById: Map<string, Record<string, unknown>>
  sources: Record<string, unknown>[]
  sourceById: Map<string, Record<string, unknown>>
  reviewStatus: string
  reviewLabel: string
}

const REVIEW_LABELS: Record<string, string> = {
  independent_reviewed: '独立审查通过',
  independent_review_failed: '独立审查未通过',
  self_review_only: '仅完成自审',
}

export function traceableReviewLabel(status: string) {
  return REVIEW_LABELS[status] ?? '审查状态未知'
}

export function traceableRefValues(record: Record<string, unknown>, field: TraceableRefField) {
  return Array.isArray(record[field]) ? record[field].map(toDisplayText).filter(Boolean) : []
}

export function traceableRefs(record: Record<string, unknown>): TraceableRefs {
  return TRACEABLE_REF_FIELDS.reduce((result, { field }) => {
    result[field] = traceableRefValues(record, field)
    return result
  }, {} as TraceableRefs)
}

function countRefs(refs: TraceableRefs) {
  return TRACEABLE_REF_FIELDS.reduce((sum, { field }) => sum + refs[field].length, 0)
}

/** derived 表示由材料规则推导；旧原型中的 inferred 也按相同含义处理。 */
function isDerived(point: Record<string, unknown>) {
  const basis = toDisplayText(point.basis)
  return basis === 'derived' || basis === 'inferred'
}

export function buildTraceablePointsModel(content: string, materialContent?: string): TraceablePointsModel | null {
  let artifactValue: unknown
  let materialValue: unknown
  try { artifactValue = JSON.parse(content) } catch { return null }
  try { materialValue = materialContent ? JSON.parse(materialContent) : undefined } catch { materialValue = undefined }

  const artifact = toRecord(artifactValue)
  if (!artifact || artifact.artifactType !== 'traceable_test_points') return null
  const material = toRecord(materialValue)

  const moduleGroups = new Map<string, { id: string; title: string; scenes: Map<string, TraceableScene> }>()
  const points: TraceablePoint[] = []
  const pointById = new Map<string, TraceablePoint>()
  const sceneById = new Map<string, TraceableScene>()

  toRecordArray(artifact.testPoints).forEach((point, index) => {
    const rawId = toDisplayText(point.id)
    const id = rawId || `point-${index}`
    const name = toDisplayText(point.name) || '未命名测试点'
    const moduleTitle = toDisplayText(point.module) || '未分组模块'
    const sceneTitle = toDisplayText(point.dimension) || '未分组场景'
    let moduleGroup = moduleGroups.get(moduleTitle)
    if (!moduleGroup) {
      moduleGroup = { id: `module-${moduleGroups.size}`, title: moduleTitle, scenes: new Map() }
      moduleGroups.set(moduleTitle, moduleGroup)
    }
    let scene = moduleGroup.scenes.get(sceneTitle)
    if (!scene) {
      scene = {
        id: `${moduleGroup.id}-scene-${moduleGroup.scenes.size}`,
        title: sceneTitle,
        moduleId: moduleGroup.id,
        points: [],
      }
      moduleGroup.scenes.set(sceneTitle, scene)
      sceneById.set(scene.id, scene)
    }
    const refs = traceableRefs(point)
    const entry: TraceablePoint = {
      id,
      rawId,
      name,
      module: moduleTitle,
      scene: sceneTitle,
      moduleId: moduleGroup.id,
      sceneId: scene.id,
      derived: isDerived(point),
      point,
      refs,
      refCount: countRefs(refs),
    }
    points.push(entry)
    pointById.set(entry.id, entry)
    scene.points.push(entry)
  })

  const modules: TraceableModule[] = [...moduleGroups.values()].map(group => {
    const scenes = [...group.scenes.values()]
    return {
      id: group.id,
      title: group.title,
      scenes,
      points: scenes.flatMap(scene => scene.points),
    }
  })

  const gaps: TraceableGap[] = toRecordArray(artifact.coverageGaps).map((gap, index) => {
    const id = toDisplayText(gap.id) || `gap-${index}`
    const objectIds = new Set(traceableRefValues(gap, 'testObjectIds'))
    const blockIds = new Set(traceableRefValues(gap, 'materialBlockIds'))
    const relatedPointIds = points.filter(({ point }) => {
      if (objectIds.size) return traceableRefValues(point, 'testObjectIds').some(value => objectIds.has(value))
      if (blockIds.size) return traceableRefValues(point, 'materialBlockIds').some(value => blockIds.has(value))
      return false
    }).map(point => point.id)
    return {
      id,
      description: toDisplayText(gap.description) || '未命名覆盖缺口',
      blockedCoverage: toDisplayText(gap.blockedCoverage) || '未记录阻塞范围',
      gap,
      refs: traceableRefs(gap),
      relatedPointIds,
      relatedSceneIds: [...new Set(relatedPointIds.map(pointId => pointById.get(pointId)?.sceneId).filter((sceneId): sceneId is string => Boolean(sceneId)))],
    }
  })

  const issues: TraceableIssue[] = toRecordArray(artifact.reviewIssues).map((issue, index) => {
    const targetType = toDisplayText(issue.targetType)
    const targetId = toDisplayText(issue.targetId)
    const point = targetType === 'testPoint' ? pointById.get(targetId) : undefined
    const gap = targetType === 'coverageGap' ? gaps.find(entry => entry.id === targetId) : undefined
    return {
      index,
      kind: toDisplayText(issue.kind),
      targetType,
      targetId,
      issue: toDisplayText(issue.issue) || '未记录问题描述',
      suggestion: toDisplayText(issue.suggestion),
      ...(point ? { pointId: point.id, sceneId: point.sceneId } : {}),
      ...(gap ? { gapId: gap.id } : {}),
    }
  })

  const blocks = toRecordArray(material?.materialBlocks)
  const sources = toRecordArray(material?.sources)
  const reviewStatus = toDisplayText(artifact.reviewStatus)

  return {
    artifact,
    modules,
    points,
    pointById,
    sceneById,
    gaps,
    issues,
    blocks,
    blockById: new Map(blocks.map(block => [toDisplayText(block.id), block])),
    sources,
    sourceById: new Map(sources.map(source => [toDisplayText(source.id), source])),
    reviewStatus,
    reviewLabel: traceableReviewLabel(reviewStatus),
  }
}
