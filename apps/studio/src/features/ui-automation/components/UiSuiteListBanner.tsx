import { CodeOutlined, DesktopOutlined, FieldTimeOutlined, FullscreenOutlined } from '@ant-design/icons'

import { DEFAULT_UI_TEST_SUITE_RUN_CONFIG } from '../constants/defaultRunConfig'

/**
 * 列表页顶部的引擎信息条（设计稿的 telemetry banner）。
 *
 * 设计稿右上是「执行驱动 / 基准视口规格 / 并发执行节点」三格，两处与现有数据不符，按
 * 「设计稿里没有对应数据的元素一律不做」处理：
 * - 执行驱动只写引擎名，不写版本号：Playwright 版本在 api-ui-worker 的依赖里，前端拿不到；
 * - 并发执行节点要的是节点健康列表，平台没有这个接口，换成同样真实的默认步骤超时；
 * - 「集群健康」徽标同理，换成由默认运行配置推出的执行模式，不显示无法证实的健康状态。
 *
 * 视口与超时取自 DEFAULT_UI_TEST_SUITE_RUN_CONFIG，与新建测试集抽屉的默认值同源。
 */
export function UiSuiteListBanner() {
  const mode = DEFAULT_UI_TEST_SUITE_RUN_CONFIG.headless ? '无头' : '可视'
  const viewport = `${DEFAULT_UI_TEST_SUITE_RUN_CONFIG.viewportWidth} × ${DEFAULT_UI_TEST_SUITE_RUN_CONFIG.viewportHeight}`
  const timeout = `${DEFAULT_UI_TEST_SUITE_RUN_CONFIG.defaultStepTimeoutMs}ms`

  return (
    <div className="ui-suite-list-banner">
      <div className="ui-suite-list-banner-main">
        <span className="ui-suite-list-banner-icon">
          <DesktopOutlined />
        </span>
        <div>
          <div className="ui-suite-list-banner-head">
            <h1 className="ui-suite-list-banner-title">UI自动化测试集</h1>
            <span className="ui-suite-list-banner-chip tone-green">
              <span className="ui-suite-list-banner-chip-dot" aria-hidden />
              默认{mode}模式
            </span>
          </div>
          <p className="ui-suite-list-banner-subtitle">跨浏览器 Playwright / Chromium 无头及可视化回放执行引擎</p>
        </div>
      </div>

      <div className="ui-suite-list-banner-specs">
        <span className="ui-suite-list-banner-spec">
          <CodeOutlined />
          <span>
            <span className="ui-suite-list-banner-spec-label">执行引擎</span>
            <span className="ui-suite-list-banner-spec-value">Playwright / Chromium</span>
          </span>
        </span>
        <span className="ui-suite-list-banner-spec">
          <FullscreenOutlined />
          <span>
            <span className="ui-suite-list-banner-spec-label">默认视口规格</span>
            <span className="ui-suite-list-banner-spec-value is-mono">{viewport}</span>
          </span>
        </span>
        <span className="ui-suite-list-banner-spec">
          <FieldTimeOutlined />
          <span>
            <span className="ui-suite-list-banner-spec-label">默认步骤超时</span>
            <span className="ui-suite-list-banner-spec-value is-mono">{timeout}</span>
          </span>
        </span>
      </div>
    </div>
  )
}
