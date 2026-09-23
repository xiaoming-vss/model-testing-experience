/**
 * 用例优先级 → 共享色盘的色调名（P0 红 / P1 琥珀 / P2 蓝 / P3 灰）。
 *
 * 用例库列表与测试单执行工作台都要给优先级上色，按 STRUCTURE.md S4「被两个以上 feature 使用的代码必须上提」
 * 放在 shared；色调名对应 shared/styles/surface-tokens.css 里的 `.tone-*`。
 */
export type PriorityTone = 'red' | 'amber' | 'blue' | 'slate'

const PRIORITY_TONES: Record<string, PriorityTone> = {
  P0: 'red',
  P1: 'amber',
  P2: 'blue',
  P3: 'slate',
}

/** 认不出来的优先级按最弱的一档（P3 的灰）走。 */
export function priorityTone(priority?: string): PriorityTone {
  const key = priority?.trim().toUpperCase()
  return key ? PRIORITY_TONES[key] ?? 'slate' : 'slate'
}
