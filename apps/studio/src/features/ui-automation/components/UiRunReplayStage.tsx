import { StoredImage } from '@/shared/components/files/StoredFile'
import { RunCard, runCardChipClass } from '@/shared/components/RunCard'
import { LeftOutlined, RightOutlined } from '@ant-design/icons'
import { Button, Empty, Tooltip } from 'antd'

import type { UiStepSnapshot } from '../utils/detailRunView'
import type { UiTestCaseRun } from '@/services/api'

import { isUiRunPollingStatus } from '../utils/runHelpers'

/*
 * 回放舞台：设计稿这里是录屏播放器（含视频进度条、倍速、下载）。
 * 平台只产出逐步截图，没有视频文件，于是同一块地方放的是「按步骤截图回放」：
 * 浏览器外壳显示运行时的当前 URL，舞台显示当前步骤的截图，下面的滑轨按步骤打点，
 * 点击打点或前后按钮切换步骤。没有截图的步骤显示占位而不是伪造画面。
 * 卡片骨架见 shared/components/RunCard。
 */

type Props = {
  run: UiTestCaseRun | null
  snapshots: UiStepSnapshot[]
  activeIndex: number
  viewportText: string
  viewportWidth?: number
  viewportHeight?: number
  screenshotText: string
  onActiveIndexChange: (index: number) => void
}

export function UiRunReplayStage({ run, snapshots, activeIndex, viewportText, viewportWidth, viewportHeight, screenshotText, onActiveIndexChange }: Props) {
  const activeSnapshot = snapshots[activeIndex]
  const total = snapshots.length
  const aspectRatio = viewportWidth && viewportHeight && Number.isFinite(viewportWidth) && Number.isFinite(viewportHeight) && viewportWidth > 0 && viewportHeight > 0
    ? `${viewportWidth} / ${viewportHeight}` : undefined
  const progress = total > 1 ? (activeIndex / (total - 1)) * 100 : total === 1 ? 100 : 0

  return (
    <RunCard
      className="ui-wb-replay"
      dot
      title="执行回放"
      chip="Step Snapshots"
      side={<>
        <span className={runCardChipClass}>{viewportText}</span>
        <Tooltip title="截图策略">
          <span className={runCardChipClass}>{screenshotText}</span>
        </Tooltip>
      </>}
    >

      <div className="ui-wb-replay-stage flex min-h-[150px] flex-[1_1_auto] flex-col overflow-hidden rounded-[var(--srf-radius-control)] bg-[var(--srf-terminal-bg)]">
        <div className="ui-wb-replay-chrome flex items-center gap-2 bg-[var(--srf-terminal-bar)] px-2.5 py-1.5 font-[ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace] text-[11px] text-[var(--srf-terminal-muted)]">
          <span className="ui-wb-replay-chrome-dots inline-flex items-center gap-1 [&>span:first-child]:bg-[var(--srf-result-failed)] [&>span:last-child]:bg-[var(--srf-result-passed)]" aria-hidden="true">
            <span className="h-2 w-2 rounded-full bg-[var(--srf-track-pending)]" />
            <span className="h-2 w-2 rounded-full bg-[var(--srf-track-pending)]" />
            <span className="h-2 w-2 rounded-full bg-[var(--srf-track-pending)]" />
          </span>
          <span className="ui-wb-replay-chrome-url min-w-0 flex-[1_1_auto] overflow-hidden text-ellipsis whitespace-nowrap" title={run?.currentUrl || ''}>
            {run?.currentUrl || '尚未产生运行地址'}
          </span>
          <span className={`ui-wb-replay-chrome-state flex-none font-bold tracking-[0.02em] text-[var(--srf-terminal-accent)]${run && !isUiRunPollingStatus(run.status) ? ' is-done text-[var(--srf-terminal-info)]' : ''}`}>
            {run ? (isUiRunPollingStatus(run.status) ? 'AUT RUNNING' : 'AUT DONE') : 'AUT IDLE'}
          </span>
        </div>

        <div className="ui-wb-replay-canvas relative flex min-h-[120px] max-h-[min(40vh,480px)] flex-[0_1_auto] items-center justify-center overflow-hidden bg-[var(--srf-terminal-surface)]" style={{ aspectRatio }}>
          {activeSnapshot?.screenshotPath ? (
            <StoredImage
              src={activeSnapshot.screenshotPath}
              alt={`${activeSnapshot.name} 的截图`}
              className="ui-wb-replay-shot max-h-full max-w-full [&_img]:max-h-full [&_img]:object-contain"
              preview={{ mask: '查看大图' }}
            />
          ) : (
            <div className="ui-wb-replay-placeholder p-3 text-center [&_.ant-empty-description]:text-[var(--srf-terminal-muted)]">
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
            <div className="ui-wb-replay-overlay absolute left-2.5 top-2.5 inline-flex max-w-[calc(100%-20px)] items-center gap-1.5 rounded-[6px] bg-[var(--srf-terminal-chip)] px-2 py-1 font-[ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace] text-[11px] text-[var(--srf-terminal-bg)]">
              <span className={`ui-wb-replay-overlay-dot h-1.5 w-1.5 flex-none rounded-full bg-[var(--srf-tone-text,var(--srf-result-skipped))] tone-${activeSnapshot.tone}`} aria-hidden="true" />
              <span className="ui-wb-replay-overlay-text overflow-hidden text-ellipsis whitespace-nowrap">
                Step {activeSnapshot.orderNo ?? activeIndex + 1}: {activeSnapshot.keyword || 'step'}（{activeSnapshot.name}）
              </span>
            </div>
          ) : null}
        </div>
      </div>

      <div className="ui-wb-replay-track flex flex-none flex-col gap-1.5">
        <div className="ui-wb-replay-track-bar relative mx-1 mb-0.5 mt-1.5 h-1.5 rounded-full bg-[var(--srf-track)]" role="presentation">
          <div className="ui-wb-replay-track-fill absolute inset-y-0 left-0 rounded-full bg-[var(--srf-accent)]" style={{ width: `${progress}%` }} />
          {snapshots.map((snapshot, index) => (
            <button
              key={snapshot.key}
              type="button"
              className={`ui-wb-replay-pin absolute top-1/2 h-[9px] w-[9px] -translate-x-1/2 -translate-y-1/2 cursor-pointer rounded-full border-2 border-[var(--srf-card)] bg-[var(--srf-tone-text,var(--srf-track-pending))] p-0${index === activeIndex ? ' active h-3 w-3 bg-[var(--srf-accent)]' : ''} tone-${snapshot.tone}`}
              style={{ left: `${total > 1 ? (index / (total - 1)) * 100 : 50}%` }}
              title={`#${snapshot.orderNo ?? index + 1} ${snapshot.name}`}
              aria-label={`跳转到第 ${snapshot.orderNo ?? index + 1} 步 ${snapshot.name}`}
              onClick={() => onActiveIndexChange(index)}
            />
          ))}
        </div>

        <div className="ui-wb-replay-controls flex flex-wrap items-center justify-between gap-2">
          <div className="ui-wb-replay-controls-main inline-flex items-center gap-1.5 font-[ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace] text-[11px] text-[var(--srf-text-secondary)]">
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
          <span className="ui-wb-replay-hint text-[11px] text-[var(--srf-text-muted)]">按步骤截图回放，没有录屏文件</span>
        </div>
      </div>
    </RunCard>
  )
}
