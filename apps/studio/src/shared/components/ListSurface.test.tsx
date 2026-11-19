import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { ListSurface } from './ListSurface'

afterEach(cleanup)

it('渲染工具栏、提示、滚动区与固定分页', () => {
  render(
    <ListSurface ariaLabel="迭代列表" className="sprint-board-shell" bodyClassName="sprint-board"
      scrollClassName="sprint-board-scroll" footerClassName="sprint-board-footer" scrollAriaBusy
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
  expect(surface.querySelector('.table-footer.sprint-board-footer')).toHaveTextContent('分页')
})

it('支持 aria-labelledby 关联外部标题', () => {
  render(
    <>
      <h1 id="list-title">账号管理</h1>
      <ListSurface ariaLabelledBy="list-title"><div>内容</div></ListSurface>
    </>,
  )

  expect(screen.getByRole('region', { name: '账号管理' })).toHaveClass('tp-list-panel')
})
