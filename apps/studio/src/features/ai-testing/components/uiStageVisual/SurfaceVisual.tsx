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
  return <span className="uisv-type-icon inline-flex h-6 w-6 flex-[0_0_24px] items-center justify-center rounded-[5px] bg-[var(--uisv-f1f5f9)] text-[12px] text-[var(--uisv-64748b)]">{typeIcons[type] ?? <AppstoreOutlined />}</span>
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
    <div className="uisv uisv-surface grid h-full min-h-0 grid-cols-[230px_minmax(0,1fr)_344px] gap-2.5 text-[13px] max-[1200.01px]:grid-cols-[190px_minmax(0,1fr)]">
      <aside className="uisv-pane uisv-nav flex min-h-0 flex-col overflow-hidden rounded-[10px] border border-[var(--uisv-e3eaf3)] bg-[var(--uisv-fff)]">
        <div className="uisv-pane-head flex flex-none items-center justify-between px-3 pb-[9px] pt-3 text-[13.5px] font-bold text-[var(--uisv-334155)]"><span>页面</span><em className="inline-flex h-[19px] min-w-[21px] items-center justify-center rounded-[5px] bg-[var(--uisv-f1f5f9)] px-[5px] text-[11px] not-italic text-[var(--uisv-64748b)]">{data.pages.length}</em></div>
        <div className="uisv-page-list min-h-0 flex-1 overflow-auto px-1.5">
          {data.pages.map(page => {
            const controls = data.controls.filter(control => control.pageId === page.pageId)
            const pageLocatedCount = controls.filter(control => control.locators.length > 0).length
            const active = page.pageId === activePage?.pageId
            return (
              <button type="button" key={page.pageId} className={`uisv-page-item flex w-full cursor-pointer items-center gap-2 rounded-[7px] border-0 p-2 text-left font-[inherit] [&+&]:mt-px ${active ? 'active bg-[var(--uisv-eff6ff)]' : 'bg-transparent hover:bg-[var(--uisv-f8fafc)]'}`} onClick={() => setPageId(page.pageId)}>
                <span className={`uisv-page-glyph inline-flex h-[26px] w-[26px] flex-[0_0_26px] items-center justify-center rounded-[7px] text-[12px] ${active ? 'bg-[var(--uisv-dbeafe)] text-[var(--uisv-1d4ed8)]' : 'bg-[var(--uisv-f1f5f9)] text-[var(--uisv-64748b)]'}`}><AppstoreOutlined /></span>
                <span className="uisv-page-copy flex min-w-0 flex-1 flex-col gap-px"><strong className="overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-semibold text-[var(--uisv-1e293b)]">{page.title}</strong><small className="overflow-hidden text-ellipsis whitespace-nowrap text-[11.5px] text-[var(--uisv-94a3b8)]">{page.route}</small></span>
                <span className="uisv-page-count inline-flex h-[18px] min-w-[19px] items-center justify-center rounded-[4px] bg-[var(--uisv-f1f5f9)] px-1 text-[11px] text-[var(--uisv-64748b)]">{controls.length}</span>
                <span className="uisv-page-located text-[11px] tabular-nums text-[var(--uisv-94a3b8)]">{pageLocatedCount}/{controls.length}</span>
              </button>
            )
          })}
        </div>
        <div className="uisv-nav-foot m-2 flex-none rounded-[8px] bg-[var(--uisv-f8fafc)] p-2">
          <div className="uisv-nav-foot-title mb-[5px] text-[12px] font-semibold text-[var(--uisv-64748b)]">定位覆盖</div>
          <div className="uisv-cover-row grid grid-cols-[60px_minmax(0,1fr)_42px] items-center gap-[5px] text-[11px] text-[var(--uisv-64748b)]"><span>全部控件</span><span className="uisv-cover-track h-[5px] overflow-hidden rounded-[4px] bg-[var(--uisv-e9eef5)]"><i className="block h-full rounded-[inherit] bg-[var(--uisv-2563eb)]" style={{ width: `${data.controls.length ? located / data.controls.length * 100 : 0}%` }} /></span><em className="text-right text-[11px] not-italic text-[var(--uisv-94a3b8)]">{located}/{data.controls.length}</em></div>
          <div className="uisv-cover-note mt-[5px] text-[11px] leading-[1.5] text-[var(--uisv-94a3b8)]">还有 {data.controls.length - located} 个控件没有源码定位候选</div>
        </div>
      </aside>

      <main className="uisv-pane uisv-main flex min-h-0 flex-col overflow-hidden rounded-[10px] border border-[var(--uisv-e3eaf3)] bg-[var(--uisv-fff)]">
        <div className="uisv-main-head flex flex-none items-start justify-between gap-2.5 px-3 pb-2 pt-3">
          <div>
            <h3 className="m-0 overflow-hidden text-ellipsis whitespace-nowrap text-[15.5px] font-bold text-[var(--uisv-0f172a)]">{activePage?.title ?? '未命名页面'} <code className="ml-1.5 text-[11px] font-normal text-[var(--uisv-94a3b8)]">{activePage?.route}</code></h3>
            <p className="m-0 mt-1 overflow-hidden text-ellipsis whitespace-nowrap text-[12px] leading-[1.45] text-[var(--uisv-94a3b8)]">{pageControls.length} 个控件 · {pageLocated} 个有源码定位候选 · {pageControls.length - pageLocated} 个待补</p>
          </div>
          <div className="uisv-head-tags flex flex-none items-center gap-1 [&_.ant-tag]:m-0 [&_.ant-tag]:text-[11px] [&_.ant-tag]:leading-[17px]"><Tag variant="filled" color="blue">{pageControls.length} 控件</Tag>{pageControls.length - pageLocated ? <Tag variant="filled" color="warning">{pageControls.length - pageLocated} 待补</Tag> : null}</div>
        </div>
        {pageControls.length === 0 ? <div className="uisv-inline-empty flex min-h-0 flex-1 items-center justify-center"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="这个页面下还没有控件" /></div> : (
          <div className="uisv-table-wrap min-h-0 flex-1 overflow-auto border-t border-[var(--uisv-eef2f7)]">
            <div className="uisv-table uisv-surface-table min-w-[620px]">
              <div className="uisv-thead uisv-surface-grid grid h-9 grid-cols-[minmax(150px,1.35fr)_58px_minmax(150px,1.5fr)_minmax(130px,1.2fr)_76px] items-center gap-[7px] bg-[var(--uisv-f8fafc)] px-[11px] text-[11.5px] font-semibold text-[var(--uisv-7b8799)]"><span>控件</span><span>类型</span><span>定位</span><span>显示条件</span><span>状态</span></div>
              {pageControls.map(control => {
                const selected = control.controlId === activeControl?.controlId
                return (
                <button type="button" key={control.controlId} className={`uisv-row uisv-surface-grid grid min-h-[52px] w-full cursor-pointer grid-cols-[minmax(150px,1.35fr)_58px_minmax(150px,1.5fr)_minmax(130px,1.2fr)_76px] items-center gap-[7px] border-0 border-t border-[var(--uisv-f3f6fa)] px-[11px] text-left font-[inherit] text-[13px] text-[var(--uisv-334155)] ${selected ? 'selected bg-[var(--uisv-eff6ff)] shadow-[inset_3px_0_0_var(--uisv-2563eb)]' : 'bg-[var(--uisv-fff)] hover:bg-[var(--uisv-fbfdff)]'}`} onClick={() => setControlId(control.controlId)}>
                  <span className="uisv-control-cell flex min-w-0 items-center gap-1.5 [&>span:last-child]:flex [&>span:last-child]:min-w-0 [&>span:last-child]:flex-col [&>span:last-child]:gap-px"><TypeIcon type={control.type} /><span><strong className="overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-semibold text-[var(--uisv-1e293b)]">{control.name}</strong><code className="overflow-hidden text-ellipsis whitespace-nowrap text-[11px] text-[var(--uisv-94a3b8)]">{control.controlId}</code></span></span>
                  <span className="uisv-muted text-[var(--uisv-94a3b8)]">{control.typeLabel}</span>
                  <span className="uisv-locator-cell min-w-0 overflow-hidden [&_code]:block [&_code]:overflow-hidden [&_code]:text-ellipsis [&_code]:whitespace-nowrap [&_code]:text-[12px] [&_code]:text-[var(--uisv-475569)] [&_em]:text-[11px] [&_em]:not-italic [&_em]:text-[var(--uisv-b45309)]">{control.locators[0] ? <code>{control.locators[0].locatorValue}</code> : <em>无源码候选</em>}</span>
                  <span className="uisv-condition-cell overflow-hidden text-ellipsis whitespace-nowrap text-[12px] text-[var(--uisv-64748b)]" title={control.conditions[0]?.description}>{control.conditions[0]?.description ?? '—'}</span>
                  <span>{control.locators.length ? <span className="uisv-pill blue inline-flex h-[22px] items-center gap-1 whitespace-nowrap rounded-[5px] bg-[var(--uisv-eff6ff)] px-[7px] text-[11.5px] font-semibold text-[var(--uisv-1d4ed8)]">源码推断</span> : <span className="uisv-pill amber inline-flex h-[22px] items-center gap-1 whitespace-nowrap rounded-[5px] bg-[var(--uisv-fff8eb)] px-[7px] text-[11.5px] font-semibold text-[var(--uisv-b45309)]">待补定位</span>}</span>
                </button>
                )
              })}
            </div>
          </div>
        )}
        <div className="uisv-table-foot flex flex-[0_0_32px] items-center justify-between border-t border-[var(--uisv-eef2f7)] bg-[var(--uisv-fbfcfe)] px-3 text-[11px] text-[var(--uisv-94a3b8)]"><span>显示 {pageControls.length} / {data.controls.length} 个控件</span><span>点击行查看证据</span></div>
      </main>

      <aside className="uisv-pane uisv-inspector flex min-h-0 flex-col overflow-hidden rounded-[10px] border border-[var(--uisv-e3eaf3)] bg-[var(--uisv-fff)] max-[1200.01px]:hidden">
        {activeControl ? <ControlInspector control={activeControl} data={data} /> : <div className="uisv-inline-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择控件查看证据" /></div>}
      </aside>
    </div>
  )
}

function ControlInspector({ control, data }: { control: SurfaceControl; data: ReturnType<typeof parseSurface> }) {
  const interactions = (data?.interactions ?? []).filter(interaction => interaction.controlId === control.controlId)
  const unknowns = (data?.unknowns ?? []).filter(unknown => unknown.affectedIds.includes(control.controlId))
  return <div className="uisv-inspector-scroll min-h-0 flex-1 overflow-auto p-3">
    <div className="uisv-inspector-head flex items-center gap-[7px] border-b border-[var(--uisv-eef2f7)] pb-2 [&>div]:min-w-0 [&>div]:flex-1 [&_.ant-tag]:m-0 [&_.ant-tag]:text-[11px] [&_code]:mt-0.5 [&_code]:block [&_code]:overflow-hidden [&_code]:text-ellipsis [&_code]:whitespace-nowrap [&_code]:text-[11px] [&_code]:text-[var(--uisv-94a3b8)] [&_h3]:m-0 [&_h3]:overflow-hidden [&_h3]:text-ellipsis [&_h3]:whitespace-nowrap [&_h3]:text-[13.5px] [&_h3]:font-bold [&_h3]:text-[var(--uisv-0f172a)]"><TypeIcon type={control.type} /><div><h3>{control.name}</h3><code>{control.controlId}</code></div><Tag variant="filled" color="blue">{control.typeLabel}</Tag></div>
    <div className="uisv-inspector-tags mt-[7px] flex flex-wrap gap-1 [&_.ant-tag]:m-0 [&_.ant-tag]:text-[11px]"><Tag>{control.containerId || '未归属区域'}</Tag><Tag>{control.uniqueness === 'unknown' ? '唯一性未知' : control.uniqueness}</Tag></div>
    <section><h4>来源</h4><p>源码：<code>{control.sourceRef || '—'}</code></p><p>容器：<code>{control.containerId || '—'}</code></p>{control.visibleText ? <p>可见文本：{control.visibleText}</p> : null}</section>
    <section><h4>显示条件 <span>{control.conditions.length}</span></h4>{control.conditions.length ? control.conditions.map((condition, index) => <div className="uisv-note-box amber" key={`${condition.description}-${index}`}><WarningFilled /><span>{condition.description}</span></div>) : <p className="uisv-muted">无显示条件。</p>}</section>
    <section><h4>定位候选 <span>{control.locators.length}</span></h4>{control.locators.length ? control.locators.map((locator, index) => <div className="uisv-locator-box" key={`${locator.locatorValue}-${index}`}><code>{locator.locatorValue}</code><div><Tag variant="filled" color="blue">{locator.locatorType ?? 'locator'}</Tag>{locator.confirmed ? <Tag variant="filled" color="green">confirmed</Tag> : <Tag variant="filled" color="gold">源码推断</Tag>}<span>{locator.stability ?? '未知稳定性'}</span></div>{locator.reason ? <p>{locator.reason}</p> : null}</div>) : <div className="uisv-note-box amber"><ExclamationCircleFilled /><span>源码中还没有可用的定位候选，需要在运行时补充 DOM 证据。</span></div>}</section>
    {interactions.length ? <section><h4>关联交互 <span>{interactions.length}</span></h4>{interactions.slice(0, 3).map(interaction => <div className="uisv-interaction-box" key={interaction.interactionId}><strong>{interaction.interactionId}</strong><span>{interaction.description || interaction.effect || '无描述'}</span></div>)}</section> : null}
    {unknowns.length ? <section><h4>待确认 <span>{unknowns.length}</span></h4>{unknowns.slice(0, 2).map(unknown => <div className="uisv-note-box amber" key={unknown.topic}><WarningFilled /><span>{unknown.topic}</span></div>)}</section> : null}
    <div className="uisv-inspector-note">审核提示：源码候选只代表模板推断，运行时需要用真实页面确认 locator 与唯一性。</div>
  </div>
}
