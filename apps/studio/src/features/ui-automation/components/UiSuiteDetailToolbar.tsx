import { ActionButton } from '@/shared/components/ActionButton'
import {
  ArrowLeftOutlined,
  BugOutlined,
  EditOutlined,
  HistoryOutlined,
  SaveOutlined,
  SlidersOutlined,
  UploadOutlined
} from '@ant-design/icons'
import { Button, Form, Input, Select, Switch, Tooltip } from 'antd'

import type { UiSuiteReadiness } from '../utils/detailRunView'

/*
 * UI测试集详情页顶栏：返回 + 面包屑 + 当前用例信息 + 测试集/用例动作。
 *
 * 测试集流程和步骤流程共用这一行：进入用例后，面包屑追加 CASE 与步骤流程，
 * 用例名、启用状态和步骤数就地展示；调试运行与保存也只在这里出现。
 * 运行记录、导入用例与运行测试集都是测试集级动作，只在测试集流程出现；
 * 步骤流程只调试当前用例。
 * 窄屏下环境/运行记录/导入收成图标，保留 title 与 aria-label。
 */

type Props = {
  suiteName: string
  requirementName: string
  sprintName: string
  readiness: UiSuiteReadiness
  /** 最近一次运行距今多久，没有运行记录时为空。 */
  lastRunText: string
  runHistoryCount: number
  runningSuite: boolean
  debugging: boolean
  saving: boolean
  canRun: boolean
  canDebug: boolean
  showDebug?: boolean
  /** 测试集级动作（运行记录 / 导入用例 / 运行测试集）只在测试集流程出现。 */
  showSuiteActions?: boolean
  canSave: boolean
  importDisabled?: boolean
  environmentId?: string
  environmentOptions: Array<{ label: string; value: string }>
  environmentsLoading?: boolean
  /** 当前是否处于某个用例的步骤流程。 */
  showCase: boolean
  caseEditable: boolean
  caseSerial?: string
  caseName?: string
  caseStepCount: number
  caseEnabled: boolean
  /** 当前用例有未保存修改时，保存按钮高亮并显示未保存标签。 */
  saveDirty: boolean
  onEnvironmentChange: (value: string) => void
  onOpenEnvironments: () => void
  onBack: () => void
  onOpenSuiteFlow: () => void
  onOpenRunHistory: () => void
  onDebugRun: () => void
  onRunSuite: () => void
  onSave: () => void
  onImport: () => void
}

export function UiSuiteDetailToolbar({
  suiteName,
  requirementName,
  sprintName,
  readiness,
  lastRunText,
  runHistoryCount,
  runningSuite,
  debugging,
  saving,
  canRun,
  canDebug,
  showDebug = true,
  showSuiteActions = true,
  canSave,
  importDisabled = false,
  environmentId,
  environmentOptions,
  environmentsLoading,
  showCase,
  caseEditable,
  caseSerial,
  caseName,
  caseStepCount,
  caseEnabled,
  saveDirty,
  onEnvironmentChange,
  onOpenEnvironments,
  onBack,
  onOpenSuiteFlow,
  onOpenRunHistory,
  onDebugRun,
  onRunSuite,
  onSave,
  onImport,
}: Props) {
  const contextParts = [suiteName, requirementName, sprintName].filter((item) => item && item !== '-')
  const contextTitle = contextParts.join(' / ') || '测试集信息加载中'
  // 面包屑只露出测试集与需求；迭代放进 title，避免窄屏把整段层级挤断。
  const contextRest = requirementName && requirementName !== '-' ? requirementName : ''
  const historyLabel = `运行记录${runHistoryCount > 0 ? ` (${runHistoryCount})` : ''}`

  return (
    <div className={`ui-wb-toolbar${saveDirty ? ' has-unsaved-case' : ''}`}>
      <h1 className="ui-wb-visually-hidden">UI测试集详情</h1>
      <div className="ui-wb-toolbar-main">
        <Button
          type="text"
          className="ui-wb-toolbar-back"
          icon={<ArrowLeftOutlined />}
          aria-label="返回UI测试集列表"
          title="返回UI测试集列表"
          onClick={onBack}
        />
        <nav className="ui-wb-crumbs" aria-label="面包屑">
          <button type="button" className="ui-wb-crumb ui-wb-crumb-link" title="返回UI测试集列表" onClick={onBack}>测试集</button>
          <span className="ui-wb-crumb-sep" aria-hidden="true">/</span>
          {showCase ? (
            <button
              type="button"
              className="ui-wb-crumb ui-wb-crumb-suite"
              title={`返回测试集流程 · ${contextTitle}`}
              aria-label="返回测试集流程"
              onClick={onOpenSuiteFlow}
            >
              <span className="ui-wb-crumb-suite-text">
                {suiteName && suiteName !== '-'
                  ? <><strong>{suiteName}</strong>{contextRest ? <span className="ui-wb-crumb-context-rest"> · {contextRest}</span> : null}</>
                  : <span className="ui-wb-crumb-muted">加载中…</span>}
              </span>
            </button>
          ) : (
            <span className="ui-wb-crumb ui-wb-crumb-suite is-current" aria-current="page" title={contextTitle}>
              <span className="ui-wb-crumb-suite-text">
                {suiteName && suiteName !== '-'
                  ? <><strong>{suiteName}</strong>{contextRest ? <span className="ui-wb-crumb-context-rest"> · {contextRest}</span> : null}</>
                  : <span className="ui-wb-crumb-muted">加载中…</span>}
              </span>
            </span>
          )}
          {showCase ? (
            <>
              <span className="ui-wb-crumb-sep" aria-hidden="true">/</span>
              <div className="ui-wb-crumb ui-wb-crumb-case is-current" aria-current="page">
                {caseSerial ? <span className="ui-wb-case-serial">{caseSerial}</span> : null}
                {caseEditable ? (
                  <Form.Item
                    name="name"
                    className="ui-wb-crumb-name-item"
                    rules={[{ required: true, whitespace: true, message: '请输入 UI测试用例名称' }]}
                  >
                    <Input
                      maxLength={120}
                      placeholder="例如：登录成功验证"
                      aria-label="用例名称"
                      suffix={<EditOutlined className="ui-wb-crumb-name-icon" aria-hidden="true" />}
                    />
                  </Form.Item>
                ) : <span className="ui-wb-crumb-case-name">{caseName || '加载中…'}</span>}
              </div>
            </>
          ) : null}
        </nav>

        {showCase && caseEditable ? (
          <div className="ui-wb-case-meta">
            <span className="ui-wb-case-enabled">
              <Form.Item name="enabled" valuePropName="checked" noStyle>
                <Switch size="small" aria-label="启用当前用例" />
              </Form.Item>
              <span className={`ui-wb-case-status${caseEnabled ? ' tone-green' : ''}`}>{caseEnabled ? '● 已启用' : '已停用'}</span>
            </span>
            <span className="ui-wb-case-count">{caseStepCount} 个步骤</span>
          </div>
        ) : (
          <>
            <Tooltip title={readiness.hint}>
              <span className={`ui-wb-readiness tone-${readiness.tone}`}>
                <span className="ui-wb-readiness-dot" aria-hidden="true" />
                {readiness.label}
              </span>
            </Tooltip>
            <span className="ui-wb-toolbar-last-run">
              {lastRunText ? `上次运行 ${lastRunText}` : '还没有运行记录'}
            </span>
          </>
        )}
        {showCase && saveDirty ? (
          <span className="ui-wb-unsaved-chip tone-amber">
            <span className="ui-wb-unsaved-dot" aria-hidden="true" />
            未保存
          </span>
        ) : null}
      </div>

      <div className="ui-wb-toolbar-actions">
        <Select
          className="ui-wb-toolbar-environment"
          size="small"
          placeholder="选择 UI 环境"
          value={environmentId || undefined}
          loading={environmentsLoading}
          options={environmentOptions}
          onChange={onEnvironmentChange}
          popupMatchSelectWidth={false}
        />
        <Button
          className="ui-wb-toolbar-compact"
          size="small"
          icon={<SlidersOutlined />}
          title="环境"
          aria-label="环境"
          onClick={onOpenEnvironments}
        >
          <span className="ui-wb-btn-label">环境</span>
        </Button>
        {showSuiteActions ? (
          <>
            <Button
              className="ui-wb-toolbar-compact ui-wb-toolbar-history"
              icon={<HistoryOutlined />}
              title={historyLabel}
              aria-label={historyLabel}
              onClick={onOpenRunHistory}
            >
              <span className="ui-wb-btn-label">{historyLabel}</span>
            </Button>
            <Button
              className="ui-wb-toolbar-compact ui-wb-toolbar-import"
              icon={<UploadOutlined />}
              title="导入 YAML 用例到当前测试集"
              aria-label="导入用例"
              disabled={importDisabled}
              onClick={onImport}
            >
              <span className="ui-wb-btn-label">导入用例</span>
            </Button>
          </>
        ) : null}
        <span className="ui-wb-toolbar-divider" aria-hidden="true" />
        {showDebug ? <Button
          className="ui-wb-toolbar-debug"
          icon={<BugOutlined />}
          loading={debugging}
          disabled={!canDebug}
          onClick={onDebugRun}
        >
          调试运行
        </Button> : null}
        <Button className={`ui-wb-toolbar-save${saveDirty ? ' is-dirty' : ''}`} icon={<SaveOutlined />} loading={saving} disabled={!canSave} onClick={onSave}>
          保存
        </Button>
        {showSuiteActions ? (
          <>
            <span className="ui-wb-toolbar-divider" aria-hidden="true" />
            <ActionButton
              type="primary"
              className="ui-wb-toolbar-run"
              operation="run"
              loading={runningSuite}
              disabled={!canRun}
              onClick={onRunSuite}
            >
              运行测试集
            </ActionButton>
          </>
        ) : null}
      </div>
    </div>
  )
}
