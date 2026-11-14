import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import examples from '../../fixtures/visualization.json'
import type { Visualization } from '../../visualizationTypes'
import { BusinessDiagram } from './BusinessDiagram'

afterEach(cleanup)

describe('business diagrams', () => {
  for (const example of examples) {
    it(`renders ${example.name} without evidence controls`, () => {
      render(<BusinessDiagram artifact={example.output as Visualization} step={0} />)
      expect(screen.getByRole('heading', { name: '验证焦点' })).toBeInTheDocument()
      expect(screen.queryByRole('button')).not.toBeInTheDocument()
    })
  }
  it('preserves negative trigger, without marking an actual execution', () => {
    render(<BusinessDiagram artifact={examples[2].output as Visualization} step={0} />)
    expect(screen.getByText('不触发')).toBeInTheDocument()
    expect(screen.getByText('状态保持')).toBeInTheDocument()
    expect(screen.queryByText('执行通过')).not.toBeInTheDocument()
  })
})

describe('graph semantics', () => {
  it('keeps negative and conditional relationships visible', () => {
    const artifact = structuredClone(examples[2].output) as Visualization
    const relation = artifact.relations.find(item => item.polarity === 'negative')!
    relation.condition = { text: '仅保存标注时', sourceIds: ['a0'] }
    render(<BusinessDiagram artifact={artifact} step={0} />)
    expect(screen.getByText('不触发')).toBeInTheDocument()
    expect(screen.getByText('条件：仅保存标注时')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
  it('never invents connections from equally sized source and output arrays', () => {
    const artifact = structuredClone(examples[3].output) as Visualization
    artifact.relations = []
    artifact.visuals.forEach(v => { v.relationIds = [] })
    render(<BusinessDiagram artifact={artifact} step={0} />)
    expect(screen.getByText('来源')).toBeInTheDocument()
    expect(screen.getByText('预期产物')).toBeInTheDocument()
    expect(screen.queryByLabelText('对象关系')).not.toBeInTheDocument()
  })
})

it('places interval outputs by explicit relationships without inventing missing edges', () => {
  const artifact = structuredClone(examples[1].output) as Visualization
  const visual = artifact.visuals[0]
  if (visual.kind !== 'interval') throw new Error('expected interval')
  artifact.entities.push(
    { id: 'out1', kind: 'object', label: '产物一', sourceIds: ['e0'] },
    { id: 'out2', kind: 'object', label: '产物二', sourceIds: ['e0'] },
  )
  visual.entityIds.push('out1', 'out2')
  visual.data.distinctOutputEntityIds = ['out1', 'out2']
  visual.data.distinctOutputSourceIds = ['e0']
  artifact.relations.push(
    { id: 'r1', kind: 'produces', from: 'left', to: 'out2', polarity: 'positive', sourceIds: ['e0'] },
    { id: 'r2', kind: 'produces', from: 'right', to: 'out1', polarity: 'positive', sourceIds: ['e0'] },
  )
  visual.relationIds = ['r1', 'r2']
  const { container, rerender } = render(<BusinessDiagram artifact={artifact} step={0} />)
  const positions = container.querySelectorAll('.test-order-viz-mapped-item')
  expect(positions[0]).toHaveTextContent('产物二')
  expect(positions[1]).toBeEmptyDOMElement()
  expect(positions[2]).toHaveTextContent('产物一')
  visual.relationIds = ['r1']
  rerender(<BusinessDiagram artifact={artifact} step={0} />)
  expect(container.querySelector('.test-order-viz-mapped')).toBeNull()
  expect(screen.getByLabelText('对象关系')).toHaveTextContent('产物二')
})
