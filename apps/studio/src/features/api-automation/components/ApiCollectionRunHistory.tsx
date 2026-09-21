import { getExecutionStatusMeta } from '@/features/api-automation/utils/collectionRunReport'
import {
  type ApiCollectionRunSummary
} from '@/services/api'
import {
  formatTime,
  getErrorMessage,
  normalizeEnvironmentId
} from '@/utils/format'
import type { UseQueryResult } from '@tanstack/react-query'
import { Alert, Empty, Modal, Tag } from 'antd'

import type { ApiEnvironment } from '@/features/api-automation/types'
import type { ListResponse } from '@/shared/api/request'

type Props = {
  collectionRunHistoryOpen: boolean
  setCollectionRunHistoryOpen: React.Dispatch<React.SetStateAction<boolean>>
  collectionRunHistoryQuery: UseQueryResult<ListResponse<ApiCollectionRunSummary>, Error>
  collectionRunHistory: ApiCollectionRunSummary[]
  loadingCollectionRunHistoryId: string
  environments: ApiEnvironment[]
  handleOpenCollectionRunHistoryItem: (historyItem: ApiCollectionRunSummary) => void
}

export function ApiCollectionRunHistory({ collectionRunHistoryOpen, setCollectionRunHistoryOpen, collectionRunHistoryQuery, collectionRunHistory, loadingCollectionRunHistoryId, environments, handleOpenCollectionRunHistoryItem }: Props) {
  return (
    <Modal
      mask={{ closable: false }}
      open={collectionRunHistoryOpen}
      title="运行记录"
      width={760}
      footer={null}
      onCancel={() => setCollectionRunHistoryOpen(false)}
      destroyOnHidden={false}
      className="api-collection-run-history-modal"
    >
      <div className="api-collection-run-history-layout">
        {collectionRunHistoryQuery.error ? (
          <Alert showIcon type="error" title={getErrorMessage(collectionRunHistoryQuery.error)} />
        ) : collectionRunHistoryQuery.isLoading ? (
          <Empty description="运行记录加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : collectionRunHistory.length === 0 ? (
          <Empty description="暂无运行记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div className="api-collection-run-history-list">
            {collectionRunHistory.map((item, index) => {
              const statusMeta = getExecutionStatusMeta(item.status)
              const isLoading = loadingCollectionRunHistoryId === item.collectionRunId
              const environmentName =
                environments.find((environment) => normalizeEnvironmentId(environment) === item.environmentId)?.name ?? item.environmentId ?? '-'

              return (
                <button
                  key={item.collectionRunId ?? `collection-run-${index}`}
                  type="button"
                  className="api-collection-run-history-item"
                  onClick={() => handleOpenCollectionRunHistoryItem(item)}
                  disabled={Boolean(loadingCollectionRunHistoryId)}
                >
                  <div className="api-collection-run-history-item-main">
                    <div className="api-collection-run-history-item-title">
                      <strong>{formatTime(item.startedAt || item.createdAt || item.updatedAt)}</strong>
                      <Tag color={statusMeta.color}>{statusMeta.label}</Tag>
                      <Tag>{environmentName}</Tag>
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
                    <span className="api-collection-run-history-item-id">{item.collectionRunId ?? '-'}</span>
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
