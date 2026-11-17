import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { PageToolbar } from './PageToolbar'

afterEach(cleanup)

it('渲染标题块、操作区与兼容类', () => {
  render(
    <PageToolbar ariaLabel="需求列表标题" className="requirements-list-page-header"
      title={<h1>需求</h1>}
      actions={<button type="button">新建需求</button>} />,
  )

  const toolbar = screen.getByRole('region', { name: '需求列表标题' })
  expect(toolbar).toHaveClass('tp-page-toolbar', 'requirements-list-page-header')
  expect(toolbar.querySelector('.tp-page-toolbar-main')).toHaveTextContent('需求')
  expect(toolbar.querySelector('.tp-page-toolbar-actions')).toHaveTextContent('新建需求')
})
