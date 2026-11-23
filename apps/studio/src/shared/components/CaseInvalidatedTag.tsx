import { Tooltip } from 'antd'
import { invalidatedAtText } from '@/shared/utils/caseInvalidation'

type Props = {
  invalidatedAt?: string | null
  className?: string
}

/** 用例失效标签；悬停显示失效时间，避免列表里常驻时间文本。 */
export function CaseInvalidatedTag({ invalidatedAt, className = '' }: Props) {
  if (!invalidatedAt) return null
  return (
    <Tooltip title={`失效时间：${invalidatedAtText(invalidatedAt)}`}>
      <span className={`tp-tone-tag tone-orange ${className}`.trim()}>● 已失效</span>
    </Tooltip>
  )
}
