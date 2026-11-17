export type BaseServiceTab = 'llm' | 'gitlab' | 'skills' | 'mcp' | 'monitoring'

/** 顶部「基础服务」入口展开的页签。 */
export const BASE_SERVICE_TABS = [
  { key: 'gitlab', label: 'GitLab' },
  { key: 'llm', label: 'LLM模型' },
  { key: 'mcp', label: 'MCP' },
  { key: 'skills', label: 'Skill库' },
  { key: 'monitoring', label: '性能监控' },
] as const satisfies readonly { key: BaseServiceTab; label: string }[]

export function resolveBaseServiceTab(tab?: string | null): BaseServiceTab {
  if (tab === 'zentao') return 'mcp'
  if (tab === 'llm' || tab === 'gitlab' || tab === 'skills' || tab === 'mcp' || tab === 'monitoring') return tab
  return 'llm'
}
