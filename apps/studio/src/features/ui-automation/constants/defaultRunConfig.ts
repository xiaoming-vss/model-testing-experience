import type { UiScreenshotPolicy, UiTestSuite } from '../types'

export const DEFAULT_UI_TEST_SUITE_RUN_CONFIG: Pick<
  UiTestSuite,
  'headless' | 'slowMoMs' | 'viewportWidth' | 'viewportHeight' | 'defaultStepTimeoutMs' | 'screenshotPolicy'
> = {
  headless: false,
  slowMoMs: 300,
  viewportWidth: 1440,
  viewportHeight: 900,
  defaultStepTimeoutMs: 5000,
  screenshotPolicy: 'on_failure',
}

export const UI_SCREENSHOT_POLICY_OPTIONS: Array<{ label: string; value: UiScreenshotPolicy }> = [
  { label: '失败时截图', value: 'on_failure' },
  { label: '每个步骤后截图', value: 'after_each_step' },
  { label: '不截图', value: 'never' },
]

export function formatUiScreenshotPolicy(policy?: UiScreenshotPolicy) {
  return UI_SCREENSHOT_POLICY_OPTIONS.find((item) => item.value === policy)?.label ?? '失败时截图'
}