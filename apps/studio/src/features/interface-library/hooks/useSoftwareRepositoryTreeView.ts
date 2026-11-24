import { useRef, useState } from 'react'
import { interfaceGroupKey } from '../utils/interfaceGroups'

/**
 * View state of the interface navigation tree. It belongs to the page rather than the tree because
 * the tree unmounts whenever another interface loads, and it must come back as the user left it.
 */
export function useSoftwareRepositoryTreeView() {
  // Every repository starts expanded so its groups are visible; collapsing one drops its interface query.
  const [collapsedRepositories, setCollapsedRepositories] = useState<Set<string>>(() => new Set())
  // Tag groups start collapsed so large repositories stay scannable.
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => new Set())
  // Kept in a ref because scrolling must not re-render the page.
  const scrollTopRef = useRef(0)

  function toggleRepository(softwareRepositoryId: string) {
    setCollapsedRepositories(previous => toggled(previous, softwareRepositoryId))
  }

  function toggleGroup(softwareRepositoryId: string, tag: string) {
    const key = interfaceGroupKey(softwareRepositoryId, tag)
    setExpandedGroups(previous => toggled(previous, key))
  }

  return {
    collapsedRepositories,
    expandedGroups,
    scrollTopRef,
    toggleRepository,
    toggleGroup,
  }
}

export type SoftwareRepositoryTreeView = ReturnType<typeof useSoftwareRepositoryTreeView>

function toggled(values: Set<string>, value: string) {
  const next = new Set(values)
  if (next.has(value)) next.delete(value)
  else next.add(value)
  return next
}
