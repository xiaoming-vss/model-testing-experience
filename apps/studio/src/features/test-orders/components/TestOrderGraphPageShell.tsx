import type { ReactNode } from 'react'
import { MtxLogo } from '@/shared/components/MtxLogo/MtxLogo'
import { ThemeSelect } from '@/shared/components/ThemeSelect'
import { getTestOrderEntryStatusMeta, getTestOrderEntryStatusTone } from '../utils/testOrderStatus'
import type { TestOrder } from '../types'
import '@/shared/styles/surface-tokens.css'

type Props = {
  order?: TestOrder
  projectName?: string
  sprintName?: string
  children: ReactNode
}

export function TestOrderGraphPageShell({ order, projectName, sprintName, children }: Props) {
  const pending = Math.max(0, (order?.entriesTotal ?? 0) - (order?.entriesExecuted ?? 0))
  return (
    <div className="test-order-graph-page tp-surface flex h-dvh min-h-0 flex-col bg-[var(--ant-color-bg-layout)] text-[var(--srf-text)]">
      <header className="test-order-graph-page-brandbar flex flex-none flex-wrap items-center gap-4 border-b border-[var(--srf-card-border)] bg-[var(--srf-card)] px-5 py-2.5 max-[600px]:gap-2.5 max-[600px]:px-[var(--app-page-gutter)] max-[600px]:py-2">
        <div className="test-order-graph-page-brand flex items-center gap-2 text-[16px]"><MtxLogo size={30} /><strong>MTX</strong></div>
        <nav className="test-order-graph-page-context flex min-w-0 flex-1 flex-wrap items-center gap-2 text-[12px] text-[var(--srf-text-secondary)] [overflow-wrap:anywhere] max-[600px]:basis-[60%] [&_span+span]:before:mr-2 [&_span+span]:before:text-[var(--srf-text-muted)] [&_span+span]:before:content-['/']" aria-label="图谱所属范围">
          {projectName ? <span>{projectName}</span> : null}
          {sprintName ? <span>{sprintName}</span> : null}
          {order ? <span>测试单 {order.name}</span> : null}
        </nav>
        <ThemeSelect />
      </header>
      <main className="test-order-graph-page-main flex min-h-0 flex-1 flex-col px-[var(--app-page-gutter)] pb-4">
        <section className="test-order-graph-page-heading flex flex-none flex-wrap items-center gap-3 px-2 py-[18px] [overflow-wrap:anywhere] max-[600px]:gap-2 max-[600px]:px-0 max-[600px]:py-3" aria-label="测试单概况">
          <h1 className="m-0 text-xl font-semibold">用例图谱</h1>
          {order ? <>
            <span className="tp-tone-tag whitespace-normal tone-blue">{order.name}</span>
            {order.testedVersion ? <span className="test-order-graph-page-secondary text-[12px] text-[var(--srf-text-secondary)]">被测版本 {order.testedVersion}</span> : null}
            <span className="test-order-graph-page-secondary text-[12px] text-[var(--srf-text-secondary)]">已执行 {order.entriesExecuted ?? 0} / {order.entriesTotal ?? 0}</span>
            <div className="test-order-graph-page-counts ml-auto flex items-center gap-2">
              {[{ status: 'failed', count: order.entriesFailed ?? 0 }, { status: 'pending', count: pending }].map(({ status, count }) => (
                <span key={status} className={`tp-tone-tag whitespace-normal tone-${getTestOrderEntryStatusTone(status)}`}>
                  {getTestOrderEntryStatusMeta(status).label} {count}
                </span>
              ))}
            </div>
          </> : null}
        </section>
        <div className="test-order-graph-page-content flex min-h-0 flex-1 overflow-hidden rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] [&>.test-order-graph-viewer]:min-w-0 [&>.test-order-graph-viewer]:flex-1">{children}</div>
      </main>
    </div>
  )
}
