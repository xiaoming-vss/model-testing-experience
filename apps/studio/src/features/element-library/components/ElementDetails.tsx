import { Alert, Badge, Button, Input, Popconfirm, Typography } from 'antd'
import { useState } from 'react'
import { ActionButton } from '@/shared/components/ActionButton'
import { renderLocatorSample } from '../utils/locatorTemplate'
import styles from '../styles/element-library.module.css'
import type { ElementDetail, VerificationStatus } from '../types'

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  return <Badge status={status === 'verified' ? 'success' : 'warning'} text={status === 'verified' ? '已验证' : '待验证'} />
}

export function ElementDetails({ item, groupName, canWrite, deleting, onEdit, onDelete }: {
  item: ElementDetail
  groupName: string
  canWrite: boolean
  deleting: boolean
  onEdit: () => void
  onDelete: () => void
}) {
  const [samples, setSamples] = useState(new Map<string, string>())
  const [resolved, setResolved] = useState<string | null>(null)
  const [missing, setMissing] = useState(false)
  const parameterized = item.parameters.length > 0

  function preview() {
    if (item.parameters.some(({ name }) => !samples.has(name))) {
      setMissing(true)
      return
    }
    setMissing(false)
    setResolved(renderLocatorSample(item.locatorValue, item.locatorType, samples))
  }

  return <div className="flex min-w-0 flex-col gap-4">
    <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
      <strong className="text-base [overflow-wrap:anywhere]">{item.name}</strong>
      <VerificationBadge status={item.verificationStatus} />
    </div>
    <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 text-xs">
      <dt className="text-[var(--srf-text-secondary)]">所属分组</dt><dd className="m-0">{groupName}</dd>
      <dt className="text-[var(--srf-text-secondary)]">作用范围</dt><dd className="m-0 [overflow-wrap:anywhere]">{item.scope}</dd>
    </dl>
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex items-center justify-between gap-1 text-xs">
        <strong>{parameterized ? '定位模板' : '定位'}</strong><code>{item.locatorType}</code>
      </div>
      <code className={styles.locator}>{item.locatorValue.split(/(\{\{.*?\}\})/g).map((part, index) =>
        part.startsWith('{{') ? <mark className={styles.parameter} key={index}>{part}</mark> : part,
      )}</code>
    </div>
    {parameterized && <section className="flex flex-col gap-2" aria-label="模板参数">
      <strong className="text-xs">模板参数</strong>
      {item.parameters.map(({ name, description }) => <label key={name} className={styles.sample}>
        <span className="flex flex-wrap items-center gap-2 text-xs [overflow-wrap:anywhere]">
          <code className="font-semibold">{name}</code>{description && <Typography.Text type="secondary">{description}</Typography.Text>}
        </span>
        <Input aria-label={name + ' 样例值'} placeholder="输入样例值" value={samples.get(name) ?? ''} onChange={event => {
          setSamples(new Map(samples).set(name, event.target.value))
          setResolved(null)
          setMissing(false)
        }} />
      </label>)}
      {missing && <Alert type="warning" title="请填写模板参数的样例值" />}
      {resolved !== null && <div className="grid gap-1.5" aria-live="polite">
        <strong className="text-xs">解析结果</strong><code className={styles.locator}>{resolved}</code>
      </div>}
    </section>}
    {(canWrite || parameterized) && <div className="flex flex-wrap gap-2 border-t border-[var(--app-surface-border)] pt-3">
      {canWrite && <ActionButton operation="edit" onClick={onEdit}>编辑元素</ActionButton>}
      {parameterized && <Button type="primary" onClick={preview}>解析样例</Button>}
      {canWrite && <Popconfirm title="删除该元素？" onConfirm={onDelete} okButtonProps={{ danger: true, loading: deleting }}>
        <ActionButton operation="delete" iconOnly aria-label="删除元素" />
      </Popconfirm>}
    </div>}
  </div>
}
