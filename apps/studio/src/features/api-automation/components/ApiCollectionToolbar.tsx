import { ArrowLeftOutlined, HistoryOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { Button } from 'antd'

/*
 * API 测试集详情页顶栏：标题、归属与运行操作。
 * 第一行固定标题与右侧动作，第二行承载需求/迭代、环境、更新时间与失效提示；
 * 这样窄屏时动作不会被长标题挤到下一行左对齐。
 */

type Props = {
  collectionName: string
  requirementName: string
  sprintName: string
  /** 最近更新时间，取自测试集自身。 */
  updatedAt: string
  /** 当前启用环境的名称与 Base URL。 */
  environmentName: string
  environmentBaseUrl: string
  runHistoryCount: number
  runningCollection: boolean
  runDisabled: boolean
  canManageCases: boolean
  invalidatedCount: number
  onBack: () => void
  onOpenRunHistory: () => void
  onRunCollection: () => void
  onOpenCaseStatus: () => void
}

export function ApiCollectionToolbar({
  collectionName,
  requirementName,
  sprintName,
  updatedAt,
  environmentName,
  environmentBaseUrl,
  runHistoryCount,
  runningCollection,
  runDisabled,
  canManageCases,
  invalidatedCount,
  onBack,
  onOpenRunHistory,
  onRunCollection,
  onOpenCaseStatus,
}: Props) {
  return (
    <header className="api-wb-toolbar flex flex-none flex-col gap-2 rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] px-4 py-2.5">
      <div className="api-wb-toolbar-row flex flex-wrap items-center justify-between gap-2.5">
        <div className="api-wb-toolbar-main flex min-w-0 flex-auto items-center gap-2">
          <Button
            type="text"
            className="api-wb-toolbar-back"
            icon={<ArrowLeftOutlined />}
            aria-label="返回API测试集列表"
            title="返回API测试集列表"
            onClick={onBack}
          />
          <div className="flex min-w-0 flex-col gap-px">
            <div className="flex min-w-0 items-baseline gap-1.5">
              <span className="api-wb-toolbar-label flex-none text-[11px] font-semibold text-[var(--srf-text-muted)]">API 测试集</span>
              <span className="flex-none text-[var(--srf-text-muted)]" aria-hidden>/</span>
              <h1 className="api-wb-toolbar-title tp-list-title max-w-[320px] truncate text-[15px]">{collectionName}</h1>
            </div>
            <div className="api-wb-toolbar-meta flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[11px] leading-[18px] text-[var(--srf-text-muted)]">
              <span className="api-wb-toolbar-path">/ {requirementName}{sprintName ? ` / ${sprintName}` : ''}</span>
              <span aria-hidden>·</span>
              <span
                className="api-wb-toolbar-env inline-flex max-w-[360px] items-center gap-1.5 rounded-full border border-[var(--srf-card-border)] bg-[var(--srf-chip)] px-2 py-0.5 font-mono text-[11px] leading-[18px] text-[var(--srf-chip-text)]"
                title={environmentBaseUrl || '当前项目还没有可用环境'}
              >
                <span className={`api-wb-toolbar-env-dot h-1.5 w-1.5 flex-none rounded-full ${environmentBaseUrl ? 'bg-[var(--srf-result-passed)]' : 'bg-[var(--srf-result-skipped)]'}`} aria-hidden="true" />
                {environmentName ? <span className="flex-none">{environmentName}</span> : null}
                {environmentName ? <span aria-hidden className="opacity-50">·</span> : null}
                <span className="truncate">{environmentBaseUrl || '未选择环境'}</span>
              </span>
              <span aria-hidden>·</span>
              <span className="api-wb-toolbar-updated">更新 {updatedAt}</span>
              {invalidatedCount > 0 ? (
                <>
                  <span aria-hidden>·</span>
                  <span className="api-wb-toolbar-invalidated text-[var(--app-status-warning-text)]">
                    运行将排除 {invalidatedCount} 条失效用例
                  </span>
                </>
              ) : null}
            </div>
          </div>
        </div>

        <div className="api-wb-toolbar-actions flex flex-wrap items-center gap-2">
          <Button className="api-wb-toolbar-case-status" disabled={!canManageCases} onClick={onOpenCaseStatus}>
            用例状态
          </Button>
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
    </header>
  )
}
