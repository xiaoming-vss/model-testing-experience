import {
  assertComparatorLabelMap,
  assertSourceLabelMap,
  type RunResultView
} from '@/features/api-automation/config/collectionConfig'
import {
  formatOptionalValue,
  parseMaybeJsonValue
} from '@/features/api-automation/utils/apiCaseEditor'
import {
  type ApiAssertComparator,
  type ApiAssertSource,
  type ApiCaseRunResult
} from '@/services/api'
import { Empty, Tag } from 'antd'
import { type ReactNode } from 'react'

export function renderRunResultContent(params: {
  view: RunResultView
  request?: ApiCaseRunResult['request']
  response?: ApiCaseRunResult['response']
  extractResults?: ApiCaseRunResult['extractResults']
  assertResults?: ApiCaseRunResult['assertResults']
  emptyExtractDescription?: string
  emptyAssertDescription?: string
}): ReactNode {
  const {
    view,
    request,
    response,
    extractResults: currentExtractResults = [],
    assertResults: currentAssertResults = [],
    emptyExtractDescription = '暂无提取结果',
    emptyAssertDescription = '暂无断言结果',
  } = params

  if (view === 'request') {
    const hasRequestSnapshot = Boolean(request?.url || request?.method || request?.bodyType || request?.headersJson || request?.queryJson || request?.body)
    if (!hasRequestSnapshot) {
      return <Empty description="请求快照尚未生成" image={Empty.PRESENTED_IMAGE_SIMPLE} />
    }

    return (
      <pre className="api-case-run-result-pre compact">
        {JSON.stringify(
          {
            url: request?.url,
            method: request?.method,
            bodyType: request?.bodyType,
            headers: parseMaybeJsonValue(request?.headersJson),
            query: parseMaybeJsonValue(request?.queryJson),
            body: parseMaybeJsonValue(request?.body),
          },
          null,
          2,
        )}
      </pre>
    )
  }

  if (view === 'response') {
    const hasResponseSnapshot = Boolean(response?.statusCode || response?.headersJson || response?.body)
    if (!hasResponseSnapshot) {
      return <Empty description="响应结果尚未生成" image={Empty.PRESENTED_IMAGE_SIMPLE} />
    }

    return (
      <pre className="api-case-run-result-pre compact">
        {JSON.stringify(parseMaybeJsonValue(response?.body), null, 2)}
      </pre>
    )
  }

  if (view === 'extract') {
    return (
      <div className="api-case-run-result-subsection">
        {currentExtractResults.length === 0 ? (
          <Empty description={emptyExtractDescription} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div className="api-case-run-result-list">
            {currentExtractResults.map((item, index) => (
              <div key={`${item.extractRuleId ?? index}`} className={`api-case-run-result-row${item.success ? '' : ' failed'}`}>
                <div className="api-case-run-result-row-title">
                  <strong>{item.name ?? `提取 ${index + 1}`}</strong>
                  <Tag color={item.success ? 'success' : 'error'}>{item.success ? '成功' : '失败'}</Tag>
                  {item.usedDefault ? <Tag color="gold">默认值</Tag> : null}
                </div>
                <div className="api-case-run-result-row-meta">
                  <span className="api-case-run-result-meta-item">
                    <strong>变量</strong>
                    <span>{formatOptionalValue(item.varKey)}</span>
                  </span>
                  <span className="api-case-run-result-meta-item">
                    <strong>值</strong>
                    <span>{formatOptionalValue(item.value)}</span>
                  </span>
                  <span className="api-case-run-result-meta-item">
                    <strong>信息</strong>
                    <span>{formatOptionalValue(item.errorMessage)}</span>
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="api-case-run-result-subsection">
      {currentAssertResults.length === 0 ? (
        <Empty description={emptyAssertDescription} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div className="api-case-run-result-list">
          {currentAssertResults.map((item, index) => (
            <div key={`${item.assertRuleId ?? index}`} className={`api-case-run-result-row${item.success ? '' : ' failed'}`}>
              <div className="api-case-run-result-row-title">
                <strong>{item.name ?? `断言 ${index + 1}`}</strong>
                <Tag color={item.success ? 'success' : 'error'}>{item.success ? '成功' : '失败'}</Tag>
              </div>
              <div className="api-case-run-result-row-meta">
                <span className="api-case-run-result-meta-item">
                  <strong>来源</strong>
                  <span>{assertSourceLabelMap[item.assertSource as ApiAssertSource] ?? formatOptionalValue(item.assertSource)}</span>
                </span>
                <span className="api-case-run-result-meta-item">
                  <strong>比较</strong>
                  <span>{assertComparatorLabelMap[item.comparator as ApiAssertComparator] ?? formatOptionalValue(item.comparator)}</span>
                </span>
                <span className="api-case-run-result-meta-item">
                  <strong>目标</strong>
                  <span>{formatOptionalValue(item.targetExpr)}</span>
                </span>
                <span className="api-case-run-result-meta-item">
                  <strong>期望</strong>
                  <span>{formatOptionalValue(item.expectedValue)}</span>
                </span>
                <span className="api-case-run-result-meta-item">
                  <strong>实际</strong>
                  <span>{formatOptionalValue(item.actualValue)}</span>
                </span>
                <span className="api-case-run-result-meta-item">
                  <strong>信息</strong>
                  <span>{formatOptionalValue(item.errorMessage)}</span>
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
