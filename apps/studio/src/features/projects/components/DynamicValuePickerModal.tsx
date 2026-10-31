import type { ApiEnvironmentVar } from '@/services/api'
import { CheckOutlined, CodeSandboxOutlined, FunctionOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, Input, Modal } from 'antd'
import { useEffect, useMemo, useState } from 'react'

export type DynamicValueBuiltin = {
  token: string
  label: string
  description: string
  example?: string
}

type PickerMode = 'environment' | 'builtin'

type Props = {
  open: boolean
  /** 当前 UI 环境变量；没有选择环境时传空数组并设置 hasEnvironment=false。 */
  environmentVars: ApiEnvironmentVar[]
  hasEnvironment: boolean
  environmentLoading?: boolean
  builtinFunctions: DynamicValueBuiltin[]
  /** 环境变量插入的最终 token，默认 {{name}}；XPath 定位需要 {{name|xpath}}。 */
  formatVariableToken?: (name: string) => string
  /** 插入目标字段的中文名，显示在弹窗副标题里。 */
  targetLabel?: string
  onInsert: (token: string) => void
  onClose: () => void
}

type PickerItem = {
  key: string
  title: string
  description: string
  example: string
  type: string
}

export function DynamicValuePickerModal({
  open,
  environmentVars,
  hasEnvironment,
  environmentLoading = false,
  builtinFunctions,
  formatVariableToken = (name) => `{{${name}}}`,
  targetLabel,
  onInsert,
  onClose,
}: Props) {
  const [mode, setMode] = useState<PickerMode>('environment')
  const [search, setSearch] = useState('')
  const [selectedKey, setSelectedKey] = useState('')

  const items = useMemo<PickerItem[]>(
    () =>
      mode === 'builtin'
        ? builtinFunctions.map((item) => ({
          key: item.token,
          title: item.label,
          description: item.description,
          example: item.example ?? '',
          type: '内置函数',
        }))
        : environmentVars.map((item) => ({
          key: formatVariableToken(item.varKey),
          title: item.varKey,
          description: item.description?.trim() ?? '',
          example: '',
          type: '环境变量',
        })),
    [builtinFunctions, environmentVars, formatVariableToken, mode],
  )

  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    if (!keyword) return items
    return items.filter((item) =>
      `${item.title} ${item.description} ${item.key}`.toLowerCase().includes(keyword),
    )
  }, [items, search])

  // 弹窗每次打开都回到环境变量页；切换来源时选中第一条，避免保留另一来源的 key。
  useEffect(() => {
    if (!open) return
    setMode('environment')
    setSearch('')
    setSelectedKey(environmentVars[0] ? formatVariableToken(environmentVars[0].varKey) : '')
  }, [open])  // eslint-disable-line react-hooks/exhaustive-deps

  const selectedItem = filteredItems.find((item) => item.key === selectedKey)
  // 变量异步到达或搜索把当前选中项过滤掉时，回落到列表第一条，避免预览为空。
  const activeKey = selectedItem
    ? selectedKey
    : filteredItems[0]?.key ?? ''

  function selectMode(nextMode: PickerMode) {
    setMode(nextMode)
    setSearch('')
    setSelectedKey(
      nextMode === 'builtin'
        ? builtinFunctions[0]?.token ?? ''
        : environmentVars[0]
          ? formatVariableToken(environmentVars[0].varKey)
          : '',
    )
  }

  function handleInsert() {
    if (!activeKey) return
    onInsert(activeKey)
  }

  const emptyText = !hasEnvironment
    ? '请先选择 UI 环境'
    : environmentLoading
      ? '环境变量加载中...'
      : mode === 'builtin'
        ? '没有匹配的内置函数'
        : '没有匹配的环境变量'

  return (
    <Modal
      mask={{ closable: false }}
      open={open}
      title={(
        <div className="api-env-var-picker-heading">
          <div className="api-env-var-picker-heading-title">插入动态值</div>
          <div className="api-env-var-picker-heading-subtitle">
            从环境变量或内置函数中选择一个值，自动插入到当前输入框
            {targetLabel ? `（${targetLabel}）` : ''}
          </div>
        </div>
      )}
      footer={null}
      centered
      width={880}
      destroyOnHidden={false}
      className="api-env-var-picker-modal"
      onCancel={onClose}
    >
      <div className="api-env-var-picker api-env-var-picker-modal-body">
        <div className="api-env-var-picker-workspace">
          <nav className="api-env-var-picker-sources" aria-label="动态值来源">
            <button
              type="button"
              className={`api-env-var-picker-source${mode === 'environment' ? ' active' : ''}`}
              onClick={() => selectMode('environment')}
            >
              <CodeSandboxOutlined />
              <span>环境变量</span>
              <span className="api-env-var-picker-source-count">{environmentVars.length}</span>
            </button>
            <button
              type="button"
              className={`api-env-var-picker-source${mode === 'builtin' ? ' active' : ''}`}
              onClick={() => selectMode('builtin')}
            >
              <FunctionOutlined />
              <span>内置函数</span>
              <span className="api-env-var-picker-source-count">{builtinFunctions.length}</span>
            </button>
          </nav>

          <section className="api-env-var-picker-browser">
            <Input
              allowClear
              prefix={<SearchOutlined />}
              className="api-env-var-picker-search"
              placeholder={mode === 'builtin' ? '搜索函数名或表达式' : '搜索变量名'}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              disabled={mode === 'environment' && !hasEnvironment}
            />
            <div className="api-env-var-picker-list">
              {filteredItems.length === 0 ? (
                <div className="api-env-var-picker-empty">{emptyText}</div>
              ) : (
                filteredItems.map((item) => {
                  const active = item.key === activeKey
                  return (
                    <button
                      key={item.key}
                      type="button"
                      className={`api-env-var-picker-item${active ? ' active' : ''}`}
                      onClick={() => setSelectedKey(item.key)}
                      onDoubleClick={() => onInsert(item.key)}
                    >
                      <span className="api-env-var-picker-item-status" />
                      <span className="api-env-var-picker-item-main">
                        <span className="api-env-var-picker-item-key">{item.title}</span>
                        {item.description ? (
                          <span className="api-env-var-picker-item-desc">{item.description}</span>
                        ) : null}
                        {mode === 'builtin' && item.example ? (
                          <code className="api-env-var-picker-item-example">{item.example}</code>
                        ) : null}
                      </span>
                      <span className="api-env-var-picker-item-type">{item.type}</span>
                      {active ? <CheckOutlined className="api-env-var-picker-item-check" /> : null}
                    </button>
                  )
                })
              )}
            </div>
          </section>

          <aside className="api-env-var-picker-preview">
            <div className="api-env-var-picker-preview-title">插入预览</div>
            <code className="api-env-var-picker-preview-token">
              {selectedItem?.key || '请选择动态值'}
            </code>
            <dl className="api-env-var-picker-preview-meta">
              <div>
                <dt>来源</dt>
                <dd>{mode === 'builtin' ? '内置函数' : '当前环境'}</dd>
              </div>
              <div>
                <dt>{mode === 'builtin' ? '函数名' : '变量名'}</dt>
                <dd>{selectedItem?.title || '-'}</dd>
              </div>
            </dl>
            <p className="api-env-var-picker-preview-description">
              {selectedItem?.description || (mode === 'builtin'
                ? '插入后将在运行时由后端生成对应值。'
                : '将以上内容插入当前输入框后，运行时会自动替换为对应的环境变量值。')}
            </p>
          </aside>
        </div>

        <div className="api-env-var-picker-footer">
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            className="api-env-var-picker-insert-btn"
            disabled={!activeKey}
            onClick={handleInsert}
          >
            插入变量
          </Button>
        </div>
      </div>
    </Modal>
  )
}
