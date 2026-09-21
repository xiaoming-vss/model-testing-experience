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
import { Alert, Button, Empty, Modal, Segmented, Tag } from 'antd'
import { renderUiRunStepResultList } from '../utils/renderUiRunSteps'

import type { UiTestSuiteRunItem } from '@/features/ui-automation/types'
import type { UseQueryResult } from '@tanstack/react-query'

type Props = {
  suiteRunReportOpen: boolean
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

export function UiSuiteRunReport({ suiteRunReportOpen, closeSuiteRunReport, suiteRunReportQuery, suiteRunReport, handleRefreshSuiteRunReport, refreshingSuiteRunReport, selectedSuiteRunId, suiteRunReportView, setSuiteRunReportView, orderedSuiteRunItems, selectedSuiteRunSummary, expandedSuiteRunItemIds, toggleSuiteRunItem }: Props) {
  return (
    <Modal
      mask={{ closable: false }}
      open={suiteRunReportOpen}
      title="测试集运行报告"
      width={1180}
      footer={null}
      onCancel={closeSuiteRunReport}
      destroyOnHidden={false}
      rootClassName="api-collection-run-report-modal-root"
      className="api-collection-run-report-modal"
    >
      {suiteRunReportQuery.error && !suiteRunReport ? (
        <Alert showIcon type="error" title={getErrorMessage(suiteRunReportQuery.error)} />
      ) : suiteRunReportQuery.isLoading && !suiteRunReport ? (
        <Empty description="测试集报告加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : suiteRunReport ? (
        <div className="api-collection-run-report-layout">
          <div className="api-collection-run-report-static">
            <div className="api-collection-run-report-head">
              <div className="api-collection-run-report-head-main">
                <div className="api-collection-run-report-title">
                  <Text strong>运行结果</Text>
                  <Tag color={getExecutionStatusMeta(suiteRunReport.status).color}>{getExecutionStatusMeta(suiteRunReport.status).label}</Tag>
                </div>
                <div className="api-collection-run-report-meta">
                  <span>开始：{formatTime(suiteRunReport.startedAt)}</span>
                  <span>结束：{formatTime(suiteRunReport.finishedAt)}</span>
                  <span>总耗时：{suiteRunReport.durationMs ?? 0} ms</span>
                  <span>当前 URL：{suiteRunReport.currentUrl || '-'}</span>
                  <span>Trace：{suiteRunReport.tracePath || '-'}</span>
                </div>
              </div>
              <div className="api-collection-run-report-head-actions">
                <Button onClick={handleRefreshSuiteRunReport} loading={refreshingSuiteRunReport} disabled={!selectedSuiteRunId}>
                  刷新报告
                </Button>
              </div>
            </div>

            <div className="api-collection-run-report-summary-grid">
              <div className="api-collection-run-report-summary-item">
                <span>总数</span>
                <strong>{suiteRunReport.totalCount ?? 0}</strong>
              </div>
              <div className="api-collection-run-report-summary-item success">
                <span>成功</span>
                <strong>{suiteRunReport.successCount ?? 0}</strong>
              </div>
              <div className="api-collection-run-report-summary-item failed">
                <span>失败</span>
                <strong>{suiteRunReport.failedCount ?? 0}</strong>
              </div>
              <div className="api-collection-run-report-summary-item error">
                <span>异常</span>
                <strong>{suiteRunReport.errorCount ?? 0}</strong>
              </div>
              <div className="api-collection-run-report-summary-item skipped">
                <span>跳过</span>
                <strong>{suiteRunReport.skippedCount ?? 0}</strong>
              </div>
              <div className="api-collection-run-report-summary-item">
                <span>报告 ID</span>
                <strong>{suiteRunReport.suiteRunId ?? '-'}</strong>
              </div>
            </div>

            {suiteRunReport.errorMessage ? (
              <Alert showIcon type="error" title={suiteRunReport.errorMessage} className="api-case-run-result-alert" />
            ) : null}

            <Segmented
              className="api-case-run-result-segmented"
              options={uiSuiteRunReportViewOptions}
              value={suiteRunReportView}
              onChange={(value) => setSuiteRunReportView(value as UiSuiteRunReportView)}
            />
          </div>

          <div className="api-collection-run-report-scroll">
            <div className="api-collection-run-report-content">
              {suiteRunReportView === 'snapshot' ? (
                suiteRunReport.snapshot ? (
                  <pre className="api-case-run-result-pre compact">{prettyPrintValue(suiteRunReport.snapshot)}</pre>
                ) : (
                  <Empty description="暂无运行快照" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )
              ) : orderedSuiteRunItems.length === 0 ? (
                <Empty
                  description={selectedSuiteRunSummary?.status && isUiRunPollingStatus(selectedSuiteRunSummary.status) ? '运行中，报告生成中...' : '暂无测试集运行明细'}
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              ) : (
                <div className="api-collection-run-report-list">
                  {orderedSuiteRunItems.map((item, index) => {
                    const itemKey = getUiTestSuiteRunItemKey(item, index)
                    const expanded = expandedSuiteRunItemIds.includes(itemKey)
                    const statusMeta = getExecutionStatusMeta(item.status)

                    return (
                      <div key={itemKey} className={`api-collection-run-report-item${expanded ? ' expanded' : ''}`}>
                        <button type="button" className="api-collection-run-report-item-head" onClick={() => toggleSuiteRunItem(itemKey)}>
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
                              <span>用例名称：{item.caseName || '-'}</span>
                              <span>itemId：{item.itemId || '-'}</span>
                              <span>当前 URL：{item.currentUrl || '-'}</span>
                              <span>步骤数：{item.stepResults?.length ?? 0}</span>
                              <span>失败后继续：{item.continueOnFailure ? '是' : '否'}</span>
                            </div>
                            {item.errorMessage ? <Alert showIcon type="error" title={item.errorMessage} className="api-case-run-result-alert" /> : null}
                            <div className="api-case-run-result-block">
                              {renderUiRunStepResultList(item.stepResults ?? [], '该用例暂无步骤结果')}
                              {item.snapshot ? <pre className="api-case-run-result-pre compact">{prettyPrintValue(item.snapshot)}</pre> : null}
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
