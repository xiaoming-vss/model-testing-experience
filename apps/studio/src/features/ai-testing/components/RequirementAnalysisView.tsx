import { Empty } from 'antd'
import { useMemo, useState } from 'react'
import { JsonEditor } from '@/shared/components/JsonEditor/JsonEditor'
import '@/features/ai-testing/styles/functional-import-confirm.css'
import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/requirement-analysis.css'
import '@/features/ai-testing/styles/run-result.css'
import { isJsonText, parseRequirementAnalysisContent } from '../utils/functionalOutput'
import { ArtifactViewTabs } from './ArtifactViewTabs'
import { TestScopeAnalysisView } from './TestScopeAnalysisView'

export type RequirementAnalysisViewMode = 'json' | 'diagram'

export function RequirementAnalysisDiagramView({ content, materialContent }: {
  content: string
  materialContent?: string
}) {
  const parsed = useMemo(() => parseRequirementAnalysisContent(content), [content])
  return parsed
    ? <TestScopeAnalysisView analysis={parsed} materialContent={materialContent} />
    : <Empty description="测试范围风险分析格式无效，请重新生成" />
}

export function RequirementAnalysisView({ content }: { content: string }) {
  const [activeView, setActiveView] = useState<RequirementAnalysisViewMode>('diagram')
  return <ArtifactViewTabs jsonCopyText={content}
    className="ai-requirement-analysis-tabs"
    size="small"
    activeKey={activeView}
    onChange={(key) => setActiveView(key as RequirementAnalysisViewMode)}
    items={[
      { key: 'diagram', label: '可视化', children: <RequirementAnalysisDiagramView content={content} /> },
      { key: 'json', label: 'json', children: isJsonText(content)
        ? <JsonEditor value={content} showCopy={false} readOnly foldable minHeight={640} />
        : <pre className="ai-task-code-block">{content}</pre> },
    ]} />
}
