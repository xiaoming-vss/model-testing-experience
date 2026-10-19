import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it } from 'vitest'
import { AnalysisOverview } from './AnalysisOverview'

afterEach(cleanup)

it('模块详情支持切换与收起，边界内容保留', async () => {
  const user = userEvent.setup()
  render(<AnalysisOverview overview={{ purpose: '处理数据', actors: ['审核员'], entryPoints: [
    { function: '采集数据 M01', path: '/data', action: '上传文件' },
    { function: '导出 M02', path: '/export', action: '下载文件' },
  ] }} />)
  await user.click(screen.getByRole('button', { name: /采集数据 M01/ }))
  expect(screen.getByText('/data')).toBeVisible()
  expect(screen.queryByRole('searchbox')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /导出 M02/ }))
  expect(screen.queryByText('/data')).not.toBeInTheDocument()
  expect(screen.getByText('/export')).toBeVisible()
  await user.click(screen.getByRole('button', { name: /导出 M02/ }))
  expect(screen.queryByText('/export')).not.toBeInTheDocument()
  expect(screen.getByText('审核员')).toBeVisible()
  expect(screen.getByText('审核员').tagName).toBe('LI')
})

it('空概览保留空态且没有重复的分析入口', () => {
  render(<AnalysisOverview overview={{}} />)
  expect(screen.getByText('暂无业务模块')).toBeVisible()
  expect(screen.queryByText('data')).not.toBeInTheDocument()
  expect(screen.queryByRole('complementary', { name: '详细分析入口' })).not.toBeInTheDocument()
})
