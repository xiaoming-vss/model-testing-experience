import type { ApiAssertComparator, ApiAssertSource, ApiCollectionRunItem, ApiCollectionRunReport } from '@/services/api'
import { formatTime } from '@/utils/format'
import { assertComparatorLabelMap, assertSourceLabelMap } from '../config/collectionConfig'
import { formatOptionalValue, parseMaybeJsonValue } from './apiCaseEditor'

function escapeHtml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function stringifyForReport(value: unknown) {
  if (value === undefined || value === null || value === '') return '-'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

export function sanitizeFileName(value: string) {
  const sanitized = Array.from(value, (character) => {
    const code = character.charCodeAt(0)
    if (code <= 31 || '<>:"/\\|?*'.includes(character)) {
      return '-'
    }
    return character
  }).join('')

  return sanitized.trim() || 'collection-report'
}

export function getExecutionStatusMeta(status?: string) {
  switch (status) {
    case 'pending':
      return { color: 'default' as const, label: '等待中' }
    case 'running':
      return { color: 'green' as const, label: '运行中' }
    case 'success':
      return { color: 'success' as const, label: '成功' }
    case 'failed':
      return { color: 'error' as const, label: '失败' }
    case 'error':
      return { color: 'volcano' as const, label: '异常' }
    case 'skipped':
      return { color: 'default' as const, label: '跳过' }
    default:
      return { color: 'default' as const, label: status || '-' }
  }
}

export function buildCollectionRunReportHtml(params: {
  collectionName: string
  environmentName: string
  report: ApiCollectionRunReport
  items: ApiCollectionRunItem[]
}) {
  const { collectionName, environmentName, report, items } = params
  const reportStatus = getExecutionStatusMeta(report.status)
  const runtimeVarsText = stringifyForReport(parseMaybeJsonValue(report.runtimeVarsJson))
  const summaryCards = [
    ['总数', String(report.totalCount ?? 0)],
    ['成功', String(report.successCount ?? 0)],
    ['失败', String(report.failedCount ?? 0)],
    ['异常', String(report.errorCount ?? 0)],
    ['跳过', String(report.skippedCount ?? 0)],
    ['报告 ID', report.collectionRunId ?? '-'],
  ]

  const summaryHtml = summaryCards
    .map(
      ([label, value]) => `
        <div class="summary-card">
          <span class="summary-label">${escapeHtml(label)}</span>
          <strong class="summary-value">${escapeHtml(value)}</strong>
        </div>
      `,
    )
    .join('')

  const itemsHtml = items
    .map((item, index) => {
      const itemStatus = getExecutionStatusMeta(item.status)
      const itemExtractResults = item.extractResults ?? []
      const itemAssertResults = item.assertResults ?? []
      const requestSnapshot = {
        url: item.request?.url,
        method: item.request?.method,
        bodyType: item.request?.bodyType,
        headers: parseMaybeJsonValue(item.request?.headersJson),
        query: parseMaybeJsonValue(item.request?.queryJson),
        body: parseMaybeJsonValue(item.request?.body),
      }
      const responseSnapshot = parseMaybeJsonValue(item.response?.body)
      const runtimeVarsSnapshot = parseMaybeJsonValue(item.runtimeVarsJson)

      const extractHtml =
        itemExtractResults.length === 0
          ? '<div class="empty-hint">暂无提取结果</div>'
          : itemExtractResults
              .map(
                (result, resultIndex) => `
                  <div class="result-card ${result.success ? '' : 'is-failed'}">
                    <div class="result-title-row">
                      <strong>${escapeHtml(result.name ?? `提取 ${resultIndex + 1}`)}</strong>
                      <span class="pill ${result.success ? 'pill-success' : 'pill-error'}">${result.success ? '成功' : '失败'}</span>
                      ${result.usedDefault ? '<span class="pill pill-warn">默认值</span>' : ''}
                    </div>
                    <div class="result-meta-grid">
                      <div><span>变量</span><strong>${escapeHtml(formatOptionalValue(result.varKey))}</strong></div>
                      <div><span>值</span><strong>${escapeHtml(formatOptionalValue(result.value))}</strong></div>
                      <div><span>信息</span><strong>${escapeHtml(formatOptionalValue(result.errorMessage))}</strong></div>
                    </div>
                  </div>
                `,
              )
              .join('')

      const assertHtml =
        itemAssertResults.length === 0
          ? '<div class="empty-hint">暂无断言结果</div>'
          : itemAssertResults
              .map(
                (result, resultIndex) => `
                  <div class="result-card ${result.success ? '' : 'is-failed'}">
                    <div class="result-title-row">
                      <strong>${escapeHtml(result.name ?? `断言 ${resultIndex + 1}`)}</strong>
                      <span class="pill ${result.success ? 'pill-success' : 'pill-error'}">${result.success ? '成功' : '失败'}</span>
                    </div>
                    <div class="result-meta-grid">
                      <div><span>来源</span><strong>${escapeHtml(assertSourceLabelMap[result.assertSource as ApiAssertSource] ?? formatOptionalValue(result.assertSource))}</strong></div>
                      <div><span>比较</span><strong>${escapeHtml(assertComparatorLabelMap[result.comparator as ApiAssertComparator] ?? formatOptionalValue(result.comparator))}</strong></div>
                      <div><span>目标</span><strong>${escapeHtml(formatOptionalValue(result.targetExpr))}</strong></div>
                      <div><span>期望</span><strong>${escapeHtml(formatOptionalValue(result.expectedValue))}</strong></div>
                      <div><span>实际</span><strong>${escapeHtml(formatOptionalValue(result.actualValue))}</strong></div>
                      <div><span>信息</span><strong>${escapeHtml(formatOptionalValue(result.errorMessage))}</strong></div>
                    </div>
                  </div>
                `,
              )
              .join('')

      return `
        <section class="case-card">
          <div class="case-head">
            <div class="case-title-row">
              <span class="order-chip">#${escapeHtml(String(item.orderNo ?? index + 1))}</span>
              <h2>${escapeHtml(item.caseName || `用例 ${index + 1}`)}</h2>
<span class="pill ${itemStatus.label === '成功' || itemStatus.label === '运行中' ? 'pill-success' : itemStatus.label === '失败' || itemStatus.label === '异常' ? 'pill-error' : 'pill-default'}">${escapeHtml(itemStatus.label)}</span>
              ${item.continueOnFailure ? '<span class="pill pill-info">失败后继续</span>' : ''}
            </div>
            <div class="case-meta">
              <span>耗时：${escapeHtml(String(item.durationMs ?? 0))} ms</span>
              <span>开始：${escapeHtml(formatTime(item.startedAt))}</span>
              <span>结束：${escapeHtml(formatTime(item.finishedAt))}</span>
              <span>状态码：${escapeHtml(String(item.response?.statusCode ?? '-'))}</span>
            </div>
          </div>
          <div class="inline-meta">
            <span>caseId：${escapeHtml(item.caseId || '-')}</span>
            <span>caseRunId：${escapeHtml(item.caseRunId || '-')}</span>
            <span>提取失败：${escapeHtml(String(itemExtractResults.filter((result) => !result.success).length))}</span>
            <span>断言失败：${escapeHtml(String(itemAssertResults.filter((result) => !result.success).length))}</span>
          </div>
          ${item.errorMessage ? `<div class="error-banner">${escapeHtml(item.errorMessage)}</div>` : ''}
          <div class="snapshot-grid">
            <section class="snapshot-card">
              <h3>请求快照</h3>
              <pre>${escapeHtml(stringifyForReport(requestSnapshot))}</pre>
            </section>
            <section class="snapshot-card">
              <h3>响应结果</h3>
              <pre>${escapeHtml(stringifyForReport(responseSnapshot))}</pre>
            </section>
          </div>
          <section class="snapshot-card">
            <h3>运行变量快照</h3>
            <pre>${escapeHtml(stringifyForReport(runtimeVarsSnapshot))}</pre>
          </section>
          <section class="result-section">
            <h3>提取结果</h3>
            ${extractHtml}
          </section>
          <section class="result-section">
            <h3>断言结果</h3>
            ${assertHtml}
          </section>
        </section>
      `
    })
    .join('')

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${escapeHtml(collectionName)} - API测试集报告</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: #0f172a;
      --surface: #182235;
      --surface-soft: #202c40;
      --border: rgba(148, 163, 184, 0.2);
      --text: #e8edf7;
      --text-secondary: #9aa6bf;
      --success: #67c23a;
      --error: #f56c6c;
      --info: #409eff;
      --warn: #e6a23c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 28px;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: radial-gradient(circle at top, #1e293b 0%, #0f172a 60%);
      color: var(--text);
    }
    .page { max-width: 1400px; margin: 0 auto; display: flex; flex-direction: column; gap: 18px; }
    .hero, .case-card, .snapshot-card, .summary-card, .result-card {
      border: 1px solid var(--border);
      border-radius: 16px;
      background: rgba(24, 34, 53, 0.94);
      backdrop-filter: blur(8px);
    }
    .hero { padding: 20px; display: flex; flex-direction: column; gap: 14px; }
    .hero-top { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .hero-top h1 { margin: 0; font-size: 24px; line-height: 32px; }
    .hero-meta { display: flex; flex-wrap: wrap; gap: 8px 18px; color: var(--text-secondary); font-size: 13px; line-height: 20px; }
    .summary-grid { display: grid; grid-template-columns: repeat(5, minmax(84px, 0.9fr)) minmax(220px, 1.8fr); gap: 12px; }
    .summary-card { padding: 10px 12px; display: flex; flex-direction: column; gap: 4px; }
    .summary-label { color: var(--text-secondary); font-size: 12px; line-height: 18px; }
    .summary-value { font-size: 16px; line-height: 22px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .pill { display: inline-flex; align-items: center; justify-content: center; padding: 2px 10px; border-radius: 999px; font-size: 12px; line-height: 18px; border: 1px solid transparent; }
    .pill-success { color: #9ee6a3; background: rgba(103, 194, 58, 0.14); border-color: rgba(103, 194, 58, 0.22); }
    .pill-error { color: #ffb4b4; background: rgba(245, 108, 108, 0.14); border-color: rgba(245, 108, 108, 0.22); }
    .pill-info { color: #a9d0ff; background: rgba(64, 158, 255, 0.14); border-color: rgba(64, 158, 255, 0.22); }
    .pill-warn { color: #ffd79e; background: rgba(230, 162, 60, 0.14); border-color: rgba(230, 162, 60, 0.22); }
    .pill-default { color: var(--text-secondary); background: rgba(148, 163, 184, 0.12); border-color: rgba(148, 163, 184, 0.18); }
    .case-card { padding: 18px; display: flex; flex-direction: column; gap: 14px; }
    .case-head { display: flex; flex-direction: column; gap: 8px; }
    .case-title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .case-title-row h2 { margin: 0; font-size: 18px; line-height: 26px; }
    .order-chip { padding: 2px 8px; border-radius: 999px; background: rgba(64, 158, 255, 0.14); color: #a9d0ff; font-size: 12px; line-height: 18px; }
    .case-meta, .inline-meta { display: flex; flex-wrap: wrap; gap: 8px 16px; color: var(--text-secondary); font-size: 12px; line-height: 18px; }
    .error-banner { padding: 10px 12px; border-radius: 12px; color: #ffb4b4; background: rgba(245, 108, 108, 0.12); border: 1px solid rgba(245, 108, 108, 0.2); }
    .snapshot-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .snapshot-card { padding: 14px; }
    .snapshot-card h3, .result-section h3 { margin: 0 0 10px; font-size: 14px; line-height: 22px; }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      overflow-wrap: anywhere;
      font-family: Consolas, "SFMono-Regular", monospace;
      font-size: 12px;
      line-height: 20px;
      color: #dbe7ff;
    }
    .result-section { display: flex; flex-direction: column; gap: 10px; }
    .result-card { padding: 12px; display: flex; flex-direction: column; gap: 10px; }
    .result-card.is-failed { border-color: rgba(245, 108, 108, 0.2); }
    .result-title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .result-meta-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    .result-meta-grid div { display: flex; flex-direction: column; gap: 4px; }
    .result-meta-grid span { color: var(--text-secondary); font-size: 12px; line-height: 18px; }
    .result-meta-grid strong { font-size: 13px; line-height: 20px; word-break: break-word; }
    .empty-hint { color: var(--text-secondary); font-size: 13px; line-height: 20px; }
    @media (max-width: 1200px) {
      .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .snapshot-grid, .result-meta-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="hero-top">
        <h1>${escapeHtml(collectionName)} · API测试集报告</h1>
<span class="pill ${reportStatus.label === '成功' || reportStatus.label === '运行中' ? 'pill-success' : reportStatus.label === '失败' || reportStatus.label === '异常' ? 'pill-error' : 'pill-default'}">${escapeHtml(reportStatus.label)}</span>
      </div>
      <div class="hero-meta">
        <span>环境：${escapeHtml(environmentName)}</span>
        <span>开始：${escapeHtml(formatTime(report.startedAt))}</span>
        <span>结束：${escapeHtml(formatTime(report.finishedAt))}</span>
        <span>总耗时：${escapeHtml(String(report.durationMs ?? 0))} ms</span>
      </div>
      ${report.errorMessage ? `<div class="error-banner">${escapeHtml(report.errorMessage)}</div>` : ''}
      <div class="summary-grid">${summaryHtml}</div>
      <section class="snapshot-card">
        <h3>运行变量快照</h3>
        <pre>${escapeHtml(runtimeVarsText)}</pre>
      </section>
    </section>
    ${itemsHtml}
  </div>
</body>
</html>`
}
