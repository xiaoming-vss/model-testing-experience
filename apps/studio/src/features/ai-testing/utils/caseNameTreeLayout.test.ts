import { describe, expect, it, vi } from 'vitest'
import type { CaseNameTreeNode } from './caseNameTree'
import { buildTreeFlow, layoutTreeFlow } from './caseNameTreeLayout'

const leaf = (id: string): CaseNameTreeNode => ({ id, title: id, kind: 'point', children: [] })
const tree: CaseNameTreeNode = { id: 'root', title: '需求', kind: 'root', children: [{ id: 'model', title: '模块', kind: 'model', children: [{ id: 'scene', title: '场景', kind: 'testModel', children: [leaf('first'), leaf('second'), leaf('third')] }] }] }

describe('caseNameTreeLayout', () => {
  it('keeps artifact order and separates nodes with different measured heights', () => {
    const callback = vi.fn()
    const graph = buildTreeFlow(tree, 'second', callback, callback)
    const nodes = graph.nodes.map(node => ({ ...node, measured: { width: node.id === 'first' ? 240 : 300, height: node.id === 'first' ? 90 : 38 } }))
    const result = layoutTreeFlow(nodes, graph.edges)
    const find = (id: string) => result.find(node => node.id === id)!
    expect(find('second').position.y).toBeGreaterThanOrEqual(find('first').position.y + 90 + 10)
    expect(find('third').position.y).toBeGreaterThanOrEqual(find('second').position.y + 38 + 10)
    expect(find('first').position.x).toBe(find('second').position.x)
    expect(find('second').data.selected).toBe(true)
    expect(graph.edges).toHaveLength(5)
  })

  it('attaches the delete callback only to test points', () => {
    const graph = buildTreeFlow(tree, undefined, undefined, undefined, vi.fn())
    const data = (id: string) => graph.nodes.find(node => node.id === id)!.data
    expect(data('first').onDelete).toBeTypeOf('function')
    expect(data('root').onDelete).toBeUndefined()
    expect(data('model').onDelete).toBeUndefined()
    expect(data('scene').onDelete).toBeUndefined()
  })
})
