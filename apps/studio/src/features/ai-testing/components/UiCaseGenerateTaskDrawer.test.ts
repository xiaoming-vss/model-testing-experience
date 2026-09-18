import { describe, expect, it } from 'vitest'
import { validateUiSourceArchive } from '../utils/uiSourceArchive'

describe('UI 源码包前端校验', () => {
  it('拒绝缺失文件、非 ZIP 和超过 100 MiB 的文件', () => {
    expect(validateUiSourceArchive()).toBe('请选择源码 ZIP')
    expect(validateUiSourceArchive(new File(['text'], 'source.txt'))).toBe('只支持 .zip 源码包')
    const oversized = new File(['zip'], 'source.zip')
    Object.defineProperty(oversized, 'size', { value: 100 * 1024 * 1024 + 1 })
    expect(validateUiSourceArchive(oversized)).toBe('源码包不能超过 100 MiB')
  })

  it('接受不超过限制的 ZIP 文件', () => {
    expect(validateUiSourceArchive(new File(['zip'], 'source.ZIP'))).toBeUndefined()
  })
})
