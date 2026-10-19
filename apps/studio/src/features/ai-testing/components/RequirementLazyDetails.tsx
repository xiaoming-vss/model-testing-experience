import { useState, type ReactNode } from 'react'

/** Folded sections do not mount their expensive fact renderers. */
export function RequirementLazyDetails({ className, summary, children, defaultOpen = false }: {
  className: string; summary: ReactNode; children: ReactNode; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return <details className={className} open={open}>
    <summary onClick={event => { event.preventDefault(); setOpen(value => !value) }}>{summary}</summary>
    {open && children}
  </details>
}
