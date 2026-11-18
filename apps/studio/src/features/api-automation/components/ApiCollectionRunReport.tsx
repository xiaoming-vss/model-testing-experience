import { RunWaitingReason } from '@/domain/runs/RunWaitingReason'
import { StopRunButton } from '@/domain/runs/StopRunButton'
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
import { useViewMotion } from '@/shared/ui/useViewMotion'
import { cx } from '@/shared/utils/cx'
import styles from '@/shared/styles/run-view.module.css'
import {
  runReportContentClass,
  runReportContentInnerClass,
  runReportHeadActionsClass,
  runReportHeadClass,
  runReportHeadMainClass,
  runReportInlineMetaClass,
  runReportItemArrowClass,
  runReportItemBodyClass,
  runReportItemClass,
  runReportItemHeadClass,
  runReportItemMetaClass,
  runReportItemOrderClass,
  runReportItemTitleClass,
  runReportLayoutClass,
  runReportListClass,
  runReportListMoreClass,
  runReportMetaClass,
  runReportScrollClass,
  runReportStaticClass,
  runReportSummaryErrorClass,
  runReportSummaryFailedClass,
  runReportSummaryGridClass,
  runReportSummaryItemClass,
  runReportSummarySkippedClass,
  runReportSummarySuccessClass,
  runReportTitleClass,
  runResultAlertClass,
  runResultBlockClass,
  runResultPreClass,
  runResultPreCompactClass,
} from '@/shared/utils/surfaceClasses'
import {
  formatTime,
  getErrorMessage,
  normalizeEnvironmentId
} from '@/utils/format'
import { DownOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Modal, Segmented, Tag } from 'antd'
import { useEffect, useState } from 'react'
import { renderRunResultContent } from '../utils/renderApiRunResult'

import type { ApiCollectionRunItem, ApiEnvironment } from '@/features/api-automation/types'
import type { UseQueryResult } from '@tanstack/react-query'

type Props = {
  collectionRunReportOpen: boolean
  canStop?: boolean
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

const RUN_REPORT_PAGE_SIZE = 30

function RunResultPanel({ view, children }: { view: RunResultView; children: React.ReactNode }) {
  const panelRef = useViewMotion(runResultViewOptions.findIndex(option => option.value === view))
  return <div ref={panelRef} className={runResultBlockClass}>{children}</div>
}

export function ApiCollectionRunReportModal({ canStop, collectionRunReportOpen, setCollectionRunReportOpen, setSelectedCollectionRunId, collectionRunReportQuery, collectionRunReport, environments, handleExportCollectionRunReportHtml, handleRefreshCollectionRunReport, refreshingCollectionRunReport, selectedCollectionRunId, collectionRunReportView, setCollectionRunReportView, orderedCollectionRunItems, expandedCollectionRunItemIds, collectionRunItemViews, toggleCollectionRunItem, handleCollectionRunItemViewChange, selectedCollectionRunSummary }: Props) {
  const viewRef = useViewMotion(collectionReportViewOptions.findIndex(option => option.value === collectionRunReportView))
  // 报告条目可能很多，运行中还会持续刷新；先渲染前一段，展开详情按需追加，避免每轮轮询重画全部行。
  const [visibleItemCount, setVisibleItemCount] = useState(RUN_REPORT_PAGE_SIZE)
  useEffect(() => {
    setVisibleItemCount(RUN_REPORT_PAGE_SIZE)
  }, [selectedCollectionRunId])
  const visibleRunItems = orderedCollectionRunItems.slice(0, visibleItemCount)
  const remainingRunItems = orderedCollectionRunItems.length - visibleRunItems.length
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
      destroyOnHidden
      rootClassName={cx('api-collection-run-report-modal-root', styles.root, styles.reportRoot)}
      className="api-collection-run-report-modal"
    >
      {collectionRunReportQuery.error && !collectionRunReport ? (
        <Alert showIcon type="error" title={getErrorMessage(collectionRunReportQuery.error)} />
      ) : collectionRunReportQuery.isLoading && !collectionRunReport ? (
        <Empty description="API测试集报告加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : collectionRunReport ? (
        <div className={runReportLayoutClass}>
          <div className={runReportStaticClass}>
            <div className={runReportHeadClass}>
              <div className={runReportHeadMainClass}>
                <div className={runReportTitleClass}>
                  <Text strong>运行结果</Text>
                  <Tag color={getExecutionStatusMeta(collectionRunReport.status).color}>{getExecutionStatusMeta(collectionRunReport.status).label}</Tag>
                  <RunWaitingReason status={collectionRunReport.status} />
                </div>
                <div className={runReportMetaClass}>
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
              <div className={runReportHeadActionsClass}>
                <ActionButton operation="refresh"
                  onClick={handleRefreshCollectionRunReport}
                  loading={refreshingCollectionRunReport}
                  disabled={!selectedCollectionRunId}
                >刷新报告</ActionButton>
                {canStop ? <StopRunButton kind="api-collection" runId={selectedCollectionRunId} status={collectionRunReport.status} /> : null}
                <ActionButton operation="download" onClick={handleExportCollectionRunReportHtml} disabled={!collectionRunReport}>
                  导出 HTML
                </ActionButton>
              </div>
            </div>

            <div className={runReportSummaryGridClass}>
              <div className={runReportSummaryItemClass}>
                <span>总数</span>
                <strong>{collectionRunReport.totalCount ?? 0}</strong>
              </div>
              <div className={`${runReportSummaryItemClass} ${runReportSummarySuccessClass}`}>
                <span>成功</span>
                <strong>{collectionRunReport.successCount ?? 0}</strong>
              </div>
              <div className={`${runReportSummaryItemClass} ${runReportSummaryFailedClass}`}>
                <span>失败</span>
                <strong>{collectionRunReport.failedCount ?? 0}</strong>
              </div>
              <div className={`${runReportSummaryItemClass} ${runReportSummaryErrorClass}`}>
                <span>异常</span>
                <strong>{collectionRunReport.errorCount ?? 0}</strong>
              </div>
              <div className={`${runReportSummaryItemClass} ${runReportSummarySkippedClass}`}>
                <span>跳过</span>
                <strong>{collectionRunReport.skippedCount ?? 0}</strong>
              </div>
              <div className={runReportSummaryItemClass}>
                <span>报告 ID</span>
                <strong>{collectionRunReport.collectionRunId ?? '-'}</strong>
              </div>
            </div>

            {collectionRunReport.errorMessage ? (
              <Alert showIcon type="error" title={collectionRunReport.errorMessage} className={runResultAlertClass} />
            ) : null}

            <Segmented
              className="api-case-run-result-segmented"
              options={collectionReportViewOptions}
              value={collectionRunReportView}
              onChange={(value) => setCollectionRunReportView(value as CollectionReportView)}
            />
          </div>

          <div ref={viewRef} className={runReportScrollClass}>
            <div className={`${runReportContentClass} ${runReportContentInnerClass}`}>
              {collectionRunReportView === 'runtime' ? (
                <pre className={`${runResultPreClass} ${runResultPreCompactClass}`}>
                  {JSON.stringify(parseMaybeJsonValue(collectionRunReport.runtimeVarsJson), null, 2)}
                </pre>
              ) : orderedCollectionRunItems.length === 0 ? (
                <Empty description="暂无API测试集运行明细" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <div className={runReportListClass}>
                  {visibleRunItems.map((item, index) => {
                    const itemKey = getCollectionRunItemKey(item, index)
                    const expanded = expandedCollectionRunItemIds.includes(itemKey)
                    const itemView = collectionRunItemViews[itemKey] ?? 'response'
                    const statusMeta = getExecutionStatusMeta(item.status)
                    const itemExtractResults = item.extractResults ?? []
                    const itemAssertResults = item.assertResults ?? []

                    return (
                      <div key={itemKey} className={`${runReportItemClass}${expanded ? ' expanded' : ''}`}>
                        <button type="button" className={runReportItemHeadClass} onClick={() => toggleCollectionRunItem(itemKey)}>
                          <div className={runReportItemTitleClass}>
                            <span className={runReportItemOrderClass}>#{item.orderNo ?? index + 1}</span>
                            <strong>{item.caseName || `用例 ${index + 1}`}</strong>
                            <Tag color={statusMeta.color}>{statusMeta.label}</Tag>
                            {item.continueOnFailure ? <Tag color="processing">失败后继续</Tag> : null}
                          </div>
                          <div className={runReportItemMetaClass}>
                            <span>耗时：{item.durationMs ?? 0} ms</span>
                            <span>开始：{formatTime(item.startedAt)}</span>
                            <span>结束：{formatTime(item.finishedAt)}</span>
                            <DownOutlined className={`${runReportItemArrowClass}${expanded ? ' expanded' : ''}`} />
                          </div>
                        </button>

                        {expanded ? (
                          <div className={runReportItemBodyClass}>
                            <div className={runReportInlineMetaClass}>
                              <span>caseId：{item.caseId || '-'}</span>
                              <span>caseRunId：{item.caseRunId || '-'}</span>
                              <span>状态码：{item.response?.statusCode ?? '-'}</span>
                              <span>提取失败：{itemExtractResults.filter((result) => !result.success).length}</span>
                              <span>断言失败：{itemAssertResults.filter((result) => !result.success).length}</span>
                            </div>
                            {item.errorMessage ? <Alert showIcon type="error" title={item.errorMessage} className={runResultAlertClass} /> : null}
                            <Segmented
                              className="api-case-run-result-segmented"
                              options={runResultViewOptions}
                              value={itemView}
                              onChange={(value) => handleCollectionRunItemViewChange(itemKey, value as RunResultView)}
                            />
                            <RunResultPanel view={itemView}>
                              {renderRunResultContent({
                                view: itemView,
                                request: item.request,
                                response: item.response,
                                extractResults: itemExtractResults,
                                assertResults: itemAssertResults,
                                emptyExtractDescription: '该用例没有提取结果',
                                emptyAssertDescription: '该用例没有断言结果',
                              })}
                            </RunResultPanel>
                          </div>
                        ) : null}
                      </div>
                    )
                  })}
                  {remainingRunItems > 0 ? (
                    <div className={runReportListMoreClass}>
                      <Button size="small" onClick={() => setVisibleItemCount(count => count + RUN_REPORT_PAGE_SIZE)}>
                        显示更多（还剩 {remainingRunItems} 条）
                      </Button>
                    </div>
                  ) : null}
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
