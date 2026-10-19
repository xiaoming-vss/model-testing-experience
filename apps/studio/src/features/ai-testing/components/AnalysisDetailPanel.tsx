import type { ReactNode } from 'react'
import { formatTextList } from '@/features/ai-testing/utils/functionalOutput'
import '@/features/ai-testing/styles/analysis-rule-details.css'

export function AnalysisDetailValue({ value, list = false }: { value: unknown; list?: boolean }) {
  const text = formatTextList(value)
  if (!text) return <p>{Array.isArray(value) ? '无' : '未明确'}</p>
  return list ? <ul>{text.split('\n').filter((line) => line.trim()).map((line, index) => <li key={index}>{line}</li>)}</ul> : <p>{text}</p>
}

export function AnalysisDetailPanel({ title, emphasis = false, children }: { title: string; emphasis?: boolean; children: ReactNode }) {
  return <section className={`ai-analysis-rule-panel${emphasis ? ' is-emphasis' : ''}`}>
    <h4>{title}</h4>{children}
  </section>
}