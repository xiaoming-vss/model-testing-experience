import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import type { ModuleGenerationProgress } from '../api/generationChain.api'
import { ModuleGenerationProgressPanel } from './ModuleGenerationProgressPanel'

afterEach(cleanup)
const progress: ModuleGenerationProgress = {
  attemptId: 'attempt', sequence: 3, concurrency: 2, status: 'running',
  modules: [
    { id: '0', module: '文件校验', status: 'completed', caseCount: 5, elapsedMs: 62000, repairAttempt: 0 },
    { id: '1', module: 'IMU 校验', status: 'running', caseCount: 0, elapsedMs: 0, repairAttempt: 0 },
    { id: '2', module: '标定外参校验', status: 'repairing', caseCount: 0, elapsedMs: 0, repairAttempt: 1 },
    { id: '3', module: '质量报告', status: 'queued', caseCount: 0, elapsedMs: 0, repairAttempt: 0 },
  ],
}
it('显示每个模块的真实状态、完成数量和耗时，轮询后更新', () => {
  const { rerender } = render(<ModuleGenerationProgressPanel progress={progress} />)
  expect(screen.getByText('已完成 1/4 个模块')).toBeVisible()
  expect(screen.getByRole('status')).toHaveTextContent('2 个生成中 · 最多同时 2 个')
  const rows = within(screen.getByRole('list', { name: '模块子任务' })).getAllByRole('listitem')
  expect(rows[0]).toHaveTextContent('5 条用例 · 62 秒')
  expect(rows[1]).toHaveTextContent('生成中')
  expect(rows[2]).toHaveTextContent('校验修复中 1/2')
  expect(rows[3]).toHaveTextContent('排队中')
  rerender(<ModuleGenerationProgressPanel progress={{ ...progress, status: 'merging', modules: progress.modules.map(m => ({ ...m, status: 'completed' })) }} />)
  expect(screen.getByRole('status')).toHaveTextContent('正在合并并校验完整用例')
  expect(screen.getByText('已完成 4/4 个模块')).toBeVisible()
})
it('失败时不误报成功，保留失败和已停止的模块', () => {
  render(<ModuleGenerationProgressPanel progress={{ ...progress, status: 'failed', modules: [
    { ...progress.modules[0], status: 'failed' }, { ...progress.modules[1], status: 'canceled' },
  ] }} />)
  expect(screen.getByRole('status')).toHaveTextContent('生成失败，未发布部分结果')
  expect(screen.getByText('失败', { exact: true })).toBeVisible()
  expect(screen.getByText('已停止')).toBeVisible()
  expect(screen.getByText('已完成 0/2 个模块')).toBeVisible()
})

it('测试点初稿完成后继续显示全局复核与增量修订，不误报整阶段成功', () => {
  const points: ModuleGenerationProgress = {
    ...progress, stage: 'case_names', status: 'reviewing', reviewRound: 1,
    modules: progress.modules.map(module => ({ ...module, status: 'completed', pointCount: 3 })),
  }
  const { rerender } = render(<ModuleGenerationProgressPanel progress={points} />)
  expect(screen.getByRole('region', { name: '测试点分组进度' })).toBeVisible()
  expect(screen.getByText('初稿已完成 4/4 个分组')).toBeVisible()
  expect(screen.getByRole('status')).toHaveTextContent('正在进行首次全局覆盖与依据审查')
  expect(screen.getAllByText(/3 个测试点（初稿）/)).toHaveLength(4)
  expect(screen.queryByText('测试点生成及独立复核完成')).toBeNull()
  rerender(<ModuleGenerationProgressPanel progress={{ ...points, status: 'revising', issueCount: 5 }} />)
  expect(screen.getByRole('status')).toHaveTextContent('正在修订 5 条审查意见')
  rerender(<ModuleGenerationProgressPanel progress={{ ...points, status: 'reviewing', reviewRound: 2 }} />)
  expect(screen.getByRole('status')).toHaveTextContent('第 2 轮增量复核')
  rerender(<ModuleGenerationProgressPanel progress={{ ...points, status: 'review_failed', issueCount: 2 }} />)
  expect(screen.getByRole('status')).toHaveTextContent('仍有 2 条审查意见待人工核查')
  expect(screen.queryByText('测试点生成及独立复核完成')).toBeNull()
})
