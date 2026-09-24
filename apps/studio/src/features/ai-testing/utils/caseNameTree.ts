import { toRecord } from '@/shared/utils/value'
import { toCaseNamePointList, toDisplayText } from '@/features/ai-testing/utils/functionalOutput'

export type CaseNameTreeNode = {
  id: string
  title: string
  kind: 'root' | 'model' | 'testModel' | 'point'
  children: CaseNameTreeNode[]
}

function parseCaseNameRows(value: unknown, inheritedModel = '', inheritedTestModel = ''): Array<{ model: string; testModel: string; testPoints: string[] }> {
  if (Array.isArray(value)) {
    return value.flatMap((item) => parseCaseNameRows(item, inheritedModel, inheritedTestModel))
  }

  if (!value || typeof value !== 'object') {
    const text = toDisplayText(value)
    return text ? [{ model: inheritedModel || '未分组模块', testModel: inheritedTestModel || '未分组场景', testPoints: [text] }] : []
  }

  const record = value as Record<string, unknown>
  const model = toDisplayText(record.model) || inheritedModel
  const testModel = toDisplayText(record.test_model) || inheritedTestModel
  const directPoints = toCaseNamePointList(record.test_points)
  const rows = directPoints.length > 0 ? [{ model: model || '未分组模块', testModel: testModel || '未分组场景', testPoints: directPoints }] : []

  const nestedRows = Object.entries(record)
    .filter(([key]) => key !== 'model' && key !== 'test_model' && key !== 'test_points')
    .flatMap(([key, nestedValue]) => {
      const nextModel = model || key
      const nextTestModel = model ? testModel || key : testModel
      return parseCaseNameRows(nestedValue, nextModel, nextTestModel)
    })

  return [...rows, ...nestedRows]
}

function buildCategoryCaseNameTree(parsed: unknown, rootTitle: string): CaseNameTreeNode | null {
  const rootRecord = toRecord(parsed)
  const categories = rootRecord?.categories
  if (!Array.isArray(categories)) return null

  const categoryNodes = categories.reduce<CaseNameTreeNode[]>((categoryNodes, category, categoryIndex) => {
    const categoryRecord = toRecord(category)
    const data = categoryRecord?.data
    if (!categoryRecord || !Array.isArray(data)) return categoryNodes

    const testModelNodes = data.reduce<CaseNameTreeNode[]>((testModelNodes, item, dataIndex) => {
      const itemRecord = toRecord(item)
      const points = itemRecord?.test_points
      if (!itemRecord || !Array.isArray(points)) return testModelNodes

      const pointNodes = points.reduce<CaseNameTreeNode[]>((pointNodes, point, pointIndex) => {
        const title = toDisplayText(point)
        if (!title) return pointNodes
        pointNodes.push({
          id: `category-${categoryIndex}-data-${dataIndex}-point-${pointIndex}`,
          title,
          kind: 'point',
          children: [],
        })
        return pointNodes
      }, [])

      testModelNodes.push({
        id: `category-${categoryIndex}-data-${dataIndex}`,
        title: toDisplayText(itemRecord.test_model) || '未分组场景',
        kind: 'testModel',
        children: pointNodes,
      })

      return testModelNodes
    }, [])

    if (testModelNodes.length === 0) return categoryNodes

    categoryNodes.push({
      id: `category-${categoryIndex}`,
      title: toDisplayText(categoryRecord.model) || '未分组模块',
      kind: 'model',
      children: testModelNodes,
    })

    return categoryNodes
  }, [])

  if (categoryNodes.length === 0) return null

  return {
    id: 'root',
    title: rootTitle || '功能测试用例生成',
    kind: 'root',
    children: categoryNodes,
  }
}

type CategoryCaseNameNodePath = {
  categoryIndex: number
  dataIndex?: number
  pointIndex?: number
}

function parseCategoryCaseNameNodePath(nodeId: string): CategoryCaseNameNodePath | null {
  const match = /^category-(\d+)(?:-data-(\d+))?(?:-point-(\d+))?$/.exec(nodeId)
  if (!match) return null

  return {
    categoryIndex: Number(match[1]),
    dataIndex: match[2] === undefined ? undefined : Number(match[2]),
    pointIndex: match[3] === undefined ? undefined : Number(match[3]),
  }
}

function updateCaseNamePointTitle(point: unknown, nextTitle: string) {
  const pointRecord = toRecord(point)
  if (!pointRecord) return nextTitle
  if ('case_name' in pointRecord) return { ...pointRecord, case_name: nextTitle }
  if ('name' in pointRecord) return { ...pointRecord, name: nextTitle }
  if ('title' in pointRecord) return { ...pointRecord, title: nextTitle }
  if ('test_point' in pointRecord) return { ...pointRecord, test_point: nextTitle }
  return { ...pointRecord, case_name: nextTitle }
}

export function updateCategoryCaseNamesContent(content: string, nodeId: string, action: 'rename' | 'delete', nextTitle?: string) {
  let parsed: unknown
  try {
    parsed = JSON.parse(content)
  } catch {
    return null
  }

  const rootRecord = toRecord(parsed)
  const path = parseCategoryCaseNameNodePath(nodeId)
  if (!rootRecord || !path || !Array.isArray(rootRecord.categories)) return null

  const categories = [...rootRecord.categories]
  const categoryRecord = toRecord(categories[path.categoryIndex])
  if (!categoryRecord) return null

  if (path.dataIndex === undefined) {
    if (action === 'delete') {
      categories.splice(path.categoryIndex, 1)
    } else if (nextTitle) {
      categories[path.categoryIndex] = { ...categoryRecord, model: nextTitle }
    }
    return JSON.stringify({ ...rootRecord, categories }, null, 2)
  }

  const data = categoryRecord.data
  if (!Array.isArray(data)) return null
  const nextData = [...data]
  const itemRecord = toRecord(nextData[path.dataIndex])
  if (!itemRecord) return null

  if (path.pointIndex === undefined) {
    if (action === 'delete') {
      nextData.splice(path.dataIndex, 1)
      if (nextData.length === 0) {
        categories.splice(path.categoryIndex, 1)
      } else {
        categories[path.categoryIndex] = { ...categoryRecord, data: nextData }
      }
    } else if (nextTitle) {
      nextData[path.dataIndex] = { ...itemRecord, test_model: nextTitle }
      categories[path.categoryIndex] = { ...categoryRecord, data: nextData }
    }
    return JSON.stringify({ ...rootRecord, categories }, null, 2)
  }

  const points = itemRecord.test_points
  if (!Array.isArray(points)) return null
  const nextPoints = [...points]

  if (action === 'delete') {
    nextPoints.splice(path.pointIndex, 1)
    if (nextPoints.length === 0) {
      nextData.splice(path.dataIndex, 1)
    } else {
      nextData[path.dataIndex] = { ...itemRecord, test_points: nextPoints }
    }

    if (nextData.length === 0) {
      categories.splice(path.categoryIndex, 1)
    } else {
      categories[path.categoryIndex] = { ...categoryRecord, data: nextData }
    }
  } else if (nextTitle) {
    nextPoints[path.pointIndex] = updateCaseNamePointTitle(nextPoints[path.pointIndex], nextTitle)
    nextData[path.dataIndex] = { ...itemRecord, test_points: nextPoints }
    categories[path.categoryIndex] = { ...categoryRecord, data: nextData }
  }

  return JSON.stringify({ ...rootRecord, categories }, null, 2)
}

export function buildCaseNameTree(content: string, rootTitle: string): CaseNameTreeNode | null {
  if (!content.trim()) return null

  try {
    const parsed = JSON.parse(content)
    const categoryTree = buildCategoryCaseNameTree(parsed, rootTitle)
    if (categoryTree) return categoryTree

    const rows = parseCaseNameRows(parsed)
    if (rows.length === 0) return null

    const modelMap = new Map<string, Map<string, string[]>>()
    rows.forEach((row) => {
      const model = row.model || '未分组模块'
      const testModel = row.testModel || '未分组场景'
      const testModelMap = modelMap.get(model) ?? new Map<string, string[]>()
      const points = testModelMap.get(testModel) ?? []
      row.testPoints.forEach((point) => {
        if (point && !points.includes(point)) points.push(point)
      })
      testModelMap.set(testModel, points)
      modelMap.set(model, testModelMap)
    })

    return {
      id: 'root',
      title: rootTitle || '功能测试用例生成',
      kind: 'root',
      children: [...modelMap.entries()].map(([model, testModelMap], modelIndex) => ({
        id: `model-${modelIndex}`,
        title: model,
        kind: 'model',
        children: [...testModelMap.entries()].map(([testModel, testPoints], testModelIndex) => ({
          id: `model-${modelIndex}-test-${testModelIndex}`,
          title: testModel,
          kind: 'testModel',
          children: testPoints.map((point, pointIndex) => ({
            id: `model-${modelIndex}-test-${testModelIndex}-point-${pointIndex}`,
            title: point,
            kind: 'point',
            children: [],
          })),
        })),
      })),
    }
  } catch {
    return null
  }
}

export function renameCaseNameTreeNode(tree: CaseNameTreeNode, nodeId: string, nextTitle: string): CaseNameTreeNode {
  if (tree.id === nodeId) {
    return { ...tree, title: nextTitle }
  }

  return {
    ...tree,
    children: tree.children.map((child) => renameCaseNameTreeNode(child, nodeId, nextTitle)),
  }
}

function pruneEmptyCaseNameTreeNode(node: CaseNameTreeNode): CaseNameTreeNode | null {
  if (node.kind === 'point') return node

  const children = node.children
    .map(pruneEmptyCaseNameTreeNode)
    .filter((child): child is CaseNameTreeNode => Boolean(child))

  if (node.kind !== 'root' && children.length === 0) return null
  return { ...node, children }
}

export function deleteCaseNameTreeNode(tree: CaseNameTreeNode, nodeId: string): CaseNameTreeNode {
  if (tree.id === nodeId) return tree

  const nextTree = {
    ...tree,
    children: tree.children
      .filter((child) => child.id !== nodeId)
      .map((child) => deleteCaseNameTreeNode(child, nodeId)),
  }

  return pruneEmptyCaseNameTreeNode(nextTree) ?? { ...tree, children: [] }
}

export function serializeCaseNameTree(tree: CaseNameTreeNode) {
  const rows = tree.children.flatMap((model) =>
    model.children.map((testModel) => ({
      model: model.title,
      test_model: testModel.title,
      test_points: testModel.children.map((point) => point.title),
    })),
  )

  return JSON.stringify(rows, null, 2)
}

export function countCaseNameTree(tree: CaseNameTreeNode | null) {
  const models = tree?.children.length ?? 0
  const testModels = tree?.children.reduce((sum, model) => sum + model.children.length, 0) ?? 0
  const testPoints = tree?.children.reduce((sum, model) => sum + model.children.reduce((itemSum, testModel) => itemSum + testModel.children.length, 0), 0) ?? 0
  return { models, testModels, testPoints }
}

export const CASE_NAME_TREE_NODE_HEIGHT = 38

const CASE_NAME_TREE_ROW_GAP = 14

const CASE_NAME_TREE_POINT_GAP = 10

export const CASE_NAME_TREE_CONNECTOR_WIDTH = 86

function getStackHeight(count: number, gap = CASE_NAME_TREE_ROW_GAP) {
  if (count <= 0) return CASE_NAME_TREE_NODE_HEIGHT
  return count * CASE_NAME_TREE_NODE_HEIGHT + (count - 1) * gap
}

export function getTestModelHeight(testModel: CaseNameTreeNode) {
  return getStackHeight(testModel.children.length, CASE_NAME_TREE_POINT_GAP)
}

export function getModelHeight(model: CaseNameTreeNode) {
  if (model.children.length === 0) return CASE_NAME_TREE_NODE_HEIGHT
  return model.children.reduce((sum, testModel, index) => (
    sum + getTestModelHeight(testModel) + (index === 0 ? 0 : CASE_NAME_TREE_ROW_GAP)
  ), 0)
}

export function getTreeHeight(tree: CaseNameTreeNode) {
  if (tree.children.length === 0) return CASE_NAME_TREE_NODE_HEIGHT
  return tree.children.reduce((sum, model, index) => (
    sum + getModelHeight(model) + (index === 0 ? 0 : CASE_NAME_TREE_ROW_GAP)
  ), 0)
}

export function getModelTargetYs(tree: CaseNameTreeNode) {
  let cursor = 0
  return tree.children.map((model) => {
    const height = getModelHeight(model)
    const y = cursor + height / 2
    cursor += height + CASE_NAME_TREE_ROW_GAP
    return y
  })
}

export function getTestModelTargetYs(model: CaseNameTreeNode) {
  let cursor = 0
  return model.children.map((testModel) => {
    const height = getTestModelHeight(testModel)
    const y = cursor + height / 2
    cursor += height + CASE_NAME_TREE_ROW_GAP
    return y
  })
}

export function getPointTargetYs(testModel: CaseNameTreeNode) {
  return testModel.children.map((_, index) => (
    CASE_NAME_TREE_NODE_HEIGHT / 2 + index * (CASE_NAME_TREE_NODE_HEIGHT + CASE_NAME_TREE_POINT_GAP)
  ))
}
