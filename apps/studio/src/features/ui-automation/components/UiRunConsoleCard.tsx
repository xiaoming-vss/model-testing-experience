import type { UiTestCaseRun } from '@/services/api'
import { CopyOutlined, DownOutlined, FilterOutlined, UpOutlined } from '@ant-design/icons'
import { Button, Dropdown, Empty, Tooltip } from 'antd'
import { useMemo, useState } from 'react'

import { buildUiRunLogLines, buildUiRunMetrics, type UiRunLogLevel } from '../utils/detailRunView'
import { getExecutionStatusMeta } from '../utils/runHelpers'
import { prettyPrintValue } from '../utils/uiTestCaseEditor'

/*
 * 执行控制台：设计稿的 Live Log 是 Playwright 的实时日志通道，前端没有这条通道，
 * 所以每一行都由运行记录里的步骤结果拼出来（关键字 + 步骤名 + 状态 + 耗时 + 实际值），
 * 末行是按实际计数生成的汇总结论。右下角三项指标同理：FCP / 网络请求数 / 内存占用没有数据源，
 * 换成运行耗时、通过步骤数、失败步骤数。
 * 运行快照（浏览器信息与运行配置）原来在「运行快照」页签里，现在收进底部的展开区。
 * 日志级别过滤按设计稿的 Filter 做：范围就是真实存在的四种级别，不新增假分类。
 * 样式见 styles/detail-inspector-v2.css。
 */

const LOG_LEVEL_FILTERS: Array<{ key: UiRunLogLevel | 'all'; label: string }> = [
  { key: 'all', label: '全部级别' },
  { key: 'info', label: 'info' },
  { key: 'wait', label: 'wait' },
  { key: 'assert', label: 'assert' },
  { key: 'error', label: 'error' },
]

const LOG_LEVEL_LABELS: Record<UiRunLogLevel | 'all', string> = {
  all: '全部级别',
  info: 'info',
  wait: 'wait',
  assert: 'assert',
  error: 'error',
  done: 'done',
}

type Props = {
  run: UiTestCaseRun | null
  refreshing: boolean
  onRefresh: () => void
}

export function UiRunConsoleCard({ run, refreshing, onRefresh }: Props) {
  const [snapshotOpen, setSnapshotOpen] = useState(false)
  const [levelFilter, setLevelFilter] = useState<UiRunLogLevel | 'all'>('all')
  const logLines = useMemo(() => buildUiRunLogLines(run), [run])
  // 汇总行永远保留：过滤后看不到结论会让控制台读起来少一截。
  const visibleLogLines = useMemo(
    () => (levelFilter === 'all' ? logLines : logLines.filter((line) => line.level === levelFilter || line.level === 'done')),
    [levelFilter, logLines],
  )
  const metrics = buildUiRunMetrics(run)
  const statusMeta = getExecutionStatusMeta(run?.status)
  const snapshotSections = [
    { label: '浏览器信息', value: run?.snapshot?.browser },
    { label: '运行配置', value: run?.snapshot?.options },
  ].filter((item) => item.value !== undefined && item.value !== null)

  async function handleCopy() {
    const text = [
      `# 运行 ${run?.runId ?? run?.uiTestCaseRunId ?? '-'} ${statusMeta.label} 耗时 ${run?.durationMs ?? '-'} ms`,
      ...visibleLogLines.map((line) => `[${line.level}] ${line.time} ${line.command} ${line.result}`.trim()),
    ].join('\n')

    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // 剪贴板不可用（非安全上下文 / 无权限）时保持静默，控制台内容仍然可见。
    }
  }

  return (
    <section className="ui-wb-card ui-wb-console">
      <header className="ui-wb-card-head">
        <div className="ui-wb-card-title">
          执行控制台
          <span className="ui-wb-card-chip">Live Log</span>
          {run ? <span className={`ui-wb-console-status tone-${run.success === false ? 'red' : 'green'}`}>{statusMeta.label}</span> : null}
        </div>
        <div className="ui-wb-card-head-side">
          <span className="ui-wb-console-meta">
            {run ? `运行 ID ${run.runId ?? run.uiTestCaseRunId ?? '-'}` : '暂无运行记录'}
          </span>
          <Dropdown
            trigger={['click']}
            menu={{
              items: LOG_LEVEL_FILTERS.map((item) => ({ key: item.key, label: item.label })),
              selectable: true,
              selectedKeys: [levelFilter],
              onClick: ({ key }) => setLevelFilter(key as UiRunLogLevel | 'all'),
            }}
          >
            <Button type="text" size="small" className="ui-wb-console-action" icon={<FilterOutlined />} disabled={logLines.length === 0}>
              过滤{levelFilter === 'all' ? '' : `：${LOG_LEVEL_LABELS[levelFilter]}`}
            </Button>
          </Dropdown>
          <Tooltip title="复制控制台内容">
            <Button type="text" size="small" className="ui-wb-console-action" icon={<CopyOutlined />} disabled={logLines.length === 0} onClick={handleCopy} />
          </Tooltip>
          <Button type="text" size="small" className="ui-wb-console-action" loading={refreshing} disabled={!run} onClick={onRefresh}>
            刷新
          </Button>
        </div>
      </header>

      <div className="ui-wb-console-log" role="log" aria-label="执行日志">
        {visibleLogLines.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有可显示的日志" className="ui-wb-console-empty" />
        ) : (
          visibleLogLines.map((line) => (
            <div key={line.key} className={`ui-wb-console-line is-${line.level}`}>
              <span className="ui-wb-console-level">[{line.level}]</span>
              {line.time ? <span className="ui-wb-console-time">{line.time}</span> : null}
              {line.command ? <span className="ui-wb-console-command">{line.command}</span> : null}
              <span className="ui-wb-console-result">{line.result}</span>
            </div>
          ))
        )}
      </div>

      <div className="ui-wb-console-metrics">
        {metrics.map((metric) => (
          <div key={metric.key} className="ui-wb-metric">
            <span className="ui-wb-metric-label">{metric.label}</span>
            <span className={`ui-wb-metric-value${metric.tone ? ` tone-${metric.tone}` : ''}`}>{metric.value}</span>
          </div>
        ))}
      </div>

      {snapshotSections.length > 0 ? (
        <div className="ui-wb-console-snapshot">
          <Button
            type="text"
            size="small"
            className="ui-wb-console-snapshot-toggle"
            icon={snapshotOpen ? <UpOutlined /> : <DownOutlined />}
            onClick={() => setSnapshotOpen((current) => !current)}
          >
            运行快照
          </Button>
          {snapshotOpen ? (
            <div className="ui-wb-console-snapshot-body">
              {snapshotSections.map((section) => (
                <div key={section.label} className="ui-wb-console-snapshot-block">
                  <div className="ui-wb-console-snapshot-label">{section.label}</div>
                  <pre className="ui-wb-console-snapshot-pre">{prettyPrintValue(section.value)}</pre>
                </div>
              ))}
              {run?.tracePath ? <div className="ui-wb-console-snapshot-trace">Trace：{run.tracePath}</div> : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
