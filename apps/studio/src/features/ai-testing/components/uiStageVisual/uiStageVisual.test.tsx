import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { DesignVisual } from './DesignVisual'
import { SurfaceVisual } from './SurfaceVisual'
import { UiStageVisual } from './UiStageVisual'
import { YamlVisual } from './YamlVisual'

const surface = JSON.stringify({
  schemaVersion: 'ui_test_surface/1.0',
  pages: [
    { pageId: 'page_retrieval', title: '数据检索', route: '/data-management/retrieval' },
    { pageId: 'page_transform', title: '数据转换管理', route: '/data-management/transform-data' },
  ],
  controls: [
    { controlId: 'ctl_convert', pageId: 'page_retrieval', semanticName: '转换数据', controlType: 'button', sourceRef: 'retrieval/index.vue:822', containerId: 'c_toolbar', conditions: [{ description: '发布数据页签 + 已勾选行 + 转换权限' }], locatorCandidates: [{ locatorType: 'xpath', locatorValue: "//button[normalize-space(.)='转换数据']", confirmed: false, stability: 'stable' }] },
    { controlId: 'ctl_checkbox', pageId: 'page_retrieval', semanticName: '数据行勾选框', controlType: 'checkbox', containerId: 'c_table', conditions: [{ description: '行主键决定定位' }], locatorCandidates: [] },
    { controlId: 'ctl_convert', pageId: 'page_transform', semanticName: '转换任务列表', controlType: 'columnHeader', containerId: 'c_transform_table', locatorCandidates: [] },
  ],
  unknowns: [{ topic: '行级元素定位证据缺失', reason: '运行时 DOM 未提供', sourceRef: 'retrieval/index.vue:833', affectedIds: ['ctl_checkbox'] }],
  interactions: [{ interactionId: 'act_convert_open', controlId: 'ctl_convert', description: '按 checkedRowKeys 打开转换抽屉', effect: 'open drawer' }],
})

const design = JSON.stringify({
  schemaVersion: 'ui_test_scenarios/2.0',
  cases: [
    {
      caseId: 'case-1', name: '单条发布数据发起转换', goal: '验证单条转换', coverage: 'partial', sourceTitle: '单条发布数据发起转换',
      preconditions: ['已登录', '准备 1 条发布数据'],
      limitations: ['“未混入其他数据”需要 absent 断言'],
      steps: [
        { sourceStepNo: 1, sourceAction: '进入数据检索并勾选发布数据。', actions: [{ actionId: 'A1', operation: 'navigate', target: '数据检索', status: 'included' }], expectations: [{ expectationId: 'E1', assertion: 'text_eq', target: '勾选状态', value: '已勾选', status: 'included' }] },
        { sourceStepNo: 2, sourceAction: '打开转换面板，核对转换总数。', actions: [{ actionId: 'A2', operation: 'click', target: '转换数据', status: 'included' }], expectations: [{ expectationId: 'E2', assertion: 'text_eq', target: '转换总数', value: '1', status: 'included' }, { expectationId: 'E3', assertion: 'absent', target: '校验提示', status: 'excluded', reason: '需要 absent 能力' }] },
      ],
    },
    { caseId: 'case-2', name: '另一条 UI 场景', goal: '验证其他路径', coverage: 'full', sourceTitle: '另一条 UI 场景', preconditions: [], limitations: [], steps: [] },
  ],
  capabilities: { assertions: ['visible', 'text_eq'], operations: ['navigate', 'click'] },
})

const yaml = `- name: 单条发布数据发起转换
  enabled: true
  stepsJson:
    - orderNo: 1
      stepName: 打开数据检索页面
      keyword: open
      missingFields:
        - fields: [operationValue]
          operation: 打开页面
          target: 页面地址
          reason: 未提供 targetBaseUrl
    - orderNo: 2
      stepName: 点击转换数据
      keyword: click
      locatorType: xpath
      locatorValue: "//button[normalize-space(.)='转换数据']"
`

afterEach(() => cleanup())

it('renders surface pages, controls and locator evidence', () => {
  render(<SurfaceVisual content={surface} onShowRaw={() => {}} />)
  expect(screen.getByRole('heading', { name: /数据检索/ })).toBeInTheDocument()
  expect(screen.getAllByText('发布数据页签 + 已勾选行 + 转换权限').length).toBeGreaterThan(0)
  expect(screen.getAllByText('待补定位').length).toBeGreaterThan(0)

  fireEvent.click(screen.getByText('数据行勾选框').closest('button')!)
  expect(screen.getByRole('heading', { name: '数据行勾选框' })).toBeInTheDocument()
  expect(screen.getByText('行级元素定位证据缺失')).toBeInTheDocument()
  expect(screen.getByText('源码中还没有可用的定位候选，需要在运行时补充 DOM 证据。')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: /数据转换管理/ }))
  expect(screen.getByRole('heading', { name: /数据转换管理/ })).toBeInTheDocument()
  expect(screen.getAllByText('转换任务列表').length).toBeGreaterThan(0)
})

it('renders design cases, steps and excluded expectations', () => {
  render(<DesignVisual content={design} onShowRaw={() => {}} />)
  expect(screen.getByRole('heading', { name: '单条发布数据发起转换' })).toBeInTheDocument()
  expect(screen.getByText('部分覆盖')).toBeInTheDocument()
  expect(screen.getAllByText('含排除项').length).toBeGreaterThan(0)

  fireEvent.click(screen.getByRole('button', { name: /打开转换面板/ }))
  expect(screen.getByRole('heading', { name: '步骤 2' })).toBeInTheDocument()
  expect(screen.getAllByText('打开转换面板，核对转换总数。').length).toBeGreaterThan(0)
  expect(screen.getByText('excluded')).toBeInTheDocument()
  expect(screen.getByText('需要 absent 能力')).toBeInTheDocument()
})

it('renders YAML cases, readiness and missing fields', () => {
  render(<YamlVisual content={yaml} onShowRaw={() => {}} />)
  expect(screen.getByRole('heading', { name: '单条发布数据发起转换' })).toBeInTheDocument()
  expect(screen.getAllByText('1 项待补').length).toBeGreaterThan(0)
  expect(screen.getByText('页面地址')).toBeInTheDocument()
  expect(screen.getByText('未提供 targetBaseUrl')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: /点击转换数据/ }))
  expect(screen.getByRole('heading', { name: '点击转换数据' })).toBeInTheDocument()
  expect(screen.getByText('这个步骤没有声明字段缺口；仍需核对测试数据、设计冲突与定位正确性。')).toBeInTheDocument()
})

it('falls back to raw content when a visualization cannot parse', () => {
  const onShowRaw = vi.fn()
  render(<UiStageVisual stage="ui_design" content="{invalid" onShowRaw={onShowRaw} />)
  expect(screen.getByText('UI 用例设计 JSON 暂时无法解析')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '切换到原文' }))
  expect(onShowRaw).toHaveBeenCalledTimes(1)
})

it('does not mark data-bound gaps or design conflicts as executable', () => {
  const content = `- name: 数据关联用例
  draftVersion: ui_yaml_draft/2.0
  dataRequirements:
    - id: release
      title: 发布数据
      fields:
        id: {label: 发布数据ID, value: null}
      conditions: [已完成打包]
      confirmed: false
  designConflicts:
    - reason: 运行时ID不能提取
      requiredCapability: 变量提取
      sourceRefs: ['expectation:E1']
  stepsJson:
    - orderNo: 1
      stepName: 勾选目标记录
      keyword: click
      locatorType: xpath
      locatorValue: null
      dataBindings:
        locatorValue: '//tr[td={{data.release.id|xpath}}]'
`
  render(<YamlVisual content={content} onShowRaw={() => {}} />)
  expect(screen.getByText('此用例仍有待处理内容')).toBeInTheDocument()
  expect(screen.getByText('设计冲突：运行时ID不能提取')).toBeInTheDocument()
  expect(screen.getByText('关联测试数据')).toBeInTheDocument()
  expect(screen.queryByText('全部就绪')).not.toBeInTheDocument()
})
