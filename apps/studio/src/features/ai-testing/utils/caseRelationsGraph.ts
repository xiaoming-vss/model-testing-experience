import { toRecord } from '@/shared/utils/value'
// 用例图谱（relation_analysis / caseRelations）的解析与图模型。
// 产物契约见 ai-worker contracts.RelationAnalysisOutput：main_paths + edges(next|branch)。

export type CaseRelationsEdgeType = 'next' | 'branch'

export type CaseRelationsPath = {
  pathId: string
  caseIds: string[]
}

export type CaseRelationsEdge = {
  edgeId: string
  fromCaseId: string
  toCaseId: string
  relationType: CaseRelationsEdgeType
  order: number
}

export type CaseRelationsData = {
  paths: CaseRelationsPath[]
  edges: CaseRelationsEdge[]
}

export type CaseRelationsCaseMeta = {
  caseId: string
  title: string
  module: string
  priority: string
  caseType: string
  precondition: string[]
  testSteps: string[]
  expectedResults: string[]
}

export type RelationsGraphNode = {
  caseId: string
  title: string
  module: string
  number: number
  onMainPath: boolean
  shared?: boolean
  isolated: boolean
  pathIndex: number
  spineIndex: number
}

export type RelationsGraphModel = {
  nodes: RelationsGraphNode[]
  nodeById: Map<string, RelationsGraphNode>
  paths: CaseRelationsPath[]
  edges: CaseRelationsEdge[]
  edgeIdsByCase: Map<string, Set<string>>
  neighborIdsByCase: Map<string, Set<string>>
}

export const RELATIONS_NODE_WIDTH = 236
export const RELATIONS_NODE_HEIGHT = 96
function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => (typeof item === 'string' ? item.trim() : ''))
    .filter(Boolean)
}

export function parseCaseRelationsContent(content?: unknown): CaseRelationsData | null {
  if (content === undefined || content === null || content === '') return null
  let parsed: unknown = content
  if (typeof content === 'string') {
    if (!content.trim()) return null
    try {
      parsed = JSON.parse(content)
    } catch {
      return null
    }
  }
  const record = toRecord(parsed)
  if (!record) return null

  const rawPaths = Array.isArray(record.main_paths) ? record.main_paths : Array.isArray(record.mainPaths) ? record.mainPaths : []
  const paths: CaseRelationsPath[] = []
  rawPaths.forEach((item) => {
    const pathRecord = toRecord(item)
    if (!pathRecord) return
    const caseIds = toStringArray(pathRecord.case_ids ?? pathRecord.caseIds)
    if (caseIds.length === 0) return
    paths.push({
      pathId: String(pathRecord.path_id ?? pathRecord.pathId ?? `path-${paths.length + 1}`),
      caseIds,
    })
  })

  const rawEdges = Array.isArray(record.edges) ? record.edges : []
  const edges: CaseRelationsEdge[] = []
  rawEdges.forEach((item) => {
    const edgeRecord = toRecord(item)
    if (!edgeRecord) return
    const fromCaseId = String(edgeRecord.from_case_id ?? edgeRecord.fromCaseId ?? '').trim()
    const toCaseId = String(edgeRecord.to_case_id ?? edgeRecord.toCaseId ?? '').trim()
    const relationType = edgeRecord.relation_type === 'branch' || edgeRecord.relationType === 'branch' ? 'branch' : 'next'
    const order = Number(edgeRecord.order)
    if (!fromCaseId || !toCaseId || fromCaseId === toCaseId) return
    edges.push({
      edgeId: String(edgeRecord.edge_id ?? edgeRecord.edgeId ?? `edge-${edges.length + 1}`),
      fromCaseId,
      toCaseId,
      relationType,
      order: Number.isFinite(order) ? order : edges.length + 1,
    })
  })

  if (paths.length === 0 && edges.length === 0) return null
  return { paths, edges }
}

// 详细用例的列表字段形如 ["1. 打开设置页", "2. 关闭开关"]，展示时去掉手工序号交给列表样式。
function toStringItems(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => (typeof item === 'string' ? item.trim() : ''))
    .filter(Boolean)
    .map((item) => item.replace(/^\d+\.\s*/, ''))
}

export function parseDetailedCaseMeta(content?: unknown): Map<string, CaseRelationsCaseMeta> {
  const metaById = new Map<string, CaseRelationsCaseMeta>()
  if (content === undefined || content === null || content === '') return metaById
  let parsed: unknown = content
  if (typeof content === 'string') {
    if (!content.trim()) return metaById
    try {
      parsed = JSON.parse(content)
    } catch {
      return metaById
    }
  }
  const record = toRecord(parsed)
  const rawCases = Array.isArray(parsed)
    ? parsed
    : record && Array.isArray(record.cases)
      ? record.cases
      : []
  rawCases.forEach((item) => {
    const caseRecord = toRecord(item)
    if (!caseRecord) return
    const caseId = String(caseRecord.case_id ?? caseRecord.caseId ?? '').trim()
    if (!caseId || metaById.has(caseId)) return
    const title = [caseRecord.case_title, caseRecord['Case Title'], caseRecord.case_name, caseRecord.name, caseRecord.title]
      .map((value) => (typeof value === 'string' ? value.trim() : ''))
      .find(Boolean)
    metaById.set(caseId, {
      caseId,
      title: title || `用例 ${caseId.slice(0, 8)}`,
      module: String(caseRecord.case_module ?? caseRecord.module ?? '').trim(),
      priority: String(caseRecord.priority ?? '').trim(),
      caseType: String(caseRecord.case_type ?? caseRecord.caseType ?? '').trim(),
      precondition: toStringItems(caseRecord.precondition ?? caseRecord.preCondition),
      testSteps: toStringItems(caseRecord.test_steps ?? caseRecord.testSteps),
      expectedResults: toStringItems(caseRecord.expected_results ?? caseRecord.expectedResult ?? caseRecord.expectedResults),
    })
  })
  return metaById
}

// 图谱模型：节点只来自 case_id，每条 edge 就是一条有向连线，main_paths 只负责圈出主骨。
// 从主骨出发沿全部出边（branch 与非主骨 next）发现分支节点——分支内部的 next（如 10→22）
// 也是合法延伸，不能丢；发现不到的边端点构成未连通组件；没有任何关联的用例单独展示。
export function buildRelationsGraphModel(data: CaseRelationsData, caseMetaById: Map<string, CaseRelationsCaseMeta>): RelationsGraphModel {
  const nodeById = new Map<string, RelationsGraphNode>()
  const paths: CaseRelationsPath[] = []

  const ensureNode = (caseId: string, init?: Partial<RelationsGraphNode>) => {
    const existing = nodeById.get(caseId)
    if (existing) {
      if (!init) return existing
      return { ...existing, ...init }
    }
    const node: RelationsGraphNode = {
      caseId,
      title: caseMetaById.get(caseId)?.title || `用例 ${caseId.slice(0, 8)}`,
      module: caseMetaById.get(caseId)?.module || '',
      number: 0,
      onMainPath: false,
      isolated: false,
      pathIndex: 0,
      spineIndex: 0,
      ...init,
    }
    nodeById.set(caseId, node)
    return node
  }

  data.paths.forEach((path, pathIndex) => {
    const caseIds: string[] = []
    path.caseIds.forEach((caseId, spineIndex) => {
      caseIds.push(caseId)
      ensureNode(caseId, { onMainPath: true, pathIndex, spineIndex })
    })
    paths.push({ pathId: path.pathId, caseIds })
  })

  const outgoing = new Map<string, CaseRelationsEdge[]>()
  data.edges.forEach((edge) => {
    const list = outgoing.get(edge.fromCaseId) ?? []
    list.push(edge)
    outgoing.set(edge.fromCaseId, list)
  })
  outgoing.forEach((list) => list.sort((a, b) => a.order - b.order))

  const anchorOf = new Map<string, RelationsGraphNode>()
  const branchQueue = paths.flatMap((path) => path.caseIds)
  paths.forEach((path) => path.caseIds.forEach((caseId) => {
    const node = nodeById.get(caseId)
    if (node) anchorOf.set(caseId, node)
  }))
  const visited = new Set(branchQueue)
  while (branchQueue.length > 0) {
    const current = branchQueue.shift() as string
    const anchor = anchorOf.get(current)
    ;(outgoing.get(current) ?? []).forEach((edge) => {
      if (visited.has(edge.toCaseId)) return
      visited.add(edge.toCaseId)
      ensureNode(edge.toCaseId, {
        pathIndex: anchor?.pathIndex ?? 0,
        spineIndex: anchor?.spineIndex ?? 0,
      })
      const child = nodeById.get(edge.toCaseId)
      if (child && anchor) anchorOf.set(edge.toCaseId, anchor)
      branchQueue.push(edge.toCaseId)
    })
  }

  // 上游与未连通组件也必须保留每条边的两个端点，不能只补源节点而漏掉末端。
  data.edges.forEach((edge) => {
    for (const caseId of [edge.fromCaseId, edge.toCaseId]) {
      if (visited.has(caseId)) continue
      visited.add(caseId)
      ensureNode(caseId)
    }
  })

  // 独立用例：没有任何关联边、也不在主骨上的用例，单独展示。
  caseMetaById.forEach((meta) => {
    if (!visited.has(meta.caseId)) {
      visited.add(meta.caseId)
      ensureNode(meta.caseId)
    }
  })

  // 编号跟随详细用例的原始顺序，与候选结果列表保持一致。
  const numbersByCaseId = new Map<string, number>()
  let nextFallbackNumber = caseMetaById.size
  nodeById.forEach((node) => {
    const metaIndex = [...caseMetaById.keys()].indexOf(node.caseId)
    if (metaIndex >= 0) {
      numbersByCaseId.set(node.caseId, metaIndex + 1)
    } else {
      numbersByCaseId.set(node.caseId, ++nextFallbackNumber)
    }
  })
  numbersByCaseId.forEach((number, caseId) => {
    const node = nodeById.get(caseId)
    if (node) node.number = number
  })

  const visibleEdges = data.edges.filter((edge) => nodeById.has(edge.fromCaseId) && nodeById.has(edge.toCaseId))
  const edgeIdsByCase = new Map<string, Set<string>>()
  const neighborIdsByCase = new Map<string, Set<string>>()
  const registerRelation = (caseId: string, neighborId: string, edgeId: string) => {
    const edgeIds = edgeIdsByCase.get(caseId) ?? new Set<string>()
    edgeIds.add(edgeId)
    edgeIdsByCase.set(caseId, edgeIds)
    const neighbors = neighborIdsByCase.get(caseId) ?? new Set<string>()
    neighbors.add(neighborId)
    neighborIdsByCase.set(caseId, neighbors)
  }
  visibleEdges.forEach((edge) => {
    registerRelation(edge.fromCaseId, edge.toCaseId, edge.edgeId)
    registerRelation(edge.toCaseId, edge.fromCaseId, edge.edgeId)
  })
  nodeById.forEach((node) => {
    node.isolated = !edgeIdsByCase.has(node.caseId)
  })

  return {
    nodes: [...nodeById.values()],
    nodeById,
    paths,
    edges: visibleEdges,
    edgeIdsByCase,
    neighborIdsByCase,
  }
}
