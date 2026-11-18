import { TEST_ORDER_VERDICTS } from '../utils/testOrderExecution'

type Props = {
  status?: string
  disabled: boolean
  showShortcuts?: boolean
  reverseOrder?: boolean
  layout?: 'grid' | 'flex'
  onJudge: (status: string) => void
}

export function TestOrderVerdictButtons({ status, disabled, showShortcuts = false, reverseOrder = false, layout = 'grid', onJudge }: Props) {
  const verdicts = reverseOrder ? [...TEST_ORDER_VERDICTS].reverse() : TEST_ORDER_VERDICTS
  return <div className={`test-order-verdict-grid ${layout === 'flex' ? 'flex max-w-full flex-wrap gap-2' : 'grid grid-cols-2 gap-2'}`}>
    {verdicts.map((option) => <button
      key={option.value}
      type="button"
      className={`test-order-judge-btn flex min-h-11 flex-[0_0_112px] cursor-pointer items-center justify-between gap-2 rounded-[var(--srf-radius-control)] border border-[var(--srf-tone-border,var(--srf-card-border))] bg-[var(--srf-tone-bg,var(--srf-card))] px-3 py-2 font-[inherit] text-[13px] font-semibold text-[var(--srf-tone-text,var(--srf-text-secondary))] transition-[border-color,box-shadow] duration-150 hover:not-disabled:border-[var(--srf-tone-text,var(--srf-accent))] disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--srf-tone-text,var(--srf-accent))] tone-${option.tone}${status === option.value ? ' active border-[var(--srf-tone-text,var(--srf-accent))] shadow-[inset_0_0_0_1px_var(--srf-tone-text,var(--srf-accent))]' : ''}`}
      disabled={disabled}
      aria-label={`判定该用例为${option.label}`}
      aria-pressed={status === option.value}
      onClick={() => onJudge(option.value)}
    >
      <span>{option.label}</span>
      {showShortcuts ? <span className="test-order-judge-key min-w-[18px] flex-none rounded-[4px] bg-[var(--srf-card)] px-[5px] text-center font-mono text-[10px] leading-4 text-[var(--srf-tone-text,var(--srf-text-muted))]">{option.key}</span> : null}
    </button>)}
  </div>
}
