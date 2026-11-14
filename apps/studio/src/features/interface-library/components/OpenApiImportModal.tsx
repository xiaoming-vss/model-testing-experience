import { InboxOutlined, WarningOutlined } from '@ant-design/icons'
import { Alert, Button, Checkbox, Empty, Modal, Segmented, Select, Space, Steps, Tag, Upload } from 'antd'
import type { UploadFile } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { ApiError } from '@/services/api'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { ApiApp, ImportCommitResult, ImportItem, ImportPreview } from '../types'
import { parseJsonText } from '../utils/interfaceForm'

type Props = {
  open: boolean
  apps: ApiApp[]
  defaultAppId?: string
  onClose: () => void
  onImported: () => void
}

type ImportMode = 'upload' | 'editor'

const MAX_IMPORT_BYTES = 8 * 1024 * 1024
const INLINE_FILE_NAME = 'inline-openapi.json'

const CHANGE_LABELS: Record<ImportItem['changeType'], string> = {
  new: '新增',
  modified: '修改',
  unchanged: '未变化',
  library_only: '仅库中存在',
}

const CHANGE_COLORS: Record<ImportItem['changeType'], string> = {
  new: 'green',
  modified: 'blue',
  unchanged: 'default',
  library_only: 'orange',
}

export function OpenApiImportModal({
  open,
  apps,
  defaultAppId = '',
  onClose,
  onImported,
}: Props) {
  const [step, setStep] = useState(0)
  const [mode, setMode] = useState<ImportMode>('upload')
  const [appId, setAppId] = useState(defaultAppId)
  const [file, setFile] = useState<File | null>(null)
  const [jsonText, setJsonText] = useState('')
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const [applyBasePath, setApplyBasePath] = useState(false)
  const [result, setResult] = useState<ImportCommitResult | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setStep(0)
    setMode('upload')
    setAppId(defaultAppId || apps.find(app => app.enabled)?.appId || apps[0]?.appId || '')
    setFile(null)
    setJsonText('')
    setPreview(null)
    setSelectedKeys(new Set())
    setApplyBasePath(false)
    setResult(null)
    setSubmitting(false)
    setPreviewing(false)
    setError('')
  }, [apps, defaultAppId, open])

  const selectedApp = apps.find(app => app.appId === appId)
  const actionableItems = useMemo(
    () => preview?.items.filter(item => item.changeType === 'new' || item.changeType === 'modified') ?? [],
    [preview],
  )
  const selectedItems = actionableItems.filter(item => selectedKeys.has(item.key))
  const basePathBlocked = Boolean(preview?.basePathChange && !preview.basePathChange.canApply)
  const inlineJsonState = parseJsonText(jsonText)
  const sourceLabel = preview?.source.name || (mode === 'editor' ? '直接输入 JSON' : file?.name) || 'OpenAPI 文档'

  function inlineJsonError() {
    if (!jsonText.trim()) return '请粘贴 OpenAPI JSON 内容'
    if (new Blob([jsonText]).size > MAX_IMPORT_BYTES) return 'JSON 内容不能超过 8 MB'
    if (!inlineJsonState.valid) return `JSON 格式错误：${inlineJsonState.error}`
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
    if (!appId) {
      message.error('请选择接口应用')
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
      const data = await interfaceLibraryApi.previewOpenApiImport(appId, source)
      setPreview(data)
      setSelectedKeys(
        new Set(
          data.items
            .filter(item => item.changeType === 'new' || item.changeType === 'modified')
            .map(item => item.key),
        ),
      )
      setApplyBasePath(false)
      setStep(1)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setPreviewing(false)
    }
  }

  async function commit() {
    if (!preview || !appId) return
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
      const data = await interfaceLibraryApi.commitOpenApiImport(appId, {
        file: source,
        sourceDigest: preview.source.digest,
        selectedKeys: selectedItems.map(item => item.key),
        expectedItems,
        applyBasePath: basePathBlocked ? false : applyBasePath,
        expectedAppVersion:
          applyBasePath && !basePathBlocked ? selectedApp?.version : undefined,
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

  function close() {
    if (submitting || previewing) return
    onClose()
  }

  return (
    <Modal
      open={open}
      title="导入 OpenAPI / Swagger"
      width={900}
      onCancel={close}
      mask={{ closable: !submitting && !previewing }}
      footer={null}
      destroyOnHidden
    >
      <Steps
        current={step}
        size="small"
        className="if-import-steps"
        items={[{ title: '选择文档' }, { title: '预览差异' }, { title: '导入结果' }]}
      />
      {error ? <Alert type="error" showIcon title={error} className="if-import-error" /> : null}

      {step === 0 ? (
        <div className="if-import-step">
          <label className="if-import-field">
            <span>接口应用</span>
            <Select
              aria-label="选择导入的接口应用"
              value={appId || undefined}
              placeholder="请选择接口应用"
              options={apps.map(app => ({
                label: `${app.name}${app.enabled ? '' : '（已停用）'}`,
                value: app.appId,
              }))}
              onChange={setAppId}
            />
          </label>
          <Segmented
            className="if-import-mode"
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
            <div className="if-import-editor">
              <div className="if-editor-block-head">
                <span>OpenAPI JSON</span>
                <span className={`if-json-state${inlineJsonState.valid ? ' is-valid' : ' is-invalid'}`}>
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
              <div className="if-import-note">
                直接粘贴 OpenAPI JSON 文档，提交时按内联 JSON 文件解析；文档最大 8 MB，原始输入不会单独保存。
              </div>
            </div>
          )}
          <div className="if-import-actions">
            <Button onClick={close}>取消</Button>
            <Button type="primary" loading={previewing} onClick={() => void loadPreview()}>
              预览差异
            </Button>
          </div>
        </div>
      ) : null}

      {step === 1 && preview ? (
        <div className="if-import-step">
          <div className="if-import-summary">
            <span className="if-import-source">
              {sourceLabel}
              {preview.source.version ? ` · ${preview.source.version}` : ''}
            </span>
            {(['new', 'modified', 'unchanged', 'library_only'] as const).map(type => (
              <Tag key={type} color={CHANGE_COLORS[type]}>
                {CHANGE_LABELS[type]} {preview.summary[type === 'library_only' ? 'libraryOnly' : type]}
              </Tag>
            ))}
          </div>
          {preview.basePathChange ? (
            <Alert
              type={preview.basePathChange.canApply ? 'warning' : 'error'}
              showIcon
              title={`文档 base path 为 ${preview.basePathChange.document || '空'}，应用当前为 ${preview.basePathChange.current || '空'}`}
              description={
                preview.basePathChange.canApply ? (
                  <Checkbox
                    checked={applyBasePath}
                    onChange={event => setApplyBasePath(event.target.checked)}
                  >
                    同时更新应用 base path
                  </Checkbox>
                ) : (
                  '普通成员不能修改应用 base path，请联系项目所有者更新应用后再导入。'
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
                <ul className="if-import-warnings">
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
          <div className="if-import-list">
            {preview.items.map(item => {
              const selectable = item.changeType === 'new' || item.changeType === 'modified'
              return (
                <label
                  key={item.key}
                  className={`if-import-item${selectable ? '' : ' is-disabled'}${selectedKeys.has(item.key) ? ' is-selected' : ''}`}
                >
                  <Checkbox
                    checked={selectedKeys.has(item.key)}
                    disabled={!selectable}
                    onChange={event => toggleKey(item.key, event.target.checked)}
                  />
                  <Tag className={`if-method if-method-${item.method.toLowerCase()}`}>{item.method}</Tag>
                  <span className="if-import-item-name">{item.name}</span>
                  <code>{item.path}</code>
                  <Tag color={CHANGE_COLORS[item.changeType]}>{CHANGE_LABELS[item.changeType]}</Tag>
                  {item.changedFields.length ? (
                    <span className="if-import-changed">{item.changedFields.join(' / ')}</span>
                  ) : null}
                </label>
              )
            })}
            {preview.items.length === 0 ? <Empty description="文档中没有接口" /> : null}
          </div>
          <div className="if-import-note">
            文档字段会覆盖同名接口；启用状态和关联需求保留。文档中已移除的接口保持原样，不自动停用或删除。
          </div>
          <div className="if-import-actions">
            <Button onClick={() => setStep(0)} disabled={submitting}>上一步</Button>
            <Button
              type="primary"
              loading={submitting}
              disabled={!selectedItems.length || basePathBlocked}
              onClick={() => void commit()}
            >
              导入选中 {selectedItems.length} 项
            </Button>
          </div>
        </div>
      ) : null}

      {step === 2 && result ? (
        <div className="if-import-step">
          <Alert
            type="success"
            showIcon
            title="导入完成"
            description={`新增 ${result.created} 个，更新 ${result.updated} 个，跳过 ${result.skipped} 个；仅库中存在 ${result.libraryOnly} 个保持原样。`}
          />
          <div className="if-import-result">
            <Space wrap>
              <Tag color="green">应用 base path：{result.appBasePath || '无前缀'}</Tag>
            </Space>
          </div>
          <div className="if-import-actions">
            <Button type="primary" onClick={onImported}>查看接口库</Button>
          </div>
        </div>
      ) : null}
    </Modal>
  )
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  return getErrorMessage(error)
}
