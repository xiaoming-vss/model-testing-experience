import { describe, expect, it } from 'vitest'
import {
  RELATIONS_NODE_HEIGHT,
  RELATIONS_NODE_WIDTH,
  RELATIONS_SCALE_LIMITS,
  buildRelationsGraphModel,
  clampRelationsScale,
  layoutRelationsFishbone,
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

    const layout = layoutRelationsFishbone(model, 'horizontal')
    expect(layout.nodes.get('E')).toBeDefined()
    // E 是 D 的 next 延伸：贴着 D 沿走廊延伸，而不是回到主骨上
    const d = layout.nodes.get('D')!
    const e = layout.nodes.get('E')!
    const separated = Math.abs(e.centerX - d.centerX) >= RELATIONS_NODE_WIDTH || Math.abs(e.centerY - d.centerY) >= RELATIONS_NODE_HEIGHT
    expect(separated).toBe(true)
    expect(Math.abs(e.centerX - d.centerX)).toBeLessThan(RELATIONS_NODE_WIDTH * 2)
    expect(Math.abs(e.centerY - d.centerY)).toBeLessThan(RELATIONS_NODE_HEIGHT * 3)
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

    const layout = layoutRelationsFishbone(model, 'horizontal')
    const solo = layout.nodes.get('solo')!
    const m1 = layout.nodes.get('m1')!
    const p1 = layout.nodes.get('p1')!
    // 独立用例与未连通组件在主骨 lane 之外单独成行
    expect(solo.centerY).not.toBe(m1.centerY)
    expect(p1.centerY).not.toBe(m1.centerY)
    expect(p1.centerY).toBe(solo.centerY)
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
    expect(model.edges.some((edge) => edge.fromCaseId === 'A' && edge.toCaseId === 'C')).toBe(true)
    const layout = layoutRelationsFishbone(model, 'horizontal')
    const c = layout.nodes.get('C')!
    expect(c.onMainPath).toBe(true)
    expect(c.spineIndex).toBe(2)
  })
})

describe('layoutRelationsFishbone', () => {
  const model = buildRelationsGraphModel(parseCaseRelationsContent(relationsContent)!, parseDetailedCaseMeta(casesContent))

  it('横向布局：主骨水平对齐且按顺序排布，分支偏离主骨', () => {
    const layout = layoutRelationsFishbone(model, 'horizontal')
    const spine = ['c1', 'c2', 'c3'].map((caseId) => layout.nodes.get(caseId)!)
    expect(new Set(spine.map((node) => node.y))).toHaveProperty('size', 1)
    expect(spine[0]!.x).toBeLessThan(spine[1]!.x)
    expect(spine[1]!.x).toBeLessThan(spine[2]!.x)
    const branch = layout.nodes.get('c4')!
    expect(branch.y).not.toBe(spine[0]!.y)
  })

  it('节点之间不重叠', () => {
    const layout = layoutRelationsFishbone(model, 'horizontal')
    const nodes = [...layout.nodes.values()]
    nodes.forEach((a, index) => {
      nodes.slice(index + 1).forEach((b) => {
        const separated = Math.abs(a.centerX - b.centerX) >= RELATIONS_NODE_WIDTH || Math.abs(a.centerY - b.centerY) >= RELATIONS_NODE_HEIGHT
        expect(separated).toBe(true)
      })
    })
  })

  it('纵向布局：主骨垂直对齐且分支不重叠', () => {
    const vertical = layoutRelationsFishbone(model, 'vertical')
    const spine = ['c1', 'c2', 'c3'].map((caseId) => vertical.nodes.get(caseId)!)
    expect(new Set(spine.map((node) => node.x))).toHaveProperty('size', 1)
    expect(spine[0]!.y).toBeLessThan(spine[1]!.y)
    const nodes = [...vertical.nodes.values()]
    nodes.forEach((a, index) => {
      nodes.slice(index + 1).forEach((b) => {
        const separated = Math.abs(a.centerX - b.centerX) >= RELATIONS_NODE_WIDTH || Math.abs(a.centerY - b.centerY) >= RELATIONS_NODE_HEIGHT
        expect(separated).toBe(true)
      })
    })
  })

  it('分支节点贴着主骨锚点展开，不会串成远离主骨的长柱', () => {
    const layout = layoutRelationsFishbone(model, 'horizontal')
    const spineY = layout.nodes.get('c1')!.centerY
    // 最大偏移 = 首层肋距 + 3 层台阶 + 半个节点高；超出即退化成整列堆叠
    const maxOffset = 128 + 3 * 118 + RELATIONS_NODE_HEIGHT / 2
    const branchNodes = [...layout.nodes.values()].filter((node) => !node.onMainPath)
    branchNodes.forEach((node) => {
      expect(Math.abs(node.centerY - spineY)).toBeLessThanOrEqual(maxOffset)
    })
  })

  it.each(['horizontal', 'vertical'] as const)('兄弟节点围绕父节点错落展开，共享引用和环不重复放置：%s', (orientation) => {
    const pairs = [['root', 'parent'], ['parent', 'left'], ['parent', 'above'], ['left', 'shared'], ['above', 'shared'], ['shared', 'parent']]
    const data = parseCaseRelationsContent(JSON.stringify({
      main_paths: [{ case_ids: ['root', 'end'] }],
      edges: pairs.map(([from, to], i) => ({ edge_id: `e${i}`, from_case_id: from, to_case_id: to, relation_type: 'branch', order: i })),
    }))!
    const model = buildRelationsGraphModel(data, new Map())
    const layout = layoutRelationsFishbone(model, orientation)
    expect(layout.nodes.size).toBe(6)
    expect(model.edges).toHaveLength(pairs.length)
    const parent = layout.nodes.get('parent')!, left = layout.nodes.get('left')!, above = layout.nodes.get('above')!
    const u = (node: typeof parent) => orientation === 'horizontal' ? node.centerX : node.centerY
    const v = (node: typeof parent) => orientation === 'horizontal' ? node.centerY : node.centerX
    expect(u(left)).toBeLessThan(u(above))
    expect(u(above)).toBeLessThan(u(parent))
    expect(v(left)).toBeLessThan(v(parent))
    expect(v(above)).toBeLessThan(v(left))
    const nodes = [...layout.nodes.values()]
    nodes.forEach((a, i) => nodes.slice(i + 1).forEach((b) => {
      expect(Math.abs(a.centerX - b.centerX) >= RELATIONS_NODE_WIDTH || Math.abs(a.centerY - b.centerY) >= RELATIONS_NODE_HEIGHT).toBe(true)
    }))
  })

  it('多条主骨各占一条 lane，互不重叠', () => {
    const data = parseCaseRelationsContent(JSON.stringify({
      main_paths: [
        { path_id: 'P1', case_ids: ['a1', 'a2'] },
        { path_id: 'P2', case_ids: ['b1', 'b2'] },
      ],
      edges: [
        { edge_id: 'ea', from_case_id: 'a1', to_case_id: 'a2', relation_type: 'next', order: 1 },
        { edge_id: 'eb', from_case_id: 'b1', to_case_id: 'b2', relation_type: 'next', order: 1 },
      ],
    }))!
    const layout = layoutRelationsFishbone(buildRelationsGraphModel(data, new Map()), 'horizontal')
    const a = layout.nodes.get('a1')!
    const b = layout.nodes.get('b1')!
    expect(Math.abs(a.centerY - b.centerY)).toBeGreaterThanOrEqual(RELATIONS_NODE_HEIGHT)
  })
})

describe('clampRelationsScale', () => {
  it('限制缩放范围', () => {
    expect(clampRelationsScale(0.01)).toBe(RELATIONS_SCALE_LIMITS.min)
    expect(clampRelationsScale(9)).toBe(RELATIONS_SCALE_LIMITS.max)
    expect(clampRelationsScale(1.3)).toBe(1.3)
  })
})
