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
    const file = new File(['original'], 'requirement.html')
    await expect(requirementsApi.createRequirement('s', { name: 'r', documentType: 'richtext', file }))
      .rejects.toThrow('S3')
    await expect(requirementsApi.replaceRequirementDocument('r', { documentType: 'richtext', file }))
      .rejects.toThrow('S3')
    expect(request).not.toHaveBeenCalled()
    expect(uploadStoredFile).not.toHaveBeenCalled()
  })

  it('requires a Word file instead of synthesizing a plain-text file', async () => {
    vi.mocked(storageCapabilities).mockResolvedValue({ enabled: true, maxBytes: 100 })
    await expect(requirementsApi.createRequirement('s', { name: 'r', documentType: 'word' }))
      .rejects.toThrow('请上传需求文件或填写需求内容')
    expect(uploadStoredFile).not.toHaveBeenCalled()
  })

  it('does not submit a requirement when S3 upload fails', async () => {
    vi.mocked(storageCapabilities).mockResolvedValue({ enabled: true, maxBytes: 100 })
    vi.mocked(request).mockResolvedValue({ projectId: 'p' })
    vi.mocked(uploadStoredFile).mockRejectedValue(new Error('upload failed'))
    await expect(requirementsApi.createRequirement('s', { name: 'r', documentType: 'richtext', documentContent: 'source' }))
      .rejects.toThrow('upload failed')
    expect(request).toHaveBeenCalledTimes(1)
  })
})

it('creates rich text as an HTML source file', async () => {
  vi.mocked(storageCapabilities).mockResolvedValue({ enabled: true, maxBytes: 1000 })
  vi.mocked(request).mockResolvedValue({ projectId: 'p' })
  vi.mocked(uploadStoredFile).mockResolvedValue('html-1')
  await requirementsApi.createRequirement('s', { name: '图文', documentType: 'richtext', documentContent: '<h2>标题</h2>' })
  const file = vi.mocked(uploadStoredFile).mock.calls.at(-1)![1]
  expect(file.name).toBe('requirement.html')
  expect(file.type).toBe('text/html')
  expect(request).toHaveBeenLastCalledWith('/v1/sprints/s/requirements', {
    method: 'POST', body: JSON.stringify({ name: '图文', documentType: 'richtext', documentFileId: 'html-1' }),
  })
})

it('updates source and name together only after HTML upload completes', async () => {
  vi.resetAllMocks()
  vi.mocked(storageCapabilities).mockResolvedValue({ enabled: true, maxBytes: 1000 })
  vi.mocked(request).mockResolvedValueOnce({ name: 'old', sprintId: 's' }).mockResolvedValueOnce({ projectId: 'p' })
  vi.mocked(uploadStoredFile).mockResolvedValue('html-2')
  await requirementsApi.replaceRequirementDocument('r', { name: 'new', documentType: 'richtext', documentContent: '<p>修改正文</p>' })
  expect(request).toHaveBeenLastCalledWith('/v1/requirements/r', {
    method: 'PATCH', body: JSON.stringify({ documentFileId: 'html-2', name: 'new', documentType: 'richtext' }),
  })
  expect(vi.mocked(request).mock.calls.at(-1)![1]?.body).not.toContain('documentContent')
})

it('preserves the existing requirement when replacement upload fails', async () => {
  vi.resetAllMocks()
  vi.mocked(storageCapabilities).mockResolvedValue({ enabled: true, maxBytes: 1000 })
  vi.mocked(request).mockResolvedValueOnce({ name: 'old', sprintId: 's' }).mockResolvedValueOnce({ projectId: 'p' })
  vi.mocked(uploadStoredFile).mockRejectedValue(new Error('S3 unavailable'))
  await expect(requirementsApi.replaceRequirementDocument('r', { documentType: 'richtext', documentContent: '<p>new</p>' })).rejects.toThrow('S3 unavailable')
  expect(vi.mocked(request).mock.calls.every(([, options]) => !options?.method)).toBe(true)
})
