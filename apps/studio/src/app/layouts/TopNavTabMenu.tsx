import {
  useEffect,
  useRef,
  type FocusEvent as ReactFocusEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { Link } from 'react-router-dom'
import { Popover } from 'antd'
import { DownOutlined } from '@ant-design/icons'
import { SidebarIcon, type SidebarIconName } from './SidebarIcon'

export type TopNavTabItem<Key extends string> = { key: Key; label: string }

type TopNavTabMenuProps<Key extends string> = {
  label: string
  menuLabel: string
  icon: SidebarIconName
  items: readonly [TopNavTabItem<Key>, ...TopNavTabItem<Key>[]]
  activeKey: Key | null
  hrefForItem: (key: Key) => string
  triggerHref?: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * 顶部一级入口的二级页签浮层：默认只显示入口，悬停展开页签。
 * 测试、资产库和基础服务共用这套交互，避免每个入口各写一份键盘与触屏逻辑。
 */
export function TopNavTabMenu<Key extends string>({
  label,
  menuLabel,
  icon,
  items,
  activeKey,
  hrefForItem,
  triggerHref,
  open,
  onOpenChange,
}: TopNavTabMenuProps<Key>) {
  const triggerRef = useRef<HTMLAnchorElement>(null)
  const menuRef = useRef<HTMLElement>(null)
  const focusMenuOnOpenRef = useRef(false)
  const pointerTypeRef = useRef('')
  const suppressHoverOpenRef = useRef(false)
  const onOpenChangeRef = useRef(onOpenChange)

  useEffect(() => {
    onOpenChangeRef.current = onOpenChange
  }, [onOpenChange])

  const resolvedTriggerHref = triggerHref ?? hrefForItem(activeKey ?? items[0].key)

  useEffect(() => {
    if (!open || !focusMenuOnOpenRef.current) return
    let frame = 0
    function focusWhenReady() {
      const links = Array.from(menuRef.current?.querySelectorAll<HTMLAnchorElement>('a') ?? [])
      if (!links.length) {
        frame = window.requestAnimationFrame(focusWhenReady)
        return
      }
      focusMenuOnOpenRef.current = false
      const index = items.findIndex(item => item.key === activeKey)
      links[Math.max(0, Math.min(index, links.length - 1))]?.focus()
    }
    frame = window.requestAnimationFrame(focusWhenReady)
    return () => window.cancelAnimationFrame(frame)
  }, [open, activeKey, items])

  useEffect(() => {
    if (!open) return
    function handlePointerDown(event: PointerEvent) {
      const target = event.target
      if (!(target instanceof Element)) return
      if (target.closest('.top-nav-menu-trigger, .top-nav-menu-popover')) return
      onOpenChangeRef.current(false)
    }
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') onOpenChangeRef.current(false)
    }
    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleEscape)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [open])

  function menuLinks() {
    return Array.from(menuRef.current?.querySelectorAll<HTMLAnchorElement>('a') ?? [])
  }

  function handleTriggerKeyDown(event: ReactKeyboardEvent<HTMLAnchorElement>) {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
    event.preventDefault()
    focusMenuOnOpenRef.current = true
    onOpenChange(true)
  }

  function handleMenuKeyDown(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      onOpenChange(false)
      triggerRef.current?.focus()
      return
    }
    const links = menuLinks()
    const index = links.indexOf(document.activeElement as HTMLAnchorElement)
    if (index < 0) return
    const next = event.key === 'Home' ? 0
      : event.key === 'End' ? links.length - 1
        : event.key === 'ArrowRight' || event.key === 'ArrowDown' ? (index + 1) % links.length
          : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? (index - 1 + links.length) % links.length
            : -1
    if (next < 0) return
    event.preventDefault()
    links[next].focus()
  }

  function handleMenuBlur(event: ReactFocusEvent<HTMLElement>) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) onOpenChange(false)
  }

  function handleTriggerPointerDown(event: ReactPointerEvent<HTMLAnchorElement>) {
    pointerTypeRef.current = event.pointerType
  }

  function handleTriggerClick(event: ReactMouseEvent<HTMLAnchorElement>) {
    if (event.detail === 0) {
      onOpenChange(false)
      return
    }
    // 触屏没有 hover：点按仍进入默认页，同时展开页签供下一次选择。
    if (pointerTypeRef.current === 'touch' || !open) {
      onOpenChange(true)
      return
    }
    onOpenChange(false)
  }

  function handleOpenChange(nextOpen: boolean) {
    // 点击页签后鼠标仍停在浮层上，rc-trigger 会因 popup mouseenter 再次打开；
    // 短暂忽略这段 hover 重开，让页面直接露出切换后的内容。
    if (nextOpen && suppressHoverOpenRef.current) return
    onOpenChange(nextOpen)
  }

  function handleSelectTab() {
    suppressHoverOpenRef.current = true
    onOpenChange(false)
    triggerRef.current?.focus({ preventScroll: true })
    window.setTimeout(() => { suppressHoverOpenRef.current = false }, 300)
  }

  const menu = <nav ref={menuRef} className="top-nav-menu" aria-label={menuLabel}
    onKeyDown={handleMenuKeyDown} onBlur={handleMenuBlur}>
    {items.map(item => <Link key={item.key} to={hrefForItem(item.key)}
      className="top-nav-menu-link"
      aria-current={activeKey === item.key ? 'page' : undefined}
      onClick={handleSelectTab}>
      {item.label}
    </Link>)}
  </nav>

  return <Popover
    open={open}
    onOpenChange={handleOpenChange}
    trigger={['hover']}
    placement="bottom"
    arrow={{ pointAtCenter: true }}
    mouseEnterDelay={0.08}
    mouseLeaveDelay={0.18}
    content={menu}
    classNames={{ root: 'top-nav-menu-popover' }}
    styles={{ container: { padding: 8, border: '1px solid var(--app-glass-border-strong)', borderRadius: 12 } }}
  >
    <Link ref={triggerRef} to={resolvedTriggerHref}
      className={`sidebar-link top-nav-menu-trigger${activeKey ? ' is-active' : ''}`}
      aria-current={activeKey ? 'page' : undefined}
      aria-expanded={open}
      title={label}
      onKeyDown={handleTriggerKeyDown}
      onPointerDown={handleTriggerPointerDown}
      onClick={handleTriggerClick}>
      <SidebarIcon name={icon} />
      <span className="sidebar-link-label">{label}</span>
      {activeKey ? <span className="top-nav-menu-active-dot" aria-hidden="true" /> : null}
      <DownOutlined className="top-nav-menu-caret" aria-hidden="true" />
    </Link>
  </Popover>
}
