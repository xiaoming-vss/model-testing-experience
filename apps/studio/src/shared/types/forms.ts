import type { UiTestSuite } from '@/services/api'

export type CollectionFormValues = {
  requirementId?: string
  name: string
  summary?: string
}

export type UiTestSuiteFormValues = {
  requirementId?: string
  name: string
  description?: string
  headless?: boolean
  slowMoMs?: number
  viewportWidth?: number
  viewportHeight?: number
  defaultStepTimeoutMs?: number
  screenshotPolicy?: UiTestSuite['screenshotPolicy']
}
