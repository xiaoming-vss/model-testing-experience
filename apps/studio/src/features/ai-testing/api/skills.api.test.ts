import { beforeEach, describe, expect, it, vi } from 'vitest'
import { skillFolder, skillsApi } from './skills.api'
import { request } from '@/shared/api/request'
import { storageCapabilities, uploadStoredFile } from '@/shared/api/files'

vi.mock('@/shared/api/request', () => ({ request: vi.fn(), requestBlob: vi.fn() }))
vi.mock('@/shared/api/files', () => ({ storageCapabilities: vi.fn(), uploadStoredFile: vi.fn() }))

function file(path: string) {
  const result = new File(['data'], path.split('/').at(-1)!)
  Object.defineProperty(result, 'webkitRelativePath', { value: path })
  return result
}

beforeEach(() => vi.resetAllMocks())
describe('skill folders', () => {
  it('rejects a loose file, missing SKILL.md and multiple roots', () => {
    expect(() => skillFolder([new File(['x'], 'package.zip')])).toThrow()
    expect(() => skillFolder([file('test/a.md')])).toThrow('SKILL.md')
    expect(() => skillFolder([file('a/SKILL.md'), file('b/a.py')])).toThrow('一个')
  })
  it('uploads all files and publishes relative paths only after completion', async () => {
    vi.mocked(storageCapabilities).mockResolvedValue({ enabled: true, maxBytes: 100 })
    vi.mocked(uploadStoredFile).mockResolvedValueOnce('one').mockResolvedValueOnce('two')
    await skillsApi.uploadAiSkill('p', { files: [file('test/SKILL.md'), file('test/scripts/a.py')] })
    expect(request).toHaveBeenCalledWith('/v1/projects/p/skills', {
      method: 'POST', body: JSON.stringify({ name: 'test', files: [
        { path: 'SKILL.md', fileId: 'one' }, { path: 'scripts/a.py', fileId: 'two' },
      ] }),
    })
  })
  it('does not publish a partial folder when a file upload fails', async () => {
    vi.mocked(storageCapabilities).mockResolvedValue({ enabled: true, maxBytes: 100 })
    vi.mocked(uploadStoredFile).mockResolvedValueOnce('one').mockRejectedValueOnce(new Error('failed'))
    await expect(skillsApi.uploadAiSkill('p', { files: [file('test/SKILL.md'), file('test/a.py')] })).rejects.toThrow('failed')
    expect(request).not.toHaveBeenCalled()
  })
})
