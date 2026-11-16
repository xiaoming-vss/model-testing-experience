import { describe, expect, it } from 'vitest'
import { hasRequirementDocument } from './requirementDocument'

describe('requirement source availability', () => {
  it('does not treat a historical filename and download route as an uploaded source', () => {
    expect(hasRequirementDocument({
      documentType: 'richtext', documentFilename: 'requirement.html',
      documentDownloadUrl: '/v1/requirements/requirement/download', documentFileId: '',
    })).toBe(false)
  })

  it('recognizes an attached source file', () => {
    expect(hasRequirementDocument({ documentType: 'richtext', documentFileId: 'file-1' })).toBe(true)
  })
})
