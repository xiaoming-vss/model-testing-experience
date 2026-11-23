import { ActionButton } from '@/shared/components/ActionButton'
import { CaseInvalidatedTag } from '@/shared/components/CaseInvalidatedTag'
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
  canManageCases: boolean
  invalidatedCount: number
  caseInvalidatedAt?: string | null
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
  onOpenCaseStatus: () => void
}

const CRUMB_BASE = 'ui-wb-crumb inline-flex items-center gap-1.5 min-w-0 rounded-[6px] border-0 bg-transparent px-1.5 py-[3px] text-[13px] leading-5 whitespace-nowrap'
const CRUMB_BUTTON = `${CRUMB_BASE} flex-none cursor-pointer font-medium text-[var(--srf-accent)] hover:bg-[var(--srf-accent-soft)] hover:text-[var(--srf-accent)] hover:underline underline-offset-[3px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--srf-accent)]`
const CRUMB_CASE = `${CRUMB_BASE} ui-wb-crumb-case flex-[0_1_auto] min-w-[150px] p-0 font-semibold text-[var(--srf-text)]`
const COMPACT_BUTTON = 'max-[1800px]:w-7 max-[1800px]:px-0 max-[1800px]:[&_.ant-btn-icon]:me-0'
const COMPACT_LABEL = 'max-[1800px]:hidden'

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
  canManageCases,
  invalidatedCount,
  caseInvalidatedAt,
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
  onOpenCaseStatus,
}: Props) {
  const contextParts = [suiteName, requirementName, sprintName].filter((item) => item && item !== '-')
  const contextTitle = contextParts.join(' / ') || '测试集信息加载中'
  // 面包屑只露出测试集与需求；迭代放进 title，避免窄屏把整段层级挤断。
  const contextRest = requirementName && requirementName !== '-' ? requirementName : ''
  const historyLabel = `运行记录${runHistoryCount > 0 ? ` (${runHistoryCount})` : ''}`

  return (
    <div className={`ui-wb-toolbar flex-none flex flex-wrap items-center justify-between gap-2.5 rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] px-4 py-2.5 min-[1181px]:flex-nowrap${saveDirty ? ' has-unsaved-case' : ''}`}>
      <h1 className="ui-wb-visually-hidden sr-only">UI测试集详情</h1>
      <div className="ui-wb-toolbar-main flex min-w-0 flex-wrap items-center gap-2.5 min-[1181px]:flex-auto min-[1181px]:flex-nowrap min-[1181px]:overflow-hidden">
        <Button
          type="text"
          className="ui-wb-toolbar-back"
          icon={<ArrowLeftOutlined />}
          aria-label="返回UI测试集列表"
          title="返回UI测试集列表"
          onClick={onBack}
        />
        <nav className="ui-wb-crumbs flex min-w-0 flex-wrap items-center gap-0.5 min-[1181px]:flex-nowrap min-[1181px]:overflow-hidden" aria-label="面包屑">
          <button type="button" className={`${CRUMB_BUTTON} ui-wb-crumb-link`} title="返回UI测试集列表" onClick={onBack}>测试集</button>
          <span className="ui-wb-crumb-sep flex-none select-none whitespace-nowrap text-xs text-[var(--srf-card-border)]" aria-hidden="true">/</span>
          {showCase ? (
            <button
              type="button"
              className={`${CRUMB_BUTTON} ui-wb-crumb-suite flex-[0_1_auto] max-w-[280px] overflow-hidden max-[1439px]:max-w-[140px] max-[1180px]:max-w-[280px] max-narrow:max-w-[220px] max-[700px]:max-w-[180px]`}
              title={`返回测试集流程 · ${contextTitle}`}
              aria-label="返回测试集流程"
              onClick={onOpenSuiteFlow}
            >
              <span className="ui-wb-crumb-suite-text block min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">
                {suiteName && suiteName !== '-'
                  ? <><strong className={showCase ? 'font-semibold text-[var(--srf-accent)]' : 'font-semibold text-[var(--srf-text)]'}>{suiteName}</strong>{contextRest ? <span className="ui-wb-crumb-context-rest text-xs text-[var(--srf-text-muted)] max-[1439px]:hidden"> · {contextRest}</span> : null}</>
                  : <span className="ui-wb-crumb-muted text-xs text-[var(--srf-text-muted)]">加载中…</span>}
              </span>
            </button>
          ) : (
            <span className={`${CRUMB_BASE} ui-wb-crumb-suite is-current flex-[0_1_auto] max-w-[280px] overflow-hidden font-semibold text-[var(--srf-text)] max-[1439px]:max-w-[140px] max-[1180px]:max-w-[280px] max-narrow:max-w-[220px] max-[700px]:max-w-[180px]`} aria-current="page" title={contextTitle}>
              <span className="ui-wb-crumb-suite-text block min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">
                {suiteName && suiteName !== '-'
                  ? <><strong className={showCase ? 'font-semibold text-[var(--srf-accent)]' : 'font-semibold text-[var(--srf-text)]'}>{suiteName}</strong>{contextRest ? <span className="ui-wb-crumb-context-rest text-xs text-[var(--srf-text-muted)] max-[1439px]:hidden"> · {contextRest}</span> : null}</>
                  : <span className="ui-wb-crumb-muted text-xs text-[var(--srf-text-muted)]">加载中…</span>}
              </span>
            </span>
          )}
          {showCase ? (
            <>
              <span className="ui-wb-crumb-sep flex-none select-none whitespace-nowrap text-xs text-[var(--srf-card-border)]" aria-hidden="true">/</span>
              <div className={`${CRUMB_CASE} is-current`} aria-current="page">
                {caseSerial ? <span className="ui-wb-case-serial flex-none rounded-[4px] bg-[var(--srf-chip)] px-1.5 py-0.5 font-[ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace] text-xs font-semibold leading-[18px] text-[var(--srf-accent)]">{caseSerial}</span> : null}
                {caseEditable ? (
                  <Form.Item
                    name="name"
                    className="ui-wb-crumb-name-item relative m-0 min-w-[110px] max-w-[260px] flex-[0_1_220px] max-narrow:flex-[0_1_180px] max-[700px]:min-w-[96px] max-[700px]:flex-[0_1_150px]"
                    rules={[{ required: true, whitespace: true, message: '请输入 UI测试用例名称' }]}
                  >
                    <Input
                      maxLength={120}
                      placeholder="例如：登录成功验证"
                      aria-label="用例名称"
                      suffix={<EditOutlined className="ui-wb-crumb-name-icon text-[11px] text-[var(--srf-text-muted)]" aria-hidden="true" />}
                    />
                  </Form.Item>
                ) : <span className="ui-wb-crumb-case-name max-w-[260px] overflow-hidden text-ellipsis whitespace-nowrap font-semibold text-[var(--srf-text)] max-[700px]:max-w-[150px]">{caseName || '加载中…'}</span>}
              </div>
            </>
          ) : null}
        </nav>

        {showCase && caseEditable ? (
          <div className="ui-wb-case-meta flex flex-none flex-row flex-nowrap items-center gap-2.5 border-0 bg-transparent p-0">
            <span className="ui-wb-case-enabled inline-flex items-center gap-1.5">
              <Form.Item name="enabled" valuePropName="checked" noStyle>
                <Switch size="small" aria-label="启用当前用例" />
              </Form.Item>
              <span className={`ui-wb-case-status whitespace-nowrap text-[12px]${caseEnabled ? ' tone-green text-[var(--srf-tone-text)]' : ' text-[var(--srf-text-muted)]'}`}>{caseEnabled ? '● 已启用' : '已停用'}</span>
              <CaseInvalidatedTag invalidatedAt={caseInvalidatedAt} className="flex-none" />
            </span>
            <span className="ui-wb-case-count whitespace-nowrap text-[12px] text-[var(--srf-text-muted)]">{caseStepCount} 个步骤</span>
          </div>
        ) : (
          <>
            <Tooltip title={readiness.hint}>
              <span className={`ui-wb-readiness inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-[var(--srf-tone-border,var(--srf-card-border))] bg-[var(--srf-tone-bg,var(--srf-chip))] px-2 py-0.5 text-[11px] font-semibold leading-4 text-[var(--srf-tone-text,var(--srf-chip-text))] tone-${readiness.tone}`}>
                <span className="ui-wb-readiness-dot h-1.5 w-1.5 flex-none rounded-full bg-current" aria-hidden="true" />
                {readiness.label}
              </span>
            </Tooltip>
            <span className="ui-wb-toolbar-last-run text-xs text-[var(--srf-text-muted)]">
              {lastRunText ? `上次运行 ${lastRunText}` : '还没有运行记录'}
            </span>
          </>
        )}
        {showCase && saveDirty ? (
          <span className="ui-wb-unsaved-chip inline-flex h-5 flex-none items-center gap-[5px] whitespace-nowrap rounded-full border border-[var(--srf-tone-border)] bg-[var(--srf-tone-bg)] px-[7px] text-[10px] font-medium leading-[18px] text-[var(--srf-tone-text)] tone-amber">
            <span className="ui-wb-unsaved-dot h-[5px] w-[5px] flex-none rounded-full bg-current" aria-hidden="true" />
            未保存
          </span>
        ) : null}
      </div>

      <div className="ui-wb-toolbar-actions flex flex-wrap items-center gap-1.5 min-[1181px]:flex-none min-[1181px]:flex-nowrap max-[700px]:w-full max-[700px]:justify-start min-[1801px]:gap-2">
        <Select
          className="ui-wb-toolbar-environment min-w-[140px] max-w-[200px] min-[1801px]:min-w-[150px]"
          size="small"
          placeholder="选择 UI 环境"
          value={environmentId || undefined}
          loading={environmentsLoading}
          options={environmentOptions}
          onChange={onEnvironmentChange}
          popupMatchSelectWidth={false}
        />
        <Button
          className={`ui-wb-toolbar-compact ${COMPACT_BUTTON}`}
          size="small"
          icon={<SlidersOutlined />}
          title="环境"
          aria-label="环境"
          onClick={onOpenEnvironments}
        >
          <span className={`ui-wb-btn-label ${COMPACT_LABEL}`}>环境</span>
        </Button>
        {showSuiteActions ? (
          <>
            <Button
              className={`ui-wb-toolbar-compact ui-wb-toolbar-case-status ${COMPACT_BUTTON}`}
              title="管理用例状态"
              aria-label="管理用例状态"
              disabled={!canManageCases}
              onClick={onOpenCaseStatus}
            >
              <span className={`ui-wb-btn-label ${COMPACT_LABEL}`}>用例状态</span>
            </Button>
            <Button
              className={`ui-wb-toolbar-compact ui-wb-toolbar-history ${COMPACT_BUTTON}`}
              icon={<HistoryOutlined />}
              title={historyLabel}
              aria-label={historyLabel}
              onClick={onOpenRunHistory}
            >
              <span className={`ui-wb-btn-label ${COMPACT_LABEL}`}>{historyLabel}</span>
            </Button>
            <Button
              className={`ui-wb-toolbar-compact ui-wb-toolbar-import ${COMPACT_BUTTON}`}
              icon={<UploadOutlined />}
              title="导入 YAML 用例到当前测试集"
              aria-label="导入用例"
              disabled={importDisabled}
              onClick={onImport}
            >
              <span className={`ui-wb-btn-label ${COMPACT_LABEL}`}>导入用例</span>
            </Button>
          </>
        ) : null}
        <span className="ui-wb-toolbar-divider h-[18px] w-px bg-[var(--srf-card-border)]" aria-hidden="true" />
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
            <span className="ui-wb-toolbar-divider h-[18px] w-px bg-[var(--srf-card-border)]" aria-hidden="true" />
            <ActionButton
              type="primary"
              className="ui-wb-toolbar-run"
              operation="run"
              loading={runningSuite}
              disabled={!canRun}
              title={invalidatedCount > 0 ? `运行将排除 ${invalidatedCount} 条失效用例` : undefined}
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
