import { beforeEach, describe, expect, it, vi } from 'vitest'
import { requirementsApi } from './requirements.api'
import { request } from '@/shared/api/request'
import { storageCapabilities, uploadStoredFile } from '@/shared/api/files'

vi.mock('@/shared/api/request', () => ({ request: vi.fn(), requestBlob: vi.fn() }))
vi.mock('@/shared/api/files', () => ({ storageCapabilities: vi.fn(), uploadStoredFile: vi.fn() }))

describe('S3-only requirement uploads', () => {
  beforeEach(() => vi.resetAllMocks())

  it('does not fall back to platform upload when storage is disabled', async () => {
    vi.mocked(storageCapabilities).mockResolvedValue({ enabled: false, maxBytes: 100 })
    const file = new File(['original'], 'requirement.txt')
    await expect(requirementsApi.createRequirement('s', { name: 'r', documentType: 'text', file }))
      .rejects.toThrow('S3')
    await expect(requirementsApi.replaceRequirementDocument('r', { documentType: 'text', file }))
      .rejects.toThrow('S3')
    expect(request).not.toHaveBeenCalled()
    expect(uploadStoredFile).not.toHaveBeenCalled()
  })

  it('uploads typed text as a file and submits only its file ID', async () => {
    vi.mocked(storageCapabilities).mockResolvedValue({ enabled: true, maxBytes: 100 })
    vi.mocked(request).mockResolvedValue({ projectId: 'p' })
    vi.mocked(uploadStoredFile).mockResolvedValue('file-1')
    await requirementsApi.createRequirement('s', { name: 'r', documentType: 'text', documentContent: 'source' })
    expect(uploadStoredFile).toHaveBeenCalledWith('p', expect.any(File), 'requirement', undefined)
    expect(request).toHaveBeenLastCalledWith('/v1/sprints/s/requirements', {
      method: 'POST', body: JSON.stringify({ name: 'r', documentType: 'text', documentFileId: 'file-1' }),
    })
  })

  it('does not submit a requirement when S3 upload fails', async () => {
    vi.mocked(storageCapabilities).mockResolvedValue({ enabled: true, maxBytes: 100 })
    vi.mocked(request).mockResolvedValue({ projectId: 'p' })
    vi.mocked(uploadStoredFile).mockRejectedValue(new Error('upload failed'))
    await expect(requirementsApi.createRequirement('s', { name: 'r', documentType: 'text', documentContent: 'source' }))
      .rejects.toThrow('upload failed')
    expect(request).toHaveBeenCalledTimes(1)
  })
})
