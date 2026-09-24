import { seedOwnerProject } from '@/test/projectAccess'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TestThemeProvider as ThemeProvider } from '@/test/TestThemeProvider'
import type { ReactNode } from 'react'
import {
  TaskDetailInstructionEditor,
  TaskDetailNavItem,
  TaskDetailNavPanel,
  TaskDetailToolbar,
} from './TaskDetailShell'

/*
 * 这组零件是五个详情页共用的骨架，页面测试只能覆盖各自用到的形状，
 * 所以这里把「kind / separator / badge 各渲染成什么」这份契约单独钉住：
 * 样式层 `styles/task-detail-v2.css` 正是按这些类名接管的。
 */
afterEach(cleanup)

/** ProjectActionButton 要读项目权限，所以统一套一层 provider。 */
function renderShell(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  return render(<ThemeProvider><QueryClientProvider client={client}>{node}</QueryClientProvider></ThemeProvider>)
}

describe('详情页共用外壳零件', () => {
  it('工具条按 kind 渲染取值形态，并按 separator 画分组线与中点', () => {
    const { container } = renderShell(
      <TaskDetailToolbar
        back={<button type="button">返回</button>}
        fields={[
          { label: '任务名称', value: '任务 A', kind: 'name', separator: 'line' },
          { label: '迭代', value: 'v1.2.0', kind: 'chip-accent' },
          { label: '来源类型', value: 'docx', kind: 'chip-muted' },
          { label: '更新时间', value: '2026/9/14', kind: 'time', separator: 'dot' },
        ]}
        actions={<button type="button">运行</button>}
      />,
    )

    const toolbar = container.querySelector('.ai-task-detail-toolbar')
    expect(toolbar).not.toBeNull()
    expect(screen.getByText('任务 A')).toHaveClass('ai-task-detail-toolbar-name')
    expect(screen.getByText('v1.2.0')).toHaveClass('ai-task-detail-chip')
    expect(screen.getByText('docx')).toHaveClass('ai-task-detail-chip', 'is-muted')
    expect(screen.getByText('2026/9/14')).toHaveClass('ai-task-detail-time')

    // 分组竖线只在标了 separator: 'line' 的那一项里出现，中点同理。
    expect(container.querySelectorAll('.ai-task-detail-toolbar-divider')).toHaveLength(1)
    expect(container.querySelectorAll('.ai-task-detail-meta-sep')).toHaveLength(1)
    // 每个字段都带标签，动作组留在工具条第二段。
    expect(screen.getByText('任务名称')).toHaveClass('ai-task-detail-toolbar-label')
    expect(within(toolbar as HTMLElement).getByRole('button', { name: '运行' })).toBeInTheDocument()
  })

  it('导航条目只有传了 badge 才渲染计数徽标，选中态落在 active 类上', () => {
    const { container } = renderShell(
      <TaskDetailNavPanel tip="提示文案">
        <TaskDetailNavItem title="来源内容" sub="docx · 0 字符" icon={<span />} active={false} onClick={() => {}} />
        <TaskDetailNavItem title="运行记录" sub="共 3 条运行记录" icon={<span />} active badge={3} onClick={() => {}} />
      </TaskDetailNavPanel>,
    )

    expect(screen.getByText('任务信息')).toBeInTheDocument()
    expect(screen.getByText('提示文案')).toBeInTheDocument()
    expect(container.querySelectorAll('.ai-task-detail-nav-item')).toHaveLength(2)
    expect(container.querySelectorAll('.ai-task-detail-nav-item.active')).toHaveLength(1)
    expect(container.querySelectorAll('.ai-task-detail-nav-badge')).toHaveLength(1)
    expect(screen.getByText('3')).toHaveClass('ai-task-detail-nav-badge')
  })

  it('指令编辑器只在草稿变动后允许保存', () => {
    const onSave = vi.fn()
    renderShell(<TaskDetailInstructionEditor value="原指令" dirty={false} saving={false} onChange={vi.fn()} onSave={onSave} />)

    expect(screen.getByRole('button', { name: '保存指令' })).toBeDisabled()
    expect(onSave).not.toHaveBeenCalled()
  })

  it('指令编辑器改动后可保存，正在保存时禁止重复提交', () => {
    const onSave = vi.fn()
    renderShell(<TaskDetailInstructionEditor value="新指令" dirty saving={false} onChange={vi.fn()} onSave={onSave} />)

    const save = screen.getByRole('button', { name: '保存指令' })
    expect(save).toBeEnabled()
    save.click()
    expect(onSave).toHaveBeenCalledTimes(1)

    cleanup()
    renderShell(<TaskDetailInstructionEditor value="新指令" dirty saving onChange={vi.fn()} onSave={onSave} />)
    expect(screen.getByRole('button', { name: /保存指令/ })).toBeDisabled()
  })
})
