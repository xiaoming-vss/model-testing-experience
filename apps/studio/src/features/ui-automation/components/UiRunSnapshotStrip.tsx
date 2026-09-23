import { Empty, Image } from 'antd'
import { useEffect, useRef } from 'react'

import type { UiStepSnapshot } from '../utils/detailRunView'

/*
 * 关键帧条：设计稿的「关键帧快照 (Visual Diff: 0.00%) + 基线一致」需要视觉差异基线与比对结果，
 * 平台没有这套数据（见 STRUCTURE.md），所以标题只写实际有的：这一步有几张截图、当前看的是哪一步。
 * 缩略图来自运行结果里每个步骤的 screenshotPath。
 *
 * 这一条是单行横向滚动（截图多时不能长高，否则会把下面的执行控制台顶出视口），
 * 所以当前帧被外部切换时要把它滚进视野；直接写 scrollLeft 而不是 scrollIntoView，
 * 免得连带把页面纵向滚走。样式见 styles/detail-inspector-v2.css。
 */

type Props = {
  snapshots: UiStepSnapshot[]
  activeIndex: number
  onSelect: (index: number) => void
}

export function UiRunSnapshotStrip({ snapshots, activeIndex, onSelect }: Props) {
  const listRef = useRef<HTMLDivElement | null>(null)
  const withShots = snapshots.filter((item) => item.screenshotPath)

  useEffect(() => {
    const list = listRef.current
    const active = list?.querySelector<HTMLElement>('.ui-wb-strip-item.active')
    if (!list || !active) return

    const listRect = list.getBoundingClientRect()
    const activeRect = active.getBoundingClientRect()
    list.scrollLeft += activeRect.left - listRect.left - (list.clientWidth - activeRect.width) / 2
  }, [activeIndex, withShots.length])

  return (
    <section className="ui-wb-card ui-wb-strip">
      <header className="ui-wb-card-head">
        <div className="ui-wb-card-title">关键帧快照</div>
        <span className="ui-wb-card-chip is-mono">
          {withShots.length} / {snapshots.length} 步有截图
        </span>
      </header>

      {withShots.length === 0 ? (
        <div className="ui-wb-strip-empty">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本次运行没有步骤截图" />
        </div>
      ) : (
        <div className="ui-wb-strip-list" ref={listRef}>
          {snapshots.map((snapshot, index) => {
            if (!snapshot.screenshotPath) return null

            return (
              <button
                key={snapshot.key}
                type="button"
                className={`ui-wb-strip-item${index === activeIndex ? ' active' : ''}`}
                aria-current={index === activeIndex}
                onClick={() => onSelect(index)}
              >
                <span className="ui-wb-strip-thumb">
                  <Image src={snapshot.screenshotPath} alt={`${snapshot.name} 截图缩略图`} preview={false} />
                  <span className={`ui-wb-strip-order tone-${snapshot.tone}`}>
                    #{snapshot.orderNo ?? index + 1}
                    {snapshot.elapsedText ? ` ${snapshot.elapsedText}` : ''}
                  </span>
                </span>
                <span className="ui-wb-strip-name" title={snapshot.name}>
                  {snapshot.name}
                </span>
              </button>
            )
          })}
        </div>
      )}
    </section>
  )
}
