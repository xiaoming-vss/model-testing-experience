import { type RunResultView, runResultViewOptions } from '../config/collectionConfig'
import { getExecutionStatusMeta } from '../utils/collectionRunReport'
import { renderRunResultContent } from '../utils/renderApiRunResult'
import type { ApiCaseRunResult } from '@/services/api'
import { Alert } from 'antd'

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

export function ApiCaseRunConsole({ result, environmentName, view, onViewChange }: Props) {
  const status = result.status ?? (result.success ? 'success' : 'failed')
  const statusMeta = getExecutionStatusMeta(status)
  const tone = resolveStatusTone(status)
  const extractResults = result.extractResults ?? []
  const assertResults = result.assertResults ?? []
  const failedExtractCount = extractResults.filter((item) => !item.success).length
  const failedAssertCount = assertResults.filter((item) => !item.success).length
  const passedAssertCount = assertResults.length - failedAssertCount
  const statusCode = result.response?.statusCode

  const viewTabs = runResultViewOptions.map((option) => ({
    ...option,
    label: option.value === 'response' ? `${option.label} (JSON)` : option.label,
    count:
      option.value === 'extract' ? extractResults.length : option.value === 'assert' ? assertResults.length : 0,
  }))

  return (
    <div className="api-wb-console">
      <div className="api-wb-console-banner">
        <div className="api-wb-console-banner-main">
          <span className="api-wb-console-title">请求结果</span>
          <span className={`api-wb-status tone-${tone}`}>
            <span className="api-wb-status-dot" aria-hidden="true" />
            {statusCode ? `${statusCode} · ` : ''}
            {statusMeta.label}
          </span>
          <span className="api-wb-console-meta">
            <span>耗时 <strong>{result.durationMs ?? 0} ms</strong></span>
            <span>大小 <strong>{formatResponseSize(result.response?.body)}</strong></span>
            <span>环境 <strong>{environmentName}</strong></span>
            <span>提取失败 <strong>{failedExtractCount}</strong></span>
          </span>
        </div>
        <div className="api-wb-console-verdict">
          {assertResults.length === 0 ? (
            <span className="api-wb-assert-summary tone-slate">没有断言规则</span>
          ) : failedAssertCount === 0 ? (
            <span className="api-wb-assert-summary tone-green">
              断言全部通过 ({passedAssertCount}/{assertResults.length})
            </span>
          ) : (
            <span className="api-wb-assert-summary tone-red">
              断言失败 {failedAssertCount}/{assertResults.length}
            </span>
          )}
        </div>
      </div>

      {result.errorMessage ? (
        <Alert showIcon type="error" title={result.errorMessage} className="api-wb-console-alert" />
      ) : null}

      <div className="api-wb-console-tabs" role="tablist">
        {viewTabs.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={view === tab.value}
            className={`api-wb-console-tab${view === tab.value ? ' active' : ''}`}
            onClick={() => onViewChange(tab.value)}
          >
            {tab.label}
            {tab.count > 0 ? <span className="api-wb-console-tab-count">{tab.count}</span> : null}
          </button>
        ))}
      </div>

      <div className="api-wb-console-body">
        {renderRunResultContent({
          view,
          request: result.request,
          response: result.response,
          extractResults,
          assertResults,
        })}
      </div>

      <div className="api-wb-console-foot">
        {assertResults.length === 0 ? (
          <span className="api-wb-console-foot-empty">没有断言结果</span>
        ) : (
          assertResults.map((item, index) => (
            <span
              key={item.assertRuleId ?? index}
              className={`api-wb-console-foot-item${item.success ? '' : ' failed'}`}
            >
              {item.name ?? `断言 ${index + 1}`}（{item.success ? 'PASS' : 'FAIL'}）
            </span>
          ))
        )}
      </div>
    </div>
  )
}
