import { FlagOutlined, OrderedListOutlined, ProfileOutlined } from '@ant-design/icons'
import type { TestOrderEntry } from '../types'

type Props = { snapshot?: TestOrderEntry['snapshot'] }

export function TestOrderCaseContent({ snapshot }: Props) {
  const preconditions = snapshot?.preconditions ?? []
  const steps = snapshot?.steps ?? []

  return (
    <div className="test-order-case-content flex-none min-w-0 p-6 text-[14px] leading-6 text-[var(--srf-text)] max-narrow:p-4">
      <section className="test-order-section min-w-0" aria-label="前置条件">
        <div className="test-order-content-conditions px-5 py-4 max-narrow:p-3">
          <div className="test-order-content-conditions-head mb-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
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
        <table className="test-order-content-table">
          <caption>测试执行步骤与预期结果</caption>
          <thead>
            <tr>
              <th scope="col">步骤</th>
              <th scope="col"><OrderedListOutlined aria-hidden="true" /> 操作说明与测试数据</th>
              <th scope="col"><FlagOutlined aria-hidden="true" /> 预期结果与断言</th>
            </tr>
          </thead>
          <tbody>
            {steps.length === 0 ? (
              <tr><td colSpan={3} className="test-order-content-empty m-0 text-[12px] text-[var(--srf-text-muted)]">暂无测试步骤</td></tr>
            ) : steps.map((step, index) => (
              <tr key={index}>
                <td><span className="test-order-content-step-no inline-flex h-8 w-8 flex-none items-center justify-center rounded-[var(--srf-radius-control)] bg-[var(--srf-accent-soft)] font-mono text-[15px] font-semibold text-[var(--srf-accent)]">{String(index + 1).padStart(2, '0')}</span></td>
                <td>{step.action || '—'}</td>
                <td>
                  <FlagOutlined className="test-order-content-expected-icon" aria-hidden="true" />
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
