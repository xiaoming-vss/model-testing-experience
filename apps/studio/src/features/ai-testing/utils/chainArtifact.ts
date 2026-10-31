import { parse, parseDocument, visit } from 'yaml'

export type ChainVisualRow = { label: string; value: string }
export type ChainVisualGroup = {
  key: string
  kind: string
  title: string
  subtitle?: string
  rows: ChainVisualRow[]
}
export type DiffLine = { type: 'same' | 'add' | 'remove'; text: string }

const MAX_VALUE = 180

function text(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    return value
      .map(item => (typeof item === 'object' ? JSON.stringify(item) : String(item)))
      .join('、')
      .slice(0, MAX_VALUE)
  }
  if (typeof value === 'object') {
    const raw = JSON.stringify(value)
    return raw.length > MAX_VALUE ? `${raw.slice(0, MAX_VALUE)}…` : raw
  }
  return String(value)
}

export function parseArtifact(content: string): unknown {
  const source = content.trim()
  if (!source) return undefined
  try {
    return parse(source)
  } catch {
    return undefined
  }
}

function titleOf(item: Record<string, unknown>, index: number): string {
  const title = item.title ?? item.name ?? item.caseName ?? item.case_name
  if (typeof title === 'string' && title.trim()) return title.trim()
  const id = item.caseId ?? item.case_id ?? item.id ?? item.pageId ?? item.moduleId
  if (typeof id === 'string' && id.trim()) return id.trim()
  return `第 ${index + 1} 项`
}

function rowsOf(item: Record<string, unknown>, skip: string[]): ChainVisualRow[] {
  const rows: ChainVisualRow[] = []
  for (const [label, value] of Object.entries(item)) {
    if (skip.includes(label)) continue
    if (value === null || value === undefined || value === '') continue
    if (label === 'stepsJson' || label === 'steps') {
      if (!Array.isArray(value)) continue
      value.forEach((step, index) => {
        if (typeof step !== 'object' || step === null) {
          rows.push({ label: `步骤 ${index + 1}`, value: text(step) })
          return
        }
        const record = step as Record<string, unknown>
        const action = record.stepName ?? record.action ?? record.keyword ?? ''
        const expected = record.expected ?? record.expectation ?? record.operationValue
        rows.push({
          label: `步骤 ${index + 1}`,
          value: [text(action), text(expected)].filter(Boolean).join(' → '),
        })
      })
      continue
    }
    if (label === 'content' && typeof value === 'object' && value !== null) {
      const content = value as Record<string, unknown>
      for (const [contentLabel, contentValue] of Object.entries(content)) {
        if (contentValue === null || contentValue === undefined || contentValue === '') continue
        rows.push({ label: contentLabel, value: text(contentValue) })
      }
      continue
    }
    rows.push({ label, value: text(value) })
  }
  return rows
}

function itemGroup(
  item: Record<string, unknown>,
  index: number,
  kind: string,
): ChainVisualGroup {
  const title = titleOf(item, index)
  const scenario = item.scenario ?? item.module ?? item.page ?? item.pageId
  return {
    key: `${kind}-${index}-${title}`,
    kind,
    title,
    subtitle: typeof scenario === 'string' ? scenario : undefined,
    rows: rowsOf(item, ['title', 'name', 'caseName', 'case_name', 'module', 'scenario', 'page']),
  }
}

function listGroups(value: unknown[], kind: string): ChainVisualGroup[] {
  const grouped = new Map<string, ChainVisualGroup>()
  value.forEach((entry, index) => {
    if (typeof entry !== 'object' || entry === null) {
      const key = `${kind}-${index}`
      grouped.set(key, { key, kind, title: `第 ${index + 1} 项`, rows: [{ label: '内容', value: text(entry) }] })
      return
    }
    const item = entry as Record<string, unknown>
    const group = itemGroup(item, index, kind)
    const scenario = item.scenario ?? item.module ?? item.page
    if (typeof scenario === 'string' && scenario.trim()) {
      const groupKey = `${kind}-${scenario}`
      const existing = grouped.get(groupKey)
      if (existing) {
        existing.rows.push({
          label: group.title,
          value: group.rows.map(row => `${row.label}：${row.value}`).join('；'),
        })
      } else {
        grouped.set(groupKey, {
          ...group,
          key: groupKey,
          title: scenario.trim(),
          rows: [{
            label: group.title,
            value: group.rows.map(row => `${row.label}：${row.value}`).join('；'),
          }],
        })
      }
      return
    }
    grouped.set(group.key, group)
  })
  return [...grouped.values()]
}

export function buildVisualGroups(content: string): ChainVisualGroup[] {
  const data = parseArtifact(content)
  if (data === undefined) return []
  if (Array.isArray(data)) return listGroups(data, '条目')
  if (typeof data !== 'object' || data === null) {
    return [{ key: 'scalar', kind: '内容', title: '产物内容', rows: [{ label: '内容', value: text(data) }] }]
  }
  const record = data as Record<string, unknown>
  const groups: ChainVisualGroup[] = []
  for (const [key, value] of Object.entries(record)) {
    if (!Array.isArray(value) || !value.length) continue
    groups.push(...listGroups(value, key))
  }
  if (!groups.length) {
    groups.push({
      key: 'object',
      kind: '内容',
      title: '产物内容',
      rows: rowsOf(record, []),
    })
  }
  return groups
}

function boundedDiff(before: string[], after: string[]): DiffLine[] {
  if (before.length * after.length > 250_000) {
    let prefix = 0
    while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) prefix++
    let suffix = 0
    while (
      suffix < before.length - prefix &&
      suffix < after.length - prefix &&
      before[before.length - 1 - suffix] === after[after.length - 1 - suffix]
    ) {
      suffix++
    }
    return [
      ...before.slice(0, prefix).map(line => ({ type: 'same' as const, text: line })),
      ...before.slice(prefix, before.length - suffix).map(line => ({ type: 'remove' as const, text: line })),
      ...after.slice(prefix, after.length - suffix).map(line => ({ type: 'add' as const, text: line })),
      ...before.slice(before.length - suffix).map(line => ({ type: 'same' as const, text: line })),
    ]
  }
  const dp = Array.from({ length: before.length + 1 }, () => new Array<number>(after.length + 1).fill(0))
  for (let i = before.length - 1; i >= 0; i--) {
    for (let j = after.length - 1; j >= 0; j--) {
      dp[i][j] = before[i] === after[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }
  const lines: DiffLine[] = []
  let i = 0
  let j = 0
  while (i < before.length && j < after.length) {
    if (before[i] === after[j]) {
      lines.push({ type: 'same', text: before[i] })
      i++
      j++
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      lines.push({ type: 'remove', text: before[i++] })
    } else {
      lines.push({ type: 'add', text: after[j++] })
    }
  }
  while (i < before.length) lines.push({ type: 'remove', text: before[i++] })
  while (j < after.length) lines.push({ type: 'add', text: after[j++] })
  return lines
}

export function formatDiffArtifact(content: string): string {
  if (!content.trim()) return ''
  try {
    return JSON.stringify(JSON.parse(content), null, 2)
  } catch {
    try {
      const document = parseDocument(content)
      const value: unknown = document.errors.length ? undefined : document.toJS()
      if (typeof value === 'object' && value !== null) {
        visit(document, { Collection: (_key, node) => { node.flow = false } })
        return document.toString({ indent: 2, lineWidth: 0 }).trimEnd()
      }
    } catch { /* Unparseable artifacts remain readable as their original text. */ }
    return content.replace(/\r\n/g, '\n')
  }
}

export type DiffCell = { text: string; lineNumber: number; changed: boolean }
export type SplitDiffRow = { before?: DiffCell; after?: DiffCell }

export function splitDiffLines(lines: DiffLine[]): SplitDiffRow[] {
  const rows: SplitDiffRow[] = []
  let beforeNumber = 0
  let afterNumber = 0
  let index = 0
  while (index < lines.length) {
    const line = lines[index]
    if (line.type === 'same') {
      rows.push({
        before: { text: line.text, lineNumber: ++beforeNumber, changed: false },
        after: { text: line.text, lineNumber: ++afterNumber, changed: false },
      })
      index++
      continue
    }
    const removed: DiffCell[] = []
    const added: DiffCell[] = []
    while (index < lines.length && lines[index].type !== 'same') {
      const change = lines[index++]
      if (change.type === 'remove') removed.push({ text: change.text, lineNumber: ++beforeNumber, changed: true })
      else added.push({ text: change.text, lineNumber: ++afterNumber, changed: true })
    }
    for (let i = 0; i < Math.max(removed.length, added.length); i++) {
      rows.push({ before: removed[i], after: added[i] })
    }
  }
  return rows
}

export function diffArtifact(before: string, after: string): DiffLine[] {
  before = formatDiffArtifact(before)
  after = formatDiffArtifact(after)
  if (!before && !after) return []
  if (!before.trim()) return after.split('\n').map(text => ({ type: 'add' as const, text }))
  return boundedDiff(before.split('\n'), after.split('\n'))
}

export function diffStats(lines: DiffLine[]): { add: number; remove: number } {
  return lines.reduce(
    (result, line) => {
      if (line.type === 'add') result.add++
      if (line.type === 'remove') result.remove++
      return result
    },
    { add: 0, remove: 0 },
  )
}
