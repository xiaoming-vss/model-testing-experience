/** A flow is executable only when every node belongs to one directed, acyclic chain. */
export function getFlowOrder(ids: string[], links: Array<{ source: string; target: string }>): string[] | null {
  if (ids.length === 0) return []
  const known = new Set(ids)
  const incoming = new Map(ids.map((id) => [id, 0]))
  const next = new Map<string, string>()
  for (const { source, target } of links) {
    if (!known.has(source) || !known.has(target) || source === target || next.has(source)) return null
    next.set(source, target)
    incoming.set(target, (incoming.get(target) ?? 0) + 1)
    if (incoming.get(target)! > 1) return null
  }
  const starts = ids.filter((id) => incoming.get(id) === 0)
  if (starts.length !== 1) return null
  const order: string[] = []
  let current: string | undefined = starts[0]
  while (current && !order.includes(current)) {
    order.push(current)
    current = next.get(current)
  }
  return !current && order.length === ids.length ? order : null
}
