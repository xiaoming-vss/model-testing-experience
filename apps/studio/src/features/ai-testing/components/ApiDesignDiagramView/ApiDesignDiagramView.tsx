import { Button, Empty } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import { notify } from '@/shared/utils/toast'
import { normalizeApiDesign } from '../../utils/apiDesignDiagram'
import { ApiDesignDetail } from './ApiDesignDetail'
import { ApiDesignInterfaceRail } from './ApiDesignInterfaceRail'

function DesignState({ title, description, onShowRaw }: { title: string; description: string; onShowRaw?: () => void }) {
  return <div className="flex min-h-[240px] flex-col items-center justify-center gap-3 p-6">
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<div className="flex flex-col gap-y-1"><strong className="text-[13px] text-[var(--ai-text)]">{title}</strong><span className="text-[12px] text-[var(--ai-text-secondary)]">{description}</span></div>} />
    {onShowRaw ? <Button size="small" onClick={onShowRaw}>查看原文</Button> : null}
  </div>
}

function prefersReducedMotion() {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function ApiDesignDiagramView({ content, onShowRaw }: { content: string; onShowRaw?: () => void }) {
  const data = useMemo(() => normalizeApiDesign(content), [content])
  const initialInterface = data?.interfaces[0]
  const [selectedKey, setSelectedKey] = useState(() => initialInterface?.key ?? '')
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(initialInterface?.cases[0] ? [initialInterface.cases[0].key] : []))
  const [jumpNonce, setJumpNonce] = useState(0)
  const detailRef = useRef<HTMLDivElement>(null)
  const uncoveredRef = useRef<HTMLElement>(null)
  const pendingJumpRef = useRef(false)

  const selectedInterface = data?.interfaces.find(item => item.key === selectedKey) ?? data?.interfaces[0]
  const normalizedQuery = query.trim().toLowerCase()
  const filteredInterfaces = (data?.interfaces ?? []).filter(item => !normalizedQuery || `${item.name} ${item.method} ${item.path}`.toLowerCase().includes(normalizedQuery))

  useEffect(() => {
    if (!selectedInterface) return
    setFilter('all')
    setExpanded(new Set(selectedInterface.cases[0] ? [selectedInterface.cases[0].key] : []))
  }, [selectedInterface])

  useEffect(() => {
    if (!pendingJumpRef.current) return
    pendingJumpRef.current = false
    uncoveredRef.current?.scrollIntoView?.({ block: 'start', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
  }, [selectedInterface?.key, jumpNonce])

  if (!data) {
    return <DesignState title="当前设计产物无法解析" description="内容可能是正在编辑的中间态，或不是合法的 API 用例设计 JSON。" onShowRaw={onShowRaw} />
  }
  if (data.totalCases === 0 || !selectedInterface) {
    return <DesignState title="暂无可视化的接口用例设计" description="当前设计产物还没有任何用例，请重新生成或切换到原文检查。" onShowRaw={onShowRaw} />
  }

  const selectInterface = (key: string) => {
    const next = data.interfaces.find(item => item.key === key)
    setSelectedKey(key)
    setFilter('all')
    setExpanded(new Set(next?.cases[0] ? [next.cases[0].key] : []))
    if (typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 1200px)').matches) {
      detailRef.current?.scrollIntoView?.({ block: 'start', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
    }
  }

  const toggleCase = (key: string) => {
    setExpanded(current => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const toggleAll = () => {
    const visible = selectedInterface.cases.filter(item => filter === 'all' || item.category === filter)
    const allExpanded = visible.length > 0 && visible.every(item => expanded.has(item.key))
    setExpanded(current => {
      const next = new Set(current)
      visible.forEach(item => { if (allExpanded) next.delete(item.key); else next.add(item.key) })
      return next
    })
  }

  const copyPath = () => {
    if (!navigator.clipboard) {
      notify.error('复制失败，请手动选择路径')
      return
    }
    void navigator.clipboard.writeText(selectedInterface.path)
      .then(() => notify.success('接口路径已复制'))
      .catch(() => notify.error('复制失败，请手动选择路径'))
  }

  const jumpToUncovered = () => {
    const target = selectedInterface.uncovered.length
      ? selectedInterface
      : data.interfaces.find(item => item.uncovered.length)
    if (!target) return
    if (query.trim() && !filteredInterfaces.some(item => item.key === target.key)) setQuery('')
    pendingJumpRef.current = true
    if (target.key !== selectedInterface.key) {
      setSelectedKey(target.key)
      setFilter('all')
      setExpanded(new Set(target.cases[0] ? [target.cases[0].key] : []))
    } else {
      setJumpNonce(value => value + 1)
    }
  }

  return <div className="min-h-0 text-[var(--ai-text)]">
    <div className="grid grid-cols-[248px_minmax(0,1fr)] items-start gap-5 max-[1200px]:grid-cols-1 max-[1200px]:gap-3">
      <ApiDesignInterfaceRail data={data} filteredInterfaces={filteredInterfaces} selectedKey={selectedInterface.key} query={query}
        onQueryChange={setQuery} onSelect={selectInterface} onJumpToUncovered={jumpToUncovered} />
      <div ref={detailRef} className="min-w-0 scroll-mt-4">
        <ApiDesignDetail view={selectedInterface} filter={filter} expanded={expanded} onFilter={setFilter}
          onToggleCase={toggleCase} onToggleAll={toggleAll} onCopyPath={copyPath} uncoveredRef={uncoveredRef} />
      </div>
    </div>
  </div>
}
