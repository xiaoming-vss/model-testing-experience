import { Alert } from 'antd'
import { ReadableRequirementMaterial } from './ReadableRequirementMaterial'

export function RequirementMaterialComparison({ content, editable = false, onChange }: { content: unknown; editable?: boolean; onChange?: (content: string) => void }) {
  let value = content
  if (typeof value === 'string') {
    try { value = JSON.parse(value) } catch { /* The new viewer reports malformed JSON. */ }
  }
  if (value && typeof value === 'object' && !Array.isArray(value) && 'artifactType' in value && (value.artifactType === 'document_extraction' || (value.artifactType === 'readable_requirement_material' && 'schemaVersion' in value && value.schemaVersion !== '0.2'))) {
    return <div role="region" aria-label="材料整理结果"><Alert type="warning" showIcon title="这是旧版材料产物" description="该版本使用旧格式，无法在新版页面展示。请在右侧选择待审核的新版本，或重新生成材料整理结果；原始 JSON 仍可在 JSON 模式查看。" /></div>
  }
  return <ReadableRequirementMaterial content={content} editable={editable} onChange={onChange} />
}
