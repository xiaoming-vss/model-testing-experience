import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import type { RepositoryProfile } from '../types'
import { RepositoryProfileReportView } from './RepositoryProfileReportView'

afterEach(cleanup)

const profile: RepositoryProfile = {
  overallSummary: '当前需求主要涉及后端订单服务，另有一个无法读取的仓库。',
  repositories: [
    {
      repositoryId: 'repo-1',
      pathWithNamespace: 'team/order-service',
      role: 'backend',
      responsibilitySummary: '提供订单创建与查询接口',
      techStack: ['Java', 'Spring Boot'],
      keyPaths: ['src/main/java'],
      confidence: 0.86,
      evidence: ['pom.xml', 'controller/'],
    },
    {
      repositoryId: 'repo-2',
      pathWithNamespace: 'team/admin-web',
      role: 'unknown',
      responsibilitySummary: '无法读取该仓库，未进行画像分析',
      techStack: [],
      keyPaths: [],
      confidence: 0,
      evidence: [],
    },
  ],
}

it('主视图展示角色、路径和职责，展开后展示技术栈、目录、置信度和证据', () => {
  const { container } = render(
    <RepositoryProfileReportView
      profile={profile}
      profileErrors={{ 'repo-2': '工作分支不存在或无权限' }}
    />,
  )

  expect(screen.getByText(profile.overallSummary)).toBeVisible()
  expect(screen.getByText('team/order-service')).toBeVisible()
  expect(screen.getByText('后端')).toBeVisible()
  expect(screen.getByText('提供订单创建与查询接口')).toBeVisible()
  expect(screen.getByText('未知')).toBeVisible()
  expect(screen.queryByText('Java')).not.toBeInTheDocument()

  const expandButtons = container.querySelectorAll('.ant-table-row-expand-icon')
  expect(expandButtons.length).toBe(2)
  fireEvent.click(expandButtons[0])

  expect(screen.getByText('Java')).toBeVisible()
  expect(screen.getByText('Spring Boot')).toBeVisible()
  expect(screen.getByText('src/main/java')).toBeVisible()
  expect(screen.getByText('86%')).toBeVisible()
  expect(screen.getByText('pom.xml')).toBeVisible()
  expect(screen.getByText('controller/')).toBeVisible()

  fireEvent.click(expandButtons[1])
  expect(screen.getByText('仓库读取失败')).toBeVisible()
  expect(screen.getByText('工作分支不存在或无权限')).toBeVisible()
})

it('空画像展示空态', () => {
  render(<RepositoryProfileReportView profile={{ repositories: [], overallSummary: '' }} />)
  expect(screen.getByText('暂无仓库画像')).toBeVisible()
})
