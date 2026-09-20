// 用例图谱（relation_analysis / caseRelations）的解析与鱼骨布局。
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
const SPINE_STEP_MIN = 296
const LANE_GAP = 56
const CANVAS_PAD = 48

export type RelationsOrientation = 'horizontal' | 'vertical'

export type RelationsLaidOutNode = RelationsGraphNode & {
  x: number
  y: number
  centerX: number
  centerY: number
}

export type RelationsLayout = {
  nodes: Map<string, RelationsLaidOutNode>
  width: number
  height: number
}

export const RELATIONS_SCALE_LIMITS = { min: 0.2, max: 2.5 }

export function clampRelationsScale(scale: number) {
  return Math.min(RELATIONS_SCALE_LIMITS.max, Math.max(RELATIONS_SCALE_LIMITS.min, scale))
}

function toRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

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

  // 未连通组件：边的端点都不在已发现集合里时，从该端点独立扩出一组节点，不与主图谱强行连线。
  data.edges.forEach((edge) => {
    const seedCaseId = !visited.has(edge.fromCaseId)
      ? edge.fromCaseId
      : !visited.has(edge.toCaseId) ? edge.toCaseId : null
    if (!seedCaseId) return
    visited.add(seedCaseId)
    ensureNode(seedCaseId)
    branchQueue.push(seedCaseId)
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

// 鱼骨布局：主骨从左到右，每个主骨锚点的分支沿多条固定斜率的直肋呈扇形向外辐射
//（4 个斜率轮转，左右交替、上下交替），链条沿自己的肋线直线延伸，不再逐层爬台阶。
// 每个锚点的扇形区域在横向上互不重叠，主骨间距按两侧扇宽自适应撑开。
// u 沿主骨方向（节点左/上边缘），v 垂直主骨方向；纵向为同一抽象布局的转置，
// v 轴步长按该方向上的节点尺寸取值（横向避让节点高 96，纵向避让节点宽 236）。
export function layoutRelationsFishbone(model: RelationsGraphModel, orientation: RelationsOrientation): RelationsLayout {
  const horizontal = orientation === 'horizontal'
  // 经典鱼骨肋线：上侧分支向左斜、下侧向右斜。走廊宽度封顶 3 步（260/520/780）：
  // 链加深时在走廊内折返（1x→2x→3x→2x→1x），超过 5 层转直线延伸。
  // 同链相邻节点横向错开 ≥260（≥ 节点宽），隔层节点纵向错开 ≥2dy（横向 112 / 纵向 240）。
  // 同侧多条肋的 band 间距（384/720）与步距不成整数比，任意深度组合不会贴合。
  const rayDx = 260
  const rayDy = horizontal ? 56 : 120
  const bandStep = horizontal ? 320 : 720
  const sideBase = horizontal ? 0 : 240
  const nodeUSize = horizontal ? RELATIONS_NODE_WIDTH : RELATIONS_NODE_HEIGHT
  const nodeVSize = horizontal ? RELATIONS_NODE_HEIGHT : RELATIONS_NODE_WIDTH
  // 主骨相邻有序对沿主轴；其余全部出边（branch 与分支内部 next）都沿分支肋线递归延伸。
  const mainPairs = new Set<string>()
  model.paths.forEach((path) => {
    for (let i = 0; i < path.caseIds.length - 1; i++) {
      mainPairs.add(JSON.stringify([path.caseIds[i], path.caseIds[i + 1]]))
    }
  })
  const continueEdgesFrom = new Map<string, CaseRelationsEdge[]>()
  model.edges.forEach((edge) => {
    if (edge.relationType === 'next' && mainPairs.has(JSON.stringify([edge.fromCaseId, edge.toCaseId]))) return
    const list = continueEdgesFrom.get(edge.fromCaseId) ?? []
    list.push(edge)
    continueEdgesFrom.set(edge.fromCaseId, list)
  })

  const placed = new Map<string, { u: number; v: number }>()
  let laneCursor = 0
  let maxU = 0

  model.paths.forEach((path) => {
    const lanePositions = new Map<string, { u: number; v: number }>()

    // 1. 先以主骨锚点为原点，相对坐标铺开每个锚点的扇形分支区域。
    const fans = path.caseIds.map(() => new Map<string, { du: number; dv: number }>())
    const extents = path.caseIds.map(() => ({ left: 0, right: 0 }))
    path.caseIds.forEach((anchorId, spineIndex) => {
      const fan = fans[spineIndex]
      fan.set(anchorId, { du: 0, dv: 0 })

      // 走廊折返：步序 1x/2x/3x/2x/1x，第 6 步起沿直线延伸（du = step·x）。
      // 步序按肋内已放置节点数递增（而非图深度），同一节点的多个孩子各占一步，不会重叠。
      const duFor = (step: number) => {
        if (step >= 6) return step * rayDx
        const steps = [1, 2, 3, 2, 1]
        return steps[step - 1] * rayDx
      }

      const placeRay = (caseId: string, dy: number, sideSign: number, v0: number, stepRef: { step: number }) => {
        if (fan.has(caseId) || placed.has(caseId)) return
        stepRef.step += 1
        fan.set(caseId, { du: sideSign * duFor(stepRef.step), dv: sideSign * (sideBase + v0 + dy * stepRef.step) })
        const continueEdges = (continueEdgesFrom.get(caseId) ?? []).slice().sort((a, b) => a.order - b.order)
        continueEdges.forEach((edge) => placeRay(edge.toCaseId, dy, sideSign, v0, stepRef))
      }

      const continueEdges = (continueEdgesFrom.get(anchorId) ?? []).slice().sort((a, b) => a.order - b.order)
      const rayCountBySide = new Map<number, number>()
      continueEdges.forEach((edge, branchIndex) => {
        // 分支按顺序交替挂到上下两侧；上侧肋向左斜、下侧向右斜。
        const sideSign = branchIndex % 2 === 0 ? -1 : 1
        const k = rayCountBySide.get(sideSign) ?? 0
        rayCountBySide.set(sideSign, k + 1)
        placeRay(edge.toCaseId, rayDy, sideSign, k * bandStep, { step: 0 })
      })

      let minDu = 0
      let maxDu = 0
      fan.forEach(({ du }) => {
        minDu = Math.min(minDu, du)
        maxDu = Math.max(maxDu, du)
      })
      extents[spineIndex] = { left: Math.max(0, -minDu), right: maxDu + nodeUSize }
    })

    // 2. 按扇宽分配主骨绝对位置：相邻主骨至少 SPINE_STEP_MIN，扇形区域之间留出间隙。
    const anchorUs: number[] = []
    let nextFreeU = 0
    path.caseIds.forEach((_, spineIndex) => {
      const base = spineIndex === 0
        ? nextFreeU
        : Math.max(nextFreeU, anchorUs[spineIndex - 1] + SPINE_STEP_MIN)
      const anchorU = base + extents[spineIndex].left
      anchorUs.push(anchorU)
      nextFreeU = anchorU + extents[spineIndex].right + 48
    })

    path.caseIds.forEach((caseId, spineIndex) => {
      const u = anchorUs[spineIndex]
      maxU = Math.max(maxU, u)
      if (!lanePositions.has(caseId)) lanePositions.set(caseId, { u, v: 0 })
      const fan = fans[spineIndex]
      fan.forEach((position, branchCaseId) => {
        if (branchCaseId === caseId) return
        const absoluteU = u + position.du
        maxU = Math.max(maxU, absoluteU)
        lanePositions.set(branchCaseId, { u: absoluteU, v: position.dv })
      })
    })

    let laneSpan = nodeVSize
    lanePositions.forEach((position) => {
      laneSpan = Math.max(laneSpan, Math.abs(position.v) * 2 + nodeVSize)
    })
    const laneCenter = laneCursor + laneSpan / 2
    lanePositions.forEach((position, caseId) => {
      placed.set(caseId, { u: position.u, v: laneCenter + position.v })
    })
    laneCursor += laneSpan + LANE_GAP
  })

  // 独立展示行：未连通组件与独立用例单独成行，不与主图谱强行连线。
  const orphans = model.nodes.filter((node) => !placed.has(node.caseId))
  if (orphans.length > 0) {
    const laneSpan = nodeVSize
    const laneCenter = laneCursor + laneSpan / 2
    orphans.forEach((node, index) => {
      const u = index * SPINE_STEP_MIN
      maxU = Math.max(maxU, u)
      placed.set(node.caseId, { u, v: laneCenter })
    })
    laneCursor += laneSpan + LANE_GAP
  }

  const rawWidth = maxU + nodeUSize + CANVAS_PAD * 2
  const rawHeight = laneCursor + CANVAS_PAD - LANE_GAP

  const nodes = new Map<string, RelationsLaidOutNode>()
  placed.forEach((position, caseId) => {
    const node = model.nodeById.get(caseId)
    if (!node) return
    const u = CANVAS_PAD + position.u
    const v = position.v
    const x = horizontal ? u : v - RELATIONS_NODE_WIDTH / 2
    const y = horizontal ? v - RELATIONS_NODE_HEIGHT / 2 : u
    nodes.set(caseId, {
      ...node,
      x,
      y,
      centerX: x + RELATIONS_NODE_WIDTH / 2,
      centerY: y + RELATIONS_NODE_HEIGHT / 2,
    })
  })

  return {
    nodes,
    width: horizontal ? rawWidth : rawHeight,
    height: horizontal ? rawHeight : rawWidth,
  }
}
