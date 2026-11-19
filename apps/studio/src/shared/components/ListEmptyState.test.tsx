import { cleanup, render, screen } from '@testing-library/react'
import { AppstoreOutlined } from '@ant-design/icons'
import { afterEach, expect, it } from 'vitest'
import { ListEmptyState } from './ListEmptyState'

afterEach(cleanup)

it('渲染统一空态并保留动作与自定义类', () => {
  const { container } = render(
    <ListEmptyState className="narrow-empty" description="暂无测试集" image={<AppstoreOutlined />}>
      <button type="button">新建测试集</button>
    </ListEmptyState>,
  )

  expect(container.querySelector('.grid.min-h-\\[220px\\].place-items-center.narrow-empty')).not.toBeNull()
  expect(screen.getByText('暂无测试集')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '新建测试集' })).toBeInTheDocument()
})
