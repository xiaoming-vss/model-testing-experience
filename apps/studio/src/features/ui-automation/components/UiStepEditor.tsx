import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import {
  isValidUiIntegerOrVariable,
  isValidUiOpenUrl,
  isValidUiStepComparator,
  isValidUiStepKeyword,
  isValidUiStepLocatorType,
  requiresUiStepLocator,
  uiTestComparatorOptions,
  uiStepSaveSourceOptions,
  uiTestKeywordOptions,
  uiTestLocatorTypeOptions,
  usesUiStepComparator
} from '@/features/ui-automation/config/stepConfig'
import { buildUiStepRowView } from '@/features/ui-automation/utils/stepRowView'
import { type UiTemplateFieldKey } from '@/features/ui-automation/utils/detailView'
import { indexUiRunStepResultsByOrder } from '@/features/ui-automation/utils/detailRunView'
import {
  type UiTestStepFormValue
} from '@/features/ui-automation/utils/uiTestCaseEditor'
import type { UiTestCaseRunStepResult } from '@/services/api'
import { DownOutlined, EditOutlined, HolderOutlined } from '@ant-design/icons'
import type { InputRef } from 'antd'
import { Empty, Form, Input, Select, Switch, Tooltip } from 'antd'

import type { ProjectAction } from '@/domain/projects/types'

import { UiStepResultBadge } from './UiStepResultBadge'
import { useLayoutEffect, useRef, type JSX, type ReactNode } from 'react'

type Props = {
  watchedSteps: UiTestStepFormValue[]
  selectedStepIndex?: number
  activeTab?: 'basic' | 'extract'
  onTabChange?: (tab: 'basic' | 'extract') => void
  detailActions?: ReactNode
  expandedStepIndexes: number[]
  draggingStepIndex: number | null
  handleStepDrop: (move: (from: number, to: number) => void, targetIndex: number) => void
  can: (action: ProjectAction) => boolean
  handleStepDragStart: (event: React.DragEvent<HTMLDivElement>, index: number) => void
  setDraggingStepIndex: React.Dispatch<React.SetStateAction<number | null>>
  toggleStepPanel: (index: number) => void
  removeStep: (remove: (index: number | number[]) => void, index: number) => void
  renderTemplatePickerLabel: (stepIndex: number, fieldKey: UiTemplateFieldKey, label: string) => JSX.Element
  bindTemplateInputRef: (stepIndex: number, fieldKey: UiTemplateFieldKey) => (instance: InputRef | null) => void
  /** 最近一次调试运行的步骤结果，按 orderNo 对齐到步骤行上显示 PASS / FAIL 徽标。 */
  stepResults?: UiTestCaseRunStepResult[]
}

// 步骤编辑器样式由宿主页面引入的 ui-suite.module.css 作用域提供。
export function UiStepEditor({ watchedSteps, selectedStepIndex, activeTab = 'basic', onTabChange, detailActions, expandedStepIndexes, draggingStepIndex, handleStepDrop, can, handleStepDragStart, setDraggingStepIndex, toggleStepPanel, removeStep, renderTemplatePickerLabel, bindTemplateInputRef, stepResults = [] }: Props) {
  const stepResultByOrder = indexUiRunStepResultsByOrder(stepResults)
  const stepListRef = useRef<HTMLDivElement | null>(null)
  const previousExpandedRef = useRef(expandedStepIndexes)
  // 同一用例内允许跨步骤重名（后写覆盖），编辑器提示第一次写入的步骤号。
  const saveNameOwners = new Map<string, number>()
  watchedSteps.forEach((step, stepIndex) => {
    step.saveTo?.forEach((rule) => {
      const name = rule.name?.trim()
      if (name && !saveNameOwners.has(name)) saveNameOwners.set(name, stepIndex)
    })
  })

  // 展开靠后的步骤时，新露出的表单可能落在列表可视区下方。
  // 只对这次新展开的卡片做最小滚动：卡片能整张放进列表就滚到完整可见，放不下就对到列表顶部。
  useLayoutEffect(() => {
    const previousExpanded = previousExpandedRef.current
    previousExpandedRef.current = expandedStepIndexes
    const newlyExpandedIndex = [...expandedStepIndexes].reverse().find((index) => !previousExpanded.includes(index))
    if (newlyExpandedIndex === undefined) return

    const list = stepListRef.current
    const card = list?.querySelector<HTMLElement>(`[data-step-index="${newlyExpandedIndex}"]`)
    if (!list || !card) return

    const listRect = list.getBoundingClientRect()
    const cardRect = card.getBoundingClientRect()
    if (cardRect.height <= list.clientHeight) {
      if (cardRect.top < listRect.top) {
        list.scrollTop -= listRect.top - cardRect.top
      } else if (cardRect.bottom > listRect.bottom) {
        list.scrollTop += cardRect.bottom - listRect.bottom
      }
      return
    }

    if (cardRect.top < listRect.top || cardRect.top > listRect.bottom) {
      list.scrollTop += cardRect.top - listRect.top
    }
  }, [expandedStepIndexes])

  return (
    <Form.List name="steps">
      {(fields, { remove, move }) => (
        <>
          {fields.length === 0 ? (
            <div className="ui-test-case-step-empty rounded-[12px] border border-dashed border-[var(--tp-border-soft)] bg-[var(--app-review-surface)] p-[18px]">
              <Empty description="当前还没有步骤，请在流程末尾的「+ 添加步骤」卡片中添加" />
            </div>
          ) : (
            <div className="ui-test-case-step-list flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-0.5" ref={stepListRef}>
              {fields.map((field, index) => {
                const { key: fieldKey, ...fieldProps } = field
                const step = watchedSteps[index]
                const {
                  requiresLocator: stepRequiresLocator,
                  usesComparator: stepUsesComparator,
                  showLocatorFields,
                  showOperationField,
                  showLocatorTypeField,
                  operationFieldLabel,
                  operationFieldPlaceholder,
                  locatorFieldHint,
                  operationFieldHint,
                  locatorValueFieldClass,
                  operationValueFieldClass,
                  summary: stepSummary,
                } = buildUiStepRowView(step)
                const expanded = selectedStepIndex !== undefined || expandedStepIndexes.includes(index)
                // 详情模式一次只显示一个步骤；其余步骤只保留字段注册（noStyle + 无控件），
                // 这样保存时仍校验全部步骤，却不用为每步挂载一整套 Select / Input。
                const compact = selectedStepIndex !== undefined && selectedStepIndex !== index
                const stepResult = stepResultByOrder.get(index + 1)

                return (
                  <div
                    key={fieldKey}
                    data-step-index={index}
                    hidden={selectedStepIndex !== undefined && selectedStepIndex !== index}
                    className={`ui-test-case-step-card p-0 transition-[border-color,box-shadow] duration-200${selectedStepIndex !== undefined ? ' is-detail rounded-none border-0 bg-transparent shadow-none overflow-visible' : ' rounded-[12px] border border-[var(--srf-card-border)] bg-[var(--srf-hover)] overflow-hidden'}${expanded ? ' expanded' : ''}${expanded && selectedStepIndex === undefined ? ' border-[var(--srf-accent-border)] shadow-none' : ''}${draggingStepIndex === index ? ' dragging opacity-[0.72]' : ''}`}
                    onDragOver={(event) => {
                      event.preventDefault()
                    }}
                    onDrop={(event) => {
                      event.preventDefault()
                      handleStepDrop(move, index)
                    }}
                  >
                    <div
                      className={`ui-test-case-step-card-top flex items-center justify-between gap-4${selectedStepIndex === undefined ? ' cursor-grab px-4 py-3.5 active:cursor-grabbing' : ' cursor-default px-0 pb-3 pt-0'}`}
                      draggable={can('write') && selectedStepIndex === undefined}
                      onDragStart={(event) => handleStepDragStart(event, index)}
                      onDragEnd={() => setDraggingStepIndex(null)}
                      onClick={selectedStepIndex === undefined ? () => toggleStepPanel(index) : undefined}
                    >
                      <div className="ui-test-case-step-card-main min-w-0 flex flex-1 items-center gap-2.5">
                        <div className="ui-test-case-step-card-leading flex flex-none items-center gap-2">
                          {/* 设计稿在行首画了拖拽手柄；整行本来就可拖（见上面的 draggable），这里只是把可拖这件事画出来。 */}
                          {selectedStepIndex === undefined ? <span className="ui-wb-step-grip inline-flex items-center text-sm text-[var(--srf-text-muted)] cursor-grab active:cursor-grabbing" aria-hidden="true">
                            <HolderOutlined />
                          </span> : null}
                          {selectedStepIndex === undefined ? <button
                            type="button"
                            className={`ui-test-case-step-toggle inline-flex h-7 w-7 flex-none cursor-pointer items-center justify-center rounded-[8px] border border-[var(--tp-border-soft)] bg-[var(--app-review-code-bg)] p-0 text-[var(--tp-text-secondary)] transition-[color,transform,border-color,background-color] duration-200 hover:border-[var(--app-review-border-hover)] hover:bg-[var(--app-request-card-shadow-hover)] hover:text-[var(--app-accent)]${expanded ? ' expanded rotate-180 text-[var(--app-accent)]' : ''}`}
                            aria-label={expanded ? '折叠步骤' : '展开步骤'}
                            aria-expanded={expanded}
                            onClick={(event) => {
                              event.stopPropagation()
                              toggleStepPanel(index)
                            }}
                          >
                            <DownOutlined />
                          </button> : null}
                          <span className={`ui-test-case-step-order inline-flex h-6 w-6 flex-none items-center justify-center rounded-[6px] p-0 font-[ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace] text-[11px] font-bold${expanded ? ' bg-[var(--srf-accent)] text-[var(--srf-on-accent)]' : ' bg-[var(--srf-count-badge)] text-[var(--srf-accent-strong)]'}`}>#{index + 1}</span>
                        </div>
                        <div
                          className="ui-test-case-step-card-title min-w-0 flex flex-1 flex-col gap-1"
                          onClick={(event) => event.stopPropagation()}
                          onMouseDown={(event) => event.stopPropagation()}
                        >
                          <div className="ui-test-case-step-title-head flex items-center gap-3">
                            <Form.Item
                              {...fieldProps}
                              noStyle={compact}
                              name={[field.name, 'stepName']}
                              className="ui-test-case-step-title-item mb-0 min-w-0 flex-1"
                              rules={[{ required: true, whitespace: true, message: '请输入步骤名称' }]}
                            >
                              {compact ? null : <Input
                                placeholder="点击输入步骤名称"
                                maxLength={120}
                                className="ui-test-case-step-title-input"
                                suffix={<EditOutlined className="ui-test-case-step-title-edit-icon text-xs text-[var(--tp-text-muted)]" />}
                              />}
                            </Form.Item>
                          </div>
                          {selectedStepIndex === undefined ? <div className="ui-wb-step-summary flex min-w-0 flex-wrap items-center gap-1.5 font-[ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace] text-[11px] leading-4 text-[var(--srf-text-muted)]">
                            <span className="ui-wb-step-summary-text">{stepSummary}</span>
                            {stepResult ? (
                              <UiStepResultBadge stepResult={stepResult} />
                            ) : step?.keyword?.trim() ? null : (
                              <span className="ui-wb-step-status is-draft flex-none rounded border border-[var(--srf-card-border)] bg-[var(--srf-chip)] px-1.5 py-px font-[ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace] text-[10px] font-bold leading-4 text-[var(--srf-text-muted)]">草稿</span>
                            )}
                          </div> : null}
                        </div>
                      </div>
                      <div className="ui-test-case-step-actions flex flex-none flex-wrap items-center gap-2 pt-1.5" onClick={(event) => event.stopPropagation()}>
                        {compact ? null : <Tooltip title="删除步骤">
                          <ProjectActionButton action="write"
                            type="text"
                            size="small"
                            className="ui-test-case-step-delete-action action-btn-delete"
                            operation="delete" iconOnly
                            onClick={() => removeStep(remove, index)}
                          />
                        </Tooltip>}
                      </div>
                    </div>

                    {selectedStepIndex === index ? detailActions : null}
                    {selectedStepIndex !== undefined && selectedStepIndex === index ? <div className="ui-step-config-tabs mb-4 flex gap-6 border-b border-[var(--srf-card-border)]" role="tablist" aria-label="步骤配置分类">
                      <button type="button" role="tab" aria-selected={activeTab === 'basic'} className={`cursor-pointer border-0 border-b-2 border-transparent bg-transparent px-0 py-2 text-[var(--srf-text-secondary)]${activeTab === 'basic' ? ' border-b-[var(--srf-accent)] font-semibold text-[var(--srf-accent)]' : ''}`} onClick={() => onTabChange?.('basic')}>基础配置</button>
                      <button type="button" role="tab" aria-selected={activeTab === 'extract'} className={`cursor-pointer border-0 border-b-2 border-transparent bg-transparent px-0 py-2 text-[var(--srf-text-secondary)]${activeTab === 'extract' ? ' border-b-[var(--srf-accent)] font-semibold text-[var(--srf-accent)]' : ''}`} onClick={() => onTabChange?.('extract')}>后置提取</button>
                    </div> : null}
                    <div className={`ui-test-case-step-body flex flex-col${selectedStepIndex !== undefined ? ' gap-2 border-0 bg-transparent p-0' : ' mt-0 gap-4 border-t border-[var(--tp-border-soft)] p-4'}`} hidden={!expanded} aria-hidden={!expanded}>
                      <div className={`ui-test-case-step-grid ui-test-case-step-core-grid grid items-start${selectedStepIndex !== undefined ? ' grid-cols-1 gap-4' : ' grid-cols-2 gap-x-4 gap-y-3.5 max-[1180px]:grid-cols-1'}`} hidden={selectedStepIndex !== undefined && activeTab !== 'basic'}>
                        <Form.Item
                          {...fieldProps}
                          noStyle={compact}
                          name={[field.name, 'keyword']}
                          label="关键字"
                          rules={[
                            { required: true, message: '请选择步骤关键字' },
                            {
                              validator(_, value: string | undefined) {
                                if (!value || isValidUiStepKeyword(value)) return Promise.resolve()
                                return Promise.reject(new Error('当前关键字不受支持，请重新选择'))
                              },
                            },
                          ]}
                        >
                          {compact ? null : <Select
                            showSearch
                            placeholder="请选择关键字"
                            options={uiTestKeywordOptions}
                            optionFilterProp="label"
                          />}
                        </Form.Item>
                        <Form.Item
                          {...fieldProps}
                          noStyle={compact}
                          name={[field.name, 'locatorType']}
                          label="定位方式"
                          hidden={!compact && !showLocatorTypeField}
                          dependencies={[['steps', field.name, 'keyword']]}
                          rules={[
                            ({ getFieldValue }) => ({
                              validator(_, value: string | undefined) {
                                const keyword = getFieldValue(['steps', field.name, 'keyword'])
                                if (!requiresUiStepLocator(keyword)) {
                                  return Promise.resolve()
                                }
                                if (!value?.trim()) {
                                  return Promise.reject(new Error('当前关键字需要选择定位方式'))
                                }
                                if (!isValidUiStepLocatorType(value)) {
                                  return Promise.reject(new Error('当前定位方式不受支持，请重新选择'))
                                }
                                return Promise.resolve()
                              },
                            }),
                          ]}
                        >
                          {compact ? null : <Select
                            showSearch
                            placeholder={stepRequiresLocator ? '请选择定位方式' : '按需选择定位方式'}
                            options={uiTestLocatorTypeOptions}
                            optionFilterProp="label"
                            allowClear={!stepRequiresLocator}
                          />}
                        </Form.Item>
                      </div>

                      <div className={`ui-test-case-step-detail-grid grid items-start${selectedStepIndex !== undefined ? ' grid-cols-1 gap-4' : ' grid-cols-2 gap-x-4 gap-y-3.5 max-[1180px]:grid-cols-1'}`} hidden={selectedStepIndex !== undefined && activeTab !== 'basic'}>
                        <div
                          className="ui-test-case-step-field-note ui-test-case-step-field-wide -mt-1 text-xs leading-[18px] text-[var(--tp-text-secondary)]"
                          hidden={selectedStepIndex !== undefined || !showLocatorTypeField || !locatorFieldHint}
                        >
                          {locatorFieldHint}
                        </div>

                        <Form.Item
                          {...fieldProps}
                          noStyle={compact}
                          name={[field.name, 'locatorValue']}
                          label={selectedStepIndex !== undefined ? '定位值' : renderTemplatePickerLabel(field.name, 'locatorValue', '定位值')}
                          hidden={!compact && !showLocatorFields}
                          className={`ui-test-case-step-field ${locatorValueFieldClass} ${selectedStepIndex !== undefined ? 'col-span-1' : locatorValueFieldClass.includes('wide') ? 'col-span-2 max-[1180px]:col-span-1' : 'col-span-1'}`}
                          dependencies={[['steps', field.name, 'keyword']]}
                          rules={[
                            ({ getFieldValue }) => ({
                              validator(_, value: string | undefined) {
                                const keyword = getFieldValue(['steps', field.name, 'keyword'])
                                if (!requiresUiStepLocator(keyword) || value?.trim()) {
                                  return Promise.resolve()
                                }
                                return Promise.reject(new Error('当前关键字需要填写定位值'))
                              },
                            }),
                          ]}
                        >
                          {compact ? null : <Input
                            ref={bindTemplateInputRef(field.name, 'locatorValue')}
                            suffix={selectedStepIndex !== undefined ? renderTemplatePickerLabel(field.name, 'locatorValue', '') : undefined}
                            placeholder={stepRequiresLocator ? '例如：#username' : '按需填写'}
                            maxLength={400}
                          />}
                        </Form.Item>

                        <Form.Item
                          {...fieldProps}
                          noStyle={compact}
                          name={[field.name, 'operationValue']}
                          label={selectedStepIndex !== undefined ? <span title={operationFieldLabel}>{step?.keyword === 'open' ? '页面 URL' : '操作值'}</span> : renderTemplatePickerLabel(field.name, 'operationValue', operationFieldLabel)}
                          hidden={!compact && !showOperationField}
                          className={`ui-test-case-step-field ${operationValueFieldClass} ${selectedStepIndex !== undefined ? 'col-span-1' : operationValueFieldClass.includes('wide') ? 'col-span-2 max-[1180px]:col-span-1' : 'col-span-1'}`}
                          dependencies={[['steps', field.name, 'keyword']]}
                          rules={[
                            {
                              warningOnly: true,
                              validator(_, value: string | undefined) {
                                if (value && /\{\{\s*baseUrl\s*\}\}(?![/?#]|$)/.test(value.trim())) {
                                  return Promise.reject(new Error('{{baseUrl}} 后面建议加 /，避免和域名拼在一起'))
                                }
                                return Promise.resolve()
                              },
                            },
                            ({ getFieldValue }) => ({
                              validator(_, value: string | undefined) {
                                const keyword = getFieldValue(['steps', field.name, 'keyword'])
                                const trimmedValue = value?.trim()

                                if (keyword === 'open') {
                                  if (!trimmedValue) {
                                    return Promise.reject(new Error('open 步骤请填写完整 URL 或 {{baseUrl}} 模板'))
                                  }
                                  if (isValidUiOpenUrl(trimmedValue)) {
                                    return Promise.resolve()
                                  }
                                  return Promise.reject(new Error('open 步骤请填写完整 URL 或 {{baseUrl}} 模板'))
                                }

                                const requiredValueLabels: Record<string, string> = {
                                  input: '输入值',
                                  press: '按键或组合键',
                                  wait_text: '等待文本',
                                  assert_text: '期望文本',
                                  assert_url: '期望 URL',
                                }
                                if (keyword && requiredValueLabels[keyword] && !trimmedValue) {
                                  return Promise.reject(new Error(`${keyword} 步骤请填写${requiredValueLabels[keyword]}`))
                                }

                                if (keyword === 'sleep' || keyword === 'assert_visible' || keyword === 'assert_hidden') {
                                  if (!trimmedValue) {
                                    return Promise.reject(new Error(`${keyword} 步骤请填写毫秒数`))
                                  }
                                  if (isValidUiIntegerOrVariable(trimmedValue)) {
                                    return Promise.resolve()
                                  }
                                  return Promise.reject(new Error(`${keyword} 步骤请填写非负整数毫秒数或变量模板`))
                                }

                                if (!trimmedValue) {
                                  return Promise.resolve()
                                }

                                return Promise.resolve()
                              },
                            }),
                          ]}
                        >
                          {compact ? null : <Input
                            ref={bindTemplateInputRef(field.name, 'operationValue')}
                            suffix={selectedStepIndex !== undefined ? renderTemplatePickerLabel(field.name, 'operationValue', '') : undefined}
                            placeholder={operationFieldPlaceholder}
                            maxLength={400}
                          />}
                        </Form.Item>

                        <div
                          className="ui-test-case-step-field-note ui-test-case-step-field-wide -mt-1 text-xs leading-[18px] text-[var(--tp-text-secondary)]"
                          hidden={selectedStepIndex !== undefined || !showOperationField || !operationFieldHint}
                        >
                          {operationFieldHint}
                        </div>

                        <Form.Item
                          {...fieldProps}
                          noStyle={compact}
                          name={[field.name, 'comparator']}
                          label="比较器"
                          hidden={!compact && !stepUsesComparator}
                          className="ui-test-case-step-field ui-test-case-step-field-third col-span-1"
                          dependencies={[['steps', field.name, 'keyword']]}
                          rules={[
                            ({ getFieldValue }) => ({
                              validator(_, value: string | undefined) {
                                const keyword = getFieldValue(['steps', field.name, 'keyword'])
                                if (!usesUiStepComparator(keyword)) {
                                  return Promise.resolve()
                                }
                                if (!value?.trim()) {
                                  return Promise.reject(new Error('当前断言步骤需要选择比较器'))
                                }
                                if (!isValidUiStepComparator(value)) {
                                  return Promise.reject(new Error('当前比较器不受支持，请重新选择'))
                                }
                                return Promise.resolve()
                              },
                            }),
                          ]}
                        >
                          {compact ? null : <Select placeholder="请选择比较器" options={uiTestComparatorOptions} />}
                        </Form.Item>
                      </div>

                      <div className="ui-test-case-step-extract flex flex-col gap-2 border-t border-dashed border-[var(--tp-border)] pt-3" hidden={selectedStepIndex !== undefined && activeTab !== 'extract'}>
                        <div className="ui-test-case-step-extract-head flex items-baseline gap-2.5">
                          <span className="ui-test-case-step-extract-title text-xs font-semibold">后置提取</span>
                          {selectedStepIndex === undefined ? <span className="ui-test-case-step-extract-hint text-xs leading-[18px] text-[var(--tp-text-secondary)]">
                            步骤成功后读取页面上的值，立即写回环境变量
                          </span> : null}
                        </div>
                        <Form.List name={[field.name, 'saveTo']}>
                          {(saveFields, { add: addSaveRule, remove: removeSaveRule }) => (
                            <>
                              {saveFields.length === 0 && !compact ? (
                                <div className="ui-test-case-step-extract-empty text-xs leading-[18px] text-[var(--tp-text-secondary)]">当前没有提取规则</div>
                              ) : null}
                              {saveFields.map((saveField) => {
                                const { key: saveKey, ...saveFieldProps } = saveField
                                const ruleName = step?.saveTo?.[saveField.name]?.name?.trim() ?? ''
                                const ownerStepIndex = ruleName ? saveNameOwners.get(ruleName) : undefined
                                return (
                                  <div key={saveKey} className="ui-test-case-step-extract-row grid grid-cols-2 items-start gap-2 max-[1180px]:grid-cols-2">
                                    <Form.Item
                                      {...saveFieldProps}
                                      noStyle={compact}
                                      name={[saveField.name, 'name']}
                                      className="ui-test-case-step-extract-name"
                                      extra={
                                        ownerStepIndex !== undefined && ownerStepIndex < index ? (
                                          <span className="ui-test-case-step-extract-warning text-[11px] leading-4 text-[var(--app-status-warning-text)]">
                                            同名变量会覆盖第 {ownerStepIndex + 1} 步写入的值
                                          </span>
                                        ) : undefined
                                      }
                                      rules={[
                                        { required: true, whitespace: true, message: '请输入变量名' },
                                        {
                                          validator(_, value: string | undefined) {
                                            const name = value?.trim() ?? ''
                                            if (!name) return Promise.resolve()
                                            if (/[{}|]/.test(name) || /\s/.test(name)) {
                                              return Promise.reject(new Error('变量名不能包含空白、{ } 或 |'))
                                            }
                                            if (name === 'baseUrl') {
                                              return Promise.reject(new Error('baseUrl 是内置变量名'))
                                            }
                                            if (name.startsWith('$') || name.startsWith('data.')) {
                                              return Promise.reject(new Error('变量名不能以 $ 或 data. 开头'))
                                            }
                                            return Promise.resolve()
                                          },
                                        },
                                      ]}
                                    >
                                      {compact ? null : <Input placeholder="变量名" maxLength={120} />}
                                    </Form.Item>
                                    <Form.Item
                                      {...saveFieldProps}
                                      noStyle={compact}
                                      name={[saveField.name, 'source']}
                                      className="ui-test-case-step-extract-source"
                                      initialValue="text"
                                    >
                                      {compact ? null : <Select options={uiStepSaveSourceOptions} />}
                                    </Form.Item>
                                    <Form.Item
                                      {...saveFieldProps}
                                      noStyle={compact}
                                      name={[saveField.name, 'locatorType']}
                                      className="ui-test-case-step-extract-locator-type"
                                      dependencies={[['steps', field.name, 'saveTo', saveField.name, 'locatorValue']]}
                                    >
                                      {compact ? null : <Select
                                        allowClear
                                        placeholder="定位方式"
                                        options={uiTestLocatorTypeOptions}
                                        optionFilterProp="label"
                                        showSearch
                                      />}
                                    </Form.Item>
                                    <Form.Item
                                      {...saveFieldProps}
                                      noStyle={compact}
                                      name={[saveField.name, 'locatorValue']}
                                      className="ui-test-case-step-extract-locator-value"
                                      dependencies={[['steps', field.name, 'saveTo', saveField.name, 'locatorType']]}
                                      rules={[
                                        ({ getFieldValue }) => ({
                                          validator(_, value: string | undefined) {
                                            const path = ['steps', field.name, 'saveTo', saveField.name] as const
                                            const locatorType = getFieldValue([...path, 'locatorType']) as string | undefined
                                            const source = getFieldValue([...path, 'source']) as string | undefined
                                            const locatorValue = value?.trim() ?? ''
                                            if (source === 'url') return Promise.resolve()
                                            if (/\{\{/.test(locatorValue)) {
                                              return Promise.reject(new Error('提取定位不支持变量'))
                                            }
                                            if (Boolean(locatorType?.trim()) !== Boolean(locatorValue)) {
                                              return Promise.reject(new Error('定位方式与定位值需要同时填写或同时留空'))
                                            }
                                            const stepLocatorType = getFieldValue(['steps', field.name, 'locatorType']) as string | undefined
                                            const stepLocatorValue = getFieldValue(['steps', field.name, 'locatorValue']) as string | undefined
                                            if (!locatorType?.trim() && !locatorValue && !(stepLocatorType?.trim() && stepLocatorValue?.trim())) {
                                              return Promise.reject(new Error('本步骤没有可继承的定位，请填写定位方式与定位值'))
                                            }
                                            return Promise.resolve()
                                          },
                                        }),
                                      ]}
                                    >
                                      {compact ? null : <Input placeholder="定位值，留空继承步骤定位" maxLength={400} />}
                                    </Form.Item>
                                    <Form.Item
                                      {...saveFieldProps}
                                      noStyle={compact}
                                      name={[saveField.name, 'attribute']}
                                      className="ui-test-case-step-extract-attribute"
                                      dependencies={[['steps', field.name, 'saveTo', saveField.name, 'source']]}
                                      rules={[
                                        ({ getFieldValue }) => ({
                                          validator(_, value: string | undefined) {
                                            const source = getFieldValue([
                                              'steps',
                                              field.name,
                                              'saveTo',
                                              saveField.name,
                                              'source',
                                            ]) as string | undefined
                                            if (source === 'attribute' && !value?.trim()) {
                                              return Promise.reject(new Error('属性来源必须填写属性名'))
                                            }
                                            return Promise.resolve()
                                          },
                                        }),
                                      ]}
                                    >
                                      {compact ? null : <Input placeholder="属性名（属性来源必填）" maxLength={120} />}
                                    </Form.Item>
                                    <Form.Item
                                      {...saveFieldProps}
                                      noStyle={compact}
                                      name={[saveField.name, 'defaultValue']}
                                      className="ui-test-case-step-extract-default"
                                    >
                                      {compact ? null : <Input placeholder="默认值（可选）" maxLength={400} />}
                                    </Form.Item>
                                    {compact ? null : <Tooltip title="删除提取规则">
                                      <ProjectActionButton
                                        action="write"
                                        type="text"
                                        size="small"
                                        operation="delete"
                                        iconOnly
                                        className="ui-test-case-step-extract-remove action-btn-delete"
                                        onClick={() => removeSaveRule(saveField.name)}
                                      />
                                    </Tooltip>}
                                  </div>
                                )
                              })}
                              {compact ? null : <ProjectActionButton
                                action="write"
                                type="dashed"
                                size="small"
                                operation="create"
                                onClick={() => addSaveRule({ name: '', source: 'text' })}
                              >
                                添加提取
                              </ProjectActionButton>}
                            </>
                          )}
                        </Form.List>
                      </div>

                      {selectedStepIndex === undefined ? <div className="ui-test-case-step-footer flex flex-col gap-4 pt-0.5">
                        <div className="ui-test-case-step-footer-grid grid grid-cols-[minmax(120px,160px)_repeat(2,max-content)] items-end gap-x-[22px] gap-y-3 max-[1180px]:grid-cols-1">
                          <div className="ui-test-case-step-status-row contents">
                            <Form.Item
                              {...fieldProps}
                              name={[field.name, 'enabled']}
                              label="启用"
                              valuePropName="checked"
                              className="ui-test-case-step-inline-switch-item mb-0 flex items-center"
                            >
                              <Switch />
                            </Form.Item>
                            <Form.Item
                              {...fieldProps}
                              name={[field.name, 'continueOnFailure']}
                              label="失败后继续"
                              valuePropName="checked"
                              className="ui-test-case-step-inline-switch-item mb-0 flex items-center"
                            >
                              <Switch />
                            </Form.Item>
                          </div>
                        </div>
                      </div> : null}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}
    </Form.List>
  )
}
