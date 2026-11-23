import { CheckCircleFilled, WarningFilled } from '@ant-design/icons'

export function RequestJsonValidity({ valid }: { valid: boolean }) {
  return <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-[4px] border border-[var(--srf-tone-border)] bg-[var(--srf-tone-bg)] px-2 py-1 text-[11px] font-semibold leading-4 text-[var(--srf-tone-text)] tone-${valid ? 'green' : 'red'}`}>
    {valid ? <CheckCircleFilled aria-hidden="true" /> : <WarningFilled aria-hidden="true" />}{valid ? 'JSON 合法' : 'JSON 语法错误'}
  </span>
}
