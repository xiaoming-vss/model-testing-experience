import { parseRequirementArtifact } from '@/domain/requirements/requirementArtifact'
import type { RequirementSourceReference } from '@/domain/requirements/requirementArtifact'

type SourceReference = RequirementSourceReference
export type MaterialSource = { id: string; name: string; type: string; location: string | null; version: string | null }
export type MaterialBlock = { id: string; parentId: string | null; kind: string; title: string | null; text: string | null; items: string[]; table: unknown; image: unknown; parseStatus: string; sourceReferences: SourceReference[]; relatedQuestionIds: string[] }
export type ExtractedFact = { id: string; category: string; fact: { value: unknown; confirmationStatus: string; sourceReferences: SourceReference[]; relatedQuestionIds: string[] }; relatedBlockIds: string[] }
export type MaterialQuestion = { id: string; question: string; status: string; affectedRefs: { kind: string; id: string }[]; sourceReferences: SourceReference[]; answer: unknown }
export type ExtractionArtifact = Record<string, unknown> & { documentTitle: string; sources: MaterialSource[]; contentBlocks: MaterialBlock[]; extractedFacts: ExtractedFact[]; questions: MaterialQuestion[] }
export type MaterialSelection = { kind: 'fact' | 'question'; id: string }
const record = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value)
const strings = (value: unknown) => Array.isArray(value) && value.every(item => typeof item === 'string')
const nullableText = (value: unknown) => value === null || typeof value === 'string'
const scalar = (value: unknown) => ['string', 'number', 'boolean'].includes(typeof value)
const factValue = (value: unknown) => value === null || scalar(value) || Array.isArray(value) && value.every(scalar)
const references = (value: unknown) => Array.isArray(value) && value.every(ref => record(ref) && typeof ref.sourceId === 'string' && typeof ref.locator === 'string' && nullableText(ref.excerpt))
function array<T>(value: unknown, valid: (item: Record<string, unknown>) => boolean): T[] {
  if (!Array.isArray(value) || value.some(item => !record(item) || !valid(item))) throw new Error('材料提取内容不完整，请在原始 JSON 中修正后保存')
  return value as T[]
}

export function readMaterialSources(value: unknown): MaterialSource[] {
  return array(value, s => typeof s.id === 'string' && typeof s.name === 'string' && typeof s.type === 'string' && nullableText(s.version) && nullableText(s.location))
}

export function readExtractionArtifact(content: unknown): ExtractionArtifact {
  const parsed = parseRequirementArtifact(content)
  if (!parsed || parsed.artifactType !== 'document_extraction') throw new Error('当前内容不是有效的材料提取 JSON')
  return {
    ...parsed,
    documentTitle: String(parsed.documentTitle || '需求材料'),
    sources: readMaterialSources(parsed.sources),
    contentBlocks: array(parsed.contentBlocks, b => typeof b.id === 'string' && ['section', 'paragraph', 'list', 'table', 'image'].includes(String(b.kind)) && nullableText(b.title) && nullableText(b.text) && strings(b.items) && references(b.sourceReferences) && strings(b.relatedQuestionIds)),
    extractedFacts: array(parsed.extractedFacts, f => typeof f.id === 'string' && typeof f.category === 'string' && record(f.fact) && factValue(f.fact.value) && typeof f.fact.confirmationStatus === 'string' && references(f.fact.sourceReferences) && strings(f.fact.relatedQuestionIds) && strings(f.relatedBlockIds)),
    questions: array(parsed.questions, q => typeof q.id === 'string' && typeof q.question === 'string' && references(q.sourceReferences) && Array.isArray(q.affectedRefs) && q.affectedRefs.every(r => record(r) && typeof r.id === 'string' && typeof r.kind === 'string')),
  }
}

export function materialTarget(artifact: ExtractionArtifact, selection: MaterialSelection | undefined) {
  if (selection?.kind === 'question') {
    const question = artifact.questions.find(q => q.id === selection.id)
    const blockIds = question?.affectedRefs.flatMap(ref => ref.kind === 'block' ? [ref.id]
      : ref.kind === 'extracted_fact' ? artifact.extractedFacts.find(f => f.id === ref.id)?.relatedBlockIds ?? [] : []) ?? []
    return { references: question?.sourceReferences ?? [], blockIds: new Set(blockIds) }
  }
  const fact = artifact.extractedFacts.find(f => f.id === selection?.id)
  return { references: fact?.fact.sourceReferences ?? [], blockIds: new Set(fact?.relatedBlockIds ?? []) }
}

/** Prefer a cited source that actually contains a related material block. Confirmations can have no blocks. */
export function sourceForSelection(artifact: ExtractionArtifact, selection: MaterialSelection) {
  const target = materialTarget(artifact, selection)
  const matching = target.references.find(ref => artifact.contentBlocks.some(b => target.blockIds.has(b.id) && b.sourceReferences.some(r => r.sourceId === ref.sourceId)))
  return matching?.sourceId ?? target.references.find(ref => artifact.sources.some(s => s.id === ref.sourceId))?.sourceId ?? artifact.sources[0]?.id
}

export function extractedFactText(artifact: ExtractionArtifact, fact: ExtractedFact) {
  const value = fact.fact.value
  if (value == null) return fact.fact.confirmationStatus === 'not_applicable' ? '不适用'
    : artifact.questions.find(q => q.status !== 'resolved' && fact.fact.relatedQuestionIds.includes(q.id))?.question ?? '未明确'
  return Array.isArray(value) ? value.map(String).join('、') : String(value)
}
