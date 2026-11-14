import { ArrowRightOutlined, StopOutlined } from '@ant-design/icons'
import type { ReactNode } from 'react'
import type { Relation } from '../../visualizationTypes'

const labels: Record<string, string> = { sequence: '先于', triggers: '触发', transitions_to: '变为', contains: '包含', belongs_to: '归属', produces: '产生', excludes: '排除', compares_with: '对比' }
type Props = { relations: Relation[]; entityView: (id: string | null) => ReactNode }

/** Draw only explicit edges: array order and matching counts never imply a mapping. */
export function DiagramRelations({ relations, entityView }: Props) {
  return <div className="test-order-viz-relations" aria-label="对象关系">{relations.map(relation => <div className={`test-order-viz-relation${relation.polarity === 'negative' ? ' is-negative tone-red' : ''}`} key={relation.id}>
    {entityView(relation.from)}
    <div className="test-order-viz-connector">
      <span>{relation.polarity === 'negative' ? '不' : ''}{labels[relation.kind] ?? relation.kind}</span>
      <span className="test-order-viz-edge" aria-hidden="true">{relation.polarity === 'negative' ? <StopOutlined /> : <ArrowRightOutlined />}</span>
      {relation.condition && <small>条件：{relation.condition.text}</small>}
    </div>
    {entityView(relation.to)}
  </div>)}</div>
}
