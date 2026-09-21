import { describe, expect, it } from 'vitest'
import { isRunDeletable } from './runDeletion'

describe('运行记录可删除状态', () => {
  it.each(['pending', 'queued', 'claimed', 'running', 'PENDING'])('%s 仍在推进，不允许删除', status => {
    expect(isRunDeletable(status)).toBe(false)
  })

  it.each(['success', 'failed', 'error', 'canceled', 'waiting_review', undefined])(
    '%s 已不占 worker，允许删除',
    status => {
      expect(isRunDeletable(status)).toBe(true)
    },
  )
})
