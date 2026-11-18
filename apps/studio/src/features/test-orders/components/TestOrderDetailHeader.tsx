import { LeftOutlined, RightOutlined } from '@ant-design/icons'
import { Button, Tooltip } from 'antd'
import type { TestOrder } from '../types'

type Props = {
  order?: TestOrder
  caseTitle?: string
  narrowNav: boolean
  hasPrev: boolean
  hasNext: boolean
  onBackToOrders: () => void
  onBackToCases: () => void
  onPrev: () => void
  onNext: () => void
}

/**
 * 详情页头部：只保留面包屑，不再重复列表工具栏的筛选、进度和操作。
 * 宽屏用两侧箭头切换；窄屏在面包屑右侧显示紧凑切换，避免遮挡正文。
 */
export function TestOrderDetailHeader({
  order,
  caseTitle,
  narrowNav,
  hasPrev,
  hasNext,
  onBackToOrders,
  onBackToCases,
  onPrev,
  onNext,
}: Props) {
  return <div className="tp-list-toolbar test-order-workspace-toolbar test-order-detail-header flex-none">
    <nav className="test-order-workspace-breadcrumb flex min-w-0 flex-[0_1_auto] items-center gap-[7px]" aria-label="面包屑">
      <button
        type="button"
        className="test-order-workspace-crumb-link inline-flex h-6 cursor-pointer items-center whitespace-nowrap rounded-[5px] border-0 bg-transparent px-[5px] text-[13px] leading-none text-[var(--srf-accent)] first:-ml-[5px] hover:bg-[var(--srf-accent-soft)] hover:text-[var(--srf-accent-strong)] hover:underline hover:underline-offset-[3px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--srf-accent)]"
        aria-label="返回测试单列表"
        onClick={onBackToOrders}
      >
        测试单
      </button>
      <span className="test-order-workspace-crumb-sep inline-flex flex-none items-center text-[10px] text-[var(--srf-text-muted)]" aria-hidden="true"><RightOutlined /></span>
      <button
        type="button"
        className="test-order-workspace-crumb-link inline-flex h-6 cursor-pointer items-center whitespace-nowrap rounded-[5px] border-0 bg-transparent px-[5px] text-[13px] leading-none text-[var(--srf-accent)] first:-ml-[5px] hover:bg-[var(--srf-accent-soft)] hover:text-[var(--srf-accent-strong)] hover:underline hover:underline-offset-[3px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--srf-accent)]"
        aria-label={`返回用例列表：${order?.name ?? '测试单'}`}
        title="返回用例列表"
        onClick={onBackToCases}
      >
        {order?.name ?? '测试单'}
      </button>
      <span className="test-order-workspace-crumb-sep inline-flex flex-none items-center text-[10px] text-[var(--srf-text-muted)]" aria-hidden="true"><RightOutlined /></span>
      <h1 className="test-order-workspace-crumb-current m-0 max-w-[min(720px,56vw)] overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-semibold leading-5 text-[var(--srf-text)]" title={caseTitle ?? '用例详情'}>
        {caseTitle ?? '用例详情'}
      </h1>
    </nav>
    {narrowNav ? <div className="test-order-detail-inline-nav flex flex-none items-center gap-0.5 ml-auto">
      <Tooltip title="上一条（↑）">
        <Button
          type="text"
          shape="circle"
          aria-label="上一条"
          icon={<LeftOutlined />}
          disabled={!hasPrev}
          onClick={onPrev}
        />
      </Tooltip>
      <Tooltip title="下一条（↓）">
        <Button
          type="text"
          shape="circle"
          aria-label="下一条"
          icon={<RightOutlined />}
          disabled={!hasNext}
          onClick={onNext}
        />
      </Tooltip>
    </div> : null}
  </div>
}
