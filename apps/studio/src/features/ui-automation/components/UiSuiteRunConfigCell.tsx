import { CameraOutlined, ClockCircleOutlined, EyeInvisibleOutlined, EyeOutlined } from '@ant-design/icons'

import type { UiTestSuite, UiScreenshotPolicy } from '../types'
import { formatUiScreenshotPolicy } from '../constants/defaultRunConfig'

/**
 * 列表「运行配置」列的徽标组（设计稿的 execution config badges）：执行模式 / 视口 / 超时 + 截图策略。
 *
 * 三个徽标的形状与设计稿一致，颜色走共享九色盘，所以元素上要同时带 tone-* 类：
 * 可视是绿色（回放能看到画面），无头是中性灰；截图策略按「截得越多越显眼」排序——每步都截图是蓝色，
 * 只在失败时截图是琥珀色（设计稿里默认值就是这个色），不截图为中性灰。
 *
 * 慢动作（slowMoMs）沿用旧列表的处理：不在这里显示，进编辑抽屉看。
 */
function screenshotTone(policy?: UiScreenshotPolicy) {
  if (policy === 'after_each_step') return 'tone-blue'
  if (policy === 'never') return 'tone-slate'
  return 'tone-amber'
}

export function UiSuiteRunConfigCell({ suite }: { suite: UiTestSuite }) {
  const headless = suite.headless === true
  const viewport =
    suite.viewportWidth && suite.viewportHeight ? `${suite.viewportWidth} × ${suite.viewportHeight}` : '-'
  const timeout = suite.defaultStepTimeoutMs ? `${suite.defaultStepTimeoutMs}ms` : '-'
  const policy = formatUiScreenshotPolicy(suite.screenshotPolicy)

  return (
    <div className="ui-suite-list-config-cell">
      <span className={`ui-suite-list-badge ${headless ? 'tone-slate' : 'tone-green'}`}>
        {headless ? <EyeInvisibleOutlined /> : <EyeOutlined />}
        {headless ? '无头' : '可视'}
      </span>
      <span className="ui-suite-list-badge is-mono tone-slate">{viewport}</span>
      <span className={`ui-suite-list-badge ${screenshotTone(suite.screenshotPolicy)}`}>
        {suite.screenshotPolicy === 'on_failure' ? <CameraOutlined /> : <ClockCircleOutlined />}
        {timeout} / {policy}
      </span>
    </div>
  )
}
