import { beforeEach, describe, expect, it, vi } from 'vitest'
import { aiTestingApi } from './aiTesting.api'
import { request } from '@/shared/api/request'
import { storageCapabilities, uploadStoredFile } from '@/shared/api/files'

vi.mock('@/shared/api/request', () => ({ request: vi.fn(), requestBlob: vi.fn() }))
vi.mock('@/shared/api/files', () => ({ storageCapabilities: vi.fn(), uploadStoredFile: vi.fn() }))

beforeEach(() => vi.resetAllMocks())

describe('UI source archive S3 storage', () => {
  it('uploads directly before associating the file ID with the task', async () => {
    vi.mocked(storageCapabilities).mockResolvedValue({ enabled: true, maxBytes: 100 })
    vi.mocked(request).mockResolvedValue({ projectId: 'p' })
    vi.mocked(uploadStoredFile).mockResolvedValue('f')
    const file = new File(['zip'], 'source.zip')
    await aiTestingApi.uploadUiCaseGenerateTaskSourceArchive('t', file)
    expect(uploadStoredFile).toHaveBeenCalledWith('p', file, 'ui_source_archive')
    expect(request).toHaveBeenLastCalledWith('/v1/ui-case-generate-tasks/t/source-archive', {
      method: 'PUT', body: JSON.stringify({ fileId: 'f' }),
    })
  })

  it('does not fall back to multipart when S3 is disabled', async () => {
    vi.mocked(storageCapabilities).mockResolvedValue({ enabled: false, maxBytes: 100 })
    await expect(aiTestingApi.uploadUiCaseGenerateTaskSourceArchive('t', new File(['zip'], 'source.zip')))
      .rejects.toThrow('S3')
    expect(request).not.toHaveBeenCalled()
  })

  it('keeps the task reference unchanged on upload failure', async () => {
    vi.mocked(storageCapabilities).mockResolvedValue({ enabled: true, maxBytes: 100 })
    vi.mocked(request).mockResolvedValue({ projectId: 'p' })
    vi.mocked(uploadStoredFile).mockRejectedValue(new Error('invalid ZIP'))
    await expect(aiTestingApi.uploadUiCaseGenerateTaskSourceArchive('t', new File(['zip'], 'source.zip')))
      .rejects.toThrow('invalid ZIP')
    expect(request).toHaveBeenCalledTimes(1)
  })
})
