import { expect, it } from 'vitest'
import { buildVisualGroups, diffArtifact, diffStats } from './chainArtifact'

it('可视化按模块聚合用例，并保留步骤摘要', () => {
  const groups = buildVisualGroups(JSON.stringify({
    cases: [
      { module: '登录', name: '账号登录', steps: [{ stepName: '输入账号' }, { stepName: '点击登录' }] },
      { module: '登录', name: '密码错误', steps: [{ stepName: '输入错误密码' }] },
      { module: '权限', name: '无权限', steps: [] },
    ],
  }))
  expect(groups.map(group => group.title)).toEqual(['登录', '权限'])
  expect(groups[0].rows.map(row => row.label)).toEqual(['账号登录', '密码错误'])
  expect(groups[0].rows[0].value).toContain('输入账号')
})

it('基础 diff 标记新增、删除与相同行', () => {
  const lines = diffArtifact('name: old\nsteps: 1', 'name: new\nsteps: 1\nextra: true')
  expect(lines.map(line => line.type)).toEqual(['remove', 'add', 'same', 'add'])
  expect(diffStats(lines)).toEqual({ add: 2, remove: 1 })
})

it('空基线把全部内容标为新增', () => {
  expect(diffArtifact('', 'a\nb').every(line => line.type === 'add')).toBe(true)
})

it('格式化后比较，不把 JSON 压缩和缩进差异算成修改', () => {
  const value = { name: '清洗开关', rules: [{ enabled: true, default: false }] }
  const lines = diffArtifact(JSON.stringify(value, null, 2), JSON.stringify(value))
  expect(diffStats(lines)).toEqual({ add: 0, remove: 0 })
  expect(lines.length).toBeGreaterThan(5)
})

it('格式化 YAML 流式结构，保留正文原文', () => {
  expect(diffStats(diffArtifact('rules: [{enabled: true}]', 'rules:\n  - enabled: true')))
    .toEqual({ add: 0, remove: 0 })
  expect(diffArtifact('原始说明', '新的说明').map(line => line.text)).toEqual(['原始说明', '新的说明'])
})
