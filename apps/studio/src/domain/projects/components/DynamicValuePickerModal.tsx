import type { ApiEnvironmentVar } from '@/services/api'
import { CheckOutlined, CodeSandboxOutlined, FunctionOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, Input, Modal } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { cx } from '@/shared/utils/cx'
import environmentStyles from '../styles/environment-drawer.module.css'

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
        <div className="api-env-var-picker-heading pr-9">
          <div className="text-[18px] font-bold leading-[26px] text-[var(--tp-text)]">插入动态值</div>
          <div className="mt-[3px] text-xs font-normal leading-[18px] text-[var(--tp-text-secondary)]">
            从环境变量或内置函数中选择一个值，自动插入到当前输入框
            {targetLabel ? `（${targetLabel}）` : ''}
          </div>
        </div>
      )}
      footer={null}
      centered
      width={880}
      destroyOnHidden={false}
      className={cx('api-env-var-picker-modal', environmentStyles.root)}
      onCancel={onClose}
    >
      <div className="api-env-var-picker api-env-var-picker-modal-body w-full bg-transparent p-0">
        <div className="api-env-var-picker-workspace min-h-[330px] grid grid-cols-[168px_minmax(320px,1fr)_300px] max-narrow:grid-cols-[132px_minmax(0,1fr)]">
          <nav className="api-env-var-picker-sources flex flex-col gap-1.5 border-r border-[var(--app-frame-card-border)] bg-[var(--app-picker-header-bg)] p-3 max-narrow:p-2" aria-label="动态值来源">
            <button
              type="button"
              className={`api-env-var-picker-source grid min-h-[42px] w-full cursor-pointer grid-cols-[18px_minmax(0,1fr)_auto] items-center gap-2 rounded-[8px] border-0 px-2.5 py-0 text-left text-[13px] leading-[20px] transition-colors max-narrow:grid-cols-[16px_minmax(0,1fr)_auto] max-narrow:gap-1.5 max-narrow:px-1.5 ${mode === 'environment' ? 'bg-[var(--app-picker-option-selected)] text-[var(--app-surface-accent)]' : 'bg-transparent text-[var(--tp-text-secondary)] hover:bg-[var(--app-picker-option-hover)] hover:text-[var(--tp-text)]'}`}
              onClick={() => selectMode('environment')}
            >
              <CodeSandboxOutlined />
              <span className="overflow-hidden text-ellipsis whitespace-nowrap">环境变量</span>
              <span className="api-env-var-picker-source-count inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--app-picker-option-disabled)] px-1.5 text-[10px] leading-[20px] text-[var(--tp-text-muted)] max-narrow:hidden">{environmentVars.length}</span>
            </button>
            <button
              type="button"
              className={`api-env-var-picker-source grid min-h-[42px] w-full cursor-pointer grid-cols-[18px_minmax(0,1fr)_auto] items-center gap-2 rounded-[8px] border-0 px-2.5 py-0 text-left text-[13px] leading-[20px] transition-colors max-narrow:grid-cols-[16px_minmax(0,1fr)_auto] max-narrow:gap-1.5 max-narrow:px-1.5 ${mode === 'builtin' ? 'bg-[var(--app-picker-option-selected)] text-[var(--app-surface-accent)]' : 'bg-transparent text-[var(--tp-text-secondary)] hover:bg-[var(--app-picker-option-hover)] hover:text-[var(--tp-text)]'}`}
              onClick={() => selectMode('builtin')}
            >
              <FunctionOutlined />
              <span className="overflow-hidden text-ellipsis whitespace-nowrap">内置函数</span>
              <span className="api-env-var-picker-source-count inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--app-picker-option-disabled)] px-1.5 text-[10px] leading-[20px] text-[var(--tp-text-muted)] max-narrow:hidden">{builtinFunctions.length}</span>
            </button>
          </nav>

          <section className="api-env-var-picker-browser min-w-0 border-r border-[var(--app-frame-card-border)] px-4 pt-3 pb-4 max-narrow:border-r-0">
            <Input
              allowClear
              prefix={<SearchOutlined />}
              className="api-env-var-picker-search mb-2.5 h-[38px] rounded-[8px] bg-transparent"
              placeholder={mode === 'builtin' ? '搜索函数名或表达式' : '搜索变量名'}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              disabled={mode === 'environment' && !hasEnvironment}
            />
            <div className="api-env-var-picker-list flex min-h-[266px] max-h-[266px] flex-col overflow-auto border-0 bg-transparent p-0">
              {filteredItems.length === 0 ? (
                <div className="api-env-var-picker-empty grid min-h-full place-items-center text-center text-xs leading-[18px] text-[var(--tp-text-secondary)]">{emptyText}</div>
              ) : (
                filteredItems.map((item) => {
                  const active = item.key === activeKey
                  return (
                    <button
                      key={item.key}
                      type="button"
                      className={`api-env-var-picker-item grid min-h-[50px] w-full flex-none cursor-pointer grid-cols-[8px_minmax(0,1fr)_auto_16px] items-center gap-2.5 rounded-none border-0 border-b border-[var(--app-picker-row-border)] bg-transparent px-2.5 py-2 text-left text-[var(--tp-text)] transition-[background-color,box-shadow] hover:bg-[var(--app-picker-row-hover)] ${active ? 'rounded-[8px] border-b-[var(--app-picker-row-selected-border)] bg-[var(--app-picker-row-selected)] shadow-[inset_0_0_0_1px_var(--app-picker-row-selected-ring)]' : ''}`}
                      onClick={() => setSelectedKey(item.key)}
                      onDoubleClick={() => onInsert(item.key)}
                    >
                      <span className="api-env-var-picker-item-status h-1.5 w-1.5 rounded-full bg-[var(--app-picker-status)] shadow-[0_0_0_3px_var(--app-picker-status-ring)]" />
                      <span className="api-env-var-picker-item-main flex min-w-0 flex-auto flex-col gap-0.5">
                        <span className="api-env-var-picker-item-key min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-semibold leading-[20px] text-[var(--tp-text)]">{item.title}</span>
                        {item.description ? (
                          <span className="api-env-var-picker-item-desc w-fit max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-[11px] leading-[16px] text-[var(--tp-text-secondary)]">{item.description}</span>
                        ) : null}
                        {mode === 'builtin' && item.example ? (
                          <code className="api-env-var-picker-item-example w-fit max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-[11px] leading-[16px] text-[var(--app-accent,var(--app-picker-accent-fallback))]">{item.example}</code>
                        ) : null}
                      </span>
                      <span className="api-env-var-picker-item-type whitespace-nowrap text-[11px] leading-[18px] text-[var(--tp-text-secondary)]">{item.type}</span>
                      {active ? <CheckOutlined className="api-env-var-picker-item-check text-[13px] text-[var(--app-picker-action)]" /> : null}
                    </button>
                  )
                })
              )}
            </div>
          </section>

          <aside className="api-env-var-picker-preview min-w-0 px-[18px] py-5 max-narrow:hidden">
            <div className="api-env-var-picker-preview-title mb-3 text-[13px] font-bold leading-[20px] text-[var(--tp-text)]">插入预览</div>
            <code className="api-env-var-picker-preview-token flex min-h-[54px] items-center rounded-[10px] border border-[var(--app-frame-card-border)] bg-[var(--app-picker-header-bg)] px-3.5 py-3 font-mono text-[16px] leading-[24px] text-[var(--app-surface-accent)] break-words [overflow-wrap:anywhere]">
              {selectedItem?.key || '请选择动态值'}
            </code>
            <dl className="api-env-var-picker-preview-meta mt-5 mb-0 grid gap-2.5">
              <div className="grid grid-cols-[52px_minmax(0,1fr)] gap-2.5 text-xs leading-[18px]">
                <dt className="text-[var(--tp-text-secondary)]">来源</dt>
                <dd className="m-0 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[var(--tp-text)]">{mode === 'builtin' ? '内置函数' : '当前环境'}</dd>
              </div>
              <div className="grid grid-cols-[52px_minmax(0,1fr)] gap-2.5 text-xs leading-[18px]">
                <dt className="text-[var(--tp-text-secondary)]">{mode === 'builtin' ? '函数名' : '变量名'}</dt>
                <dd className="m-0 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[var(--tp-text)]">{selectedItem?.title || '-'}</dd>
              </div>
            </dl>
            <p className="api-env-var-picker-preview-description mt-6 mb-0 text-[11px] leading-[18px] text-[var(--tp-text-secondary)]">
              {selectedItem?.description || (mode === 'builtin'
                ? '插入后将在运行时由后端生成对应值。'
                : '将以上内容插入当前输入框后，运行时会自动替换为对应的环境变量值。')}
            </p>
          </aside>
        </div>

        <div className="api-env-var-picker-footer flex min-h-[62px] items-center justify-end gap-2.5 border-t border-[var(--app-frame-card-border)] px-[18px] py-3">
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
