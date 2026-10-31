import { useMemo, useState, type ReactNode } from 'react'
import { Empty, Tag } from 'antd'
import {
  AppstoreOutlined,
  CheckSquareOutlined,
  ExclamationCircleFilled,
  FileTextOutlined,
  FormOutlined,
  MenuOutlined,
  MoreOutlined,
  SelectOutlined,
  TableOutlined,
  ThunderboltOutlined,
  WarningFilled,
} from '@ant-design/icons'
import { parseSurface, type SurfaceControl } from './uiStageVisualUtils'
import { VisualEmpty, VisualParseError } from './VisualStates'

const typeIcons: Record<string, ReactNode> = {
  button: <ThunderboltOutlined />,
  input: <FormOutlined />,
  textarea: <FormOutlined />,
  select: <SelectOutlined />,
  columnHeader: <TableOutlined />,
  tableCell: <TableOutlined />,
  tab: <AppstoreOutlined />,
  pagination: <MoreOutlined />,
  checkbox: <CheckSquareOutlined />,
  readOnlyText: <FileTextOutlined />,
  menuItem: <MenuOutlined />,
}

function TypeIcon({ type }: { type: string }) {
  return <span className="uisv-type-icon">{typeIcons[type] ?? <AppstoreOutlined />}</span>
}

export function SurfaceVisual({ content, onShowRaw }: { content: string; onShowRaw: () => void }) {
  const data = useMemo(() => parseSurface(content), [content])
  const [pageId, setPageId] = useState('')
  const [controlId, setControlId] = useState('')
  if (!data) return <VisualParseError label="元素控件清单 JSON" onShowRaw={onShowRaw} />
  if (data.pages.length === 0 && data.controls.length === 0) {
    return <VisualEmpty title="暂无可视化的页面与控件" description="当前产物里没有 pages 或 controls；可以切换到 JSON 查看原文。" onShowRaw={onShowRaw} />
  }

  const defaultPage = data.pages.reduce((best, page) => (
    data.controls.filter(control => control.pageId === page.pageId).length
      > data.controls.filter(control => control.pageId === best.pageId).length ? page : best
  ), data.pages[0])
  const activePage = data.pages.find(page => page.pageId === pageId) ?? defaultPage
  const pageControls = data.controls.filter(control => control.pageId === activePage?.pageId)
  const activeControl = pageControls.find(control => control.controlId === controlId) ?? pageControls[0]
  const located = data.controls.filter(control => control.locators.length > 0).length
  const pageLocated = pageControls.filter(control => control.locators.length > 0).length

  return (
    <div className="uisv uisv-surface">
      <aside className="uisv-pane uisv-nav">
        <div className="uisv-pane-head"><span>页面</span><em>{data.pages.length}</em></div>
        <div className="uisv-page-list">
          {data.pages.map(page => {
            const controls = data.controls.filter(control => control.pageId === page.pageId)
            const pageLocatedCount = controls.filter(control => control.locators.length > 0).length
            return (
              <button type="button" key={page.pageId} className={`uisv-page-item${page.pageId === activePage?.pageId ? ' active' : ''}`} onClick={() => setPageId(page.pageId)}>
                <span className="uisv-page-glyph"><AppstoreOutlined /></span>
                <span className="uisv-page-copy"><strong>{page.title}</strong><small>{page.route}</small></span>
                <span className="uisv-page-count">{controls.length}</span>
                <span className="uisv-page-located">{pageLocatedCount}/{controls.length}</span>
              </button>
            )
          })}
        </div>
        <div className="uisv-nav-foot">
          <div className="uisv-nav-foot-title">定位覆盖</div>
          <div className="uisv-cover-row"><span>全部控件</span><span className="uisv-cover-track"><i style={{ width: `${data.controls.length ? located / data.controls.length * 100 : 0}%` }} /></span><em>{located}/{data.controls.length}</em></div>
          <div className="uisv-cover-note">还有 {data.controls.length - located} 个控件没有源码定位候选</div>
        </div>
      </aside>

      <main className="uisv-pane uisv-main">
        <div className="uisv-main-head">
          <div>
            <h3>{activePage?.title ?? '未命名页面'} <code>{activePage?.route}</code></h3>
            <p>{pageControls.length} 个控件 · {pageLocated} 个有源码定位候选 · {pageControls.length - pageLocated} 个待补</p>
          </div>
          <div className="uisv-head-tags"><Tag variant="filled" color="blue">{pageControls.length} 控件</Tag>{pageControls.length - pageLocated ? <Tag variant="filled" color="warning">{pageControls.length - pageLocated} 待补</Tag> : null}</div>
        </div>
        {pageControls.length === 0 ? <div className="uisv-inline-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="这个页面下还没有控件" /></div> : (
          <div className="uisv-table-wrap">
            <div className="uisv-table uisv-surface-table">
              <div className="uisv-thead uisv-surface-grid"><span>控件</span><span>类型</span><span>定位</span><span>显示条件</span><span>状态</span></div>
              {pageControls.map(control => (
                <button type="button" key={control.controlId} className={`uisv-row uisv-surface-grid${control.controlId === activeControl?.controlId ? ' selected' : ''}`} onClick={() => setControlId(control.controlId)}>
                  <span className="uisv-control-cell"><TypeIcon type={control.type} /><span><strong>{control.name}</strong><code>{control.controlId}</code></span></span>
                  <span className="uisv-muted">{control.typeLabel}</span>
                  <span className="uisv-locator-cell">{control.locators[0] ? <code>{control.locators[0].locatorValue}</code> : <em>无源码候选</em>}</span>
                  <span className="uisv-condition-cell" title={control.conditions[0]?.description}>{control.conditions[0]?.description ?? '—'}</span>
                  <span>{control.locators.length ? <span className="uisv-pill blue">源码推断</span> : <span className="uisv-pill amber">待补定位</span>}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="uisv-table-foot"><span>显示 {pageControls.length} / {data.controls.length} 个控件</span><span>点击行查看证据</span></div>
      </main>

      <aside className="uisv-pane uisv-inspector">
        {activeControl ? <ControlInspector control={activeControl} data={data} /> : <div className="uisv-inline-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择控件查看证据" /></div>}
      </aside>
    </div>
  )
}

function ControlInspector({ control, data }: { control: SurfaceControl; data: ReturnType<typeof parseSurface> }) {
  const interactions = (data?.interactions ?? []).filter(interaction => interaction.controlId === control.controlId)
  const unknowns = (data?.unknowns ?? []).filter(unknown => unknown.affectedIds.includes(control.controlId))
  return <div className="uisv-inspector-scroll">
    <div className="uisv-inspector-head"><TypeIcon type={control.type} /><div><h3>{control.name}</h3><code>{control.controlId}</code></div><Tag variant="filled" color="blue">{control.typeLabel}</Tag></div>
    <div className="uisv-inspector-tags"><Tag>{control.containerId || '未归属区域'}</Tag><Tag>{control.uniqueness === 'unknown' ? '唯一性未知' : control.uniqueness}</Tag></div>
    <section><h4>来源</h4><p>源码：<code>{control.sourceRef || '—'}</code></p><p>容器：<code>{control.containerId || '—'}</code></p>{control.visibleText ? <p>可见文本：{control.visibleText}</p> : null}</section>
    <section><h4>显示条件 <span>{control.conditions.length}</span></h4>{control.conditions.length ? control.conditions.map((condition, index) => <div className="uisv-note-box amber" key={`${condition.description}-${index}`}><WarningFilled /><span>{condition.description}</span></div>) : <p className="uisv-muted">无显示条件。</p>}</section>
    <section><h4>定位候选 <span>{control.locators.length}</span></h4>{control.locators.length ? control.locators.map((locator, index) => <div className="uisv-locator-box" key={`${locator.locatorValue}-${index}`}><code>{locator.locatorValue}</code><div><Tag variant="filled" color="blue">{locator.locatorType ?? 'locator'}</Tag>{locator.confirmed ? <Tag variant="filled" color="green">confirmed</Tag> : <Tag variant="filled" color="gold">源码推断</Tag>}<span>{locator.stability ?? '未知稳定性'}</span></div>{locator.reason ? <p>{locator.reason}</p> : null}</div>) : <div className="uisv-note-box amber"><ExclamationCircleFilled /><span>源码中还没有可用的定位候选，需要在运行时补充 DOM 证据。</span></div>}</section>
    {interactions.length ? <section><h4>关联交互 <span>{interactions.length}</span></h4>{interactions.slice(0, 3).map(interaction => <div className="uisv-interaction-box" key={interaction.interactionId}><strong>{interaction.interactionId}</strong><span>{interaction.description || interaction.effect || '无描述'}</span></div>)}</section> : null}
    {unknowns.length ? <section><h4>待确认 <span>{unknowns.length}</span></h4>{unknowns.slice(0, 2).map(unknown => <div className="uisv-note-box amber" key={unknown.topic}><WarningFilled /><span>{unknown.topic}</span></div>)}</section> : null}
    <div className="uisv-inspector-note">审核提示：源码候选只代表模板推断，运行时需要用真实页面确认 locator 与唯一性。</div>
  </div>
}
