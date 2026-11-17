import {
  DatabaseOutlined,
  DeleteOutlined,
  DownloadOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { Button, Card, Input, Popconfirm, Select, Tag, Tooltip, Upload } from 'antd'
import type { UploadProps } from 'antd'
import type { PerfDataFile } from '../types'
import {
  createPerfDataEntry,
  type PerfCaseFormValues,
  type PerfDataEntryFormValues,
  type PerfDataStrategy,
  type PerfExhaustedPolicy,
} from '../utils/perfCaseForm'

function uniqueDataName(entries: PerfDataEntryFormValues[], filename: string) {
  const base = filename.replace(/\.[^.]+$/, '').replace(/[^A-Za-z0-9_-]/g, '_') || 'data'
  const names = new Set(entries.map(entry => entry.name))
  if (!names.has(base)) return base
  let index = 2
  while (names.has(`${base}_${index}`)) index += 1
  return `${base}_${index}`
}

function DataEntryRow({
  entry,
  index,
  dataFiles,
  disabled,
  referencedFiles,
  onChange,
  onRemove,
}: {
  entry: PerfDataEntryFormValues
  index: number
  dataFiles: PerfDataFile[]
  disabled?: boolean
  referencedFiles: Set<string>
  onChange: (entry: PerfDataEntryFormValues) => void
  onRemove: () => void
}) {
  const hasInlineRows = Boolean(entry.rows && entry.rows.length > 0)
  const sourceOptions = dataFiles.map(file => ({ value: file.filename, label: file.filename }))
  if (entry.source && !sourceOptions.some(option => option.value === entry.source)) {
    sourceOptions.push({ value: entry.source, label: entry.source })
  }
  return <div className="grid gap-2 rounded-lg border border-app-surface-border bg-app-surface p-2.5">
    <div className="flex flex-wrap items-center gap-2">
      <Input
        aria-label={`数据 ${index + 1} 名称`}
        size="small"
        className="w-40"
        placeholder="数据名"
        value={entry.name}
        disabled={disabled}
        onChange={event => onChange({ ...entry, name: event.target.value })}
      />
      {hasInlineRows
        ? <Tag color="purple">内嵌数据 · {entry.rows?.length ?? 0} 行</Tag>
        : <Select
          aria-label={`数据 ${index + 1} 来源文件`}
          size="small"
          className="min-w-52"
          placeholder="选择数据文件"
          value={entry.source || undefined}
          disabled={disabled}
          options={sourceOptions}
          onChange={source => onChange({ ...entry, source })}
        />}
      <Select
        aria-label={`数据 ${index + 1} 取值策略`}
        size="small"
        className="w-36"
        value={entry.strategy}
        disabled={disabled}
        options={[
          { value: 'unique_per_iteration', label: '每次迭代唯一' },
          { value: 'per_vu', label: '每个 VU 独立' },
          { value: 'random', label: '随机取值' },
          { value: 'cycle', label: '循环取值' },
        ] satisfies { value: PerfDataStrategy; label: string }[]}
        onChange={strategy => onChange({ ...entry, strategy })}
      />
      <Select
        aria-label={`数据 ${index + 1} 用尽策略`}
        size="small"
        className="w-32"
        value={entry.onExhausted}
        disabled={disabled}
        options={[
          { value: 'cycle', label: '循环' },
          { value: 'fail', label: '失败' },
        ] satisfies { value: PerfExhaustedPolicy; label: string }[]}
        onChange={onExhausted => onChange({ ...entry, onExhausted })}
      />
      {entry.source && referencedFiles.has(entry.source) ? <Tag color="green">已上传</Tag> : null}
      <Tooltip title="删除数据引用">
        <Button
          type="text"
          size="small"
          danger
          aria-label={`删除数据引用 ${index + 1}`}
          icon={<DeleteOutlined />}
          disabled={disabled}
          onClick={onRemove}
        />
      </Tooltip>
    </div>
  </div>
}

export function PerfCaseDataSection({
  value,
  dataFiles,
  disabled,
  uploading,
  uploadProps,
  removingFileId,
  onChange,
  onDownload,
  onRemoveFile,
}: {
  value: PerfCaseFormValues
  dataFiles: PerfDataFile[]
  disabled?: boolean
  uploading: boolean
  uploadProps: UploadProps
  removingFileId?: string
  onChange: (next: PerfCaseFormValues) => void
  onDownload: (file: PerfDataFile) => void
  onRemoveFile: (file: PerfDataFile) => void
}) {
  const referencedFiles = new Set(value.data.map(entry => entry.source).filter(Boolean))

  function updateEntry(index: number, entry: PerfDataEntryFormValues) {
    onChange({ ...value, data: value.data.map((item, itemIndex) => itemIndex === index ? entry : item) })
  }

  function addReference(file: PerfDataFile) {
    onChange({
      ...value,
      data: [...value.data, createPerfDataEntry({
        name: uniqueDataName(value.data, file.filename),
        source: file.filename,
      })],
    })
  }

  return <Card
    size="small"
    title={<span className="inline-flex items-center gap-2"><DatabaseOutlined />数据文件</span>}
    extra={<Upload {...uploadProps}><Button size="small" icon={<UploadOutlined />} loading={uploading} disabled={disabled}>上传文件</Button></Upload>}
  >
    <div className="grid gap-4">
      <div className="grid gap-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold text-app-surface-text">数据引用</span>
          <Button size="small" disabled={disabled} onClick={() => onChange({ ...value, data: [...value.data, createPerfDataEntry()] })}>添加引用</Button>
        </div>
        {value.data.length === 0
          ? <div className="rounded-lg border border-dashed border-app-surface-border px-3 py-4 text-center text-xs text-app-surface-text-muted">还没有数据引用。先上传 CSV / JSON，再为它添加引用。</div>
          : value.data.map((entry, index) => <DataEntryRow
            key={entry.id}
            entry={entry}
            index={index}
            dataFiles={dataFiles}
            disabled={disabled}
            referencedFiles={referencedFiles}
            onChange={next => updateEntry(index, next)}
            onRemove={() => onChange({ ...value, data: value.data.filter((_, itemIndex) => itemIndex !== index) })}
          />)}
      </div>

      <div className="grid gap-2">
        <span className="text-xs font-semibold text-app-surface-text">已上传文件</span>
        {dataFiles.length === 0
          ? <div className="text-xs text-app-surface-text-muted">暂无数据文件，仅支持 CSV / JSON。</div>
          : dataFiles.map(file => {
            const referenced = referencedFiles.has(file.filename)
            return <div key={file.fileId} className="flex flex-wrap items-center gap-2 rounded-lg border border-app-surface-border px-2.5 py-2">
              <Tag color={file.filename.endsWith('.json') ? 'gold' : 'green'}>{file.filename.endsWith('.json') ? 'JSON' : 'CSV'}</Tag>
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs text-app-surface-text" title={file.filename}>{file.filename}</div>
                <div className="text-[11px] text-app-surface-text-muted">{formatFileSize(file.size)}</div>
              </div>
              {referenced ? <Tag color="green">已引用</Tag> : <Button size="small" disabled={disabled} onClick={() => addReference(file)}>添加引用</Button>}
              <Tooltip title="下载">
                <Button type="text" size="small" icon={<DownloadOutlined />} aria-label={`下载 ${file.filename}`} onClick={() => onDownload(file)} />
              </Tooltip>
              <Popconfirm
                title="移除这个数据文件？"
                description="仍有数据引用时不能移除；请先删除对应引用。"
                okText="移除"
                cancelText="取消"
                disabled={disabled}
                onConfirm={() => onRemoveFile(file)}
              >
                <Tooltip title="移除数据文件">
                  <Button
                    type="text"
                    size="small"
                    danger
                    disabled={disabled}
                    loading={removingFileId === file.fileId}
                    icon={<DeleteOutlined />}
                    aria-label={`移除 ${file.filename}`}
                  />
                </Tooltip>
              </Popconfirm>
            </div>
          })}
        <div className="text-[11px] text-app-surface-text-muted">仅支持 CSV / JSON；上传或移除会同时保存当前用例。单个用例最多 20 个文件、总计 100 MB。</div>
      </div>
    </div>
  </Card>
}

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
