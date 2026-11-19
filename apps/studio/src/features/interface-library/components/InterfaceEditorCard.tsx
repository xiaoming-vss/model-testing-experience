import { Button, Input, Select, Tag } from 'antd'
import { InterfaceBodyPanel } from './InterfaceBodyPanel'
import { InterfaceHeadersPanel } from './InterfaceHeadersPanel'
import { InterfaceParamsPanel } from './InterfaceParamsPanel'
import { InterfaceResponsePanel } from './InterfaceResponsePanel'
import { InterfaceSettingsPanel } from './InterfaceSettingsPanel'
import { INTERFACE_METHODS, methodTone } from '../utils/interfaceForm'
import { formatTime } from '@/utils/format'
import type { InterfaceDetailPageModel } from '../hooks/useInterfaceDetailPage'

function InterfaceEditorHeader({ page }: { page: InterfaceDetailPageModel }) {
  const {
    draft,
    isCreate,
    canWrite,
    repositories,
    selectedRepository,
    patch,
    changeRepository,
  } = page
  if (!draft) return null

  return (
    <div className="if-editor-head flex flex-none flex-col gap-[5px] px-4 pb-[9px] pt-[13px]">
      <Input
        className="if-name-input"
        value={draft.name}
        maxLength={120}
        disabled={!canWrite}
        placeholder="接口名称，例如：查询订单详情"
        aria-label="接口名称"
        onChange={event => patch({ name: event.target.value })}
      />
      <div className="if-editor-meta flex min-w-0 items-center gap-[7px] text-[11px] leading-5 text-[var(--srf-text-muted)]">
        <span>所属软件仓库</span>
        {isCreate ? (
          <Select
            className="if-app-select min-w-40"
            aria-label="所属软件仓库"
            value={draft.softwareRepositoryId || undefined}
            placeholder="选择软件仓库"
            disabled={!canWrite}
            options={repositories.map(repository => ({
              label: repository.name,
              value: repository.softwareRepositoryId,
            }))}
            onChange={changeRepository}
          />
        ) : (
          <span className="if-editor-app font-semibold text-[var(--srf-text)]">{draft.softwareRepositoryName || selectedRepository?.name || '—'}</span>
        )}
        <span className="if-meta-dot">·</span>
        <span>{draft.updatedAt ? formatTime(draft.updatedAt) : '新建'}</span>
      </div>
    </div>
  )
}

function InterfaceRequestBar({ page }: { page: InterfaceDetailPageModel }) {
  const {
    draft,
    isCreate,
    interfaceId,
    canWrite,
    interfaceInActiveProject,
    selectedRepository,
    saveMutation,
    patch,
    changePath,
  } = page
  if (!draft) return null

  const repositoryBasePath = selectedRepository?.basePath || ''
  const methodToneClass = methodTone(draft.method)

  return (
    <div className="if-request-bar flex flex-none items-center gap-2 border-b border-[var(--srf-divider)] px-4 pb-[13px] pt-2 max-[760.01px]:flex-wrap max-[760.01px]:items-stretch">
      <Select
        className={`if-method-select if-method-${methodToneClass} w-[104px] flex-none max-[760.01px]:w-[96px]`}
        aria-label="请求方法"
        value={draft.method}
        disabled={!canWrite}
        options={INTERFACE_METHODS.map(method => ({ label: method, value: method }))}
        onChange={method => patch({ method })}
      />
      <div className="if-path-input-wrap flex min-w-0 flex-auto items-stretch overflow-hidden rounded-[var(--srf-radius-control)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] focus-within:border-[var(--srf-accent-border)] focus-within:shadow-[0_0_0_3px_var(--srf-accent-soft)] max-[760.01px]:order-3 max-[760.01px]:basis-full">
        <span className="if-base-prefix flex max-w-[170px] flex-none items-center overflow-hidden text-ellipsis whitespace-nowrap border-r border-[var(--srf-divider)] bg-[var(--srf-chip)] px-2.5 font-[ui-monospace,SFMono-Regular,Menlo,Consolas,monospace] text-[11px] text-[var(--srf-text-secondary)]" title={repositoryBasePath || '软件仓库未设置 base path'}>
          {repositoryBasePath || '/…'}
        </span>
        <Input
          className="if-path-input"
          value={draft.path}
          disabled={!canWrite}
          placeholder="/orders/{orderId}"
          aria-label="接口路径"
          onChange={event => changePath(event.target.value)}
          onBlur={() => changePath(draft.path.trim())}
        />
      </div>
      {canWrite ? (
        <Button
          type="primary"
          className="if-save-button min-w-[86px] flex-none max-[760.01px]:ms-auto"
          loading={saveMutation.isPending}
          disabled={
            !draft.name.trim() ||
            !draft.path.trim() ||
            !draft.softwareRepositoryId ||
            !interfaceInActiveProject ||
            (!isCreate && draft.interfaceId !== interfaceId)
          }
          onClick={() => saveMutation.mutate()}
        >
          {isCreate ? '创建接口' : '保存'}
        </Button>
      ) : (
        <Tag className="if-readonly-tag">只读</Tag>
      )}
    </div>
  )
}

function InterfaceEditorTabs({ page }: { page: InterfaceDetailPageModel }) {
  const { tabs, activeTab, setActiveTab } = page

  return (
    <div className="if-editor-tabs flex flex-none items-stretch gap-0.5 overflow-x-auto border-b border-[var(--srf-card-border)] px-4" role="tablist" aria-label="接口编辑分区">
      {tabs.map(tab => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          id={`if-editor-tab-${tab.key}`}
          aria-controls={`if-editor-panel-${tab.key}`}
          aria-selected={activeTab === tab.key}
          className={`if-editor-tab relative inline-flex min-h-10 cursor-pointer items-center gap-[5px] whitespace-nowrap border-0 bg-transparent px-2.5 py-0 font-[inherit] text-[12px] font-semibold ${activeTab === tab.key ? ' is-active text-[var(--srf-accent)] after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-t-[2px] after:bg-[var(--srf-accent)] after:content-[""]' : ' text-[var(--srf-text-secondary)] hover:text-[var(--srf-text)]'}`}
          onClick={() => setActiveTab(tab.key)}
        >
          {tab.label}
          {tab.count !== undefined ? <span className={`if-tab-count min-w-[17px] rounded-full px-[5px] text-center text-[10px] leading-[17px] ${activeTab === tab.key ? ' bg-[var(--srf-count-badge)] text-[var(--srf-accent-strong)]' : ' bg-[var(--srf-chip)] text-[var(--srf-text-muted)]'}`}>{tab.count}</span> : null}
        </button>
      ))}
    </div>
  )
}

function InterfaceEditorPanels({ page }: { page: InterfaceDetailPageModel }) {
  const {
    draft,
    canWrite,
    activeTab,
    jsonTexts,
    setJsonTexts,
    tagsText,
    setTagsText,
    allRequirements,
    patch,
  } = page
  if (!draft) return null

  return (
    <div
      className="if-editor-body min-h-0 flex-auto overflow-auto p-4"
      role="tabpanel"
      id={`if-editor-panel- ${activeTab}`}
      aria-labelledby={`if-editor-tab- ${activeTab}`}
    >
      {activeTab === 'params' ? (
        <div className="if-tab-section flex flex-col gap-[22px]">
          <InterfaceParamsPanel
            title="Path 参数"
            hint="路径占位符自动同步；Path 参数始终必填。"
            location="path"
            rows={draft.pathParams}
            readOnly={!canWrite}
            onChange={rows => patch({ pathParams: rows })}
          />
          <InterfaceParamsPanel
            title="Query 参数"
            hint="查询参数会保存在接口定义中，后续可用于生成用例。"
            location="query"
            rows={draft.queryParams}
            readOnly={!canWrite}
            onChange={rows => patch({ queryParams: rows })}
          />
        </div>
      ) : null}

      {activeTab === 'headers' ? (
        <div className="if-tab-section">
          <InterfaceHeadersPanel
            rows={draft.headers}
            readOnly={!canWrite}
            onChange={rows => patch({ headers: rows })}
          />
        </div>
      ) : null}

      {activeTab === 'body' ? (
        <InterfaceBodyPanel
          draft={draft}
          readOnly={!canWrite}
          schemaText={jsonTexts.bodySchema}
          exampleText={jsonTexts.bodyExample}
          onSchemaText={value => setJsonTexts(previous => ({ ...previous, bodySchema: value }))}
          onExampleText={value => setJsonTexts(previous => ({ ...previous, bodyExample: value }))}
          onChange={patch}
        />
      ) : null}

      {activeTab === 'response' ? (
        <InterfaceResponsePanel
          draft={draft}
          readOnly={!canWrite}
          schemaText={jsonTexts.responseSchema}
          exampleText={jsonTexts.responseExample}
          onSchemaText={value => setJsonTexts(previous => ({ ...previous, responseSchema: value }))}
          onExampleText={value => setJsonTexts(previous => ({ ...previous, responseExample: value }))}
          onChange={patch}
        />
      ) : null}

      {activeTab === 'settings' ? (
        <InterfaceSettingsPanel
          draft={draft}
          readOnly={!canWrite}
          tagsText={tagsText}
          onTagsText={setTagsText}
          requirementOptions={allRequirements}
          onChange={patch}
        />
      ) : null}
    </div>
  )
}

export function InterfaceEditorCard({ page }: { page: InterfaceDetailPageModel }) {
  return (
    <section className="if-editor-card flex min-h-0 min-w-0 flex-auto flex-col overflow-hidden rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)]">
      <InterfaceEditorHeader page={page} />
      <InterfaceRequestBar page={page} />
      <InterfaceEditorTabs page={page} />
      <InterfaceEditorPanels page={page} />
    </section>
  )
}
