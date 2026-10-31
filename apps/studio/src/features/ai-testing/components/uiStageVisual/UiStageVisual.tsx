import { useMemo } from 'react'
import '../../styles/ui-stage-visual.css'
import { DesignVisual } from './DesignVisual'
import { SurfaceVisual } from './SurfaceVisual'
import { YamlVisual } from './YamlVisual'
import { VisualEmpty } from './VisualStates'
import type { UiGenerationStage } from '../../utils/uiGenerationStage'

/** 三阶段的可视化只读视图；原文修改统一回到 JSON/YAML 视图完成。 */
export function UiStageVisual({ stage, content, onShowRaw }: {
  stage: UiGenerationStage
  content: string
  onShowRaw: () => void
}) {
  return useMemo(() => {
    if (!content.trim()) {
      return <VisualEmpty title="当前阶段尚未生成产物" description="产物生成后这里会显示可视化结构；也可以切换到原文查看当前内容。" onShowRaw={onShowRaw} />
    }
    if (stage === 'ui_surface') return <SurfaceVisual content={content} onShowRaw={onShowRaw} />
    if (stage === 'ui_design') return <DesignVisual content={content} onShowRaw={onShowRaw} />
    return <YamlVisual content={content} onShowRaw={onShowRaw} />
  }, [content, onShowRaw, stage])
}
