import { FlagOutlined, OrderedListOutlined, ProfileOutlined } from '@ant-design/icons'
import type { TestOrderEntry } from '../types'

type Props = { snapshot?: TestOrderEntry['snapshot'] }

const TH_BASE = 'border-b border-[var(--srf-card-border)] px-[18px] py-3 text-[12px] font-semibold max-[480px]:px-2 max-[480px]:py-3'
const TH_CLASS = `${TH_BASE} bg-[var(--srf-accent-soft)] text-left text-[var(--srf-accent-strong)]`
const TD_CLASS = 'border-b border-[var(--srf-divider)] bg-[var(--srf-card)] px-[18px] py-[22px] align-top whitespace-pre-wrap [overflow-wrap:anywhere] max-[480px]:px-2 max-[480px]:py-3'

export function TestOrderCaseContent({ snapshot }: Props) {
  const preconditions = snapshot?.preconditions ?? []
  const steps = snapshot?.steps ?? []

  return (
    <div className="test-order-case-content flex-none min-w-0 p-6 text-[14px] leading-6 text-[var(--srf-text)] max-narrow:p-4">
      <section className="test-order-section min-w-0" aria-label="前置条件">
        <div className="test-order-content-conditions rounded-[var(--srf-radius-control)] border border-[var(--srf-card-border)] border-l-[3px] border-l-[var(--srf-accent-border)] bg-[var(--srf-hover)] px-5 py-4 max-narrow:p-3">
          <div className="test-order-content-conditions-head mb-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-2 [&_.anticon]:text-[var(--srf-text-secondary)]">
            <h2 className="m-0 inline-flex items-center gap-2 text-[13px] font-semibold leading-6 text-[var(--srf-text)]"><ProfileOutlined aria-hidden="true" />前置条件</h2>
            <span className="text-[11px] leading-[18px] text-[var(--srf-text-secondary)]">{preconditions.length} 项环境与数据依赖</span>
          </div>
          {preconditions.length === 0 ? (
            <p className="test-order-content-empty m-0 text-[12px] text-[var(--srf-text-muted)]">暂无前置条件</p>
          ) : (
            <ol className="test-order-content-preconditions m-0 flex list-none flex-col gap-2 p-0">
              {preconditions.map((text, index) => (
                <li className="flex items-start gap-2.5 rounded-[6px] bg-[var(--srf-card)] px-3 py-2.5 text-[13px] leading-[22px]" key={index}>
                  <span className="test-order-content-condition-no inline-flex h-6 w-6 flex-none items-center justify-center rounded-[6px] bg-[var(--srf-chip)] font-mono text-[11px] font-semibold text-[var(--srf-text-secondary)]">{String(index + 1).padStart(2, '0')}</span>
                  <p className="m-0 min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere]">{text}</p>
                </li>
              ))}
            </ol>
          )}
        </div>
      </section>
      <section className="test-order-section test-order-content-steps mt-6 min-w-0">
        <div className="test-order-content-steps-head mb-4 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <h2 className="m-0 inline-flex items-center gap-2.5 text-[15px] font-semibold leading-6 text-[var(--srf-text)]"><span className="test-order-content-steps-icon inline-flex h-7 w-7 items-center justify-center rounded-[var(--srf-radius-control)] bg-[var(--srf-accent-soft)] text-[var(--srf-accent)]"><OrderedListOutlined aria-hidden="true" /></span>测试执行步骤</h2>
          <span className="text-[11px] leading-[18px] text-[var(--srf-text-secondary)]">{steps.length} 个步骤 · 操作与预期一一对应</span>
        </div>
        <table className="test-order-content-table w-full table-fixed overflow-hidden rounded-[10px] border border-separate border-spacing-0 border-[var(--srf-card-border)] [&_tr:last-child_td]:border-b-0">
          <caption className="absolute h-px w-px overflow-hidden whitespace-nowrap [clip-path:inset(50%)]">测试执行步骤与预期结果</caption>
          <thead>
            <tr>
              <th scope="col" className={`${TH_BASE} w-16 bg-[var(--srf-hover)] text-center text-[var(--srf-text-secondary)] max-[480px]:w-12`}>步骤</th>
              <th scope="col" className={TH_CLASS}><OrderedListOutlined aria-hidden="true" /> 操作说明与测试数据</th>
              <th scope="col" className={TH_CLASS}><FlagOutlined aria-hidden="true" /> 预期结果与断言</th>
            </tr>
          </thead>
          <tbody>
            {steps.length === 0 ? (
              <tr><td colSpan={3} className={`${TD_CLASS} test-order-content-empty m-0 text-[12px] text-[var(--srf-text-muted)]`}>暂无测试步骤</td></tr>
            ) : steps.map((step, index) => (
              <tr key={index}>
                <td className={TD_CLASS}><span className="test-order-content-step-no inline-flex h-8 w-8 flex-none items-center justify-center rounded-[var(--srf-radius-control)] bg-[var(--srf-accent-soft)] font-mono text-[15px] font-semibold text-[var(--srf-accent)]">{String(index + 1).padStart(2, '0')}</span></td>
                <td className={`${TD_CLASS} font-medium`}>{step.action || '—'}</td>
                <td className={`${TD_CLASS} relative pl-11 max-[480px]:pl-7`}>
                  <FlagOutlined className="test-order-content-expected-icon absolute left-[18px] top-6 text-[13px] text-[var(--srf-accent-strong)] max-[480px]:left-2 max-[480px]:top-3.5" aria-hidden="true" />
                  <span>{step.expected || '—'}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
