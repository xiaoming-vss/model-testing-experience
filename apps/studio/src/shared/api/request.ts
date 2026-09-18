import { useAuthStore } from '@/features/auth/store/auth.store'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export type ApiEnvelope<T> = {
  code: number
  message: string
  data: T
}

export type ListResponse<T> = T[] & {
  total: number
  items: T[]
}

export type BlobResponse = {
  blob: Blob
  filename?: string
}

export type RequestConfig = {
  normalizeListResponse?: boolean
}

export function listItems<T>(response: ListResponse<T> | { items: T[] } | T[] | undefined | null): T[] {
  if (!response) return []
  if (Array.isArray(response)) return (response as { items?: T[] }).items ?? response
  return response.items
}

export function listTotal<T>(response: ListResponse<T> | { total?: number; items: T[] } | T[] | undefined | null): number {
  if (!response) return 0
  if (Array.isArray(response)) return typeof (response as { total?: unknown }).total === 'number' ? (response as ListResponse<T>).total : response.length
  return typeof response.total === 'number' ? response.total : response.items.length
}

function normalizeResponseData<T>(data: T): T {
  if (
    data &&
    typeof data === 'object' &&
    !Array.isArray(data) &&
    'items' in data &&
    Array.isArray((data as { items?: unknown }).items)
  ) {
    const source = data as { items: unknown[]; total?: unknown }
    const items = source.items.slice() as unknown[] & { total: number; items: unknown[] }
    // Keep compatibility with callers that read either the normalized array or
    // its `items` field, but never point the field back at the array itself.
    // A self-reference makes React Query's structural-sharing comparison recurse
    // forever whenever a list is refetched after a successful mutation.
    items.items = items.slice()
    items.total = typeof source.total === 'number' ? source.total : source.items.length
    return items as T
  }

  return data
}

export class ApiError extends Error {
  code: number
  status: number
  data: unknown

  constructor(message: string, code: number, status: number, data: unknown = {}) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.data = data
  }
}

export async function request<T>(path: string, options: RequestInit = {}, config: RequestConfig = {}): Promise<T> {
  const token = useAuthStore.getState().token
  const headers = new Headers(options.headers)
  const isFormDataBody = typeof FormData !== 'undefined' && options.body instanceof FormData

  if (!headers.has('Content-Type') && options.body && !isFormDataBody) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  })
  const payload = (await response.json().catch(() => ({
    code: response.ok ? 0 : response.status,
    message: response.statusText,
    data: {},
  }))) as ApiEnvelope<T>

  if (!response.ok || payload.code !== 0) {
    if (payload.code === 1001 || response.status === 401) {
      useAuthStore.getState().logout()
    }
    if (response.status === 403 && !/^\/v1\/projects\/[^/]+$/.test(path)) {
      window.dispatchEvent(new Event('project-permission-denied'))
    }
    throw new ApiError(payload.message || '请求失败', payload.code, response.status, payload.data)
  }

  return config.normalizeListResponse === false ? payload.data : normalizeResponseData(payload.data)
}

function getFilenameFromContentDisposition(contentDisposition: string | null) {
  if (!contentDisposition) return undefined

  const encodedMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (encodedMatch?.[1]) {
    return decodeURIComponent(encodedMatch[1])
  }

  const plainMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  return plainMatch?.[1]
}

export async function requestBlob(path: string, options: RequestInit = {}): Promise<BlobResponse> {
  const token = useAuthStore.getState().token
  const headers = new Headers(options.headers)

  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => ({
      code: response.status,
      message: response.statusText,
      data: {},
    }))) as ApiEnvelope<unknown>

    if (payload.code === 1001 || response.status === 401) {
      useAuthStore.getState().logout()
    }
    if (response.status === 403 && !/^\/v1\/projects\/[^/]+$/.test(path)) {
      window.dispatchEvent(new Event('project-permission-denied'))
    }
    throw new ApiError(payload.message || '请求失败', payload.code, response.status, payload.data)
  }

  return {
    blob: await response.blob(),
    filename: getFilenameFromContentDisposition(response.headers.get('Content-Disposition')),
  }
}
