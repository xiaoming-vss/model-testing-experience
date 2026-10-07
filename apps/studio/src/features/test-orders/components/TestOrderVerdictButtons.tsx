import { TEST_ORDER_VERDICTS } from '../utils/testOrderExecution'
import '../styles/workspace-verdict-v2.css'

type Props = {
  status?: string
  disabled: boolean
  showShortcuts?: boolean
  reverseOrder?: boolean
  onJudge: (status: string) => void
}

export function TestOrderVerdictButtons({ status, disabled, showShortcuts = false, reverseOrder = false, onJudge }: Props) {
  const verdicts = reverseOrder ? [...TEST_ORDER_VERDICTS].reverse() : TEST_ORDER_VERDICTS
  return <div className="test-order-verdict-grid">
    {verdicts.map((option) => <button
      key={option.value}
      type="button"
      className={`test-order-judge-btn tone-${option.tone}${status === option.value ? ' active' : ''}`}
      disabled={disabled}
      aria-label={`判定该用例为${option.label}`}
      aria-pressed={status === option.value}
      onClick={() => onJudge(option.value)}
    >
      <span>{option.label}</span>
      {showShortcuts ? <span className="test-order-judge-key">{option.key}</span> : null}
    </button>)}
  </div>
}
