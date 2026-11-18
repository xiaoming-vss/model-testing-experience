import { RunWaitingReason } from '@/domain/runs/RunWaitingReason'
import { StopRunButton } from '@/domain/runs/StopRunButton'
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
import { StoredFileDownload } from '@/shared/components/files/StoredFile'
import {
  uiSuiteRunReportViewOptions,
  type UiSuiteRunReportView
} from '@/features/ui-automation/config/stepConfig'
import { Text } from '@/features/ui-automation/utils/detailView'
import {
  getExecutionStatusMeta,
  getUiTestSuiteRunItemKey,
  isUiRunPollingStatus
} from '@/features/ui-automation/utils/runHelpers'
import {
  prettyPrintValue
} from '@/features/ui-automation/utils/uiTestCaseEditor'
import {
  type UiTestSuiteRunReport,
  type UiTestSuiteRunSummary
} from '@/services/api'
import {
  formatTime,
  getErrorMessage
} from '@/utils/format'
import { DownOutlined } from '@ant-design/icons'
import { Alert, Empty, Modal, Segmented, Tag } from 'antd'
import { renderUiRunStepResultList } from '../utils/renderUiRunSteps'

import type { UiTestSuiteRunItem } from '@/features/ui-automation/types'
import type { UseQueryResult } from '@tanstack/react-query'

type Props = {
  suiteRunReportOpen: boolean
  canStop?: boolean
  closeSuiteRunReport: () => void
  suiteRunReportQuery: UseQueryResult<UiTestSuiteRunReport, Error>
  suiteRunReport: UiTestSuiteRunReport | null
  handleRefreshSuiteRunReport: () => Promise<void>
  refreshingSuiteRunReport: boolean
  selectedSuiteRunId: string
  suiteRunReportView: UiSuiteRunReportView
  setSuiteRunReportView: React.Dispatch<React.SetStateAction<UiSuiteRunReportView>>
  orderedSuiteRunItems: UiTestSuiteRunItem[]
  selectedSuiteRunSummary: UiTestSuiteRunSummary | null
  expandedSuiteRunItemIds: string[]
  toggleSuiteRunItem: (itemKey: string) => void
}

export function UiSuiteRunReport({ canStop, suiteRunReportOpen, closeSuiteRunReport, suiteRunReportQuery, suiteRunReport, handleRefreshSuiteRunReport, refreshingSuiteRunReport, selectedSuiteRunId, suiteRunReportView, setSuiteRunReportView, orderedSuiteRunItems, selectedSuiteRunSummary, expandedSuiteRunItemIds, toggleSuiteRunItem }: Props) {
  const viewRef = useViewMotion(uiSuiteRunReportViewOptions.findIndex(option => option.value === suiteRunReportView))
  return (
    <Modal
      mask={{ closable: false }}
      open={suiteRunReportOpen}
      title="测试集运行报告"
      width={1180}
      footer={null}
      onCancel={closeSuiteRunReport}
      destroyOnHidden={false}
      rootClassName={cx('api-collection-run-report-modal-root', styles.root, styles.reportRoot)}
      className="api-collection-run-report-modal"
    >
      {suiteRunReportQuery.error && !suiteRunReport ? (
        <Alert showIcon type="error" title={getErrorMessage(suiteRunReportQuery.error)} />
      ) : suiteRunReportQuery.isLoading && !suiteRunReport ? (
        <Empty description="测试集报告加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : suiteRunReport ? (
        <div className={runReportLayoutClass}>
          <div className={runReportStaticClass}>
            <div className={runReportHeadClass}>
              <div className={runReportHeadMainClass}>
                <div className={runReportTitleClass}>
                  <Text strong>运行结果</Text>
                  <Tag color={getExecutionStatusMeta(suiteRunReport.status).color}>{getExecutionStatusMeta(suiteRunReport.status).label}</Tag>
                  <RunWaitingReason status={suiteRunReport.status} />
                </div>
                <div className={runReportMetaClass}>
                  <span>开始：{formatTime(suiteRunReport.startedAt)}</span>
                  <span>结束：{formatTime(suiteRunReport.finishedAt)}</span>
                  <span>总耗时：{suiteRunReport.durationMs ?? 0} ms</span>
                  <span>当前 URL：{suiteRunReport.currentUrl || '-'}</span>
                  <span>{suiteRunReport.tracePath ? <StoredFileDownload path={suiteRunReport.tracePath} label="下载 Trace" /> : "Trace：-"}</span>
                </div>
              </div>
              <div className={runReportHeadActionsClass}>
                <ActionButton operation="refresh" onClick={handleRefreshSuiteRunReport} loading={refreshingSuiteRunReport} disabled={!selectedSuiteRunId}>刷新报告</ActionButton>
                {canStop ? <StopRunButton kind="ui-suite" runId={selectedSuiteRunId} status={suiteRunReport.status} /> : null}
              </div>
            </div>

            <div className={runReportSummaryGridClass}>
              <div className={runReportSummaryItemClass}>
                <span>总数</span>
                <strong>{suiteRunReport.totalCount ?? 0}</strong>
              </div>
              <div className={`${runReportSummaryItemClass} ${runReportSummarySuccessClass}`}>
                <span>成功</span>
                <strong>{suiteRunReport.successCount ?? 0}</strong>
              </div>
              <div className={`${runReportSummaryItemClass} ${runReportSummaryFailedClass}`}>
                <span>失败</span>
                <strong>{suiteRunReport.failedCount ?? 0}</strong>
              </div>
              <div className={`${runReportSummaryItemClass} ${runReportSummaryErrorClass}`}>
                <span>异常</span>
                <strong>{suiteRunReport.errorCount ?? 0}</strong>
              </div>
              <div className={`${runReportSummaryItemClass} ${runReportSummarySkippedClass}`}>
                <span>跳过</span>
                <strong>{suiteRunReport.skippedCount ?? 0}</strong>
              </div>
              <div className={runReportSummaryItemClass}>
                <span>报告 ID</span>
                <strong>{suiteRunReport.suiteRunId ?? '-'}</strong>
              </div>
            </div>

            {suiteRunReport.errorMessage ? (
              <Alert showIcon type="error" title={suiteRunReport.errorMessage} className={runResultAlertClass} />
            ) : null}

            <Segmented
              className="api-case-run-result-segmented"
              options={uiSuiteRunReportViewOptions}
              value={suiteRunReportView}
              onChange={(value) => setSuiteRunReportView(value as UiSuiteRunReportView)}
            />
          </div>

          <div ref={viewRef} className={runReportScrollClass}>
            <div className={`${runReportContentClass} ${runReportContentInnerClass}`}>
              {suiteRunReportView === 'snapshot' ? (
                suiteRunReport.snapshot ? (
                  <pre className={`${runResultPreClass} ${runResultPreCompactClass}`}>{prettyPrintValue(suiteRunReport.snapshot)}</pre>
                ) : (
                  <Empty description="暂无运行快照" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )
              ) : orderedSuiteRunItems.length === 0 ? (
                <Empty
                  description={selectedSuiteRunSummary?.status && isUiRunPollingStatus(selectedSuiteRunSummary.status) ? '运行中，报告生成中...' : '暂无测试集运行明细'}
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              ) : (
                <div className={runReportListClass}>
                  {orderedSuiteRunItems.map((item, index) => {
                    const itemKey = getUiTestSuiteRunItemKey(item, index)
                    const expanded = expandedSuiteRunItemIds.includes(itemKey)
                    const statusMeta = getExecutionStatusMeta(item.status)

                    return (
                      <div key={itemKey} className={`${runReportItemClass}${expanded ? ' expanded' : ''}`}>
                        <button type="button" className={runReportItemHeadClass} onClick={() => toggleSuiteRunItem(itemKey)}>
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
                              <span>用例名称：{item.caseName || '-'}</span>
                              <span>itemId：{item.itemId || '-'}</span>
                              <span>当前 URL：{item.currentUrl || '-'}</span>
                              <span>步骤数：{item.stepResults?.length ?? 0}</span>
                              <span>失败后继续：{item.continueOnFailure ? '是' : '否'}</span>
                            </div>
                            {item.errorMessage ? <Alert showIcon type="error" title={item.errorMessage} className={runResultAlertClass} /> : null}
                            <div className={runResultBlockClass}>
                              {renderUiRunStepResultList(item.stepResults ?? [], '该用例暂无步骤结果')}
                              {item.snapshot ? <pre className={`${runResultPreClass} ${runResultPreCompactClass}`}>{prettyPrintValue(item.snapshot)}</pre> : null}
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
        <Empty
          description={selectedSuiteRunSummary?.status && isUiRunPollingStatus(selectedSuiteRunSummary.status) ? '运行中，报告生成中...' : '暂无测试集报告'}
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      )}
    </Modal>
  )
}
