import { CopyOutlined } from '@ant-design/icons'
import { message } from '@/shared/utils/feedback'
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Button, Segmented, Tabs, type TabsProps } from 'antd'
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

/** 只有复制动作、没有视图切换的产物标题栏。 */
export function ArtifactCopyAction({ copyText, copyLabel = '复制 JSON' }: { copyText?: string; copyLabel?: string }) {
  const { anchor, target } = useArtifactHeaderSlot()
  const control = <div className="ai-artifact-mode-controls"><CopyButton copyText={copyText} copyLabel={copyLabel} /></div>
  return <><span ref={anchor} hidden />{target ? createPortal(control, target) : <div className="ai-artifact-mode-toolbar">{control}</div>}</>
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
  const control = <div className="ai-artifact-mode-controls">{extra}{copyText !== undefined && <CopyButton copyText={copyText} copyLabel={copyLabel} />}<Segmented aria-label="内容展示方式" size="small" value={value} onChange={onChange} options={options} /></div>
  return <><span ref={anchor} hidden />{target ? createPortal(control, target) : <div className="ai-artifact-mode-toolbar">{control}</div>}</>
}

export function ArtifactViewTabs({ activeKey, defaultActiveKey, onChange, items, jsonCopyText, copyKey = 'json', copyLabel, ...props }: TabsProps & { jsonCopyText?: string; copyKey?: string; copyLabel?: string }) {
  const [localKey, setLocalKey] = useState(defaultActiveKey ?? items?.[0]?.key ?? '')
  const value = activeKey ?? localKey
  const change = (key: string) => { setLocalKey(key); onChange?.(key) }
  return <>
    <ArtifactModeSwitch copyText={value === copyKey ? jsonCopyText : undefined} copyLabel={copyLabel} value={value} onChange={change} options={(items ?? []).map((item) => ({
      value: item.key, label: item.key === 'json' ? 'JSON' : String(item.label),
    }))} />
    <Tabs {...props} items={items} activeKey={value} onChange={change} renderTabBar={() => <></>} />
  </>
}
