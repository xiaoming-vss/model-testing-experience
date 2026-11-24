import { useMemo } from 'react'
import { Alert } from 'antd'
import { parseRequirementArtifact } from '../../../domain/requirements/requirementArtifact'
import { RequirementMaterialReader } from './RequirementMaterialReader'
import type { RequirementMaterial } from './requirementMaterial.types'

const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const references = (value: unknown) => Array.isArray(value) && value.every(item => typeof item === 'string')

function parse(content: unknown): RequirementMaterial {
  const value = parseRequirementArtifact(content)
  if (!value || value.artifactType !== 'readable_requirement_material' || !Array.isArray(value.sources) || !Array.isArray(value.materialBlocks) || !Array.isArray(value.functions) || !Array.isArray(value.questions)) throw new Error('材料整理结果不符合当前格式，请检查 JSON')
  if (typeof value.title !== 'string' || value.sources.some(s => !record(s) || typeof s.id !== 'string' || typeof s.name !== 'string' || !(s.location === null || typeof s.location === 'string')) || value.materialBlocks.some(b => !record(b) || typeof b.id !== 'string' || typeof b.sourceId !== 'string' || typeof b.kind !== 'string' || typeof b.locator !== 'string' || !record(b.content)) || value.functions.some(f => !record(f) || typeof f.id !== 'string' || typeof f.name !== 'string' || !Array.isArray(f.sections) || f.sections.some(s => !record(s) || typeof s.title !== 'string' || !Array.isArray(s.items) || s.items.some(i => !record(i) || typeof i.text !== 'string' || typeof i.status !== 'string' || !references(i.materialBlockIds)))) || value.questions.some(q => !record(q) || typeof q.id !== 'string' || typeof q.question !== 'string' || !references(q.materialBlockIds) || !references(q.functionIds))) throw new Error('材料整理内容不完整，请检查 JSON')
  return value as unknown as RequirementMaterial
}

export function ReadableRequirementMaterial({ content, editable, onChange }: { content: unknown; editable?: boolean; onChange?: (content: string) => void }) {
  const parsed = useMemo(() => {
    try { return { value: parse(content) } } catch (error) { return { error: error instanceof Error ? error.message : '无法读取材料整理结果' } }
  }, [content])
  if (!parsed.value) return <Alert type="error" showIcon title={parsed.error} />
  const material = parsed.value

  const updateItem = (featureId: string, sectionIndex: number, itemIndex: number, text: string) => {
    if (!onChange) return
    const next = structuredClone(material)
    const item = next.functions.find(feature => feature.id === featureId)?.sections[sectionIndex]?.items[itemIndex]
    if (item) item.text = text
    onChange(JSON.stringify(next, null, 2))
  }

  const updateQuestion = (id: string, question: string) => {
    if (!onChange) return
    const next = structuredClone(material)
    const item = next.questions.find(entry => entry.id === id)
    if (item) item.question = question
    onChange(JSON.stringify(next, null, 2))
  }

  return <RequirementMaterialReader
    material={material}
    editable={Boolean(editable && onChange)}
    onItemChange={updateItem}
    onQuestionChange={updateQuestion}
  />
}
