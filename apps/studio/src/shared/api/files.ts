import { request } from './request'

type UploadTicket = { fileId: string; upload: { url: string; fields: Record<string, string> } }

export async function storageCapabilities() {
  return request<{ enabled: boolean; maxBytes: number }>('/v1/files/capabilities')
}

function sendFile(ticket: UploadTicket, file: File, progress?: (percent: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', ticket.upload.url)
    xhr.timeout = 300_000
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) progress?.(Math.round(event.loaded * 100 / event.total))
    }
    xhr.onerror = () => reject(new Error('文件上传失败，请检查网络或存储 CORS 配置后重试'))
    xhr.ontimeout = () => reject(new Error('文件上传超时，请重试'))
    xhr.onload = () => xhr.status >= 200 && xhr.status < 300
      ? resolve() : reject(new Error('文件上传失败，请重试'))
    const form = new FormData()
    Object.entries(ticket.upload.fields).forEach(([key, value]) => form.append(key, value))
    form.append('file', file)
    xhr.send(form)
  })
}

export async function uploadStoredFile(projectId: string, file: File,
  purpose: 'requirement' | 'attachment' | 'ui_source_archive' | 'project_skill', progress?: (percent: number) => void) {
  const bytes = await file.arrayBuffer()
  const sha256 = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
    (byte) => byte.toString(16).padStart(2, '0')).join('')
  const ticket = await request<UploadTicket>('/v1/files/uploads', {
    method: 'POST', body: JSON.stringify({ projectId, filename: file.name, size: file.size, sha256, purpose }),
  })
  await sendFile(ticket, file, progress)
  await request(`/v1/files/${ticket.fileId}/complete`, { method: 'POST' })
  return ticket.fileId
}

export async function readSignedFileResponse(response: Response): Promise<Response> {
  if (!response.headers.get('Content-Type')?.includes('application/json')) throw new Error('未获取到 S3 下载授权，请重试')
  const ticket = await response.json() as { url: string }
  const stored = await fetch(ticket.url, { credentials: 'omit' })
  if (!stored.ok) throw new Error('文件下载失败，请重试')
  return stored
}
