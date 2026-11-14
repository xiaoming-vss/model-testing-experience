import type { Constraint } from '../visualizationTypes'

const operators = { eq: '=', gt: '>', gte: '≥', lt: '<', lte: '≤' }
export function formatConstraint(value: Constraint) {
  return `${operators[value.operator]} ${value.value} ${value.unit}`
}
