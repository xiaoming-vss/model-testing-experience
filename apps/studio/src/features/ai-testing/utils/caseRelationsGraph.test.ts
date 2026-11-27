import { describe, expect, it } from 'vitest'
import {
  buildRelationsGraphModel,
  parseCaseRelationsContent,
  parseDetailedCaseMeta,
} from './caseRelationsGraph'

const relationsContent = JSON.stringify({
  schema_version: '2.0',
  main_paths: [{ path_id: 'P1', case_ids: ['c1', 'c2', 'c3'] }],
  edges: [
    { edge_id: 'e1', from_case_id: 'c1', to_case_id: 'c2', relation_type: 'next', order: 1 },
    { edge_id: 'e2', from_case_id: 'c2', to_case_id: 'c3', relation_type: 'next', order: 1 },
    { edge_id: 'e3', from_case_id: 'c1', to_case_id: 'c4', relation_type: 'branch', order: 1 },
    { edge_id: 'e4', from_case_id: 'c1', to_case_id: 'c5', relation_type: 'branch', order: 2 },
    { edge_id: 'e5', from_case_id: 'c4', to_case_id: 'c6', relation_type: 'branch', order: 1 },
  ],
})

const casesContent = JSON.stringify({
  cases: [
    { case_id: 'c6', case_module: '模块B', case_title: '用例六' },
    { case_id: 'c1', case_module: '模块A', case_title: '验证管理员开启本地清洗开关' },
    { case_id: 'c2', case_module: '模块A', case_title: '验证保存后新作业按新开关处理' },
    { case_id: 'c3', case_module: '模块A', case_title: '验证关闭开关后作业不清洗' },
    { case_id: 'c4', case_module: '模块A', case_title: '验证未修改配置时开关默认打开' },
    { case_id: 'c5', case_module: '模块B', case_title: '验证升级后开关保持升级前配置' },
  ],
})

describe('parseCaseRelationsContent', () => {
  it('解析 main_paths 与 edges', () => {
    const data = parseCaseRelationsContent(relationsContent)
    expect(data?.paths).toEqual([{ pathId: 'P1', caseIds: ['c1', 'c2', 'c3'] }])
    expect(data?.edges).toHaveLength(5)
    expect(data?.edges[3]).toMatchObject({ fromCaseId: 'c1', toCaseId: 'c5', relationType: 'branch', order: 2 })
  })

  it('无法解析时返回 null', () => {
    expect(parseCaseRelationsContent('not-json')).toBeNull()
    expect(parseCaseRelationsContent('')).toBeNull()
    expect(parseCaseRelationsContent('[]')).toBeNull()
  })
})

describe('parseDetailedCaseMeta', () => {
  it('按 case_id 建立索引并保留原始顺序', () => {
    const metaById = parseDetailedCaseMeta(casesContent)
    expect(metaById.get('c1')?.title).toBe('验证管理员开启本地清洗开关')
    expect(metaById.get('c1')?.module).toBe('模块A')
    expect([...metaById.keys()][0]).toBe('c6')
  })

  it('容忍缺失 case_id 的用例', () => {
    const metaById = parseDetailedCaseMeta(JSON.stringify({ cases: [{ case_title: '无编号用例' }] }))
    expect(metaById.size).toBe(0)
  })

  it('解析前置条件、测试步骤与预期结果并去掉手工序号', () => {
    const metaById = parseDetailedCaseMeta(JSON.stringify({
      cases: [{
        case_id: 'c9',
        case_title: '验证关闭开关后作业不清洗',
        precondition: ['1. 管理员已登录', '2. 本地清洗开关已开启'],
        test_steps: ['1. 新建采集作业', '2. 执行作业并查看结果'],
        expected_results: ['1. 作业执行成功', '2. 结果数据未发生清洗'],
      }],
    }))
    const meta = metaById.get('c9')
    expect(meta?.precondition).toEqual(['管理员已登录', '本地清洗开关已开启'])
    expect(meta?.testSteps).toEqual(['新建采集作业', '执行作业并查看结果'])
    expect(meta?.expectedResults).toEqual(['作业执行成功', '结果数据未发生清洗'])
  })
})

describe('buildRelationsGraphModel', () => {
  const model = buildRelationsGraphModel(parseCaseRelationsContent(relationsContent)!, parseDetailedCaseMeta(casesContent))

  it('主线用例标记 pathIndex 与 spineIndex', () => {
    const c2 = model.nodeById.get('c2')
    expect(c2?.onMainPath).toBe(true)
    expect(c2?.pathIndex).toBe(0)
    expect(c2?.spineIndex).toBe(1)
  })

  it('分支用例沿 branch 边从主线发现', () => {
    const c6 = model.nodeById.get('c6')
    expect(c6?.onMainPath).toBe(false)
    expect(c6?.spineIndex).toBe(0)
  })

  it('编号跟随详细用例顺序', () => {
    expect(model.nodeById.get('c1')?.number).toBe(2)
    expect(model.nodeById.get('c6')?.number).toBe(1)
  })

  it('选中用例的邻接与边索引双向可见', () => {
    expect(model.neighborIdsByCase.get('c4')).toContain('c6')
    expect(model.neighborIdsByCase.get('c6')).toContain('c4')
    expect(model.edgeIdsByCase.get('c6')?.size).toBe(1)
  })

  it('分支内部的 next 用例沿分支延伸，不会丢失', () => {
    // 对应 spec：A→B→C 主骨，B branch 出 D，D next 延伸出 E
    const data = parseCaseRelationsContent(JSON.stringify({
      main_paths: [{ path_id: 'P1', case_ids: ['A', 'B', 'C'] }],
      edges: [
        { edge_id: 'e1', from_case_id: 'A', to_case_id: 'B', relation_type: 'next', order: 1 },
        { edge_id: 'e2', from_case_id: 'B', to_case_id: 'C', relation_type: 'next', order: 1 },
        { edge_id: 'e3', from_case_id: 'B', to_case_id: 'D', relation_type: 'branch', order: 1 },
        { edge_id: 'e4', from_case_id: 'D', to_case_id: 'E', relation_type: 'next', order: 1 },
      ],
    }))!
    const model = buildRelationsGraphModel(data, parseDetailedCaseMeta(JSON.stringify({
      cases: [
        { case_id: 'A', case_title: '甲' }, { case_id: 'B', case_title: '乙' }, { case_id: 'C', case_title: '丙' },
        { case_id: 'D', case_title: '丁' }, { case_id: 'E', case_title: '戊' },
      ],
    })))
    expect(model.nodeById.get('E')).toBeDefined()
    expect(model.nodeById.get('E')?.onMainPath).toBe(false)
    expect(model.edges.some((edge) => edge.fromCaseId === 'D' && edge.toCaseId === 'E')).toBe(true)
  })

  it('独立用例与未连通组件单独成行展示，不强行补线', () => {
    const data = parseCaseRelationsContent(JSON.stringify({
      main_paths: [{ path_id: 'P1', case_ids: ['m1', 'm2'] }],
      edges: [
        { edge_id: 'e1', from_case_id: 'm1', to_case_id: 'm2', relation_type: 'next', order: 1 },
        // 与主图谱互不连接的独立组件
        { edge_id: 'e2', from_case_id: 'p1', to_case_id: 'p2', relation_type: 'next', order: 1 },
      ],
    }))!
    const cases = JSON.stringify({
      cases: [
        { case_id: 'm1', case_title: '主骨一' }, { case_id: 'm2', case_title: '主骨二' },
        { case_id: 'p1', case_title: '组件一' }, { case_id: 'p2', case_title: '组件二' },
        { case_id: 'solo', case_title: '无关联用例' },
      ],
    })
    const model = buildRelationsGraphModel(data, parseDetailedCaseMeta(cases))
    expect(model.nodeById.get('solo')?.isolated).toBe(true)
    expect(model.nodeById.get('p1')?.isolated).toBe(false)
    expect(model.edges.every((edge) => edge.edgeId !== 'e2' || (edge.fromCaseId === 'p1' && edge.toCaseId === 'p2'))).toBe(true)
  })

  it('主骨节点之间的非相邻 next 不是主骨边，但仍会绘制', () => {
    const data = parseCaseRelationsContent(JSON.stringify({
      main_paths: [{ path_id: 'P1', case_ids: ['A', 'B', 'C'] }],
      edges: [
        { edge_id: 'e1', from_case_id: 'A', to_case_id: 'B', relation_type: 'next', order: 1 },
        { edge_id: 'e2', from_case_id: 'B', to_case_id: 'C', relation_type: 'next', order: 1 },
        { edge_id: 'e3', from_case_id: 'A', to_case_id: 'C', relation_type: 'next', order: 2 },
      ],
    }))!
    const model = buildRelationsGraphModel(data, new Map())
    expect(model.edges.some((edge) => edge.fromCaseId === 'A' && edge.toCaseId === 'C')).toBe(true)  })
})
