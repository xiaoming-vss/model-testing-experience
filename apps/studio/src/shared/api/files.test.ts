import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readSignedFileResponse, uploadStoredFile } from './files'

const { request } = vi.hoisted(() => ({ request: vi.fn() }))
vi.mock('./request', () => ({ request }))

class FakeXHR {
  static body: FormData
  static target: string
  static status = 204
  static statuses: number[] = []
  static responseText = ''
  status = FakeXHR.statuses.shift() ?? FakeXHR.status
  responseText = FakeXHR.responseText
  timeout = 0
  upload = { onprogress: undefined as ((event: unknown) => void) | undefined }
  onload?: () => void
  open(method: string, url: string) { expect(method).toBe('POST'); FakeXHR.target = url }
  send(body: FormData) { FakeXHR.body = body; this.onload?.() }
}

beforeEach(() => {
  request.mockReset()
  FakeXHR.status = 204
  FakeXHR.statuses = []
  FakeXHR.responseText = ''
  vi.stubGlobal('XMLHttpRequest', FakeXHR)
  vi.stubGlobal('crypto', { subtle: { digest: vi.fn().mockResolvedValue(new Uint8Array(32).buffer) } })
})

describe('direct storage upload', () => {
  it('posts signed fields directly and completes before exposing file ID', async () => {
    request.mockResolvedValueOnce({ fileId: 'f', upload: { url: 'https://s3.test', fields: { key: 'staging', policy: 'signed' } } })
      .mockResolvedValueOnce({ status: 'ready' })
    const file = new File(['hello'], 'hello.txt')
    Object.defineProperty(file, 'arrayBuffer', { value: async () => new ArrayBuffer(5) })
    expect(await uploadStoredFile('p', file, 'requirement')).toBe('f')
    expect(FakeXHR.target).toBe('https://s3.test')
    expect(FakeXHR.body.get('key')).toBe('staging')
    expect(FakeXHR.body.get('file')).toBeInstanceOf(File)
    expect(request).toHaveBeenLastCalledWith('/v1/files/f/complete', { method: 'POST' })
  })

  it('does not finalize a failed S3 upload', async () => {
    FakeXHR.status = 403
    request.mockResolvedValueOnce({ fileId: 'f', upload: { url: 'https://s3.test', fields: {} } })
    const file = new File(['hello'], 'hello.txt')
    Object.defineProperty(file, 'arrayBuffer', { value: async () => new ArrayBuffer(5) })
    await expect(uploadStoredFile('p', file, 'requirement')).rejects.toThrow('403')
    expect(request).toHaveBeenCalledTimes(1)
  })
})


it('rejects a legacy binary response instead of displaying it as a requirement file', async () => {
  await expect(readSignedFileResponse(new Response('old file', {
    headers: { 'Content-Type': 'application/octet-stream' },
  }))).rejects.toThrow('S3')
})


it('renews an expired upload and finalizes only the successfully uploaded file', async () => {
  FakeXHR.statuses = [403, 204]
  FakeXHR.responseText = '<Error><Code>AccessDenied</Code><Message>Request has expired</Message></Error>'
  request.mockResolvedValueOnce({ fileId: 'expired', upload: { url: 'https://s3.test/old', fields: {} } })
    .mockResolvedValueOnce({ fileId: 'fresh', upload: { url: 'https://s3.test/new', fields: {} } })
    .mockResolvedValueOnce({ status: 'ready' })
  const file = new File(['hello'], 'hello.txt')
  Object.defineProperty(file, 'arrayBuffer', { value: async () => new ArrayBuffer(5) })
  expect(await uploadStoredFile('p', file, 'requirement')).toBe('fresh')
  expect(request.mock.calls.map(([path]) => path)).toEqual(['/v1/files/uploads', '/v1/files/uploads', '/v1/files/fresh/complete'])
})

it('stops expired uploads after three attempts without exposing a file ID', async () => {
  FakeXHR.status = 403
  FakeXHR.responseText = '<Error><Code>RequestExpired</Code></Error>'
  request.mockResolvedValue({ fileId: 'expired', upload: { url: 'https://s3.test', fields: {} } })
  const file = new File(['hello'], 'hello.txt')
  Object.defineProperty(file, 'arrayBuffer', { value: async () => new ArrayBuffer(5) })
  await expect(uploadStoredFile('p', file, 'requirement')).rejects.toThrow('403')
  expect(request).toHaveBeenCalledTimes(3)
})

it('recovers from a lost completion response with a fresh upload and bounds platform retries', async () => {
  request.mockResolvedValueOnce({ fileId: 'uncertain', upload: { url: 'https://s3.test/a', fields: {} } })
    .mockRejectedValueOnce(new TypeError('connection reset'))
    .mockResolvedValueOnce({ fileId: 'fresh', upload: { url: 'https://s3.test/b', fields: {} } })
    .mockResolvedValueOnce({ status: 'ready' })
  const file = new File(['hello'], 'hello.txt')
  Object.defineProperty(file, 'arrayBuffer', { value: async () => new ArrayBuffer(5) })
  expect(await uploadStoredFile('p', file, 'requirement')).toBe('fresh')
  expect(request.mock.calls.map(([path]) => path)).toEqual(['/v1/files/uploads', '/v1/files/uncertain/complete', '/v1/files/uploads', '/v1/files/fresh/complete'])
})
