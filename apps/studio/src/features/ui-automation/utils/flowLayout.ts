// 与 execution-flow.css 中卡片的实际渲染尺寸一致（含内边距、描边与基础行高），
// 否则 fitView 会按偏小的初始尺寸计算，放大后最右一列会贴到画布边缘。
export const FLOW_NODE_WIDTH = 206
export const FLOW_NODE_HEIGHT = 108
export const FLOW_COLUMN_PITCH = 240
export const FLOW_ROW_PITCH = 148

// 排布时优先把内容铺成接近画布比例的矩形，避免步骤多时只剩一条长横线。
const TARGET_ASPECT = 2.4
// 旧版默认排布：横向 240 等距，纵向上下一高一低。用于识别可以安全迁移的自动布局。
export const LEGACY_COLUMN_PITCH = 240
export const LEGACY_ROW_OFFSETS = [90, 140] as const

export type FlowHandleSide = 'left' | 'right' | 'top' | 'bottom'

export type FlowNodePlacement = {
  position: { x: number; y: number }
  sourceSide: FlowHandleSide
  targetSide: FlowHandleSide
}

export function flowColumns(count: number): number {
  if (count <= 1) return 1
  let columns = 2
  let bestScore = -Infinity
  for (let candidate = 2; candidate <= Math.min(count, 12); candidate += 1) {
    const rows = Math.ceil(count / candidate)
    const width = (candidate - 1) * FLOW_COLUMN_PITCH + FLOW_NODE_WIDTH
    const height = (rows - 1) * FLOW_ROW_PITCH + FLOW_NODE_HEIGHT
    const score = Math.min(TARGET_ASPECT / width, 1 / height)
    if (score > bestScore) {
      bestScore = score
      columns = candidate
    }
  }
  return columns
}

/**
 * 蛇形折行排布：第一行从左到右，第二行从右到左。
 * 行末卡片的出线朝下，下一行首张卡片的入线朝上，行内其余卡片沿当前行方向连接。
 * withAddSlot 表示流程末尾还会出现一张“添加”卡片；它若另起一行，最后一张卡片必须朝下。
 */
export function computeFlowLayout(count: number, options: { withAddSlot?: boolean } = {}): { columns: number; nodes: FlowNodePlacement[] } {
  const columns = flowColumns(count)
  const withAddSlot = Boolean(options.withAddSlot) && count > 0
  const rows = Math.max(1, Math.ceil((count + (withAddSlot ? 1 : 0)) / columns))
  const nodes: FlowNodePlacement[] = Array.from({ length: count }, (_, index): FlowNodePlacement => {
    const row = Math.floor(index / columns)
    const slot = index % columns
    const column = row % 2 === 0 ? slot : columns - slot - 1
    const rowLength = Math.min(columns, count - row * columns)
    const rowEnd = slot === rowLength - 1
    const forward = row % 2 === 0
    return {
      position: { x: column * FLOW_COLUMN_PITCH, y: row * FLOW_ROW_PITCH },
      sourceSide: rowEnd && row < rows - 1 ? 'bottom' : forward ? 'right' : 'left',
      targetSide: slot === 0 && row > 0 ? 'top' : forward ? 'left' : 'right',
    }
  })
  return { columns, nodes }
}

export function oppositeFlowSide(side: FlowHandleSide): FlowHandleSide {
  if (side === 'left') return 'right'
  if (side === 'right') return 'left'
  if (side === 'top') return 'bottom'
  return 'top'
}
