import { RunWaitingReason } from '@/domain/runs/RunWaitingReason'
import { type RunResultView, runResultViewOptions } from '../config/collectionConfig'
import { getExecutionStatusMeta } from '../utils/collectionRunReport'
import { renderRunResultContent } from '../utils/renderApiRunResult'
import type { ApiCaseRunResult } from '@/services/api'
import { Alert } from 'antd'
import { StopRunButton } from '@/domain/runs/StopRunButton'
import { getApiCaseRunId } from '../utils/detailView'
import { cx } from '@/shared/utils/cx'
import styles from '@/shared/styles/run-view.module.css'
import { useMemo } from 'react'

/*
 * API 用例运行结果控制台：设计稿里是右栏下半部分的一条独立区域
 * （状态横幅 + 断言简报 + 视图切换条 + 内容区 + 底部逐条断言状态）。
 * 视图切换条替代了原来的 Segmented——设计稿画的是文字页签，计数也放在页签上。
 * 内容区仍走共用的 renderRunResultContent（测试集运行报告弹窗也用它）。
 */

type Props = {
  result: ApiCaseRunResult
  environmentName: string
  view: RunResultView
  onViewChange: (view: RunResultView) => void
  canStop?: boolean
}

/** 运行状态 → 色盘色调，取值来自 shared/styles/surface-tokens.css 的 `.tone-*`。 */
function resolveStatusTone(status?: string) {
  switch (status) {
    case 'success':
      return 'green'
    case 'failed':
    case 'error':
      return 'red'
    case 'running':
    case 'pending':
      return 'amber'
    default:
      return 'slate'
  }
}

function formatResponseSize(body?: string) {
  if (!body) return '-'
  const bytes = new TextEncoder().encode(body).length
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(2)} KB`
}

export function ApiCaseRunConsole({ result, environmentName, view, onViewChange, canStop }: Props) {
  const status = result.status ?? (result.success ? 'success' : 'failed')
  const statusMeta = getExecutionStatusMeta(status)
  const tone = resolveStatusTone(status)
  const extractResults = useMemo(() => result.extractResults ?? [], [result.extractResults])
  const assertResults = useMemo(() => result.assertResults ?? [], [result.assertResults])
  const failedExtractCount = extractResults.filter((item) => !item.success).length
  const failedAssertCount = assertResults.filter((item) => !item.success).length
  const passedAssertCount = assertResults.length - failedAssertCount
  const statusCode = result.response?.statusCode
  const responseSize = useMemo(() => formatResponseSize(result.response?.body), [result.response?.body])
  const resultContent = useMemo(() => renderRunResultContent({
    view,
    request: result.request,
    response: result.response,
    extractResults,
    assertResults,
  }), [assertResults, extractResults, result.request, result.response, view])

  const viewTabs = runResultViewOptions.map((option) => ({
    ...option,
    label: option.value === 'response' ? `${option.label} (JSON)` : option.label,
    count:
      option.value === 'extract' ? extractResults.length : option.value === 'assert' ? assertResults.length : 0,
  }))

  return (
    <div className={cx('api-wb-console flex h-full flex-col overflow-hidden bg-[var(--srf-hover)]', styles.root)} data-tab-motion-scope>
      <div className="api-wb-console-banner flex flex-wrap items-center justify-between gap-2 border-b border-[var(--srf-divider)] bg-[var(--srf-card)] px-4 py-2">
        <div className="api-wb-console-banner-main flex min-w-0 flex-wrap items-center gap-2.5">
          <span className="api-wb-console-title text-[12px] font-bold text-[var(--srf-text)]">请求结果</span>
          <span className={`api-wb-status inline-flex items-center gap-1.5 rounded-full border border-[var(--srf-tone-border)] bg-[var(--srf-tone-bg)] px-2 py-0.5 text-[11px] font-semibold leading-4 text-[var(--srf-tone-text)] tone-${tone}`}>
            <span className="api-wb-status-dot h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
            {statusCode ? `${statusCode} · ` : ''}
            {statusMeta.label}
          </span>
          <RunWaitingReason status={status} />
          <span className="api-wb-console-meta flex flex-wrap items-center gap-2.5 text-[11px] text-[var(--srf-text-muted)]">
            <span>耗时 <strong className="font-mono font-semibold text-[var(--srf-text-secondary)]">{result.durationMs ?? 0} ms</strong></span>
            <span>大小 <strong className="font-mono font-semibold text-[var(--srf-text-secondary)]">{responseSize}</strong></span>
            <span>环境 <strong className="font-mono font-semibold text-[var(--srf-text-secondary)]">{environmentName}</strong></span>
            <span>提取失败 <strong className="font-mono font-semibold text-[var(--srf-text-secondary)]">{failedExtractCount}</strong></span>
          </span>
        </div>
        <div className="api-wb-console-verdict">
          {canStop ? <StopRunButton kind="api-case" runId={getApiCaseRunId(result)} status={status} /> : null}
          {assertResults.length === 0 ? (
            <span className="api-wb-assert-summary rounded-full border border-[var(--srf-tone-border)] bg-[var(--srf-tone-bg)] px-2 py-0.5 text-[11px] font-semibold leading-4 text-[var(--srf-tone-text)] tone-slate">没有断言规则</span>
          ) : failedAssertCount === 0 ? (
            <span className="api-wb-assert-summary rounded-full border border-[var(--srf-tone-border)] bg-[var(--srf-tone-bg)] px-2 py-0.5 text-[11px] font-semibold leading-4 text-[var(--srf-tone-text)] tone-green">
              断言全部通过 ({passedAssertCount}/{assertResults.length})
            </span>
          ) : (
            <span className="api-wb-assert-summary rounded-full border border-[var(--srf-tone-border)] bg-[var(--srf-tone-bg)] px-2 py-0.5 text-[11px] font-semibold leading-4 text-[var(--srf-tone-text)] tone-red">
              断言失败 {failedAssertCount}/{assertResults.length}
            </span>
          )}
        </div>
      </div>

      {result.errorMessage ? (
        <Alert showIcon type="error" title={result.errorMessage} className="api-wb-console-alert mx-4 mt-2.5" />
      ) : null}

      <div className="api-wb-console-tabs flex flex-wrap items-center gap-4 border-b border-[var(--srf-divider)] bg-[var(--srf-card)] px-4" role="tablist" data-tab-motion-scoped>
        {viewTabs.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={view === tab.value}
            className={`api-wb-console-tab inline-flex cursor-pointer items-center gap-1.5 border-0 border-b-2 bg-transparent py-2 text-[12px] transition-colors hover:text-[var(--srf-text)]${view === tab.value ? ' active border-b-[var(--srf-accent)] font-semibold text-[var(--srf-accent)]' : ' border-b-transparent text-[var(--srf-text-secondary)]'}`}
            onClick={() => onViewChange(tab.value)}
          >
            {tab.label}
            {tab.count > 0 ? <span className="api-wb-console-tab-count rounded-full bg-[var(--srf-chip)] px-[5px] font-mono text-[10px] leading-4 text-[var(--srf-text-secondary)]">{tab.count}</span> : null}
          </button>
        ))}
      </div>

      <div className="api-wb-console-body min-h-0 flex-auto overflow-auto px-4 py-3" data-tab-motion-panel>
        {resultContent}
      </div>

      <div className="api-wb-console-foot flex flex-wrap items-center gap-3.5 border-t border-[var(--srf-divider)] bg-[var(--srf-card)] px-4 py-2">
        {assertResults.length === 0 ? (
          <span className="api-wb-console-foot-empty text-[11px] text-[var(--srf-text-muted)]">没有断言结果</span>
        ) : (
          assertResults.map((item, index) => (
            <span
              key={item.assertRuleId ?? index}
              className={`api-wb-console-foot-item text-[11px] ${item.success ? 'text-[var(--srf-result-passed)]' : 'failed text-[var(--srf-result-failed)]'}`}
            >
              {item.name ?? `断言 ${index + 1}`}（{item.success ? 'PASS' : 'FAIL'}）
            </span>
          ))
        )}
      </div>
    </div>
  )
}
