import { Tag } from 'antd'
import { cx } from '@/shared/utils/cx'

const TONE: Record<string, string> = {
  get: 'text-[var(--app-http-method-get)] border-[color:color-mix(in_srgb,var(--app-http-method-get)_30%,var(--srf-card-border))] bg-[color:color-mix(in_srgb,var(--app-http-method-get)_10%,var(--srf-card))]',
  post: 'text-[var(--app-http-method-post)] border-[color:color-mix(in_srgb,var(--app-http-method-post)_30%,var(--srf-card-border))] bg-[color:color-mix(in_srgb,var(--app-http-method-post)_10%,var(--srf-card))]',
  put: 'text-[var(--app-http-method-put)] border-[color:color-mix(in_srgb,var(--app-http-method-put)_30%,var(--srf-card-border))] bg-[color:color-mix(in_srgb,var(--app-http-method-put)_10%,var(--srf-card))]',
  patch: 'text-[var(--app-http-method-patch)] border-[color:color-mix(in_srgb,var(--app-http-method-patch)_30%,var(--srf-card-border))] bg-[color:color-mix(in_srgb,var(--app-http-method-patch)_10%,var(--srf-card))]',
  delete: 'text-[var(--app-http-method-delete)] border-[color:color-mix(in_srgb,var(--app-http-method-delete)_30%,var(--srf-card-border))] bg-[color:color-mix(in_srgb,var(--app-http-method-delete)_10%,var(--srf-card))]',
}
const NEUTRAL = 'text-[var(--srf-text-secondary)] border-[var(--srf-card-border)] bg-[var(--srf-chip)]'
const BASE = 'if-method m-0 min-w-12 flex-[0_0_auto] rounded-[5px] border px-1.5 text-center font-[ui-monospace,SFMono-Regular,Menlo,Consolas,monospace] text-[10px] font-bold leading-5 tracking-[0.02em]'

function methodBadgeClass(method: string) {
  const tone = method.toLowerCase()
  return cx('if-method', `if-method-${TONE[tone] ? tone : 'other'}`, BASE, TONE[tone] ?? NEUTRAL)
}

export function MethodBadge({ method, className }: { method: string; className?: string }) {
  return <Tag className={cx(methodBadgeClass(method), className)}>{method}</Tag>
}
