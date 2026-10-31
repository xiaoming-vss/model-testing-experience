import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { AiSkillLibraryPage } from './AiSkillLibraryPage'
import { api, type AiSkillLibraryItem } from '@/services/api'

vi.mock('@/features/projects/hooks/useActiveProject', () => ({
  useActiveProject: () => ({ activeProjectId: 'project-1', projectsQuery: { error: null } }),
}))
vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

it('renders skills with the shared service card structure and metadata', async () => {
  const skill: AiSkillLibraryItem = {
    skillSpaceId: 'skill-1', projectId: 'project-1', filename: 'testing-case', isDefault: false,
    fileCount: 8, size: 24576, updatedAt: '2026-09-16T06:09:52Z',
  }
  vi.spyOn(api, 'getAiSkillLibraryItems').mockResolvedValue(listResponse([skill]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><AiSkillLibraryPage embedded /></QueryClientProvider>)

  expect(await screen.findByText('testing-case')).toBeInTheDocument()
  expect(screen.getByText('testing-case').closest('.ant-card')).toHaveClass('base-services-connection-card')
  expect(screen.getByText('项目自定义')).toBeInTheDocument()
  expect(screen.getByText('文件数')).toBeInTheDocument()
  expect(screen.getByText('8')).toBeInTheDocument()
  expect(screen.getByText('24.0 KB')).toBeInTheDocument()
  expect(screen.getByText('最近更新')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '下载 Skill' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '上传 Skill' })).toBeInTheDocument()
})

it('keeps system skills in the same card and marks them as default', async () => {
  vi.spyOn(api, 'getAiSkillLibraryItems').mockResolvedValue(listResponse<AiSkillLibraryItem>([
    { skillSpaceId: 'skill-2', filename: 'generate-solution-test-cases', isDefault: true, fileCount: 14, size: 132100 },
  ]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><AiSkillLibraryPage embedded /></QueryClientProvider>)

  expect(await screen.findByText('generate-solution-test-cases')).toBeInTheDocument()
  expect(screen.getByText('系统默认')).toBeInTheDocument()
  expect(screen.getByText('129.0 KB')).toBeInTheDocument()
})
