/**
 * 用例类型的色调解读：按关键词归类到共享色盘的色调名。
 *
 * 优先级那套映射被两个 feature 用到，按 S4 上提到了 `shared/utils/priorityTone.ts`。
 */

/** 用例类型的色调。`slate` 是没有匹配到任何关键词时的兜底色。 */
export const CASE_TYPE_TONES = [
  'blue',
  'indigo',
  'purple',
  'teal',
  'green',
  'amber',
  'orange',
  'red',
  'slate',
] as const

export type CaseTypeTone = (typeof CASE_TYPE_TONES)[number]

/**
 * 用例类型的建议值，编辑器（AutoComplete）与用例库的类型筛选共用这一份，避免两处漂移。
 * 后端按 case_type 精确匹配，所以筛选下拉只能给这些确定的值，不给用户手打的自由文本。
 */
export const CASE_TYPE_PRESETS = [
  '功能测试',
  '异常测试',
  '边界测试',
  '流程测试',
  '兼容测试',
  '安全测试',
]

/** 关键词按顺序匹配，先命中先算，所以更具体的关键词要排在前面。 */
const CASE_TYPE_KEYWORDS: Array<[keyword: string, tone: CaseTypeTone]> = [
  ['兼容', 'blue'],
  ['易用', 'amber'],
  ['体验', 'amber'],
  ['功能', 'purple'],
  ['安全', 'red'],
  ['异常', 'orange'],
  ['边界', 'teal'],
  ['流程', 'indigo'],
  ['升级', 'green'],
  ['性能', 'green'],
  ['安装部署', 'indigo'],
]

/**
 * 用例类型是自由文本（编辑器里是 AutoComplete，只有建议值没有枚举），
 * 所以按关键词归色调，认不出来的走兜底色。
 */
export function caseTypeTone(caseType?: string): CaseTypeTone {
  const text = caseType?.trim()
  if (!text) return 'slate'

  for (const [keyword, tone] of CASE_TYPE_KEYWORDS) {
    if (text.includes(keyword)) return tone
  }
  return 'slate'
}
