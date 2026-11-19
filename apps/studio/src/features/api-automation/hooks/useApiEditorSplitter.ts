import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import {
  MIN_EDITOR_RESULT_HEIGHT,
  MIN_EDITOR_TOP_HEIGHT,
} from '../config/collectionConfig'

export function useApiEditorSplitter({ hasRunResult }: { hasRunResult: boolean }) {
  const [editorTopHeight, setEditorTopHeight] = useState(520)
  const [isResizingEditor, setIsResizingEditor] = useState(false)
  const editorLayoutRef = useRef<HTMLDivElement | null>(null)
  const editorResizeRef = useRef<{ startY: number; startHeight: number } | null>(null)

  useEffect(() => {
    if (!hasRunResult || !isResizingEditor) return

    function handlePointerMove(event: PointerEvent) {
      const containerHeight = editorLayoutRef.current?.getBoundingClientRect().height ?? 0
      const dragState = editorResizeRef.current
      if (!dragState || containerHeight === 0) return

      const delta = event.clientY - dragState.startY
      const maxHeight = Math.max(MIN_EDITOR_TOP_HEIGHT, containerHeight - MIN_EDITOR_RESULT_HEIGHT - 18)
      const nextHeight = Math.max(MIN_EDITOR_TOP_HEIGHT, Math.min(maxHeight, dragState.startHeight + delta))
      setEditorTopHeight(nextHeight)
    }

    function handlePointerUp() {
      setIsResizingEditor(false)
      editorResizeRef.current = null
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)

    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', handlePointerUp)
    }
  }, [isResizingEditor, hasRunResult])

  useEffect(() => {
    if (!hasRunResult) return

    function syncEditorTopHeight() {
      const containerHeight = editorLayoutRef.current?.getBoundingClientRect().height ?? 0
      if (containerHeight === 0) return

      const maxHeight = Math.max(MIN_EDITOR_TOP_HEIGHT, containerHeight - MIN_EDITOR_RESULT_HEIGHT - 18)
      setEditorTopHeight((current) => Math.max(MIN_EDITOR_TOP_HEIGHT, Math.min(maxHeight, current)))
    }

    syncEditorTopHeight()
    window.addEventListener('resize', syncEditorTopHeight)

    return () => {
      window.removeEventListener('resize', syncEditorTopHeight)
    }
  }, [hasRunResult])

  function handleEditorSplitterPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    const containerHeight = editorLayoutRef.current?.getBoundingClientRect().height ?? 0
    if (containerHeight === 0) return

    editorResizeRef.current = {
      startY: event.clientY,
      startHeight: editorTopHeight,
    }
    setIsResizingEditor(true)
    event.currentTarget.setPointerCapture(event.pointerId)
    event.preventDefault()
  }

  return {
    editorTopHeight,
    isResizingEditor,
    editorLayoutRef,
    handleEditorSplitterPointerDown,
  } as const
}
