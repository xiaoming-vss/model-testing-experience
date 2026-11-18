import { ArrowLeftOutlined, HistoryOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { Button } from 'antd'

/*
 * API 测试集详情页顶栏：返回 / 测试集名 + 需求 + 迭代 / 当前环境 / 运行记录 / 运行测试集。
 * 设计稿把这几项画在同一行；测试集与需求的层级信息原来在侧栏头部和「Collection 详情」卡片里，
 * 这里合到顶栏后那两块就不再需要。样式见 styles/api-detail-shell.module.css。
 */

type Props = {
  collectionName: string
  requirementName: string
  sprintName: string
  /** 最近更新时间，取自测试集自身。 */
  updatedAt: string
  /** 当前启用环境的 Base URL，没有环境时为空。 */
  environmentBaseUrl: string
  runHistoryCount: number
  runningCollection: boolean
  runDisabled: boolean
  onBack: () => void
  onOpenRunHistory: () => void
  onRunCollection: () => void
}

export function ApiCollectionToolbar({
  collectionName,
  requirementName,
  sprintName,
  updatedAt,
  environmentBaseUrl,
  runHistoryCount,
  runningCollection,
  runDisabled,
  onBack,
  onOpenRunHistory,
  onRunCollection,
}: Props) {
  return (
    <div className="api-wb-toolbar flex flex-none flex-wrap items-center justify-between gap-2.5 rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] px-4 py-2.5">
      <div className="api-wb-toolbar-main flex min-w-0 flex-wrap items-center gap-2.5">
        <Button
          type="text"
          className="api-wb-toolbar-back"
          icon={<ArrowLeftOutlined />}
          aria-label="返回API测试集列表"
          title="返回API测试集列表"
          onClick={onBack}
        />
        <h1 className="api-wb-toolbar-title m-0 flex min-w-0 flex-wrap items-baseline gap-1.5 text-[14px] font-bold leading-[22px] text-[var(--srf-text)]">
          <span className="api-wb-toolbar-label font-semibold text-[var(--srf-text-secondary)]">Collection 详情:</span>
          <span className="api-wb-toolbar-name text-[var(--srf-text)]">{collectionName}</span>
          <span className="api-wb-toolbar-path text-[12px] font-medium text-[var(--srf-text-muted)]">/ {requirementName} / {sprintName}</span>
        </h1>
        <span
          className="api-wb-toolbar-env inline-flex max-w-[320px] items-center gap-1.5 overflow-hidden text-ellipsis whitespace-nowrap rounded-[var(--srf-radius-control)] border border-[var(--srf-card-border)] bg-[var(--srf-chip)] px-2 py-0.5 font-mono text-[11px] leading-[18px] text-[var(--srf-chip-text)]"
          title={environmentBaseUrl || '当前项目还没有可用环境'}
        >
          <span className={`api-wb-toolbar-env-dot h-1.5 w-1.5 flex-none rounded-full ${environmentBaseUrl ? 'bg-[var(--srf-result-passed)]' : 'bg-[var(--srf-result-skipped)]'}`} aria-hidden="true" />
          {environmentBaseUrl || '未选择环境'}
        </span>
        <span className="api-wb-toolbar-updated text-[12px] text-[var(--srf-text-muted)]">更新 {updatedAt}</span>
      </div>

      <div className="api-wb-toolbar-actions flex flex-wrap items-center gap-2">
        <Button className="api-wb-toolbar-history" icon={<HistoryOutlined />} onClick={onOpenRunHistory}>
          运行记录{runHistoryCount > 0 ? ` (${runHistoryCount})` : ''}
        </Button>
        <Button
          type="primary"
          className="api-wb-toolbar-run"
          icon={<PlayCircleOutlined />}
          loading={runningCollection}
          disabled={runDisabled}
          onClick={onRunCollection}
        >
          运行测试集
        </Button>
      </div>
    </div>
  )
}
