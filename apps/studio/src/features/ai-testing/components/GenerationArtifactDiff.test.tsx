import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { GenerationArtifactDiff } from './GenerationArtifactDiff'

afterEach(cleanup)

it('旧版本在左、当前产物在右，格式化并对齐修改及新增行', () => {
  render(<GenerationArtifactDiff before={JSON.stringify({ name: '旧名称', enabled: true })}
    after={JSON.stringify({ name: '新名称', enabled: true, extra: '新增' })}
    beforeLabel="v1" afterLabel="待审核产物" />)
  const table = screen.getByRole('table', { name: '版本差异' })
  expect(within(table).getAllByRole('columnheader').map(cell => cell.textContent)).toEqual(['v1旧版本', '待审核产物当前内容'])
  const changed = within(table).getAllByRole('row').find(row => row.textContent?.includes('旧名称'))!
  const cells = within(changed).getAllByRole('cell')
  expect(cells[0]).toHaveTextContent('"name": "旧名称"')
  expect(cells[0]).toHaveClass('is-remove')
  expect(cells[1]).toHaveTextContent('"name": "新名称"')
  expect(cells[1]).toHaveClass('is-add')
  expect(table.querySelectorAll('code').length).toBeGreaterThan(5)
})

it('删除行右侧留空，后续相同行保持同一行', () => {
  render(<GenerationArtifactDiff before={"第一行\n删除行\n末行"} after={"第一行\n末行"} beforeLabel="v1" afterLabel="v2" />)
  const row = screen.getByText('删除行').closest('tr')!
  expect(within(row).getAllByRole('cell')[1]).toHaveClass('is-empty')
  const last = screen.getAllByText('末行')
  expect(last[0].closest('tr')).toBe(last[1].closest('tr'))
})
