import { Empty } from 'antd'
import { useMemo } from 'react'
import '@/features/ai-testing/styles/functional-import-confirm.css'
import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/requirement-analysis.css'
import '@/features/ai-testing/styles/run-result.css'
import { parseRequirementAnalysisContent } from '../utils/functionalOutput'
import { TestScopeAnalysisView } from './TestScopeAnalysisView'

export function RequirementAnalysisDiagramView({ content, materialContent }: {
  content: string
  materialContent?: string
}) {
  const parsed = useMemo(() => parseRequirementAnalysisContent(content), [content])
  return parsed
    ? <TestScopeAnalysisView analysis={parsed} materialContent={materialContent} />
    : <Empty description="测试范围风险分析格式无效，请重新生成" />
}
