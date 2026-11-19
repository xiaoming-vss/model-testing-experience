import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { EntityCard } from './EntityCard'
import entityCardModuleCss from '@/shared/styles/entity-card.module.css?raw'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderCard(onOpen = vi.fn()) {
  render(
    <MemoryRouter>
      <EntityCard
        title={<a href="/detail">详情对象</a>}
        status={<span>执行中</span>}
        meta={[
          { label: '所属迭代', value: '1.2.1' },
          { label: '被测版本', value: '1.2.0' },
        ]}
        footerNote="最近更新 2026-11-14"
        actions={<button type="button">运行</button>}
        onOpen={onOpen}
      >
        <p>主体内容</p>
      </EntityCard>
    </MemoryRouter>,
  )
  return onOpen
}

it('渲染标题、状态、主体、meta 与 footer 操作', () => {
  renderCard()

  expect(screen.getByRole('heading', { level: 2, name: '详情对象' })).toBeInTheDocument()
  expect(screen.getByText('执行中')).toBeInTheDocument()
  expect(screen.getByText('主体内容')).toBeInTheDocument()
  expect(screen.getByText('所属迭代')).toBeInTheDocument()
  expect(screen.getByText('1.2.1')).toBeInTheDocument()
  expect(screen.getByText('被测版本')).toBeInTheDocument()
  expect(screen.getByText('1.2.0')).toBeInTheDocument()
  expect(screen.getByText('最近更新 2026-11-14')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '运行' })).toBeInTheDocument()
})

it('点卡片空白处进入，点内部操作不触发进入', async () => {
  const onOpen = renderCard()
  const user = userEvent.setup()

  await user.click(screen.getByText('主体内容'))
  expect(onOpen).toHaveBeenCalledTimes(1)

  await user.click(screen.getByRole('button', { name: '运行' }))
  expect(onOpen).toHaveBeenCalledTimes(1)
})

it('支持兼容类、标题层级与 footer/actions 类', () => {
  render(
    <MemoryRouter>
      <EntityCard className="legacy-card" titleAs="h3" title="迭代对象"
        footerNote="备注" footerNoteClassName="legacy-note"
        actions={<button type="button">操作</button>} actionsClassName="legacy-actions">
        <p>主体内容</p>
      </EntityCard>
    </MemoryRouter>,
  )

  const heading = screen.getByRole('heading', { level: 3, name: '迭代对象' })
  expect(heading.closest('article')).toHaveClass('entity-card', 'legacy-card')
  expect(screen.getByText('备注')).toHaveClass('entity-card-note', 'legacy-note')
  expect(screen.getByRole('button', { name: '操作' }).parentElement).toHaveClass('entity-card-actions', 'legacy-actions')
})

it('标题链接通过模块选择器继承颜色，不依赖 important utility', () => {
  expect(entityCardModuleCss).toMatch(/\.title a\s*\{[^}]*color:\s*inherit/)
  expect(entityCardModuleCss).not.toMatch(/!important/)
})
