import {
  collectionReportViewOptions,
  runResultViewOptions,
  type CollectionReportView,
  type RunResultView
} from '@/features/api-automation/config/collectionConfig'
import {
  getCollectionRunItemKey,
  parseMaybeJsonValue
} from '@/features/api-automation/utils/apiCaseEditor'
import { getExecutionStatusMeta } from '@/features/api-automation/utils/collectionRunReport'
import { Text, isApiRunPollingStatus } from '@/features/api-automation/utils/detailView'
import {
  type ApiCollectionRunReport,
  type ApiCollectionRunSummary
} from '@/services/api'
import { ActionButton } from '@/shared/components/ActionButton'
import {
  formatTime,
  getErrorMessage,
  normalizeEnvironmentId
} from '@/utils/format'
import { DownOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Modal, Segmented, Tag } from 'antd'
import { renderRunResultContent } from '../utils/renderApiRunResult'

import type { ApiCollectionRunItem, ApiEnvironment } from '@/features/api-automation/types'
import type { UseQueryResult } from '@tanstack/react-query'

type Props = {
  collectionRunReportOpen: boolean
  setCollectionRunReportOpen: React.Dispatch<React.SetStateAction<boolean>>
  setSelectedCollectionRunId: React.Dispatch<React.SetStateAction<string>>
  collectionRunReportQuery: UseQueryResult<ApiCollectionRunReport, Error>
  collectionRunReport: ApiCollectionRunReport | null
  environments: ApiEnvironment[]
  handleExportCollectionRunReportHtml: () => void
  handleRefreshCollectionRunReport: () => Promise<void>
  refreshingCollectionRunReport: boolean
  selectedCollectionRunId: string
  collectionRunReportView: CollectionReportView
  setCollectionRunReportView: React.Dispatch<React.SetStateAction<CollectionReportView>>
  orderedCollectionRunItems: ApiCollectionRunItem[]
  expandedCollectionRunItemIds: string[]
  collectionRunItemViews: Record<string, RunResultView>
  toggleCollectionRunItem: (itemKey: string) => void
  handleCollectionRunItemViewChange: (itemKey: string, view: RunResultView) => void
  selectedCollectionRunSummary: ApiCollectionRunSummary | undefined
}

export function ApiCollectionRunReportModal({ collectionRunReportOpen, setCollectionRunReportOpen, setSelectedCollectionRunId, collectionRunReportQuery, collectionRunReport, environments, handleExportCollectionRunReportHtml, handleRefreshCollectionRunReport, refreshingCollectionRunReport, selectedCollectionRunId, collectionRunReportView, setCollectionRunReportView, orderedCollectionRunItems, expandedCollectionRunItemIds, collectionRunItemViews, toggleCollectionRunItem, handleCollectionRunItemViewChange, selectedCollectionRunSummary }: Props) {
  return (
    <Modal
      mask={{ closable: false }}
      open={collectionRunReportOpen}
      title="API测试集报告"
      width={1180}
      footer={null}
      onCancel={() => {
        setCollectionRunReportOpen(false)
        setSelectedCollectionRunId('')
      }}
      destroyOnHidden={false}
      rootClassName="api-collection-run-report-modal-root"
      className="api-collection-run-report-modal"
    >
      {collectionRunReportQuery.error && !collectionRunReport ? (
        <Alert showIcon type="error" title={getErrorMessage(collectionRunReportQuery.error)} />
      ) : collectionRunReportQuery.isLoading && !collectionRunReport ? (
        <Empty description="API测试集报告加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : collectionRunReport ? (
        <div className="api-collection-run-report-layout">
          <div className="api-collection-run-report-static">
            <div className="api-collection-run-report-head">
              <div className="api-collection-run-report-head-main">
                <div className="api-collection-run-report-title">
                  <Text strong>运行结果</Text>
                  <Tag color={getExecutionStatusMeta(collectionRunReport.status).color}>{getExecutionStatusMeta(collectionRunReport.status).label}</Tag>
                </div>
                <div className="api-collection-run-report-meta">
                  <span>
                    环境：
                    {environments.find((environment) => normalizeEnvironmentId(environment) === collectionRunReport.environmentId)?.name ??
                      collectionRunReport.environmentId ??
                      '-'}
                  </span>
                  <span>开始：{formatTime(collectionRunReport.startedAt)}</span>
                  <span>结束：{formatTime(collectionRunReport.finishedAt)}</span>
                  <span>总耗时：{collectionRunReport.durationMs ?? 0} ms</span>
                </div>
              </div>
              <div className="api-collection-run-report-head-actions">
                <ActionButton operation="download" onClick={handleExportCollectionRunReportHtml} disabled={!collectionRunReport}>
                  导出 HTML
                </ActionButton>
                <Button
                  onClick={handleRefreshCollectionRunReport}
                  loading={refreshingCollectionRunReport}
                  disabled={!selectedCollectionRunId}
                >
                  刷新报告
                </Button>
              </div>
            </div>

            <div className="api-collection-run-report-summary-grid">
              <div className="api-collection-run-report-summary-item">
                <span>总数</span>
                <strong>{collectionRunReport.totalCount ?? 0}</strong>
              </div>
              <div className="api-collection-run-report-summary-item success">
                <span>成功</span>
                <strong>{collectionRunReport.successCount ?? 0}</strong>
              </div>
              <div className="api-collection-run-report-summary-item failed">
                <span>失败</span>
                <strong>{collectionRunReport.failedCount ?? 0}</strong>
              </div>
              <div className="api-collection-run-report-summary-item error">
                <span>异常</span>
                <strong>{collectionRunReport.errorCount ?? 0}</strong>
              </div>
              <div className="api-collection-run-report-summary-item skipped">
                <span>跳过</span>
                <strong>{collectionRunReport.skippedCount ?? 0}</strong>
              </div>
              <div className="api-collection-run-report-summary-item">
                <span>报告 ID</span>
                <strong>{collectionRunReport.collectionRunId ?? '-'}</strong>
              </div>
            </div>

            {collectionRunReport.errorMessage ? (
              <Alert showIcon type="error" title={collectionRunReport.errorMessage} className="api-case-run-result-alert" />
            ) : null}

            <Segmented
              className="api-case-run-result-segmented"
              options={collectionReportViewOptions}
              value={collectionRunReportView}
              onChange={(value) => setCollectionRunReportView(value as CollectionReportView)}
            />
          </div>

          <div className="api-collection-run-report-scroll">
            <div className="api-collection-run-report-content">
              {collectionRunReportView === 'runtime' ? (
                <pre className="api-case-run-result-pre compact">
                  {JSON.stringify(parseMaybeJsonValue(collectionRunReport.runtimeVarsJson), null, 2)}
                </pre>
              ) : orderedCollectionRunItems.length === 0 ? (
                <Empty description="暂无API测试集运行明细" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <div className="api-collection-run-report-list">
                  {orderedCollectionRunItems.map((item, index) => {
                    const itemKey = getCollectionRunItemKey(item, index)
                    const expanded = expandedCollectionRunItemIds.includes(itemKey)
                    const itemView = collectionRunItemViews[itemKey] ?? 'response'
                    const statusMeta = getExecutionStatusMeta(item.status)
                    const itemExtractResults = item.extractResults ?? []
                    const itemAssertResults = item.assertResults ?? []

                    return (
                      <div key={itemKey} className={`api-collection-run-report-item${expanded ? ' expanded' : ''}`}>
                        <button type="button" className="api-collection-run-report-item-head" onClick={() => toggleCollectionRunItem(itemKey)}>
                          <div className="api-collection-run-report-item-title">
                            <span className="api-collection-run-report-item-order">#{item.orderNo ?? index + 1}</span>
                            <strong>{item.caseName || `用例 ${index + 1}`}</strong>
                            <Tag color={statusMeta.color}>{statusMeta.label}</Tag>
                            {item.continueOnFailure ? <Tag color="processing">失败后继续</Tag> : null}
                          </div>
                          <div className="api-collection-run-report-item-meta">
                            <span>耗时：{item.durationMs ?? 0} ms</span>
                            <span>开始：{formatTime(item.startedAt)}</span>
                            <span>结束：{formatTime(item.finishedAt)}</span>
                            <DownOutlined className={`api-collection-run-report-item-arrow${expanded ? ' expanded' : ''}`} />
                          </div>
                        </button>

                        {expanded ? (
                          <div className="api-collection-run-report-item-body">
                            <div className="api-collection-run-report-item-inline-meta">
                              <span>caseId：{item.caseId || '-'}</span>
                              <span>caseRunId：{item.caseRunId || '-'}</span>
                              <span>状态码：{item.response?.statusCode ?? '-'}</span>
                              <span>提取失败：{itemExtractResults.filter((result) => !result.success).length}</span>
                              <span>断言失败：{itemAssertResults.filter((result) => !result.success).length}</span>
                            </div>
                            {item.errorMessage ? <Alert showIcon type="error" title={item.errorMessage} className="api-case-run-result-alert" /> : null}
                            <Segmented
                              className="api-case-run-result-segmented"
                              options={runResultViewOptions}
                              value={itemView}
                              onChange={(value) => handleCollectionRunItemViewChange(itemKey, value as RunResultView)}
                            />
                            <div className="api-case-run-result-block">
                              {renderRunResultContent({
                                view: itemView,
                                request: item.request,
                                response: item.response,
                                extractResults: itemExtractResults,
                                assertResults: itemAssertResults,
                                emptyExtractDescription: '该用例没有提取结果',
                                emptyAssertDescription: '该用例没有断言结果',
                              })}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <Empty description={isApiRunPollingStatus(selectedCollectionRunSummary?.status) ? '运行中，报告生成中...' : '暂无API测试集报告'} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
    </Modal>
  )
}
