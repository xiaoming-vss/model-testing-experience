import { ArrowLeftOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import { useEffect, useId, useRef, type ReactNode } from 'react'

type ArtifactFrameProps = {
  open?: boolean
  title?: ReactNode
  className?: string
  children?: ReactNode
  footer?: ReactNode
  hideHeader?: boolean
  onCancel?: () => void
}

/** 保留产物标题栏插槽与滚动结构，在画布内阅读时不遮挡或锁定右侧栏。 */
export function GenerationArtifactFrame({ hideHeader, ...props }: ArtifactFrameProps) {
  const titleId = useId()
  const frame = useRef<HTMLElement>(null)
  useEffect(() => {
    if (!props.open) return
    const previous = document.activeElement as HTMLElement | null
    frame.current?.focus()
    return () => { if (previous?.isConnected) previous.focus() }
  }, [props.open])
  if (!props.open) return null
  return <section ref={frame} tabIndex={-1} role="dialog" aria-modal={false} aria-labelledby={titleId}
    className={`ant-modal gc-embedded-artifact ${props.className ?? ''}`}>
      {hideHeader ? <span id={titleId} hidden>{props.title}</span> : <div className="ant-modal-header">
        <div className="ant-modal-title" id={titleId}>{props.title}</div>
        <Button className="gc-return-canvas" size="small" icon={<ArrowLeftOutlined aria-hidden />}
          onClick={() => props.onCancel?.()}>返回流程</Button>
      </div>}
      <div className="ant-modal-body">{props.children}</div>
      {props.footer ? <div className="ant-modal-footer">{props.footer}</div> : null}
  </section>
}
