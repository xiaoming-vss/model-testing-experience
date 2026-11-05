import { Input, type InputRef } from 'antd'
import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react'

type Props = {
  ariaLabel: string
  placeholder: string
  className: string
  /** 外部快捷键需要聚焦输入框时传入。 */
  inputRef?: RefObject<InputRef | null>
  prefix?: ReactNode
  suffix?: ReactNode
  delayMs?: number
  /** 父级清空筛选时递增，让输入框同步清空。 */
  resetKey?: number
  onCommit: (value: string) => void
}

/**
 * 输入态留在组件内部，停止输入后才把值交给页面。
 * 这样每敲一个字不会重渲染整张列表，列表只在真正搜索时更新。
 */
export function DebouncedSearchInput({ ariaLabel, placeholder, className, inputRef, prefix, suffix, delayMs = 300, resetKey = 0, onCommit }: Props) {
  const ownRef = useRef<InputRef>(null)
  const ref = inputRef ?? ownRef
  const [value, setValue] = useState('')
  const commitRef = useRef(onCommit)
  useEffect(() => { commitRef.current = onCommit })

  useEffect(() => {
    const timer = setTimeout(() => commitRef.current(value.trim()), delayMs)
    return () => clearTimeout(timer)
  }, [delayMs, value])

  useEffect(() => {
    if (resetKey > 0) setValue('')
  }, [resetKey])

  return <Input
    ref={ref}
    className={className}
    allowClear
    prefix={prefix}
    suffix={suffix}
    aria-label={ariaLabel}
    placeholder={placeholder}
    value={value}
    onChange={(event) => setValue(event.target.value)}
  />
}
