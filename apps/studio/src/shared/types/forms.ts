import type { UiTestSuite } from '@/services/api'

export type CollectionFormValues = {
  sprintId?: string
  requirementId?: string
  name: string
  summary?: string
}

export type UiTestSuiteFormValues = {
  sprintId?: string
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
