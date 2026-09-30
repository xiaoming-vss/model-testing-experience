import { render, screen, cleanup } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { BugActivityFeed } from './BugActivityFeed'
import { formatTime } from '@/utils/format'
import type { BugActivity } from '../types'
afterEach(cleanup)
const activity: BugActivity = { activityId: '1', bugId: '1', kind: 'status_change', actorUserId: 'u1',
  action: 'reject', fromStatus: 'processing', toStatus: 'rejected', content: '', detail: { rejectReason: 'deferred' } }
it('没有补充说明时仍展示拒绝原因及前后状态', () => {
  render(<BugActivityFeed items={[activity]} resolveUserName={() => '小明'} />)
  expect(screen.getByText('拒绝原因：遗留')).toBeInTheDocument()
  expect(screen.getByText('处理中 → 已拒绝')).toBeInTheDocument()
})
it('信息修改仅显示一次，转派显示前后责任人', () => {
  render(<BugActivityFeed items={[
    { ...activity, kind: 'edit', action: 'edit', detail: { changes: [{ field: 'priority', from: 'low', to: 'high' }] } },
    { ...activity, activityId: '2', kind: 'transfer', action: 'transfer', detail: { fromUserId: 'u1', toUserId: 'u2' } },
  ]} resolveUserName={(id) => id === 'u1' ? '小明' : '小李'} />)
  expect(screen.getAllByText('优先级：低 → 高')).toHaveLength(1)
  expect(screen.getByText('将责任人从 小明 转派给 小李')).toBeInTheDocument()
})

it('处理记录和评论展示接口返回的创建时间，并兼容旧字段', () => {
  const createdAt = '2026-09-28T06:01:17Z'
  const legacyTime = '2026-09-28T06:03:20Z'
  render(<BugActivityFeed items={[
    { ...activity, createdAt },
    { ...activity, activityId: 'comment', kind: 'comment', action: 'comment', content: '已复现', detail: {}, created_at: legacyTime },
  ]} resolveUserName={() => '小明'} />)
  expect(screen.getByText(formatTime(createdAt))).toBeInTheDocument()
  expect(screen.getByText(formatTime(legacyTime))).toBeInTheDocument()
})
