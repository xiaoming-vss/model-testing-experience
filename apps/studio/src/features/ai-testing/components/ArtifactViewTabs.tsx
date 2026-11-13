import { CopyOutlined } from '@ant-design/icons'
import { message } from '@/shared/utils/feedback'
import { useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Button, Segmented, Tabs, type TabsProps } from 'antd'
import type { TabsRef } from 'antd/es/tabs'
import { animateTabPanel } from '@/shared/ui/tabMotion'
import '@/features/ai-testing/styles/artifact-view-switch.css'

/** 把产物操作放进弹窗标题栏右侧，标题左侧保留原有标题。 */
function useArtifactHeaderSlot() {
  const anchor = useRef<HTMLSpanElement>(null)
  const [target, setTarget] = useState<HTMLElement | null>(null)
  useLayoutEffect(() => {
    const title = anchor.current?.closest('.ant-modal')?.querySelector('.ant-modal-header')
    if (!title) return
    const slot = document.createElement('div')
    slot.className = 'ai-artifact-mode-slot'
    title.classList.add('ai-artifact-mode-heading')
    title.append(slot)
    setTarget(slot)
    return () => {
      slot.remove()
      if (!title.querySelector('.ai-artifact-mode-slot')) title.classList.remove('ai-artifact-mode-heading')
    }
  }, [])
  return { anchor, target }
}

function CopyButton({ copyText, copyLabel = '复制 JSON' }: { copyText?: string; copyLabel?: string }) {
  return <Button size="small" type="text" icon={<CopyOutlined />} aria-label={copyLabel} disabled={!copyText} onClick={async () => {
    try { await navigator.clipboard.writeText(copyText ?? ''); message.success('已复制') }
    catch { message.error('复制失败，请重试或手动选择复制') }
  }}>复制</Button>
}

/** 视图切换与复制本体，供标题栏或正文内工具条直接摆放。 */
export function ArtifactModeControls({ value, onChange, options, extra, copyText, copyLabel = '复制 JSON' }: {
  copyText?: string
  copyLabel?: string
  extra?: ReactNode
  value: string
  onChange: (value: string) => void
  options: { label: string; value: string }[]
}) {
  return <div className="ai-artifact-mode-controls">{extra}{copyText !== undefined && <CopyButton copyText={copyText} copyLabel={copyLabel} />}<Segmented aria-label="内容展示方式" size="small" value={value} onChange={onChange} options={options} /></div>
}

export function ArtifactModeSwitch({ value, onChange, options, extra, copyText, copyLabel = '复制 JSON' }: {
  copyText?: string
  copyLabel?: string
  extra?: ReactNode
  value: string
  onChange: (value: string) => void
  options: { label: string; value: string }[]
}) {
  const { anchor, target } = useArtifactHeaderSlot()
  const control = <ArtifactModeControls value={value} onChange={onChange} options={options} extra={extra} copyText={copyText} copyLabel={copyLabel} />
  return <><span ref={anchor} hidden />{target ? createPortal(control, target) : <div className="ai-artifact-mode-toolbar">{control}</div>}</>
}

export function ArtifactViewTabs({ activeKey, defaultActiveKey, onChange, items, jsonCopyText, copyKey = 'json', copyLabel, ...props }: TabsProps & { jsonCopyText?: string; copyKey?: string; copyLabel?: string }) {
  const [localKey, setLocalKey] = useState(defaultActiveKey ?? items?.[0]?.key ?? '')
  const value = activeKey ?? localKey
  const tabsRef = useRef<TabsRef>(null)
  // 隐藏的页签保持挂载以保留展开/滚动/选中状态，但冻结它最后一次可见时的 children：
  // 父级编辑当前页签时不再把新内容推给隐藏页签，隐藏页签就不会跟着每次击键重算。
  const [inactiveChildren, setInactiveChildren] = useState<Record<string, ReactNode>>({})
  const paneStateRef = useRef({ key: value, items })
  const visibleItems = useMemo(() => (items ?? []).map(item => {
    const key = String(item.key ?? '')
    if (key === value) return item
    return key in inactiveChildren ? { ...item, children: inactiveChildren[key] } : item
  }), [inactiveChildren, items, value])
  useLayoutEffect(() => {
    const previous = paneStateRef.current
    if (previous.key !== value) {
      const leaving = (items ?? []).find(item => String(item.key ?? '') === previous.key)
      if (leaving) setInactiveChildren(current => ({ ...current, [previous.key]: leaving.children }))
    }
    paneStateRef.current = { key: value, items }
  }, [items, value])
  const selectedIndex = (items ?? []).findIndex(item => item.key === value)
  const previousIndex = useRef(selectedIndex)
  useLayoutEffect(() => {
    const previous = previousIndex.current
    previousIndex.current = selectedIndex
    if (previous < 0 || selectedIndex < 0 || previous === selectedIndex) return
    const panel = tabsRef.current?.nativeElement?.querySelector<HTMLElement>('.ant-tabs-content-holder')
    if (panel) animateTabPanel(panel, selectedIndex - previous)
  }, [selectedIndex])
  const change = (key: string) => { setLocalKey(key); onChange?.(key) }
  return <>
    <ArtifactModeSwitch copyText={value === copyKey ? jsonCopyText : undefined} copyLabel={copyLabel} value={value} onChange={change} options={(items ?? []).map((item) => ({
      value: item.key, label: item.key === 'json' ? 'JSON' : String(item.label),
    }))} />
    <Tabs ref={tabsRef} {...props} items={visibleItems} activeKey={value} onChange={change} renderTabBar={() => <></>} />
  </>
}
