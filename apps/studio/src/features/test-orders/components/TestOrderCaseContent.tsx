import { FlagOutlined, OrderedListOutlined, ProfileOutlined } from '@ant-design/icons'
import type { TestOrderEntry } from '../types'
import '../styles/workspace-content-v3.css'

type Props = { snapshot?: TestOrderEntry['snapshot'] }

export function TestOrderCaseContent({ snapshot }: Props) {
  const preconditions = snapshot?.preconditions ?? []
  const steps = snapshot?.steps ?? []

  return (
    <div className="test-order-case-content">
      <section className="test-order-section" aria-label="前置条件">
        <div className="test-order-content-conditions">
          <div className="test-order-content-conditions-head">
            <h2><ProfileOutlined aria-hidden="true" />前置条件</h2>
            <span>{preconditions.length} 项环境与数据依赖</span>
          </div>
          {preconditions.length === 0 ? (
            <p className="test-order-content-empty">暂无前置条件</p>
          ) : (
            <ol className="test-order-content-preconditions">
              {preconditions.map((text, index) => (
                <li key={index}>
                  <span className="test-order-content-condition-no">{String(index + 1).padStart(2, '0')}</span>
                  <p>{text}</p>
                </li>
              ))}
            </ol>
          )}
        </div>
      </section>
      <section className="test-order-section test-order-content-steps">
        <div className="test-order-content-steps-head">
          <h2><span className="test-order-content-steps-icon"><OrderedListOutlined aria-hidden="true" /></span>测试执行步骤</h2>
          <span>{steps.length} 个步骤 · 操作与预期一一对应</span>
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
              <tr><td colSpan={3} className="test-order-content-empty">暂无测试步骤</td></tr>
            ) : steps.map((step, index) => (
              <tr key={index}>
                <td><span className="test-order-content-step-no">{String(index + 1).padStart(2, '0')}</span></td>
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
