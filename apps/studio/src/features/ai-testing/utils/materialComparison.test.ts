import source from '@/domain/requirements/fixtures/document-extraction.example.json?raw'
import { expect, it } from 'vitest'
import { materialTarget, readExtractionArtifact, sourceForSelection } from './materialComparison'

it('多来源事实优先定位确实存在关联材料的来源', () => {
  const artifact = readExtractionArtifact(source)
  artifact.sources.push({ id: 'SRC02', name: '明确补充', type: 'user_confirmation', location: null, version: null })
  const fact = artifact.extractedFacts[0]
  fact.fact.sourceReferences.unshift({ sourceId: 'SRC02', locator: '用户补充', excerpt: null })
  expect(sourceForSelection(artifact, { kind: 'fact', id: fact.id })).toBe('SRC01')
  fact.relatedBlockIds = []
  expect(sourceForSelection(artifact, { kind: 'fact', id: fact.id })).toBe('SRC02')
})

it('问题同时关联材料块和提取事实时，合并可定位的材料而不伪造缺失引用', () => {
  const artifact = readExtractionArtifact(source)
  artifact.questions[0].affectedRefs = [{ kind: 'block', id: 'B02' }, { kind: 'extracted_fact', id: 'EF02' }, { kind: 'extracted_fact', id: 'missing' }]
  expect([...materialTarget(artifact, { kind: 'question', id: 'Q01' }).blockIds]).toEqual(['B02', 'B03'])
})
