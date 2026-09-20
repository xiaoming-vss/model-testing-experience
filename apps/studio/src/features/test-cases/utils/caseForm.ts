import type { CreateFunctionTestCasePayload, FunctionCaseContent, FunctionCaseLibraryItem } from '../types'

export type FunctionCaseFormValues = CreateFunctionTestCasePayload

export function createDefaultCaseFormValues(orderNo: number): FunctionCaseFormValues {
  return {
    title: '',
    module: '',
    priority: 'P2',
    caseType: '功能测试',
    content: { preconditions: [], steps: [] },
    orderNo,
  }
}

/** 用例正文优先取 content；老数据只有拼接好的前置条件 / 步骤 / 预期。 */
export function readFunctionCaseContent(item?: FunctionCaseLibraryItem | null): FunctionCaseContent {
  if (item?.content) return item.content

  return {
    preconditions: item?.preconditions ? [item.preconditions] : [],
    steps:
      item?.steps || item?.expectedResults
        ? [{ action: item.steps ?? '', expected: item.expectedResults ?? '' }]
        : [],
  }
}

export function buildCaseFormValues(item: FunctionCaseLibraryItem): FunctionCaseFormValues {
  const content = readFunctionCaseContent(item)
  return {
    ...createDefaultCaseFormValues(item.orderNo ?? 1),
    title: item.title,
    module: item.module ?? '',
    priority: item.priority ?? 'P2',
    caseType: item.caseType ?? '功能测试',
    content: {
      preconditions: [...content.preconditions],
      steps: content.steps.map((step) => ({ ...step })),
    },
  }
}
