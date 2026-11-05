import { act, cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { createRef, type ComponentProps } from 'react'
import { ReactFlow } from '@xyflow/react'
import { UiExecutionFlow, type UiExecutionFlowHandle } from './UiExecutionFlow'

afterEach(cleanup)

vi.mock('@xyflow/react', async (load) => {
  const actual = await load<typeof import('@xyflow/react')>()
  return {
    ...actual,
    ReactFlow: (props: ComponentProps<typeof ReactFlow>) => <div data-testid="flow-mock" data-only-visible={String(props.onlyRenderVisibleElements ?? false)}>
      {props.nodes?.map((node) => <span key={node.id} data-testid={`node-${node.id}`} data-x={node.position.x} data-y={node.position.y} data-source={String((node.data as { sourceSide?: unknown }).sourceSide ?? '')} data-target={String((node.data as { targetSide?: unknown }).targetSide ?? '')} data-reveal={String((node.data as { revealDelay?: unknown }).revealDelay ?? '')} />)}
      {props.edges?.map((edge) => <span key={edge.id} data-testid={`edge-${edge.id}`} data-running={String(edge.data?.running)} />)}
      <button onClick={(event) => props.onNodeClick?.(event, props.nodes![1])}>选择 b</button>
      <button onClick={() => props.onEdgesChange?.([{ id: 'a-b', type: 'remove' }, { id: 'b-c', type: 'remove' }])}>断开</button>
      <button onClick={() => props.onConnect?.({ source: 'b', target: 'c', sourceHandle: null, targetHandle: null })}>连接 b c</button>
      <button onClick={() => props.onConnect?.({ source: 'c', target: 'a', sourceHandle: null, targetHandle: null })}>连接 c a</button>
    </div>,
  }
})

it('only applies a complete linear order after links are edited', async () => {
  const apply = vi.fn()
  const user = userEvent.setup()
  render(<UiExecutionFlow storageKey="test-flow" editable onApply={apply} items={['a', 'b', 'c'].map((id) => ({ id, title: id, serial: id, caption: '', enabled: true }))} />)
  expect(screen.getByRole('button', { name: '应用顺序' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: '断开' }))
  expect(screen.getByText(/连线尚未形成完整顺序/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '应用顺序' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: '连接 b c' }))
  await user.click(screen.getByRole('button', { name: '连接 c a' }))
  await user.click(screen.getByRole('button', { name: '应用顺序' }))
  expect(apply).toHaveBeenCalledWith(['b', 'c', 'a'])
})


it('单击步骤节点时通知底部编辑器选择该步骤', async () => {
  const select = vi.fn()
  const user = userEvent.setup()
  render(<UiExecutionFlow storageKey="test-flow-select" editable onApply={() => {}} onSelect={select} items={['a', 'b'].map((id) => ({ id, title: id, serial: id, caption: '', enabled: true }))} />)
  await user.click(screen.getByRole('button', { name: '选择 b' }))
  expect(select).toHaveBeenCalledWith('b')
})


it('步骤画布保存时校验并提交连线顺序', async () => {
  const ref = createRef<UiExecutionFlowHandle>()
  const apply = vi.fn()
  const user = userEvent.setup()
  render(<UiExecutionFlow ref={ref} inlineSave storageKey="test-flow-save" editable onApply={apply} items={['a', 'b', 'c'].map((id) => ({ id, title: id, serial: id, caption: '', enabled: true }))} />)
  expect(screen.queryByRole('button', { name: '应用顺序' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '断开' }))
  expect(ref.current?.prepareSave()).toBe(false)
  expect(apply).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: '连接 b c' }))
  await user.click(screen.getByRole('button', { name: '连接 c a' }))
  act(() => expect(ref.current?.prepareSave()).toBe(true))
  expect(apply).toHaveBeenCalledWith(['b', 'c', 'a'])
})


it('只在运行节点的出边显示运行光束，结束后恢复常态', () => {
  const items = ['a', 'b', 'c'].map((id) => ({ id, title: id, serial: id, caption: '', enabled: true }))
  const { rerender } = render(<UiExecutionFlow storageKey="test-flow-running" editable onApply={() => {}} items={items} runningIds={['b']} />)
  expect(screen.getByTestId('edge-a-b')).toHaveAttribute('data-running', 'false')
  expect(screen.getByTestId('edge-b-c')).toHaveAttribute('data-running', 'true')
  rerender(<UiExecutionFlow storageKey="test-flow-running" editable onApply={() => {}} items={items} runningIds={[]} />)
  expect(screen.getByTestId('edge-b-c')).toHaveAttribute('data-running', 'false')
})


it('只挂载视口内卡片，并按执行顺序错开入场', () => {
  const items = ['a', 'b', 'c'].map((id) => ({ id, title: id, serial: id, caption: '', enabled: true }))
  render(<UiExecutionFlow storageKey="test-flow-viewport" editable onApply={() => {}} items={items} />)
  expect(screen.getByTestId('flow-mock')).toHaveAttribute('data-only-visible', 'true')
  expect(screen.getByTestId('node-a')).toHaveAttribute('data-reveal', '0')
  expect(screen.getByTestId('node-b')).toHaveAttribute('data-reveal', '8')
})


it('默认把步骤卡片铺成蛇形折行并切换行末连接点', () => {
  const items = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'].map((id) => ({ id, title: id, serial: id, caption: '', enabled: true }))
  render(<UiExecutionFlow storageKey="test-flow-serpentine" editable onApply={() => {}} items={items} />)
  // 8 张卡片按 4 列折成两行，第二行从右往左接。
  expect(screen.getByTestId('node-e')).toHaveAttribute('data-x', '720')
  expect(screen.getByTestId('node-e')).toHaveAttribute('data-y', '148')
  expect(screen.getByTestId('node-d')).toHaveAttribute('data-source', 'bottom')
  expect(screen.getByTestId('node-e')).toHaveAttribute('data-target', 'top')
  expect(screen.getByTestId('node-e')).toHaveAttribute('data-source', 'left')
})


it('迁移旧的单行自动布局', () => {
  const items = ['a', 'b'].map((id) => ({ id, title: id, serial: id, caption: '', enabled: true }))
  localStorage.setItem('test-flow-legacy-layout', JSON.stringify({ a: { x: 0, y: 90 }, b: { x: 240, y: 140 } }))
  render(<UiExecutionFlow storageKey="test-flow-legacy-layout" editable onApply={() => {}} items={items} />)
  expect(screen.getByTestId('node-b')).toHaveAttribute('data-y', '0')
})


it('保留用户拖动过的位置和连接点方向', () => {
  const items = ['a', 'b'].map((id) => ({ id, title: id, serial: id, caption: '', enabled: true }))
  localStorage.setItem('test-flow-custom-layout', JSON.stringify({ a: { x: 999, y: 999, sourceSide: 'left', targetSide: 'right' } }))
  render(<UiExecutionFlow storageKey="test-flow-custom-layout" editable onApply={() => {}} items={items} />)
  expect(screen.getByTestId('node-a')).toHaveAttribute('data-x', '999')
  expect(screen.getByTestId('node-a')).toHaveAttribute('data-source', 'left')
})
