type EditorPanelHeightOptions = {
  currentHeight: number
  deltaY: number
  containerHeight: number
  minTopHeight: number
  minResultHeight: number
  splitterHeight: number
}

export function getNextEditorTopHeight({
  currentHeight,
  deltaY,
  containerHeight,
  minTopHeight,
  minResultHeight,
  splitterHeight,
}: EditorPanelHeightOptions) {
  const maxHeight = Math.max(minTopHeight, containerHeight - minResultHeight - splitterHeight)
  return Math.max(minTopHeight, Math.min(maxHeight, currentHeight + deltaY))
}
