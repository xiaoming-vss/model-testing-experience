import { FileTextOutlined, InfoCircleOutlined, InboxOutlined, SearchOutlined, WarningOutlined } from '@ant-design/icons'
import { Alert, Button, Checkbox, Empty, Input, Modal, Segmented, Select, Space, Steps, Tag, Upload } from 'antd'
import type { UploadFile } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import { ApiError } from '@/services/api'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { MethodBadge } from '@/shared/components/MethodBadge'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { SoftwareRepository, ImportCommitResult, ImportItem, ImportPreview } from '../types'
import styles from '../styles/interface-library.module.css'
import detailStyles from '../styles/interface-detail.module.css'
import { parseJsonText } from '../utils/interfaceForm'
import { UNTAGGED_GROUP, firstTag, groupLabel } from '../utils/interfaceGroups'

const interfaceScopes = `${styles.scope} ${detailStyles.scope}`

type Props = {
  open: boolean
  repositories: SoftwareRepository[]
  defaultSoftwareRepositoryId?: string
  onClose: () => void
  onImported: () => void
}

type ImportMode = 'upload' | 'editor'

type ImportGroup = {
  name: string
  items: ImportItem[]
  actionable: ImportItem[]
}

const MAX_IMPORT_BYTES = 8 * 1024 * 1024
const INLINE_FILE_NAME = 'inline-openapi.json'

const SUMMARY_TYPES = ['new', 'modified', 'unchanged', 'library_only'] as const

const CHANGE_TONES: Record<ImportItem['changeType'], { label: string; dot: string; text: string }> = {
  new: { label: '新增', dot: 'bg-[var(--app-status-approved-text)]', text: 'text-[var(--app-status-approved-text)]' },
  modified: { label: '修改', dot: 'bg-[var(--srf-accent)]', text: 'text-[var(--srf-accent)]' },
  unchanged: { label: '未变化', dot: 'bg-[var(--srf-text-muted)]', text: 'text-[var(--srf-text-muted)]' },
  library_only: { label: '仅库中存在', dot: 'bg-[var(--app-status-warning-text)]', text: 'text-[var(--app-status-warning-text)]' },
}

export function OpenApiImportModal({
  open,
  repositories,
  defaultSoftwareRepositoryId = '',
  onClose,
  onImported,
}: Props) {
  const [step, setStep] = useState(0)
  const [mode, setMode] = useState<ImportMode>('upload')
  const [softwareRepositoryId, setSoftwareRepositoryId] = useState(defaultSoftwareRepositoryId)
  const [file, setFile] = useState<File | null>(null)
  const [jsonText, setJsonText] = useState('')
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const [applyBasePath, setApplyBasePath] = useState(false)
  const [result, setResult] = useState<ImportCommitResult | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [error, setError] = useState('')
  const [groupSearch, setGroupSearch] = useState('')
  const [activeGroup, setActiveGroup] = useState('')
  const groupListRef = useRef<HTMLDivElement>(null)
  const groupSectionRefs = useRef(new Map<string, HTMLElement>())

  useEffect(() => {
    if (!open) return
    setStep(0)
    setMode('upload')
    setSoftwareRepositoryId(
      defaultSoftwareRepositoryId ||
        repositories[0]?.softwareRepositoryId ||
        '',
    )
    setFile(null)
    setJsonText('')
    setPreview(null)
    setSelectedKeys(new Set())
    setApplyBasePath(false)
    setResult(null)
    setSubmitting(false)
    setPreviewing(false)
    setError('')
    setGroupSearch('')
    setActiveGroup('')
    groupSectionRefs.current.clear()
  }, [repositories, defaultSoftwareRepositoryId, open])

  const selectedRepository = repositories.find(
    repository => repository.softwareRepositoryId === softwareRepositoryId,
  )
  const actionableItems = useMemo(
    () => preview?.items.filter(isActionable) ?? [],
    [preview],
  )
  const selectedItems = actionableItems.filter(item => selectedKeys.has(item.key))
  const basePathBlocked = Boolean(preview?.basePathChange && !preview.basePathChange.canApply)
  const libraryGroupNames = useMemo(() => {
    const names = new Set<string>(selectedRepository?.interfaceGroups ?? [])
    for (const item of preview?.items ?? []) {
      if (item.changeType === 'new') continue
      const group = targetGroupLabel(item)
      if (group !== UNTAGGED_GROUP) names.add(group)
    }
    return names
  }, [preview, selectedRepository])
  const createdGroups = useMemo(() => {
    if (!result || !preview) return []
    const names = new Set<string>()
    for (const entry of result.interfaces) {
      if (entry.changeType !== 'new') continue
      const item = preview.items.find(candidate => candidate.key === entry.key)
      const group = item ? targetGroupLabel(item) : UNTAGGED_GROUP
      if (isNewGroup(group, libraryGroupNames)) names.add(group)
    }
    return [...names].sort((left, right) => left.localeCompare(right, 'zh-CN'))
  }, [libraryGroupNames, preview, result])
  const groupedItems = useMemo<ImportGroup[]>(() => {
    const groups = new Map<string, ImportItem[]>()
    for (const item of preview?.items ?? []) {
      const group = targetGroupLabel(item)
      const items = groups.get(group)
      if (items) items.push(item)
      else groups.set(group, [item])
    }
    return [...groups.entries()]
      .sort(([left], [right]) => {
        if (left === UNTAGGED_GROUP) return 1
        if (right === UNTAGGED_GROUP) return -1
        return left.localeCompare(right, 'zh-CN')
      })
      .map(([name, items]) => ({
        name,
        items,
        actionable: items.filter(isActionable),
      }))
  }, [preview])
  const visibleGroups = useMemo(() => {
    const query = groupSearch.trim().toLowerCase()
    if (!query) return groupedItems
    return groupedItems.filter(group => group.name.toLowerCase().includes(query))
  }, [groupSearch, groupedItems])
  const inlineJsonState = parseJsonText(jsonText)
  const sourceLabel = preview?.source.name || (mode === 'editor' ? '直接输入 JSON' : file?.name) || 'OpenAPI 文档'
  const sourceKind = (/\.([A-Za-z0-9]+)$/.exec(sourceLabel)?.[1] ?? (mode === 'editor' ? 'json' : 'file')).toUpperCase()
  const headSubtitle =
    step === 0
      ? '选择软件仓库与 OpenAPI / Swagger 文档'
      : step === 1
        ? `按分组检查 ${preview?.items.length ?? 0} 个接口，选择要导入的项`
        : '查看本次导入结果'

  function inlineJsonError() {
    if (!jsonText.trim()) return '请粘贴 OpenAPI JSON 内容'
    if (new Blob([jsonText]).size > MAX_IMPORT_BYTES) return 'JSON 内容不能超过 8 MB'
    if (!inlineJsonState.valid) return `JSON 格式错误： ${inlineJsonState.error}`
    const value = inlineJsonState.value
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return 'OpenAPI 文档必须是 JSON 对象'
    }
    return ''
  }

  function importSource(): File | null {
    if (mode === 'editor') {
      if (!jsonText.trim()) return null
      return new File([jsonText], INLINE_FILE_NAME, { type: 'application/json' })
    }
    return file
  }

  function handleFile(fileList: UploadFile[]) {
    const next = fileList[0]?.originFileObj
    if (!next) {
      setFile(null)
      return
    }
    if (next.size > MAX_IMPORT_BYTES) {
      message.error('文件不能超过 8 MB')
      return
    }
    if (!/\.(json|ya?ml)$/i.test(next.name)) {
      message.error('请选择 .json、.yaml 或 .yml 文件')
      return
    }
    setFile(next)
    setPreview(null)
    setError('')
  }

  async function loadPreview() {
    if (!softwareRepositoryId) {
      message.error('请选择软件仓库')
      return
    }
    const validationError = mode === 'editor' ? inlineJsonError() : ''
    const source = importSource()
    if (validationError) {
      setError(validationError)
      return
    }
    if (!source) {
      message.error(mode === 'editor' ? '请粘贴 OpenAPI JSON 内容' : '请选择 OpenAPI/Swagger 文件')
      return
    }
    setPreviewing(true)
    setError('')
    try {
      const data = await interfaceLibraryApi.previewOpenApiImport(softwareRepositoryId, source)
      setPreview(data)
      setSelectedKeys(
        new Set(
          data.items
            .filter(isActionable)
            .map(item => item.key),
        ),
      )
      setApplyBasePath(false)
      setGroupSearch('')
      setActiveGroup('')
      setStep(1)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setPreviewing(false)
    }
  }

  async function commit() {
    if (!preview || !softwareRepositoryId) return
    if (!selectedItems.length) {
      message.error('请选择要导入的接口')
      return
    }
    const source = importSource()
    if (!source) {
      message.error(mode === 'editor' ? '请粘贴 OpenAPI JSON 内容' : '请选择 OpenAPI/Swagger 文件')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const expectedItems: Record<string, number> = {}
      selectedItems.forEach(item => {
        if (item.existingVersion !== null && item.existingVersion !== undefined) {
          expectedItems[item.key] = item.existingVersion
        }
      })
      const data = await interfaceLibraryApi.commitOpenApiImport(softwareRepositoryId, {
        file: source,
        sourceDigest: preview.source.digest,
        selectedKeys: selectedItems.map(item => item.key),
        expectedItems,
        applyBasePath: basePathBlocked ? false : applyBasePath,
        expectedSoftwareRepositoryVersion:
          applyBasePath && !basePathBlocked ? selectedRepository?.version : undefined,
      })
      setResult(data)
      setStep(2)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  function toggleKey(key: string, checked: boolean) {
    setSelectedKeys(previous => {
      const next = new Set(previous)
      if (checked) next.add(key)
      else next.delete(key)
      return next
    })
  }

  function toggleGroup(group: ImportGroup, checked: boolean) {
    setSelectedKeys(previous => {
      const next = new Set(previous)
      for (const item of group.actionable) {
        if (checked) next.add(item.key)
        else next.delete(item.key)
      }
      return next
    })
  }

  function toggleAll(checked: boolean) {
    setSelectedKeys(checked ? new Set(actionableItems.map(item => item.key)) : new Set())
  }

  function selectionFor(group: ImportGroup) {
    const selected = group.actionable.reduce(
      (count, item) => count + (selectedKeys.has(item.key) ? 1 : 0),
      0,
    )
    return {
      all: group.actionable.length > 0 && selected === group.actionable.length,
      some: selected > 0 && selected < group.actionable.length,
    }
  }

  function jumpToGroup(groupName: string) {
    setActiveGroup(groupName)
    const list = groupListRef.current
    const section = groupSectionRefs.current.get(groupName)
    if (list && section) list.scrollTop = section.offsetTop
  }

  function close() {
    if (submitting || previewing) return
    onClose()
  }

  const footer = (
    <div className="if-import-footer flex w-full items-center gap-4">
      {step === 1 ? (
        <span className="if-import-foot-note flex min-w-0 items-start gap-1.5 text-left text-[11px] leading-4 text-[var(--srf-text-secondary)] max-[640.01px]:hidden">
          <InfoCircleOutlined className="mt-0.5 flex-none" aria-hidden="true" />
          <span>按方法与路径匹配；已有接口保留库内标签和分组，已移除接口保持原样，不自动停用或删除。</span>
        </span>
      ) : null}
      <div className="if-import-foot-actions ml-auto flex flex-none items-center gap-2">
        {step === 0 ? (
          <>
            <Button onClick={close} disabled={previewing}>取消</Button>
            <Button type="primary" loading={previewing} onClick={() => void loadPreview()}>
              预览差异
            </Button>
          </>
        ) : null}
        {step === 1 ? (
          <>
            <Button onClick={() => setStep(0)} disabled={submitting}>上一步</Button>
            <Button
              type="primary"
              loading={submitting}
              disabled={!selectedItems.length || basePathBlocked}
              onClick={() => void commit()}
            >
              导入选中 {selectedItems.length} 项
            </Button>
          </>
        ) : null}
        {step === 2 ? (
          <Button type="primary" onClick={onImported}>查看接口库</Button>
        ) : null}
      </div>
    </div>
  )

  return (
    <Modal
      rootClassName={`tp-surface if-import-modal ${interfaceScopes}`}
      open={open}
      title={
        <div className="if-import-heading flex items-start gap-3 pr-7">
          <span
            className="if-import-heading-icon flex h-8 w-8 flex-none items-center justify-center rounded-[9px] border border-[var(--srf-accent-border)] bg-[var(--srf-accent-soft)] text-[16px] text-[var(--srf-accent)]"
            aria-hidden="true"
          >
            <FileTextOutlined />
          </span>
          <div className="min-w-0">
            <h2 className="m-0 text-[15px] font-semibold leading-5 text-[var(--srf-text)]">导入 OpenAPI / Swagger</h2>
            <p className="m-0 text-[11px] font-normal leading-4 text-[var(--srf-text-secondary)]">{headSubtitle}</p>
          </div>
        </div>
      }
      width={1000}
      onCancel={close}
      mask={{ closable: !submitting && !previewing }}
      footer={footer}
      destroyOnHidden
    >
      <Steps
        current={step}
        size="small"
        className="if-import-steps mb-3"
        items={[{ title: '选择文档' }, { title: '预览差异' }, { title: '导入结果' }]}
      />
      {error ? <Alert type="error" showIcon title={error} className="if-import-error mb-3" /> : null}

      {step === 0 ? (
        <div className="if-import-step flex flex-col gap-3">
          <label className="if-import-field flex flex-col gap-1.5">
            <span className="text-[12px] font-semibold text-[var(--srf-text-secondary)]">软件仓库</span>
            <Select
              aria-label="选择导入的软件仓库"
              value={softwareRepositoryId || undefined}
              placeholder="请选择软件仓库"
              options={repositories.map(repository => ({
                label: repository.name,
                value: repository.softwareRepositoryId,
              }))}
              onChange={setSoftwareRepositoryId}
            />
          </label>
          <Segmented
            className="if-import-mode self-start"
            aria-label="导入方式"
            value={mode}
            options={[
              { label: '上传文件', value: 'upload' },
              { label: '直接输入 JSON', value: 'editor' },
            ]}
            onChange={value => {
              setMode(value as ImportMode)
              setPreview(null)
              setError('')
            }}
          />
          {mode === 'upload' ? (
            <Upload.Dragger
              accept=".json,.yaml,.yml"
              maxCount={1}
              fileList={
                file
                  ? [{ uid: file.name, name: file.name, status: 'done' } as UploadFile]
                  : []
              }
              beforeUpload={() => false}
              onChange={({ fileList }) => handleFile(fileList)}
              onRemove={() => {
                setFile(null)
                setPreview(null)
                return true
              }}
            >
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p className="ant-upload-text">点击或拖拽 OpenAPI / Swagger 文件到这里</p>
              <p className="ant-upload-hint">支持 JSON / YAML 文件，最大 8 MB</p>
            </Upload.Dragger>
          ) : (
            <div className="if-import-editor flex flex-col gap-2">
              <div className="if-editor-block-head flex items-center justify-between gap-2 text-[11px] font-semibold text-[var(--srf-text-secondary)]">
                <span>OpenAPI JSON</span>
                <span className={`if-json-state ${inlineJsonState.valid ? ' is-valid' : ' is-invalid'}`}>
                  {!jsonText.trim() ? '等待输入' : inlineJsonState.valid ? 'JSON 有效' : 'JSON 格式错误'}
                </span>
              </div>
              <TextCodeEditor
                value={jsonText}
                onChange={value => {
                  setJsonText(value)
                  setPreview(null)
                  setError('')
                }}
                language="json"
                ariaLabel="OpenAPI JSON 内容"
                height={280}
              />
              <div className="if-import-note rounded-[var(--srf-radius-control)] bg-[var(--srf-chip)] px-[11px] py-[9px] text-[12px] leading-[19px] text-[var(--srf-text-secondary)]">
                直接粘贴 OpenAPI JSON 文档，提交时按内联 JSON 文件解析；文档最大 8 MB，原始输入不会单独保存。
              </div>
            </div>
          )}
        </div>
      ) : null}

      {step === 1 && preview ? (
        <div className="if-import-step if-import-preview flex min-h-0 flex-col gap-2.5">
          <div className="if-import-source-stats flex flex-wrap items-center gap-x-3 gap-y-2">
            <div className="if-import-source flex min-w-0 items-center gap-2">
              <span className="if-import-source-kind flex-none rounded-[4px] border border-[var(--srf-accent-border)] bg-[var(--srf-accent-soft)] px-[5px] py-[3px] font-mono text-[10px] font-semibold leading-none tracking-[0.06em] text-[var(--srf-accent)]">
                {sourceKind}
              </span>
              <span
                className="if-import-source-name max-w-[260px] overflow-hidden text-ellipsis whitespace-nowrap text-[12px] font-semibold text-[var(--srf-text)]"
                title={sourceLabel}
              >
                {sourceLabel}
              </span>
              {preview.source.version ? (
                <span className="if-import-source-version flex-none text-[11px] text-[var(--srf-text-secondary)]">
                  · {preview.source.version}
                </span>
              ) : null}
            </div>
            <div
              className="if-import-stats ml-auto flex flex-wrap items-center gap-x-3 gap-y-1"
              aria-label="变更概览"
            >
              {SUMMARY_TYPES.map(type => {
                const tone = CHANGE_TONES[type]
                const value = preview.summary[type === 'library_only' ? 'libraryOnly' : type]
                return (
                  <span
                    key={type}
                    className="if-import-stat inline-flex items-center gap-1.5 text-[11px] text-[var(--srf-text-secondary)]"
                  >
                    <span className={`h-1.5 w-1.5 flex-none rounded-full ${tone.dot}`} aria-hidden="true" />
                    {tone.label}
                    <b className={`text-[12px] font-semibold tabular-nums ${tone.text}`}>{value}</b>
                  </span>
                )
              })}
            </div>
          </div>

          {preview.basePathChange ? (
            <Alert
              type={preview.basePathChange.canApply ? 'warning' : 'error'}
              showIcon
              title={`文档 base path 为 ${preview.basePathChange.document || '空'}，软件仓库当前为 ${preview.basePathChange.current || '空'}`}
              description={
                preview.basePathChange.canApply ? (
                  <Checkbox
                    checked={applyBasePath}
                    onChange={event => setApplyBasePath(event.target.checked)}
                  >
                    同时更新软件仓库 base path
                  </Checkbox>
                ) : (
                  '普通成员不能修改软件仓库 base path，请联系项目所有者更新软件仓库后再导入。'
                )
              }
            />
          ) : null}
          {preview.warnings.length ? (
            <Alert
              type="info"
              showIcon
              icon={<WarningOutlined />}
              title={`文档提示（${preview.warnings.length}）`}
              description={
                <ul className="if-import-warnings m-0 max-h-[130px] overflow-auto pl-4 text-[12px] leading-[19px]">
                  {preview.warnings.slice(0, 8).map((warning, index) => (
                    <li key={`${warning.code}-${index}`}>
                      {warning.method || warning.path ? `${warning.method} ${warning.path}：` : ''}
                      {warning.message}
                    </li>
                  ))}
                  {preview.warnings.length > 8 ? <li>其余 {preview.warnings.length - 8} 条已省略</li> : null}
                </ul>
              }
            />
          ) : null}

          <div className="if-import-layout flex h-[clamp(320px,calc(100dvh_-_380px),520px)] overflow-hidden rounded-[var(--srf-radius-control)] border border-[var(--srf-card-border)]">
            <aside
              className="if-import-rail flex w-[210px] flex-none flex-col gap-1.5 border-r border-[var(--srf-card-border)] bg-[var(--app-bg)] p-2 max-[900.01px]:hidden"
              aria-label="导入分组导航"
            >
              <div className="if-import-rail-head flex items-center justify-between px-[7px] text-[11px] font-semibold text-[var(--srf-text-secondary)]">
                <span>分组</span>
                <span className="tabular-nums">{groupedItems.length}</span>
              </div>
              <Input
                allowClear
                prefix={<SearchOutlined />}
                placeholder="搜索分组"
                aria-label="搜索导入分组"
                value={groupSearch}
                onChange={event => setGroupSearch(event.target.value)}
                className="if-import-group-search w-full"
              />
              <div className="if-import-rail-list min-h-0 flex-1 overflow-y-auto pt-0.5">
                {visibleGroups.map(group => {
                  const selected = activeGroup === group.name
                  return (
                    <button
                      key={group.name}
                      type="button"
                      className={`if-import-rail-item flex h-[27px] w-full items-center gap-2 rounded-[5px] px-[7px] text-left font-[inherit] text-[11px] ${selected ? 'bg-[var(--srf-accent-soft)] font-semibold text-[var(--srf-accent)]' : 'bg-transparent text-[var(--srf-text-secondary)] hover:bg-[var(--srf-hover)] hover:text-[var(--srf-text)]'}`}
                      aria-current={selected ? 'true' : undefined}
                      title={group.name}
                      onClick={() => jumpToGroup(group.name)}
                    >
                      <span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap">{group.name}</span>
                      <span className="flex-none tabular-nums">{group.items.length}</span>
                    </button>
                  )
                })}
                {visibleGroups.length === 0 ? (
                  <p className="if-import-rail-empty px-[7px] py-2 text-[11px] text-[var(--srf-text-secondary)]">
                    {groupSearch ? '没有匹配的分组' : '文档中没有分组'}
                  </p>
                ) : null}
              </div>
            </aside>

            <div className="if-import-main flex min-w-0 flex-1 flex-col">
              <div className="if-import-list-toolbar flex h-9 flex-none items-center justify-between gap-2 border-b border-[var(--srf-card-border)] bg-[var(--srf-hover)] px-3">
                <Checkbox
                  checked={actionableItems.length > 0 && selectedItems.length === actionableItems.length}
                  indeterminate={selectedItems.length > 0 && selectedItems.length < actionableItems.length}
                  disabled={actionableItems.length === 0}
                  onChange={event => toggleAll(event.target.checked)}
                >
                  全选
                </Checkbox>
                <span
                  className="if-import-selected-count text-[11px] text-[var(--srf-text-secondary)]"
                  role="status"
                  aria-label={`已选 ${selectedItems.length} / ${actionableItems.length}`}
                >
                  已选 <b className="font-semibold tabular-nums text-[var(--srf-text)]">{selectedItems.length}</b>
                  {' / '}
                  <span className="tabular-nums">{actionableItems.length}</span>
                </span>
              </div>

              <div
                ref={groupListRef}
                className="if-import-group-list relative min-h-0 flex-1 overflow-y-auto bg-[var(--srf-card)]"
                aria-label="导入接口分组列表"
              >
                {visibleGroups.map(group => {
                  const selection = selectionFor(group)
                  return (
                    <section
                      key={group.name}
                      ref={element => {
                        if (element) groupSectionRefs.current.set(group.name, element)
                        else groupSectionRefs.current.delete(group.name)
                      }}
                      data-import-group={group.name}
                      role="group"
                      aria-label={`分组 ${group.name}`}
                      className="if-import-group"
                    >
                      <div className="if-import-group-head sticky top-0 z-[1] flex min-h-9 items-center gap-2 border-b border-[var(--srf-card-border)] bg-[var(--srf-hover)] px-3 py-1.5">
                        <Checkbox
                          checked={selection.all}
                          indeterminate={selection.some}
                          disabled={group.actionable.length === 0}
                          onChange={event => toggleGroup(group, event.target.checked)}
                          aria-label={`选择分组 ${group.name}`}
                        />
                        <span
                          className="if-import-group-name min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[12px] font-semibold text-[var(--srf-text)]"
                          title={group.name}
                        >
                          {group.name}
                        </span>
                        <span className="if-import-group-count flex-none text-[11px] tabular-nums text-[var(--srf-text-secondary)]">
                          {group.items.length}
                        </span>
                        {isNewGroup(group.name, libraryGroupNames) ? (
                          <span className="if-import-group-new ml-auto flex-none rounded-[4px] border border-[color:color-mix(in_srgb,var(--app-status-approved-text)_35%,var(--srf-card-border))] bg-[color:color-mix(in_srgb,var(--app-status-approved-text)_10%,var(--srf-card))] px-1.5 py-px text-[11px] font-semibold leading-4 text-[var(--app-status-approved-text)]">
                            新建分组
                          </span>
                        ) : null}
                      </div>
                      {group.items.map(item => (
                        <ImportGroupRow
                          key={item.key}
                          item={item}
                          selected={selectedKeys.has(item.key)}
                          onToggle={checked => toggleKey(item.key, checked)}
                        />
                      ))}
                    </section>
                  )
                })}
                {visibleGroups.length === 0 ? (
                  <Empty
                    className="if-import-empty py-10"
                    description={groupSearch ? '没有匹配的分组' : '文档中没有接口'}
                  >
                    {groupSearch ? (
                      <Button type="link" size="small" onClick={() => setGroupSearch('')}>清空搜索</Button>
                    ) : null}
                  </Empty>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {step === 2 && result ? (
        <div className="if-import-step flex flex-col gap-3">
          <Alert
            type="success"
            showIcon
            title="导入完成"
            description={`新增 ${result.created} 个，更新 ${result.updated} 个，跳过 ${result.skipped} 个；仅库中存在 ${result.libraryOnly} 个保持原样。`}
          />
          <div className="if-import-result rounded-[var(--srf-radius-control)] border border-[var(--srf-card-border)] p-3">
            <Space wrap>
              <Tag color="green">软件仓库 base path：{result.softwareRepositoryBasePath || '无前缀'}</Tag>
            </Space>
            {createdGroups.length ? (
              <div className="if-import-result-groups mt-2.5 flex flex-wrap items-center gap-2 border-t border-[var(--srf-divider)] pt-2.5 text-[12px] text-[var(--srf-text-secondary)]">
                <span>本次新建分组</span>
                <Space wrap>
                  {createdGroups.map(group => (
                    <Tag key={group} color="green">{group}</Tag>
                  ))}
                </Space>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </Modal>
  )
}

function ImportGroupRow({
  item,
  selected,
  onToggle,
}: {
  item: ImportItem
  selected: boolean
  onToggle: (checked: boolean) => void
}) {
  const selectable = isActionable(item)
  const tone = CHANGE_TONES[item.changeType]
  const stateClass = selectable
    ? selected
      ? 'is-selected cursor-pointer bg-[var(--srf-accent-soft)]'
      : 'cursor-pointer hover:bg-[var(--srf-hover)]'
    : 'cursor-default opacity-[0.72]'

  return (
    <label className={`if-import-row grid min-h-10 grid-cols-[18px_minmax(0,1.1fr)_minmax(0,1.4fr)_76px] items-center gap-2.5 border-b border-[var(--app-list-row-border)] px-3 py-1.5 max-[760.01px]:grid-cols-[18px_minmax(0,1fr)_76px] ${stateClass}`}>
      <Checkbox
        checked={selectable && selected}
        disabled={!selectable}
        onChange={event => onToggle(event.target.checked)}
        aria-label={`选择 ${item.name}`}
      />
      <span className="if-import-row-main flex min-w-0 items-center gap-2">
        <MethodBadge method={item.method} />
        <span
          className="if-import-row-name min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[12px] font-semibold text-[var(--srf-text)]"
          title={item.name}
        >
          {item.name}
        </span>
      </span>
      <code
        className="if-import-row-path overflow-hidden text-ellipsis whitespace-nowrap text-[11px] text-[var(--srf-text-secondary)] max-[760.01px]:hidden"
        title={item.path}
      >
        {item.path}
      </code>
      <span className={`if-import-row-change inline-flex items-center gap-1.5 justify-self-start text-[11px] font-medium ${tone.text}`}>
        <span className={`h-1.5 w-1.5 flex-none rounded-full ${tone.dot}`} aria-hidden="true" />
        {tone.label}
      </span>
    </label>
  )
}

function isActionable(item: ImportItem) {
  return item.changeType === 'new' || item.changeType === 'modified'
}

function targetGroupLabel(item: ImportItem) {
  return groupLabel(
    item.changeType === 'new' ? firstTag(item.tags) : firstTag(item.existingTags),
  )
}

function isNewGroup(group: string, libraryGroups: Set<string>) {
  return group !== UNTAGGED_GROUP && !libraryGroups.has(group)
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  return getErrorMessage(error)
}
