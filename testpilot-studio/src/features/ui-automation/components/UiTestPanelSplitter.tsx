import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from 'react'

type UiTestPanelSplitterProps = {
  onResize: (deltaY: number) => void
}

const KEYBOARD_RESIZE_STEP = 24

export function UiTestPanelSplitter({ onResize }: UiTestPanelSplitterProps) {
  const [isResizing, setIsResizing] = useState(false)
  const lastPointerYRef = useRef<number | null>(null)
  const onResizeRef = useRef(onResize)

  useEffect(() => {
    onResizeRef.current = onResize
  }, [onResize])

  useEffect(() => {
    if (!isResizing) return

    function handlePointerMove(event: PointerEvent) {
      const previousY = lastPointerYRef.current
      if (previousY === null) return

      const deltaY = event.clientY - previousY
      if (deltaY === 0) return

      lastPointerYRef.current = event.clientY
      onResizeRef.current(deltaY)
    }

    function stopResizing() {
      lastPointerYRef.current = null
      setIsResizing(false)
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', stopResizing)
    window.addEventListener('pointercancel', stopResizing)

    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', stopResizing)
      window.removeEventListener('pointercancel', stopResizing)
    }
  }, [isResizing])

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    lastPointerYRef.current = event.clientY
    setIsResizing(true)
    event.currentTarget.setPointerCapture?.(event.pointerId)
    event.preventDefault()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return

    onResize(event.key === 'ArrowUp' ? -KEYBOARD_RESIZE_STEP : KEYBOARD_RESIZE_STEP)
    event.preventDefault()
  }

  return (
    <div
      className={`api-case-editor-splitter${isResizing ? ' resizing' : ''}`}
      role="separator"
      aria-label="调整步骤编辑器和调试结果区域高度"
      aria-orientation="horizontal"
      tabIndex={0}
      onPointerDown={handlePointerDown}
      onKeyDown={handleKeyDown}
    >
      <span className="api-case-editor-splitter-line" />
      <span className="api-case-editor-splitter-grip">⋯</span>
    </div>
  )
}
