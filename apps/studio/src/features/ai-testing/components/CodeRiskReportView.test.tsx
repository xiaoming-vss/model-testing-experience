import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import type { CodeRiskReport } from '../types'
import { CodeRiskReportView } from './CodeRiskReportView'

afterEach(cleanup)

const receiptReport: CodeRiskReport = {
  analyzedAt: '2026-08-27T10:00:00Z',
  contextReceipt: {
    mode: 'context_preview',
    counts: { repositories: 1, changedFiles: 2, diffChars: 1234 },
    truncatedFiles: ['src/big.py'],
    summary: '已读取登录仓库上下文',
    filesRead: ['src/login.py', 'src/auth/session.py'],
    toolsUsed: ['read', 'grep'],
    repositories: [
      {
        repositoryId: 'repo-1',
        pathWithNamespace: 'team/repo-one',
        branch: 'feature/login',
        baseCommit: 'abc123',
        headCommit: 'def456',
        filesChanged: 2,
      },
    ],
  },
}

it('上下文回执展示预览横幅、仓库版本与模型读取范围', () => {
  render(<CodeRiskReportView report={receiptReport} />)

  expect(screen.getByText('上下文预览（分析 skill 未启用）')).toBeVisible()
  expect(screen.getByText('已读取登录仓库上下文')).toBeVisible()
  expect(screen.getByText('1234')).toBeVisible()
  expect(screen.getByText('team/repo-one')).toBeVisible()
  expect(screen.getByText('feature/login')).toBeVisible()
  expect(
    screen.getAllByText((_, element) => element?.textContent === 'abc123 → def456')[0],
  ).toBeVisible()
  expect(screen.getByText('src/login.py')).toBeVisible()
  expect(screen.getByText('src/auth/session.py')).toBeVisible()
  expect(screen.getByText('read')).toBeVisible()
  expect(screen.getByText('grep')).toBeVisible()
  expect(screen.getByText('部分 diff 因上下文预算被排除')).toBeVisible()
  expect(screen.getByText('src/big.py')).toBeVisible()
  expect(screen.queryByText('风险点清单')).not.toBeInTheDocument()
})

it('没有上下文回执时保持原风险报告视图', () => {
  render(
    <CodeRiskReportView
      report={{
        analyzedAt: '2026-08-27T10:00:00Z',
        repositories: [
          {
            repositoryId: 'repo-1',
            branch: 'develop',
            baselineCommit: 'abc123',
            headCommit: 'def456',
            filesChanged: 1,
          },
        ],
        risks: [{ level: 'high', location: 'src/login.py', reason: '鉴权逻辑变更' }],
      }}
    />,
  )

  expect(screen.queryByText('上下文预览（分析 skill 未启用）')).not.toBeInTheDocument()
  expect(screen.getByText('风险点清单')).toBeVisible()
  expect(screen.getByText('鉴权逻辑变更')).toBeVisible()
})
