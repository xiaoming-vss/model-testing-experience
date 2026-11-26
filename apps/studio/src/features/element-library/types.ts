export const locatorTypes = ['css', 'xpath', 'text', 'placeholder', 'label', 'test_id', 'role'] as const
export type ElementLocatorType = (typeof locatorTypes)[number]
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
