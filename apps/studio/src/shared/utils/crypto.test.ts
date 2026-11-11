import { afterEach, describe, expect, it, vi } from 'vitest'
import { randomId, sha256Hex, sha256HexFallback } from './crypto'

const bytesOf = (text: string) => new TextEncoder().encode(text).buffer

const HEX = {
  empty: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  abc: 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
  paddingBoundary: '248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1',
  long: '41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3',
}

afterEach(() => vi.unstubAllGlobals())

describe('sha256HexFallback', () => {
  it.each([
    ['', HEX.empty],
    ['abc', HEX.abc],
    ['abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq', HEX.paddingBoundary],
    ['a'.repeat(1000), HEX.long],
  ])('hashes %j like Web Crypto', (input, expected) => {
    expect(sha256HexFallback(bytesOf(input))).toBe(expected)
  })

  it('handles non-ASCII bytes', () => {
    expect(sha256HexFallback(new Uint8Array([0, 1, 2, 254, 255]).buffer))
      .toBe('103597c5abb6113da596c18e9d1da69364eafe00a2bfaa8b12e53c44bd6b0429')
  })
})

describe('sha256Hex', () => {
  it('uses crypto.subtle when the browser provides it', async () => {
    const digest = vi.fn().mockResolvedValue(new Uint8Array(32).fill(0xab).buffer)
    vi.stubGlobal('crypto', { subtle: { digest } })
    expect(await sha256Hex(bytesOf('abc'))).toBe('ab'.repeat(32))
    expect(digest).toHaveBeenCalledTimes(1)
    expect(digest.mock.calls[0][0]).toBe('SHA-256')
  })

  it('falls back to the pure JS digest on insecure origins', async () => {
    vi.stubGlobal('crypto', {})
    expect(await sha256Hex(bytesOf('abc'))).toBe(HEX.abc)
  })
})

describe('randomId', () => {
  it('uses crypto.randomUUID when available', () => {
    vi.stubGlobal('crypto', { randomUUID: () => '00000000-0000-4000-8000-000000000000' })
    expect(randomId()).toBe('00000000-0000-4000-8000-000000000000')
  })

  it('builds a v4 UUID without crypto.randomUUID', () => {
    vi.stubGlobal('crypto', { getRandomValues: (bytes: Uint8Array) => bytes.fill(0xff) })
    const id = randomId()
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    expect(id).toBe('ffffffff-ffff-4fff-bfff-ffffffffffff')
  })
})
