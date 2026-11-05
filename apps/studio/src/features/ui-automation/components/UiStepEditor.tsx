import '@/features/ui-automation/styles/index.css'
import '@/features/ui-automation/styles/step-editor-layout.css'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
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

import type { ProjectAction } from '@/features/projects/types'

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
            <div className="ui-test-case-step-empty">
              <Empty description="当前还没有步骤，请在流程末尾的「+ 添加步骤」卡片中添加" />
            </div>
          ) : (
            <div className="ui-test-case-step-list" ref={stepListRef}>
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
                    className={`ui-test-case-step-card${expanded ? ' expanded' : ''}${selectedStepIndex !== undefined ? ' is-detail' : ''}${draggingStepIndex === index ? ' dragging' : ''}`}
                    onDragOver={(event) => {
                      event.preventDefault()
                    }}
                    onDrop={(event) => {
                      event.preventDefault()
                      handleStepDrop(move, index)
                    }}
                  >
                    <div
                      className="ui-test-case-step-card-top"
                      draggable={can('write') && selectedStepIndex === undefined}
                      onDragStart={(event) => handleStepDragStart(event, index)}
                      onDragEnd={() => setDraggingStepIndex(null)}
                      onClick={selectedStepIndex === undefined ? () => toggleStepPanel(index) : undefined}
                    >
                      <div className="ui-test-case-step-card-main">
                        <div className="ui-test-case-step-card-leading">
                          {/* 设计稿在行首画了拖拽手柄；整行本来就可拖（见上面的 draggable），这里只是把可拖这件事画出来。 */}
                          {selectedStepIndex === undefined ? <span className="ui-wb-step-grip" aria-hidden="true">
                            <HolderOutlined />
                          </span> : null}
                          {selectedStepIndex === undefined ? <button
                            type="button"
                            className={`ui-test-case-step-toggle${expanded ? ' expanded' : ''}`}
                            aria-label={expanded ? '折叠步骤' : '展开步骤'}
                            aria-expanded={expanded}
                            onClick={(event) => {
                              event.stopPropagation()
                              toggleStepPanel(index)
                            }}
                          >
                            <DownOutlined />
                          </button> : null}
                          <span className="ui-test-case-step-order">#{index + 1}</span>
                        </div>
                        <div
                          className="ui-test-case-step-card-title"
                          onClick={(event) => event.stopPropagation()}
                          onMouseDown={(event) => event.stopPropagation()}
                        >
                          <div className="ui-test-case-step-title-head">
                            <Form.Item
                              {...fieldProps}
                              noStyle={compact}
                              name={[field.name, 'stepName']}
                              className="ui-test-case-step-title-item"
                              rules={[{ required: true, whitespace: true, message: '请输入步骤名称' }]}
                            >
                              {compact ? null : <Input
                                placeholder="点击输入步骤名称"
                                maxLength={120}
                                className="ui-test-case-step-title-input"
                                suffix={<EditOutlined className="ui-test-case-step-title-edit-icon" />}
                              />}
                            </Form.Item>
                          </div>
                          {selectedStepIndex === undefined ? <div className="ui-wb-step-summary">
                            <span className="ui-wb-step-summary-text">{stepSummary}</span>
                            {stepResult ? (
                              <UiStepResultBadge stepResult={stepResult} />
                            ) : step?.keyword?.trim() ? null : (
                              <span className="ui-wb-step-status is-draft">草稿</span>
                            )}
                          </div> : null}
                        </div>
                      </div>
                      <div className="ui-test-case-step-actions" onClick={(event) => event.stopPropagation()}>
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
                    {selectedStepIndex !== undefined && selectedStepIndex === index ? <div className="ui-step-config-tabs" role="tablist" aria-label="步骤配置分类">
                      <button type="button" role="tab" aria-selected={activeTab === 'basic'} onClick={() => onTabChange?.('basic')}>基础配置</button>
                      <button type="button" role="tab" aria-selected={activeTab === 'extract'} onClick={() => onTabChange?.('extract')}>后置提取</button>
                    </div> : null}
                    <div className="ui-test-case-step-body" hidden={!expanded} aria-hidden={!expanded}>
                      <div className="ui-test-case-step-grid ui-test-case-step-core-grid" hidden={selectedStepIndex !== undefined && activeTab !== 'basic'}>
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

                      <div className="ui-test-case-step-detail-grid" hidden={selectedStepIndex !== undefined && activeTab !== 'basic'}>
                        <div
                          className="ui-test-case-step-field-note ui-test-case-step-field-wide"
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
                          className={`ui-test-case-step-field ${locatorValueFieldClass}`}
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
                          className={`ui-test-case-step-field ${operationValueFieldClass}`}
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
                          className="ui-test-case-step-field-note ui-test-case-step-field-wide"
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
                          className="ui-test-case-step-field ui-test-case-step-field-third"
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

                      <div className="ui-test-case-step-extract" hidden={selectedStepIndex !== undefined && activeTab !== 'extract'}>
                        <div className="ui-test-case-step-extract-head">
                          <span className="ui-test-case-step-extract-title">后置提取</span>
                          {selectedStepIndex === undefined ? <span className="ui-test-case-step-extract-hint">
                            步骤成功后读取页面上的值，立即写回环境变量
                          </span> : null}
                        </div>
                        <Form.List name={[field.name, 'saveTo']}>
                          {(saveFields, { add: addSaveRule, remove: removeSaveRule }) => (
                            <>
                              {saveFields.length === 0 && !compact ? (
                                <div className="ui-test-case-step-extract-empty">当前没有提取规则</div>
                              ) : null}
                              {saveFields.map((saveField) => {
                                const { key: saveKey, ...saveFieldProps } = saveField
                                const ruleName = step?.saveTo?.[saveField.name]?.name?.trim() ?? ''
                                const ownerStepIndex = ruleName ? saveNameOwners.get(ruleName) : undefined
                                return (
                                  <div key={saveKey} className="ui-test-case-step-extract-row">
                                    <Form.Item
                                      {...saveFieldProps}
                                      noStyle={compact}
                                      name={[saveField.name, 'name']}
                                      className="ui-test-case-step-extract-name"
                                      extra={
                                        ownerStepIndex !== undefined && ownerStepIndex < index ? (
                                          <span className="ui-test-case-step-extract-warning">
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

                      {selectedStepIndex === undefined ? <div className="ui-test-case-step-footer">
                        <div className="ui-test-case-step-footer-grid">
                          <div className="ui-test-case-step-status-row">
                            <Form.Item
                              {...fieldProps}
                              name={[field.name, 'enabled']}
                              label="启用"
                              valuePropName="checked"
                              className="ui-test-case-step-inline-switch-item"
                            >
                              <Switch />
                            </Form.Item>
                            <Form.Item
                              {...fieldProps}
                              name={[field.name, 'continueOnFailure']}
                              label="失败后继续"
                              valuePropName="checked"
                              className="ui-test-case-step-inline-switch-item"
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
