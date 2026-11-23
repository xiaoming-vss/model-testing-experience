import { Empty } from 'antd'
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { notify } from '@/shared/utils/toast'
import { normalizeApiConfigCases } from '../../utils/apiConfigDiagram'
import { buildApiConfigContract } from '../../utils/apiConfigContract'
import styles from '../../styles/api-config.module.css'
import { ApiConfigDetail } from './ApiConfigDetail'
import { ApiConfigInterfaceRail } from './ApiConfigInterfaceRail'
import { VIEW_GRID, apiConfigFieldId } from './apiConfigClasses'

function prefersReducedMotion() {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function ApiConfigState({ title, description }: { title: string; description: string }) {
  return <div className="flex min-h-[240px] flex-col items-center justify-center gap-3 p-6">
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<div className="flex flex-col gap-y-1">
      <strong className="text-[13px] text-[var(--ai-text)]">{title}</strong>
      <span className="text-[12px] text-[var(--ai-text-secondary)]">{description}</span>
    </div>} />
  </div>
}

export function ApiConfigDiagramView({ content, defaultCollapsed = false, showRules = false }: {
  content: string
  defaultCollapsed?: boolean
  showRules?: boolean
}) {
  const data = useMemo(() => normalizeApiConfigCases(content), [content])
  const contracts = useMemo(() => new Map((data?.cases ?? []).map((apiCase) => [apiCase.key, buildApiConfigContract(apiCase)])), [data])
  const [selectedKey, setSelectedKey] = useState(() => data?.cases[0]?.key ?? '')
  const [query, setQuery] = useState('')
  const [collapsedCaseKeys, setCollapsedCaseKeys] = useState<Set<string>>(
    () => new Set(defaultCollapsed ? data?.cases.map((apiCase) => apiCase.key) ?? [] : []),
  )
  const [collapsedPaths, setCollapsedPaths] = useState<Set<string>>(new Set())
  const [jumpTarget, setJumpTarget] = useState<{ path: string } | null>(null)
  const detailRef = useRef<HTMLDivElement>(null)
  const idPrefix = useId()
  const selectedCase = data?.cases.find((apiCase) => apiCase.key === selectedKey) ?? data?.cases[0]
  const selectedContract = selectedCase ? contracts.get(selectedCase.key) : undefined
  const normalizedQuery = query.trim().toLowerCase()
  const filteredCases = (data?.cases ?? []).filter((apiCase) => {
    return !normalizedQuery || `${apiCase.name} ${apiCase.method} ${apiCase.path}`.toLowerCase().includes(normalizedQuery)
  })
  const collapsible = defaultCollapsed || showRules
  const collapsed = Boolean(selectedCase && collapsible && collapsedCaseKeys.has(selectedCase.key))

  useEffect(() => {
    setSelectedKey(data?.cases[0]?.key ?? '')
    setQuery('')
    setCollapsedCaseKeys(new Set(defaultCollapsed ? data?.cases.map((apiCase) => apiCase.key) ?? [] : []))
    setCollapsedPaths(new Set())
    setJumpTarget(null)
  }, [data, defaultCollapsed])

  useEffect(() => {
    setCollapsedPaths(new Set())
    setJumpTarget(null)
  }, [selectedKey])

  useEffect(() => {
    if (!jumpTarget || !selectedCase) return
    const row = document.getElementById(apiConfigFieldId(idPrefix, selectedCase.key, 'response', jumpTarget.path))
    if (!row) return
    row.scrollIntoView?.({ block: 'center', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
    row.classList.add(styles.fieldFlash)
    const timer = window.setTimeout(() => row.classList.remove(styles.fieldFlash), 1250)
    return () => window.clearTimeout(timer)
  }, [jumpTarget, selectedCase, idPrefix])

  if (!data) {
    return <ApiConfigState title="当前接口配置无法解析" description="内容可能是正在编辑的中间态，或不是合法的接口配置 JSON / YAML。" />
  }
  if (!selectedCase || !selectedContract) {
    return <ApiConfigState title="暂无可视化的接口配置" description="当前产物还没有任何接口，请重新生成或切换到原文检查。" />
  }

  const selectInterface = (key: string) => {
    setSelectedKey(key)
    if (typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 1200px)').matches) {
      detailRef.current?.scrollIntoView?.({ block: 'start', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
    }
  }

  const toggleSelectedCase = () => {
    setCollapsedCaseKeys((current) => {
      const next = new Set(current)
      if (next.has(selectedCase.key)) next.delete(selectedCase.key)
      else next.add(selectedCase.key)
      return next
    })
  }

  const togglePath = (path: string) => {
    setCollapsedPaths((current) => {
      const next = new Set(current)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const jumpToKey = (path: string) => {
    const target = selectedContract.response.find((row) => row.path === path)
    setCollapsedPaths((current) => {
      if (!target) return new Set()
      const next = new Set(current)
      target.ancestorPaths.forEach((ancestor) => next.delete(ancestor))
      return next
    })
    setJumpTarget({ path })
  }

  const copyPath = () => {
    if (!navigator.clipboard) {
      notify.error('复制失败，请手动选择路径')
      return
    }
    void navigator.clipboard.writeText(selectedCase.path)
      .then(() => notify.success('接口路径已复制'))
      .catch(() => notify.error('复制失败，请手动选择路径'))
  }

  return <div className="min-h-0 text-[var(--ai-text)]">
    <div className={VIEW_GRID}>
      <ApiConfigInterfaceRail data={data} contracts={contracts} filteredCases={filteredCases} selectedKey={selectedCase.key}
        query={query} onQueryChange={setQuery} onSelect={selectInterface} showRules={showRules} />
      <div ref={detailRef} className="min-w-0 scroll-mt-4">
        <ApiConfigDetail apiCase={selectedCase} contract={selectedContract} showRules={showRules} collapsible={collapsible}
          collapsed={collapsed} onToggleCollapsed={toggleSelectedCase} onCopyPath={copyPath} onJumpToKey={jumpToKey}
          collapsedPaths={collapsedPaths} onTogglePath={togglePath} idPrefix={idPrefix} />
      </div>
    </div>
  </div>
}

/** 候选 API 用例的只读预览，默认收起每条用例的细节。 */
export function ApiCandidateResultView({ content }: { content: string }) {
  if (!normalizeApiConfigCases(content)) {
    return <div className="ai-task-run-result-popover-empty flex min-h-[120px] items-center justify-center text-[13px] leading-5 text-[var(--ai-text-secondary)]">当前候选结果无法解析为 API 用例</div>
  }

  return <ApiConfigDiagramView content={content} defaultCollapsed showRules />
}
