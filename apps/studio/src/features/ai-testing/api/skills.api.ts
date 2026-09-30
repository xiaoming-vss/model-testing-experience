import { storageCapabilities, uploadStoredFile } from '@/shared/api/files'
import { request, requestBlob, type ListResponse } from '@/shared/api/request'
import type { AiSkillLibraryItem, UploadAiSkillPayload } from '../types'

export function skillFolder(files: File[]) {
  if (!files.length || files.length > 2000) throw new Error('请选择包含 SKILL.md 的技能文件夹（最多 2000 个文件）')
  const name = files[0].webkitRelativePath.split('/')[0]
  if (!/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$/.test(name)) throw new Error('技能文件夹名仅支持字母、数字、点、横线和下划线，且以字母或数字开头')
  const paths = new Set<string>()
  const entries = files.map((file) => {
    if (!file.webkitRelativePath.startsWith(`${name}/`)) throw new Error('一次只能上传一个技能文件夹')
    const path = file.webkitRelativePath.slice(name.length + 1)
    if (path.split('/').some((part) => !part || part === '.' || part === '..') || paths.has(path.toLowerCase())) throw new Error('技能文件路径重复或不合法')
    paths.add(path.toLowerCase())
    return { path, file }
  })
  if (!entries.some(({ path }) => path === 'SKILL.md')) throw new Error('技能根目录必须包含 SKILL.md')
  return { name, entries }
}

export const skillsApi = {
  getAiSkillLibraryItems: (projectId: string) => request<ListResponse<AiSkillLibraryItem>>(`/v1/projects/${projectId}/skills`),
  uploadAiSkill: async (projectId: string, { files }: UploadAiSkillPayload) => {
    const { name, entries } = skillFolder(files)
    const capabilities = await storageCapabilities()
    if (!capabilities.enabled) throw new Error('S3 文件存储未启用，请联系管理员配置')
    if (files.reduce((sum, file) => sum + file.size, 0) > capabilities.maxBytes) throw new Error('技能文件夹超过大小限制')
    const manifest = []
    for (const { path, file } of entries) {
      manifest.push({ path, fileId: await uploadStoredFile(projectId, file, 'project_skill') })
    }
    return request<AiSkillLibraryItem>(`/v1/projects/${projectId}/skills`, {
      method: 'POST', body: JSON.stringify({ name, files: manifest }),
    })
  },
  deleteAiSkill: (projectId: string, skillSpaceId: string) => request<Record<string, never>>(`/v1/projects/${projectId}/skills/${skillSpaceId}`, { method: 'DELETE' }),
  downloadAiSkill: (projectId: string, skillSpaceId: string) => requestBlob(`/v1/projects/${projectId}/skills/${skillSpaceId}/download`),
}
