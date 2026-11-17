import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { ListSurface } from './ListSurface'

afterEach(cleanup)

it('渲染工具栏、提示、滚动区与固定分页', () => {
  render(
    <ListSurface ariaLabel="迭代列表" className="sprint-board-shell" bodyClassName="sprint-board"
      scrollClassName="sprint-board-scroll" scrollAriaBusy
      toolbar={<div>工具栏</div>} notices={<div>提示</div>} footer={<div>分页</div>}>
      <div>内容</div>
    </ListSurface>,
  )

  const surface = screen.getByRole('region', { name: '迭代列表' })
  expect(surface).toHaveClass('tp-board', 'tp-list-panel', 'sprint-board-shell')
  expect(surface.querySelector('.tp-list-body.sprint-board')).not.toBeNull()
  const scroll = surface.querySelector('.tp-list-scroll.sprint-board-scroll')
  expect(scroll).toHaveAttribute('aria-busy', 'true')
  expect(scroll).toHaveTextContent('内容')
  expect(surface.querySelector('.table-footer')).toHaveTextContent('分页')
})
