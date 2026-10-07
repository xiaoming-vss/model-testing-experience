import extractionSource from '@/domain/requirements/fixtures/document-extraction.example.json?raw'
import { expect, it } from 'vitest'
import { readExtractionArtifact } from './materialComparison'
import { findUnderstandingEvidence } from './understandingComparison'

it('精确引用既有提取事实时，沿用其显式关联材料', () => {
  const artifact = readExtractionArtifact(extractionSource)
  artifact.extractedFacts[0].fact.sourceReferences[0].locator = '明确定位'
  const target = findUnderstandingEvidence(artifact, { sourceId: 'SRC01', locator: '明确定位', excerpt: null })
  expect(target.blockIds.has('B02')).toBe(true)
  expect(target.factIds.has('EF01')).toBe(true)
})

it('正文段落区间根据同一来源的真实段号对应，不把其他来源的同段号混入', () => {
  const artifact = readExtractionArtifact(extractionSource)
  artifact.sources[0].type = 'document'
  artifact.contentBlocks[0].sourceReferences[0].locator = '正文第43-47段（接入）'
  artifact.contentBlocks[1].sourceReferences[0].locator = '正文第48-50段（输出）'
  artifact.contentBlocks[2].sourceReferences[0] = { sourceId: 'SRC02', locator: '正文第48段', excerpt: null }
  expect([...findUnderstandingEvidence(artifact, { sourceId: 'SRC01', locator: '正文第44-49段（说明）', excerpt: null }).blockIds]).toEqual(['B01', 'B02'])
})

it('陌生定位仅用唯一的字面摘录回查，重复摘录不猜测对应块', () => {
  const artifact = readExtractionArtifact(extractionSource)
  const ref = { sourceId: 'SRC01', locator: '不同的材料描述', excerpt: '列表展示转换任务 ID' }
  expect([...findUnderstandingEvidence(artifact, ref).blockIds]).toEqual(['B02'])
  artifact.contentBlocks[0].text = artifact.contentBlocks[1].text
  expect(findUnderstandingEvidence(artifact, ref).blockIds.size).toBe(0)
  expect(findUnderstandingEvidence(artifact, { ...ref, excerpt: null }).blockIds.size).toBe(0)
})

it('来源本身是一张独立图片时，可定位整张图片但不虚构控件坐标', () => {
  const artifact = readExtractionArtifact(extractionSource)
  artifact.sources[0].type = 'prototype'
  artifact.contentBlocks = [{ ...artifact.contentBlocks[1], kind: 'image' }]
  expect([...findUnderstandingEvidence(artifact, { sourceId: 'SRC01', locator: '图片内的预览选项', excerpt: null }).blockIds]).toEqual(['B02'])
  expect(findUnderstandingEvidence(artifact, { sourceId: 'SRC99', locator: '图片内的预览选项', excerpt: null }).blockIds.size).toBe(0)
})
