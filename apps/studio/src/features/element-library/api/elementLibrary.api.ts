import { buildQuery, request, type ListResponse } from '@/shared/api/request'
import type { ElementDetail, ElementDraft, ElementFilters, ElementGroup, ElementSummary } from '../types'

function repositoryPath(id: string) {
  return `/v1/software-repositories/${encodeURIComponent(id)}`
}

function elementPath(id: string) {
  return `/v1/ui-elements/${encodeURIComponent(id)}`
}

export const elementLibraryApi = {
  getGroups: (repositoryId: string) =>
    request<ListResponse<ElementGroup>>(`${repositoryPath(repositoryId)}/ui-element-groups`),
  createGroup: (repositoryId: string, body: { name: string; routeTemplate: string }) =>
    request<ElementGroup>(`${repositoryPath(repositoryId)}/ui-element-groups`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  deleteGroup: (groupId: string) =>
    request<Record<string, never>>(`/v1/ui-element-groups/${encodeURIComponent(groupId)}`, { method: 'DELETE' }),
  getElements: (repositoryId: string, filters: ElementFilters) =>
    request<ListResponse<ElementSummary>>(`${repositoryPath(repositoryId)}/ui-elements${buildQuery({ ...filters })}`),
  getElement: (elementId: string) => request<ElementDetail>(elementPath(elementId)),
  createElement: (repositoryId: string, body: ElementDraft) =>
    request<ElementDetail>(`${repositoryPath(repositoryId)}/ui-elements`, { method: 'POST', body: JSON.stringify(body) }),
  updateElement: (elementId: string, body: ElementDraft & { version: number }) =>
    request<ElementDetail>(elementPath(elementId), { method: 'PATCH', body: JSON.stringify(body) }),
  deleteElement: (elementId: string, version: number) =>
    request<Record<string, never>>(`${elementPath(elementId)}${buildQuery({ version })}`, { method: 'DELETE' }),
}
