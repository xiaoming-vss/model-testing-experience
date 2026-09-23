import type { SelectProps } from 'antd'
import type { ApiAssertComparator, ApiAssertSource, ApiCase, ApiExtractRuleSource } from '@/services/api'
import { builtinTemplateFunctions as sharedBuiltinTemplateFunctions } from '@/shared/constants/templateFunctions'

export type RunResultView = 'request' | 'response' | 'extract' | 'assert'
export type CollectionReportView = 'items' | 'runtime'
export type EnvVarPickerMode = 'environment' | 'builtin'

export const DRAFT_CASE_ID = '__draft_case__'
export const MIN_EDITOR_TOP_HEIGHT = 280
export const MIN_EDITOR_RESULT_HEIGHT = 48
export const ENV_VAR_TOKEN_PREFIX = '{{'
export const ENV_VAR_TOKEN_SUFFIX = '}}'
export const builtinTemplateFunctions = sharedBuiltinTemplateFunctions

export const methodOptions: SelectProps['options'] = [
  { label: <span className="api-method-label api-method-get">GET</span>, value: 'GET' },
  { label: <span className="api-method-label api-method-post">POST</span>, value: 'POST' },
  { label: <span className="api-method-label api-method-put">PUT</span>, value: 'PUT' },
  { label: <span className="api-method-label api-method-delete">DELETE</span>, value: 'DELETE' },
  { label: <span className="api-method-label api-method-patch">PATCH</span>, value: 'PATCH' },
]

export const bodyTypeOptions: Array<{ label: string; value: NonNullable<ApiCase['bodyType']> }> = [
  { label: 'none', value: 'none' },
  { label: 'JSON', value: 'json' },
  // `form` 由 worker 作为表单体发出，落到请求上就是 x-www-form-urlencoded。
  { label: 'x-www-form-urlencoded', value: 'form' },
  { label: 'raw', value: 'raw' },
]

/**
 * 请求头面板的「快捷注入」预设：接口调试里最常手写的几个头。
 * `Authorization` 与 `X-Request-ID` 只注入键名，值留给使用者按当前环境填写。
 */
export const headerQuickInjectPresets: Array<{ label: string; key: string; value: string }> = [
  { label: 'Authorization', key: 'Authorization', value: '' },
  { label: 'Accept: application/json', key: 'Accept', value: 'application/json' },
  { label: 'X-Request-ID', key: 'X-Request-ID', value: '' },
  { label: 'User-Agent', key: 'User-Agent', value: '' },
]

export const runResultViewOptions: Array<{ label: string; value: RunResultView }> = [
  { label: '原始请求', value: 'request' },
  { label: '响应结果', value: 'response' },
  { label: '提取结果', value: 'extract' },
  { label: '断言结果', value: 'assert' },
]

export const collectionReportViewOptions: Array<{ label: string; value: CollectionReportView }> = [
  { label: '用例明细', value: 'items' },
  { label: '运行变量快照', value: 'runtime' },
]

export const assertSourceOptions: Array<{ label: string; value: ApiAssertSource }> = [
  { label: '状态码', value: 'status_code' },
  { label: '响应头', value: 'header' },
  { label: 'JSONPath', value: 'body_jsonpath' },
  { label: '响应文本', value: 'body_text' },
]

export const assertComparatorOptions: Array<{ label: string; value: ApiAssertComparator }> = [
  { label: '等于', value: 'eq' },
  { label: '不等于', value: 'neq' },
  { label: '包含', value: 'contains' },
  { label: '不包含', value: 'not_contains' },
  { label: '大于', value: 'gt' },
  { label: '大于等于', value: 'gte' },
  { label: '小于', value: 'lt' },
  { label: '小于等于', value: 'lte' },
  { label: '存在', value: 'exists' },
  { label: '正则匹配', value: 'regex' },
]

export const extractSourceOptions: Array<{ label: string; value: ApiExtractRuleSource }> = [
  { label: '响应头', value: 'header' },
  { label: 'JSONPath', value: 'body_jsonpath' },
  { label: '响应文本', value: 'body_text' },
  { label: '状态码', value: 'status_code' },
]

export const assertSourceLabelMap: Record<ApiAssertSource, string> = {
  status_code: '状态码',
  header: '响应头',
  body_jsonpath: 'JSONPath',
  body_text: '响应文本',
}

export const assertComparatorLabelMap: Record<ApiAssertComparator, string> = {
  eq: '等于',
  neq: '不等于',
  contains: '包含',
  not_contains: '不包含',
  gt: '大于',
  gte: '大于等于',
  lt: '小于',
  lte: '小于等于',
  exists: '存在',
  regex: '正则匹配',
}

export const extractSourceLabelMap: Record<ApiExtractRuleSource, string> = {
  header: '响应头',
  body_jsonpath: 'JSONPath',
  body_text: '响应文本',
  status_code: '状态码',
}

/*
 * 请求方式 → 色盘色调。用例列表的方法徽标与请求地址条的方法选择器都用它；
 * 色调名对应 shared/styles/surface-tokens.css 的 `.tone-*`，页面根节点带 `tp-surface` 才有值。
 */
export function methodTone(method: ApiCase['method']): 'green' | 'blue' | 'amber' | 'purple' | 'red' {
  switch (method) {
    case 'GET':
      return 'green'
    case 'POST':
      return 'blue'
    case 'PUT':
      return 'amber'
    case 'PATCH':
      return 'purple'
    case 'DELETE':
      return 'red'
    default:
      return 'blue'
  }
}
