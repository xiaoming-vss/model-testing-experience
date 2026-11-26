import type { ReactNode } from 'react'
import { formatBytes } from '@/shared/utils/value'

export function RequestBodyStatus({ json, valid, value, cursor }: { json: boolean; valid: boolean; value: string; cursor?: ReactNode }) {
  const bytes = new TextEncoder().encode(value).length
  const size = formatBytes(bytes)
  return <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--srf-divider)] bg-[var(--srf-hover)] px-4 py-1 text-[11px] leading-[18px] text-[var(--srf-text-secondary)]">
    <div className="flex flex-wrap items-center gap-3">
      <span>{json ? (valid ? '无语法错误' : '存在语法错误') : '无需校验'}</span>
      <span>大小: {size}</span><span>格式: {json ? 'JSON' : '文本'}</span><span>编码: UTF-8</span>
    </div>
    <div className="flex flex-wrap items-center gap-3">{json ? cursor : null}<span>空格: 2</span></div>
  </div>
}
