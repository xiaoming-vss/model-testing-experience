import { getNodesBounds, getViewportForBounds, type Node } from '@xyflow/react'
import { toBlob } from 'html-to-image'
import { saveBlob } from './download'

/** 导出 React Flow 的完整节点范围，不依赖当前视口位置。 */
export async function saveFlowImage(canvas: HTMLElement, nodes: Node[], fileName: string) {
  const viewport = canvas.querySelector<HTMLElement>('.react-flow__viewport')
  if (!viewport) throw new Error('图谱尚未准备完成')
  const bounds = getNodesBounds(nodes)
  const width = Math.ceil(bounds.width + 48)
  const height = Math.ceil(bounds.height + 48)
  const transform = getViewportForBounds(bounds, width, height, 1, 1, 0)
  const canvasStyle = getComputedStyle(canvas)
  const blob = await toBlob(viewport, {
    pixelRatio: 2,
    skipFonts: true,
    width,
    height,
    style: {
      width: `${width}px`,
      height: `${height}px`,
      transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.zoom})`,
      background: canvasStyle.getPropertyValue('--graph-export-background').trim(),
    },
  })
  if (!blob) throw new Error('导出内容为空')
  saveBlob(blob, fileName)
}
