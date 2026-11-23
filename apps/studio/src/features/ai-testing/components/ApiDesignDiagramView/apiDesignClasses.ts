/** 接口用例设计的语义色与标签文案；颜色只消费已登记的 AI/应用 token。 */

export const METHOD_BASE = 'inline-flex h-5 min-w-[46px] items-center justify-center rounded-[5px] border px-1.5 font-mono text-[10px] font-semibold tracking-[0.03em]'

const METHOD_TONE: Record<string, string> = {
  GET: 'border-[var(--app-accent-border)] bg-[var(--app-accent-surface)] text-[var(--app-accent)]',
  POST: 'border-[var(--app-status-approved-border)] bg-[var(--app-testing-success-tag-bg)] text-[var(--app-testing-success-tag-text)]',
  PATCH: 'border-[var(--app-status-warning-border)] bg-[var(--app-status-warning-bg)] text-[var(--app-status-warning-text)]',
  PUT: 'border-[var(--app-status-review-border)] bg-[var(--app-status-review-bg)] text-[var(--app-status-review-text)]',
  DELETE: 'border-[var(--app-profile-danger-border)] bg-[var(--app-profile-danger-bg)] text-[var(--app-profile-danger-text)]',
}

export function methodTone(method: string) {
  return METHOD_TONE[method] ?? 'border-[var(--app-surface-border)] bg-[var(--app-surface)] text-[var(--ai-text-secondary)]'
}

export const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  positive: '主流程与正常参数',
  negative: '非法输入应被拒绝',
  boundary: '临界值不被误判',
}

type CategoryTone = { label: string; dot: string; chip: string; active: string }

const CATEGORY_TONE: Record<string, CategoryTone> = {
  positive: {
    label: '正向',
    dot: 'bg-[var(--app-result-success-text)]',
    chip: 'border-[var(--app-status-approved-border)] bg-[var(--app-testing-success-tag-bg)] text-[var(--app-testing-success-tag-text)]',
    active: 'border-[var(--app-status-approved-border)] bg-[var(--app-testing-success-tag-bg)] text-[var(--app-result-success-text)]',
  },
  negative: {
    label: '反向',
    dot: 'bg-[var(--app-request-error-text)]',
    chip: 'border-[var(--app-request-error-border)] bg-[var(--app-profile-danger-bg)] text-[var(--app-request-error-text)]',
    active: 'border-[var(--app-request-error-border)] bg-[var(--app-profile-danger-bg)] text-[var(--app-request-error-text)]',
  },
  boundary: {
    label: '边界',
    dot: 'bg-[var(--app-status-warning-text)]',
    chip: 'border-[var(--app-status-warning-border)] bg-[var(--app-status-warning-bg)] text-[var(--app-status-warning-text)]',
    active: 'border-[var(--app-status-warning-border)] bg-[var(--app-status-warning-bg)] text-[var(--app-status-warning-text)]',
  },
}

export const NEUTRAL_FILTER_IDLE = 'border-[var(--app-surface-border)] bg-[var(--app-surface)] text-[var(--ai-text-secondary)]'
export const ACCENT_FILTER_ACTIVE = 'border-[var(--app-accent-border)] bg-[var(--app-accent-surface)] text-[var(--app-accent)]'

export function categoryMeta(category: string): CategoryTone {
  return CATEGORY_TONE[category] ?? {
    label: category || '未分类',
    dot: 'bg-[var(--ai-text-muted)]',
    chip: 'border-[var(--app-surface-border)] bg-[var(--app-surface)] text-[var(--ai-text-secondary)]',
    active: 'border-[var(--app-surface-border)] bg-[var(--app-surface-hover)] text-[var(--ai-text)]',
  }
}

export const CATEGORY_ORDER = ['positive', 'negative', 'boundary']

export const FILTER_BASE = 'inline-flex h-7 items-center gap-1.5 rounded-[7px] border px-2.5 text-[11.5px] transition-colors disabled:cursor-not-allowed disabled:opacity-40'

const PRIORITY_TONE: Record<string, string> = {
  P0: 'border-[var(--app-profile-danger-border)] bg-[var(--app-profile-danger-bg)] text-[var(--app-profile-danger-text)]',
  P1: 'border-[var(--app-accent-border)] bg-[var(--app-accent-surface)] text-[var(--app-accent)]',
  P2: 'border-[var(--app-surface-border)] bg-[var(--app-surface)] text-[var(--ai-text-secondary)]',
}

export function priorityTone(priority: string) {
  return PRIORITY_TONE[priority] ?? 'border-[var(--app-surface-border)] bg-[var(--app-surface)] text-[var(--ai-text-secondary)]'
}

const STATUS_TONE: Record<string, string> = {
  '2xx': 'border-[var(--app-status-approved-border)] bg-[var(--app-testing-success-tag-bg)] text-[var(--app-testing-success-tag-text)]',
  '4xx': 'border-[var(--app-request-error-border)] bg-[var(--app-profile-danger-bg)] text-[var(--app-request-error-text)]',
  '5xx': 'border-[var(--app-status-warning-border)] bg-[var(--app-status-warning-bg)] text-[var(--app-status-warning-text)]',
}

export function statusTone(statusClass: string) {
  return STATUS_TONE[statusClass] ?? 'border-[var(--app-surface-border)] bg-[var(--app-surface)] text-[var(--ai-text-secondary)]'
}

const OP_TONE: Record<string, string> = {
  add: 'border-[var(--app-status-approved-border)] bg-[var(--app-testing-success-tag-bg)] text-[var(--app-testing-success-tag-text)]',
  remove: 'border-[var(--app-request-error-border)] bg-[var(--app-profile-danger-bg)] text-[var(--app-request-error-text)]',
  replace: 'border-[var(--app-status-warning-border)] bg-[var(--app-status-warning-bg)] text-[var(--app-status-warning-text)]',
}

export function patchOpTone(op: string) {
  return OP_TONE[op] ?? 'border-[var(--app-surface-border)] bg-[var(--app-surface)] text-[var(--ai-text-secondary)]'
}

export function expectedStatusLabel(statusClass: string) {
  if (statusClass === '2xx') return '正常返回'
  if (statusClass === '4xx') return '请求被拒绝'
  if (statusClass === '5xx') return '服务端错误'
  return '未声明状态区间'
}

export const SMALL_SECONDARY_TEXT = 'text-[11px] text-[var(--ai-text-secondary)]'
export const STRONG_TEXT = 'font-semibold text-[var(--ai-text)]'
