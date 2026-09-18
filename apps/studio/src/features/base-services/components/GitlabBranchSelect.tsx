import { Select } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api, listItems } from '@/services/api'

export function GitlabBranchSelect({
  projectId,
  connectionId,
  repositoryId,
  value,
  placeholder,
  onChange = () => {},
  allowClear = true,
  autoSearch = '',
  disabled = false,
}: {
  projectId: string
  connectionId: string
  repositoryId: string
  value?: string
  placeholder: string
  onChange?: (branchName?: string) => void
  allowClear?: boolean
  autoSearch?: string
  disabled?: boolean
}) {
  const [search, setSearch] = useState(autoSearch)
  const [debouncedSearch, setDebouncedSearch] = useState(autoSearch)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [search])

  useEffect(() => {
    setSearch(autoSearch)
    setDebouncedSearch(autoSearch)
  }, [autoSearch, repositoryId])

  const branchesQuery = useQuery({
    queryKey: ['gitlabRepositoryBranches', projectId, connectionId, repositoryId, debouncedSearch],
    queryFn: () => api.getGitlabRepositoryBranches(projectId, connectionId, repositoryId, debouncedSearch),
    enabled: Boolean(projectId) && Boolean(connectionId) && Boolean(repositoryId),
  })
  const branchOptions = useMemo(
    () =>
      listItems(branchesQuery.data?.items ?? []).map((branch) => ({
        label: branch.name ? `${branch.name}${branch.isDefault ? '（默认）' : ''}` : '-',
        value: branch.name ?? '',
      })),
    [branchesQuery.data],
  )

  return (
    <Select
      className="requirement-code-binding-select"
      showSearch
      searchValue={search}
      filterOption={false}
      allowClear={allowClear}
      loading={branchesQuery.isLoading}
      options={branchOptions}
      placeholder={placeholder}
      disabled={disabled}
      value={value}
      onSearch={setSearch}
      onChange={(nextValue) => onChange(nextValue as string | undefined)}
    />
  )
}
