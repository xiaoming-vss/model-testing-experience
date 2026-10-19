import { toRecord } from '@/shared/utils/value'

type RecordValue = Record<string, unknown>

/** Resolve compact citations only for reading. Editors and exports retain the original JSON. */
export function resolveRequirementEvidence(artifact: RecordValue, value: unknown): unknown {
  if (artifact.artifactType !== 'requirement_understanding') return value
  if (artifact.schemaVersion !== '2.0') throw new Error('需求理解仅支持精简契约 2.0')
  if (!Array.isArray(artifact.evidence)) throw new Error('需求理解缺少集中证据表')
  const evidence = new Map<string, RecordValue>()
  const sources = new Set(Array.isArray(artifact.sources) ? artifact.sources.map(source => toRecord(source)?.id) : [])
  for (const raw of artifact.evidence) {
    const ref = toRecord(raw)
    if (!ref || typeof ref.id !== 'string' || evidence.has(ref.id) || typeof ref.sourceId !== 'string'
      || !sources.has(ref.sourceId) || typeof ref.locator !== 'string') throw new Error('需求理解证据表包含无效来源或重复标识')
    evidence.set(ref.id, { sourceId: ref.sourceId, locator: ref.locator, excerpt: ref.excerpt ?? null })
  }
  function visit(item: unknown): unknown {
    if (Array.isArray(item)) return item.map(visit)
    const object = toRecord(item)
    if (!object) return item
    const result = Object.fromEntries(Object.entries(object).map(([key, child]) => [key, key === 'evidence' ? child : visit(child)]))
    if ('evidenceIds' in object) {
      if (!Array.isArray(object.evidenceIds)) throw new Error('需求理解证据引用格式不正确')
      result.sourceReferences = object.evidenceIds.map(id => {
        const ref = evidence.get(String(id))
        if (!ref) throw new Error(`需求理解引用了不存在的证据：${String(id)}`)
        return ref
      })
      delete result.evidenceIds
    }
    if ('value' in object && !toRecord(object.value)) {
      result.confirmationStatus ??= 'confirmed'
      result.sourceReferences ??= []
      result.relatedQuestionIds ??= []
    }
    return result
  }
  return visit(value)
}
