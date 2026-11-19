import type { ReactNode } from 'react'

/** 接口库表单字段标签：统一字阶、字重与文本色。 */
export function InterfaceFieldLabel({ children }: { children: ReactNode }) {
  return <span className="if-field-label text-[12px] font-[650] leading-5 text-[var(--srf-text)]">{children}</span>
}
