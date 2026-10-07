import { afterEach, expect, it, vi } from 'vitest'
import { fetchSignedFile } from './fileTransfer'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('renews expired storage tickets without sending platform credentials', async () => {
  const authorize = vi.fn().mockResolvedValueOnce({ url: 'https://s3.test/old' }).mockResolvedValueOnce({ url: 'https://s3.test/new' })
  const fetcher = vi.fn().mockResolvedValueOnce(new Response('<Error><Code>RequestExpired</Code></Error>', { status: 403 }))
    .mockResolvedValueOnce(new Response('verified file'))
  vi.stubGlobal('fetch', fetcher)
  expect(await (await fetchSignedFile(authorize)).response.text()).toBe('verified file')
  expect(authorize).toHaveBeenCalledTimes(2)
  expect(fetcher.mock.calls).toEqual([
    ['https://s3.test/old', { credentials: 'omit' }], ['https://s3.test/new', { credentials: 'omit' }],
  ])
})

it.each([403, 404])('does not retry permanent storage failure %s', async (status) => {
  const authorize = vi.fn().mockResolvedValue({ url: 'https://s3.test/file' })
  const fetcher = vi.fn().mockResolvedValue(new Response('<Error><Code>AccessDenied</Code></Error>', { status }))
  vi.stubGlobal('fetch', fetcher)
  await expect(fetchSignedFile(authorize)).rejects.toThrow(String(status))
  expect(authorize).toHaveBeenCalledTimes(1)
})

it('stops when renewed platform authorization is revoked', async () => {
  const authorize = vi.fn().mockRejectedValue(new Error('无权操作该资源'))
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<Code>RequestExpired</Code>', { status: 403 })))
  await expect(fetchSignedFile(authorize, { url: 'https://s3.test/old' })).rejects.toThrow('无权')
  expect(authorize).toHaveBeenCalledTimes(1)
})

it('bounds transient storage failures and does not expose signed URLs in errors', async () => {
  const authorize = vi.fn().mockResolvedValue({ url: 'https://s3.test/file?secret=hidden' })
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('secret=hidden')))
  await expect(fetchSignedFile(authorize)).rejects.toThrow('文件传输中断')
  expect(authorize).toHaveBeenCalledTimes(3)
})

it('retries interrupted response bodies with a fresh ticket', async () => {
  const broken = new Response('partial')
  vi.spyOn(broken, 'arrayBuffer').mockRejectedValue(new TypeError('connection reset'))
  const authorize = vi.fn().mockResolvedValue({ url: 'https://s3.test/file' })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(broken).mockResolvedValueOnce(new Response('complete')))
  expect(await (await fetchSignedFile(authorize)).response.text()).toBe('complete')
  expect(authorize).toHaveBeenCalledTimes(2)
})

it('renews after transient platform authorization failures but stops permanent denials', async () => {
  const authorize = vi.fn().mockRejectedValueOnce(Object.assign(new Error('temporarily unavailable'), { status: 503 }))
    .mockResolvedValueOnce({ url: 'https://s3.test/fresh' })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('complete')))
  expect(await (await fetchSignedFile(authorize)).response.text()).toBe('complete')
  expect(authorize).toHaveBeenCalledTimes(2)
  const denied = vi.fn().mockRejectedValue(Object.assign(new Error('无权访问'), { status: 403 }))
  await expect(fetchSignedFile(denied)).rejects.toThrow('无权')
  expect(denied).toHaveBeenCalledTimes(1)
})
