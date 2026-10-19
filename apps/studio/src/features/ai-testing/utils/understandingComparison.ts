import { resolveRequirementEvidence } from '@/domain/requirements/requirementEvidence'
import { parseRequirementArtifact, type RequirementSourceReference } from '@/domain/requirements/requirementArtifact'
import { readMaterialSources, type ExtractionArtifact, type MaterialBlock, type MaterialSource } from './materialComparison'

type NamedContent = Record<string, unknown> & { id: string; name: string }
export type UnderstandingModule = NamedContent & { operations: NamedContent[] }
export type UnderstandingArtifact = Record<string, unknown> & { title: string; sources: MaterialSource[]; functionalOverview: Record<string, unknown>; modules: UnderstandingModule[]; businessFlows: NamedContent[]; businessRules: NamedContent[]; questions: (Record<string, unknown> & { id: string; question: string })[] }
const record = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value)
function named(value: unknown): NamedContent[] {
  if (!Array.isArray(value) || value.some(v => !record(v) || typeof v.id !== 'string' || typeof v.name !== 'string')) throw new Error('需求理解内容不完整，请在原始 JSON 中修正后保存')
  return value as NamedContent[]
}
export function readUnderstandingArtifact(content: unknown): UnderstandingArtifact {
  const raw = parseRequirementArtifact(content)
  const parsed = raw ? resolveRequirementEvidence(raw, raw) as Record<string, unknown> : null
  if (!parsed || parsed.artifactType !== 'requirement_understanding' || !record(parsed.functionalOverview)) throw new Error('当前内容不是完整的需求理解 JSON，请在原始 JSON 中修正')
  if (!Array.isArray(parsed.questions) || parsed.questions.some(q => !record(q) || typeof q.id !== 'string' || typeof q.question !== 'string')) throw new Error('需求理解的问题结构不完整，请在原始 JSON 中修正')
  return { ...parsed, title: String(parsed.title || '需求理解记录'), sources: readMaterialSources((parsed.sources as Record<string, unknown>[]).map(source => ({ location: null, version: null, ...source }))), functionalOverview: parsed.functionalOverview,
    modules: named(parsed.modules).map(module => ({ ...module, operations: named(module.operations) })), businessFlows: named(parsed.businessFlows), businessRules: named(parsed.businessRules), questions: parsed.questions as UnderstandingArtifact['questions'] }
}

function visibleText(block: MaterialBlock): string[] {
  const result = [block.title, block.text, ...(block.items ?? [])].filter((v): v is string => typeof v === 'string')
  if (record(block.table) && Array.isArray(block.table.cells)) block.table.cells.forEach(c => { if (record(c) && typeof c.text === 'string') result.push(c.text) })
  if (record(block.image)) {
    if (Array.isArray(block.image.visibleTexts)) result.push(...block.image.visibleTexts.filter((v): v is string => typeof v === 'string'))
    const meaning = record(block.image.meaning) ? block.image.meaning.value : block.image.meaning
    if (typeof meaning === 'string') result.push(meaning)
  }
  return result
}

function paragraphRanges(locator: string) {
  return [...locator.matchAll(/(?:正文第|[、；，,]\s*第)(\d+)(?:\s*[-—–~至]\s*(\d+))?段/g)]
    .map(match => [Number(match[1]), Number(match[2] ?? match[1])] as const)
    .filter(([start, end]) => start > 0 && end >= start)
}

/** Resolve explicit citation/paragraph coordinates, a single source image, or a unique literal excerpt. */
export function findUnderstandingEvidence(extraction: ExtractionArtifact | undefined, reference: RequirementSourceReference | undefined) {
  const blockIds = new Set<string>(), factIds = new Set<string>()
  if (!extraction || !reference) return { blockIds, factIds }
  const sameCitation = (r: RequirementSourceReference) => r.sourceId === reference.sourceId && r.locator.trim() === reference.locator.trim()
  const blocks = extraction.contentBlocks.filter(b => b.sourceReferences.some(r => r.sourceId === reference.sourceId))
  blocks.filter(b => b.sourceReferences.some(sameCitation)).forEach(b => blockIds.add(b.id))
  extraction.extractedFacts.filter(f => f.fact.sourceReferences.some(sameCitation)).forEach(f => { factIds.add(f.id); f.relatedBlockIds.forEach(id => { if (blocks.some(b => b.id === id)) blockIds.add(id) }) })
  if (!blockIds.size && ['document', 'text'].includes(extraction.sources.find(s => s.id === reference.sourceId)?.type ?? '')) {
    const ranges = paragraphRanges(reference.locator)
    blocks.filter(b => b.sourceReferences.some(r => r.sourceId === reference.sourceId && paragraphRanges(r.locator).some(([start, end]) => ranges.some(([from, to]) => from <= end && start <= to))))
      .forEach(b => blockIds.add(b.id))
  }
  if (!blockIds.size && blocks.length === 1 && blocks[0].kind === 'image' && ['prototype', 'screenshot', 'design'].includes(extraction.sources.find(s => s.id === reference.sourceId)?.type ?? '')) blockIds.add(blocks[0].id)
  const excerpt = reference.excerpt?.trim()
  if (!blockIds.size && excerpt) {
    const matching = blocks.filter(b => visibleText(b).some(t => t.includes(excerpt)))
    if (matching.length === 1) blockIds.add(matching[0].id)
  }
  extraction.extractedFacts.filter(f => f.relatedBlockIds.some(id => blockIds.has(id))).forEach(f => factIds.add(f.id))
  return { blockIds, factIds }
}
