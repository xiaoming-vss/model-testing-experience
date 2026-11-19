import { CheckOutlined, CodeSandboxOutlined, FunctionOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, Input, Modal } from 'antd'
import { builtinTemplateFunctions, type EnvVarPickerMode } from '../config/collectionConfig'
import type { useApiEnvVarPicker } from '../hooks/useApiEnvVarPicker'

export function ApiEnvVarPickerModal({ picker }: { picker: ReturnType<typeof useApiEnvVarPicker> }) {
  const {
    envVarPickerOpenKey,
    envVarPickerMode,
    setEnvVarPickerMode,
    envVarPickerSearch,
    setEnvVarPickerSearch,
    envVarPickerSelectedKey,
    setEnvVarPickerSelectedKey,
    envVarPickerInsertHandler,
    filteredEnvironmentVars,
    filteredBuiltinTemplateFunctions,
    environmentVars,
    environmentVarsQuery,
    resolvedEnvironmentId,
    closeEnvVarPicker,
    formatEnvironmentToken,
  } = picker
  const hasEnvironment = Boolean(resolvedEnvironmentId)
  const isBuiltinMode = envVarPickerMode === 'builtin'
  const pickerItems = isBuiltinMode
    ? filteredBuiltinTemplateFunctions.map((item) => ({
      key: item.token,
      title: item.label,
      description: item.description,
      type: '内置函数',
      example: item.example,
    }))
    : filteredEnvironmentVars.map((item) => ({
      key: formatEnvironmentToken(item.varKey),
      title: item.varKey,
      description: item.description?.trim() || '',
      type: '环境变量',
      example: '',
    }))
  const handleInsert = envVarPickerOpenKey ? envVarPickerInsertHandler : undefined
  const selectedItem = pickerItems.find((item) => item.key === envVarPickerSelectedKey)
  const selectPickerMode = (nextMode: EnvVarPickerMode) => {
    setEnvVarPickerMode(nextMode)
    setEnvVarPickerSearch('')
    setEnvVarPickerSelectedKey(
      nextMode === 'builtin'
        ? builtinTemplateFunctions[0]?.token ?? ''
        : formatEnvironmentToken(environmentVars[0]?.varKey ?? ''),
    )
  }

  return (
    <Modal
      mask={{ closable: false }}
      open={Boolean(envVarPickerOpenKey)}
      title={(
        <div className="api-env-var-picker-heading">
          <div className="api-env-var-picker-heading-title">插入动态值</div>
          <div className="api-env-var-picker-heading-subtitle">从环境变量或内置函数中选择一个值，自动插入到当前输入框</div>
        </div>
      )}
      footer={null}
      centered
      width={880}
      destroyOnHidden
      className="api-env-var-picker-modal"
      onCancel={closeEnvVarPicker}
    >
      <div className="api-env-var-picker api-env-var-picker-modal-body">
        <div className="api-env-var-picker-workspace">
          <nav className="api-env-var-picker-sources" aria-label="动态值来源">
            <button
              type="button"
              className={`api-env-var-picker-source${envVarPickerMode === 'environment' ? ' active' : ''}`}
              onClick={() => selectPickerMode('environment')}
            >
              <CodeSandboxOutlined />
              <span>环境变量</span>
              <span className="api-env-var-picker-source-count">{environmentVars.length}</span>
            </button>
            <button
              type="button"
              className={`api-env-var-picker-source${envVarPickerMode === 'builtin' ? ' active' : ''}`}
              onClick={() => selectPickerMode('builtin')}
            >
              <FunctionOutlined />
              <span>内置函数</span>
              <span className="api-env-var-picker-source-count">{builtinTemplateFunctions.length}</span>
            </button>
          </nav>

          <section className="api-env-var-picker-browser">
            <Input
              allowClear
              prefix={<SearchOutlined />}
              className="api-env-var-picker-search"
              placeholder={isBuiltinMode ? '搜索函数名或表达式' : '搜索变量名'}
              value={envVarPickerSearch}
              onChange={(event) => setEnvVarPickerSearch(event.target.value)}
              disabled={!isBuiltinMode && !hasEnvironment}
            />
            <div className="api-env-var-picker-list">
              {!isBuiltinMode && !hasEnvironment ? (
                <div className="api-env-var-picker-empty">请先选择环境</div>
              ) : !isBuiltinMode && environmentVarsQuery.isLoading ? (
                <div className="api-env-var-picker-empty">环境变量加载中...</div>
              ) : pickerItems.length === 0 ? (
                <div className="api-env-var-picker-empty">{isBuiltinMode ? '没有匹配的内置函数' : '没有匹配的环境变量'}</div>
              ) : (
                pickerItems.map((item) => {
                  const active = item.key === envVarPickerSelectedKey
                  return (
                    <button
                      key={item.key}
                      type="button"
                      className={`api-env-var-picker-item${active ? ' active' : ''}`}
                      onClick={() => setEnvVarPickerSelectedKey(item.key)}
                      onDoubleClick={() => handleInsert?.(item.key)}
                    >
                      <span className="api-env-var-picker-item-status" />
                      <span className="api-env-var-picker-item-main">
                        <span className="api-env-var-picker-item-key">{item.title}</span>
                        {item.description ? <span className="api-env-var-picker-item-desc">{item.description}</span> : null}
                        {isBuiltinMode && item.example ? <code className="api-env-var-picker-item-example">{item.example}</code> : null}
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
            <code className="api-env-var-picker-preview-token">{selectedItem?.key || '请选择动态值'}</code>
            <dl className="api-env-var-picker-preview-meta">
              <div>
                <dt>来源</dt>
                <dd>{isBuiltinMode ? '内置函数' : '当前环境'}</dd>
              </div>
              <div>
                <dt>{isBuiltinMode ? '函数名' : '变量名'}</dt>
                <dd>{selectedItem?.title || '-'}</dd>
              </div>
            </dl>
            <p className="api-env-var-picker-preview-description">
              {selectedItem?.description || (isBuiltinMode
                ? '插入后将在运行时由后端生成对应值。'
                : '将以上内容插入当前输入框后，运行时会自动替换为对应的环境变量值。')}
            </p>
          </aside>
        </div>

        <div className="api-env-var-picker-footer">
          <Button onClick={closeEnvVarPicker}>取消</Button>
          <Button
            type="primary"
            className="api-env-var-picker-insert-btn"
            disabled={!envVarPickerSelectedKey || !handleInsert}
            onClick={() => handleInsert?.(envVarPickerSelectedKey)}
          >
            插入变量
          </Button>
        </div>
      </div>
    </Modal>
  )
}
