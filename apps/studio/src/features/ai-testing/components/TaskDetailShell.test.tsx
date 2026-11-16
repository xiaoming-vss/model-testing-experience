import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { TaskDetailToolbar } from './TaskDetailShell'

/*
 * 工具条是详情页共用的骨架，页面测试只能覆盖各自用到的形状，
 * 所以这里把「kind / separator 各渲染成什么」这份契约单独钉住：
 * 样式层 `styles/task-detail-v2.css` 正是按这些类名接管的。
 */
afterEach(cleanup)

describe('详情页共用外壳零件', () => {
  it('工具条按 kind 渲染取值形态，并按 separator 画分组线与中点', () => {
    const { container } = render(
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
})
