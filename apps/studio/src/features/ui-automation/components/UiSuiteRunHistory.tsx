import {
  getExecutionStatusMeta
} from '@/features/ui-automation/utils/runHelpers'
import {
  type UiTestSuiteRunSummary
} from '@/services/api'
import {
  formatTime,
  getErrorMessage
} from '@/utils/format'
import type { UseQueryResult } from '@tanstack/react-query'
import { Alert, Empty, Modal, Tag } from 'antd'

import type { ListResponse } from '@/shared/api/request'

type Props = {
  suiteRunHistoryOpen: boolean
  setSuiteRunHistoryOpen: React.Dispatch<React.SetStateAction<boolean>>
  suiteRunHistoryQuery: UseQueryResult<ListResponse<UiTestSuiteRunSummary>, Error>
  suiteRunHistory: UiTestSuiteRunSummary[]
  loadingSuiteRunHistoryId: string
  handleOpenSuiteRunHistoryItem: (runSummary: UiTestSuiteRunSummary) => void
}

export function UiSuiteRunHistory({ suiteRunHistoryOpen, setSuiteRunHistoryOpen, suiteRunHistoryQuery, suiteRunHistory, loadingSuiteRunHistoryId, handleOpenSuiteRunHistoryItem }: Props) {
  return (
    <Modal
      mask={{ closable: false }}
      open={suiteRunHistoryOpen}
      title="测试集运行记录"
      width={920}
      footer={null}
      onCancel={() => setSuiteRunHistoryOpen(false)}
      destroyOnHidden={false}
      className="api-collection-run-history-modal"
    >
      <div className="api-collection-run-history-layout">
        {suiteRunHistoryQuery.error ? (
          <Alert showIcon type="error" title={getErrorMessage(suiteRunHistoryQuery.error)} />
        ) : suiteRunHistoryQuery.isLoading ? (
          <Empty description="运行记录加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : suiteRunHistory.length === 0 ? (
          <Empty description="暂无运行记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div className="api-collection-run-history-list">
            {suiteRunHistory.map((item, index) => {
              const statusMeta = getExecutionStatusMeta(item.status)
              const isLoading = loadingSuiteRunHistoryId === item.suiteRunId

              return (
                <button
                  key={item.suiteRunId ?? `ui-suite-run-${index}`}
                  type="button"
                  className="api-collection-run-history-item"
                  onClick={() => handleOpenSuiteRunHistoryItem(item)}
                  disabled={Boolean(loadingSuiteRunHistoryId)}
                >
                  <div className="api-collection-run-history-item-main">
                    <div className="api-collection-run-history-item-title">
                      <strong>{formatTime(item.startedAt || item.createdAt || item.updatedAt)}</strong>
                      <Tag color={statusMeta.color}>{statusMeta.label}</Tag>
                    </div>
                    <div className="api-collection-run-history-item-meta">
                      <span>总数：{item.totalCount ?? 0}</span>
                      <span>成功：{item.successCount ?? 0}</span>
                      <span>失败：{item.failedCount ?? 0}</span>
                      <span>异常：{item.errorCount ?? 0}</span>
                      <span>跳过：{item.skippedCount ?? 0}</span>
                      <span>耗时：{item.durationMs ?? 0} ms</span>
                      <span>结束：{formatTime(item.finishedAt)}</span>
                    </div>
                    {item.errorMessage ? <div className="api-collection-run-history-item-error">{item.errorMessage}</div> : null}
                  </div>
                  <div className="api-collection-run-history-item-side">
                    <span className="api-collection-run-history-item-id">{item.suiteRunId ?? '-'}</span>
                    <span className="api-collection-run-history-item-link">{isLoading ? '加载中...' : '查看报告'}</span>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </Modal>
  )
}
