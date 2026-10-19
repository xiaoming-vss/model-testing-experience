import { expect, it } from 'vitest'
import compact from './fixtures/requirement-understanding.example.json'
import { parseRequirementArtifact } from './requirementArtifact'
import { resolveRequirementEvidence } from './requirementEvidence'
import { readUnderstandingArtifact } from '@/features/ai-testing/utils/understandingComparison'

it('reads compact evidence without mutating stored content', () => {
  const original = JSON.stringify(compact)
  const parsed = parseRequirementArtifact(compact)!
  const view = readUnderstandingArtifact(parsed)
  expect(view.modules[0].purpose).toMatchObject({ value: compact.modules[0].purpose.value, confirmationStatus: 'example' })
  expect(view.businessRules[0].expectedBehavior).toEqual(compact.businessRules[0].expectedBehavior.map(fact => resolveRequirementEvidence(compact, fact)))
  expect(JSON.stringify(compact)).toBe(original)
})

it('preserves narrative prose and explicit uncertainty and resolves confirmed defaults', () => {
  const artifact = structuredClone(compact)
  const rule = artifact.businessRules[0].expectedBehavior[0] as Record<string, unknown>
  delete rule.confirmationStatus
  const view = resolveRequirementEvidence(artifact, rule) as Record<string, unknown>
  expect(view.confirmationStatus).toBe('confirmed')
  const source = compact.evidence.find(item => item.id === compact.businessRules[0].expectedBehavior[0].evidenceIds[0])!
  expect(view.sourceReferences).toEqual([{ sourceId: source.sourceId, locator: source.locator, excerpt: null }])
  expect(resolveRequirementEvidence(artifact, '普通概述')).toBe('普通概述')
  expect(resolveRequirementEvidence(artifact, { value: null, confirmationStatus: 'unconfirmed' })).toMatchObject({ value: null, confirmationStatus: 'unconfirmed' })
})

it('rejects old versions and broken evidence', () => {
  expect(() => resolveRequirementEvidence(compact, { value: '事实', evidenceIds: ['missing'] })).toThrow('不存在的证据')
  expect(() => parseRequirementArtifact({ ...compact, schemaVersion: '1.0' })).toThrow('不受支持')
  expect(() => parseRequirementArtifact({ ...compact, schemaVersion: '3.0' })).toThrow('不受支持')
  expect(() => resolveRequirementEvidence({ ...compact, evidence: [...compact.evidence, compact.evidence[0]] }, undefined)).toThrow('重复标识')
})

it('does not replace omitted optional fields with the entire artifact', () => {
  expect(resolveRequirementEvidence(compact, undefined)).toBeUndefined()
  expect(resolveRequirementEvidence(compact, null)).toBeNull()
})
