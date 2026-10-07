import { describe, expect, it } from 'vitest'
import { hasRequirementDocument, hasRequirementEnhancedText } from './requirementDocument'

describe('requirement source availability', () => {
  it('does not treat a historical filename and download route as an uploaded source', () => {
    expect(hasRequirementDocument({
      documentType: 'text', documentFilename: 'requirement.txt',
      documentDownloadUrl: '/v1/requirements/requirement/download', documentFileId: '',
    })).toBe(false)
  })

  it('recognizes an attached source file', () => {
    expect(hasRequirementDocument({ documentType: 'text', documentFileId: 'file-1' })).toBe(true)
  })

  it('keeps saved understanding text available independently of the original file', () => {
    expect(hasRequirementEnhancedText({ documentContent: '已保存的需求理解' })).toBe(true)
  })
})
