export const locatorTypes = ['css', 'xpath', 'text', 'placeholder', 'label', 'test_id', 'role'] as const
export type ElementLocatorType = (typeof locatorTypes)[number]
/** 列表里的定位方式标签，等宽大写，和接口库的方法签同一套阅读语言。 */
export const locatorTypeLabels: Record<ElementLocatorType, string> = {
  css: 'CSS',
  xpath: 'XPATH',
  text: 'TEXT',
  placeholder: 'PLACEHOLDER',
  label: 'LABEL',
  test_id: 'TEST_ID',
  role: 'ROLE',
}
export type VerificationStatus = 'pending' | 'verified'

export interface ElementGroup {
  groupId: string
  kind: 'page' | 'common'
  name: string
  routeTemplate: string
  elementCount: number
}

export interface ElementParameter {
  name: string
  description: string
}

export interface ElementDraft {
  groupId: string | null
  name: string
  scope: string
  locatorType: ElementLocatorType
  locatorValue: string
  parameters: ElementParameter[]
}

export type ElementSummary = Omit<ElementDraft, 'locatorValue' | 'parameters' | 'groupId'> & {
  groupId: string
  elementId: string
  parameterized: boolean
  verificationStatus: VerificationStatus
  version: number
}

export type ElementDetail = ElementSummary & Pick<ElementDraft, 'locatorValue' | 'parameters'> & {
  updatedAt: string
}

export interface ElementFilters {
  groupId?: string
  verificationStatus?: VerificationStatus
  keyword: string
  page: number
  pageSize: number
}
