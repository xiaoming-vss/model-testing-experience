import { expect, it } from 'vitest'
import { normalizeInstanceUrl, personalConnectionForInstance } from './personalConnections'
it('实例规范化保留路径并拒绝 URL 中的账号密码', () => {
  expect(normalizeInstanceUrl('HTTPS://GitLab.Example:443/root/')).toBe('https://gitlab.example/root')
  expect(normalizeInstanceUrl('https://user:secret@gitlab.example')).toBe('')
})
it('同实例只有一个有效本人连接才自动选择，多连接必须明确选择', () => {
  const rows = [
    { connectionId: 'a', baseUrl: 'https://a.example', status: 'active' },
    { connectionId: 'b', baseUrl: 'https://b.example', status: 'active' },
    { connectionId: 'a-old', baseUrl: 'https://a.example', status: 'auth_failed' },
  ]
  expect(personalConnectionForInstance(rows, 'https://a.example/')?.connectionId).toBe('a')
  expect(personalConnectionForInstance(rows, 'https://a.example', 'b')).toBeUndefined()
  expect(personalConnectionForInstance(rows, 'https://a.example', 'a-old')).toBeUndefined()
  rows.push({ connectionId: 'a2', baseUrl: 'https://a.example', status: 'active' })
  expect(personalConnectionForInstance(rows, 'https://a.example')).toBeUndefined()
  expect(personalConnectionForInstance(rows, 'https://a.example', 'a2')?.connectionId).toBe('a2')
  expect(personalConnectionForInstance(rows, '')).toBeUndefined()
})
