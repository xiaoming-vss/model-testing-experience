import { LeftOutlined, RightOutlined } from '@ant-design/icons'
import { Button, Empty, Image, Tooltip } from 'antd'

import type { UiStepSnapshot } from '../utils/detailRunView'
import type { UiTestCaseRun } from '@/services/api'

import { isUiRunPollingStatus } from '../utils/runHelpers'

/*
 * 回放舞台：设计稿这里是录屏播放器（含视频进度条、倍速、下载）。
 * 平台只产出逐步截图，没有视频文件，于是同一块地方放的是「按步骤截图回放」：
 * 浏览器外壳显示运行时的当前 URL，舞台显示当前步骤的截图，下面的滑轨按步骤打点，
 * 点击打点或前后按钮切换步骤。没有截图的步骤显示占位而不是伪造画面。
 * 样式见 styles/detail-inspector-v2.css。
 */

type Props = {
  run: UiTestCaseRun | null
  snapshots: UiStepSnapshot[]
  activeIndex: number
  viewportText: string
  screenshotText: string
  onActiveIndexChange: (index: number) => void
}

export function UiRunReplayStage({ run, snapshots, activeIndex, viewportText, screenshotText, onActiveIndexChange }: Props) {
  const activeSnapshot = snapshots[activeIndex]
  const total = snapshots.length
  const progress = total > 1 ? (activeIndex / (total - 1)) * 100 : total === 1 ? 100 : 0

  return (
    <section className="ui-wb-card ui-wb-replay">
      <header className="ui-wb-card-head">
        <div className="ui-wb-card-title">
          <span className="ui-wb-card-dot" aria-hidden="true" />
          执行回放
          <span className="ui-wb-card-chip">Step Snapshots</span>
        </div>
        <div className="ui-wb-card-head-side">
          <span className="ui-wb-card-chip is-mono">{viewportText}</span>
          <Tooltip title="截图策略">
            <span className="ui-wb-card-chip">{screenshotText}</span>
          </Tooltip>
        </div>
      </header>

      <div className="ui-wb-replay-stage">
        <div className="ui-wb-replay-chrome">
          <span className="ui-wb-replay-chrome-dots" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span className="ui-wb-replay-chrome-url" title={run?.currentUrl || ''}>
            {run?.currentUrl || '尚未产生运行地址'}
          </span>
          <span className={`ui-wb-replay-chrome-state${run && !isUiRunPollingStatus(run.status) ? ' is-done' : ''}`}>
            {run ? (isUiRunPollingStatus(run.status) ? 'AUT RUNNING' : 'AUT DONE') : 'AUT IDLE'}
          </span>
        </div>

        <div className="ui-wb-replay-canvas">
          {activeSnapshot?.screenshotPath ? (
            <Image
              src={activeSnapshot.screenshotPath}
              alt={`${activeSnapshot.name} 的截图`}
              className="ui-wb-replay-shot"
              preview={{ mask: '查看大图' }}
            />
          ) : (
            <div className="ui-wb-replay-placeholder">
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  !run
                    ? '还没有运行记录，先对当前用例发起一次调试运行'
                    : total === 0
                      ? '本次运行还没有步骤结果'
                      : '该步骤没有截图，可在测试集运行配置里改用「每个步骤后截图」'
                }
              />
            </div>
          )}

          {activeSnapshot ? (
            <div className="ui-wb-replay-overlay">
              <span className={`ui-wb-replay-overlay-dot tone-${activeSnapshot.tone}`} aria-hidden="true" />
              <span className="ui-wb-replay-overlay-text">
                Step {activeSnapshot.orderNo ?? activeIndex + 1}: {activeSnapshot.keyword || 'step'}（{activeSnapshot.name}）
              </span>
            </div>
          ) : null}
        </div>
      </div>

      <div className="ui-wb-replay-track">
        <div className="ui-wb-replay-track-bar" role="presentation">
          <div className="ui-wb-replay-track-fill" style={{ width: `${progress}%` }} />
          {snapshots.map((snapshot, index) => (
            <button
              key={snapshot.key}
              type="button"
              className={`ui-wb-replay-pin${index === activeIndex ? ' active' : ''} tone-${snapshot.tone}`}
              style={{ left: `${total > 1 ? (index / (total - 1)) * 100 : 50}%` }}
              title={`#${snapshot.orderNo ?? index + 1} ${snapshot.name}`}
              aria-label={`跳转到第 ${snapshot.orderNo ?? index + 1} 步 ${snapshot.name}`}
              onClick={() => onActiveIndexChange(index)}
            />
          ))}
        </div>

        <div className="ui-wb-replay-controls">
          <div className="ui-wb-replay-controls-main">
            <Tooltip title="上一步">
              <Button
                type="text"
                size="small"
                className="ui-wb-replay-nav"
                icon={<LeftOutlined />}
                aria-label="上一步"
                disabled={activeIndex <= 0}
                onClick={() => onActiveIndexChange(activeIndex - 1)}
              />
            </Tooltip>
            <Tooltip title="下一步">
              <Button
                type="text"
                size="small"
                className="ui-wb-replay-nav"
                icon={<RightOutlined />}
                aria-label="下一步"
                disabled={total === 0 || activeIndex >= total - 1}
                onClick={() => onActiveIndexChange(activeIndex + 1)}
              />
            </Tooltip>
            <span className="ui-wb-replay-position">
              {total === 0 ? '0 / 0' : `${activeIndex + 1} / ${total}`}
            </span>
            {activeSnapshot?.durationText ? <span className="ui-wb-replay-duration">{activeSnapshot.durationText}</span> : null}
          </div>
          <span className="ui-wb-replay-hint">按步骤截图回放，没有录屏文件</span>
        </div>
      </div>
    </section>
  )
}
