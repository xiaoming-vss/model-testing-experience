import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import {
  getUiStepFieldMeta,
  isValidUiStepComparator,
  isValidUiStepKeyword,
  isValidUiStepLocatorType,
  requiresUiStepLocator,
  uiTestComparatorOptions,
  uiTestKeywordOptions,
  uiTestLocatorTypeOptions,
  usesUiStepComparator,
  usesUiStepOperation
} from '@/features/ui-automation/config/stepConfig'
import { type UiTemplateFieldKey } from '@/features/ui-automation/utils/detailView'
import {
  type UiTestStepFormValue
} from '@/features/ui-automation/utils/uiTestCaseEditor'
import { DownOutlined, EditOutlined } from '@ant-design/icons'
import type { InputRef } from 'antd'
import { Empty, Form, Input, Select, Switch, Tooltip } from 'antd'

import type { ProjectAction } from '@/features/projects/types'
import type { JSX } from 'react'

type Props = {
  addStep: (add: (defaultValue?: UiTestStepFormValue | undefined, insertIndex?: number | undefined) => void, stepCount: number) => void
  watchedSteps: UiTestStepFormValue[]
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
}

export function UiStepEditor({ addStep, watchedSteps, expandedStepIndexes, draggingStepIndex, handleStepDrop, can, handleStepDragStart, setDraggingStepIndex, toggleStepPanel, removeStep, renderTemplatePickerLabel, bindTemplateInputRef }: Props) {
  return (
    <Form.List name="steps">
      {(fields, { add, remove, move }) => (
        <>
          {fields.length === 0 ? (
            <div className="ui-test-case-step-empty">
              <Empty description="当前还没有步骤">
                <ProjectActionButton action="write" type="dashed" operation="create" onClick={() => addStep(add, fields.length)}>
                  添加步骤
                </ProjectActionButton>
              </Empty>
            </div>
          ) : (
            <div className="ui-test-case-step-list">
              {fields.map((field, index) => {
                const { key: fieldKey, ...fieldProps } = field
                const step = watchedSteps[index]
                const stepKeyword = step?.keyword?.trim()
                const stepMeta = getUiStepFieldMeta(stepKeyword)
                const stepRequiresLocator = requiresUiStepLocator(stepKeyword)
                const stepUsesComparator = usesUiStepComparator(stepKeyword)
                const stepUsesOperation = usesUiStepOperation(stepKeyword)
                const showLocatorFields = stepRequiresLocator || Boolean(step?.locatorType?.trim() || step?.locatorValue?.trim())
                const showOperationField = stepUsesOperation || Boolean(step?.operationValue?.trim())
                const showLocatorTypeField = stepRequiresLocator || Boolean(step?.locatorType?.trim())
                const pairLocatorAndOperation = showLocatorFields && showOperationField
                const operationFieldLabel = stepMeta.operationLabel ? `操作值（${stepMeta.operationLabel}）` : '操作值'
                const locatorFieldHint = stepMeta.locatorHint || (stepRequiresLocator ? '当前关键字通常需要定位器。' : '')
                const operationFieldHint = stepMeta.operationHint || ''
                const locatorValueFieldClass = pairLocatorAndOperation ? 'ui-test-case-step-field-half' : 'ui-test-case-step-field-wide'
                const operationValueFieldClass = pairLocatorAndOperation
                  ? 'ui-test-case-step-field-half'
                  : stepUsesComparator
                    ? 'ui-test-case-step-field-half'
                    : 'ui-test-case-step-field-wide'
                const expanded = expandedStepIndexes.includes(index)
                const stepSummary = [
                  stepKeyword || '未设置关键字',
                  stepRequiresLocator ? step?.locatorType?.trim() || '待设定位' : step?.locatorType?.trim() || '无需定位',
                  stepUsesComparator ? step?.comparator?.trim() || '待设比较' : '',
                  step?.enabled === false ? '已禁用' : '已启用',
                ]
                  .filter(Boolean)
                  .join(' · ')

                return (
                  <div
                    key={fieldKey}
                    className={`ui-test-case-step-card${expanded ? ' expanded' : ''}${draggingStepIndex === index ? ' dragging' : ''}`}
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
                      draggable={can('write')}
                      onDragStart={(event) => handleStepDragStart(event, index)}
                      onDragEnd={() => setDraggingStepIndex(null)}
                      onClick={() => toggleStepPanel(index)}
                    >
                      <div className="ui-test-case-step-card-main">
                        <div className="ui-test-case-step-card-leading">
                          <button
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
                          </button>
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
                              name={[field.name, 'stepName']}
                              className="ui-test-case-step-title-item"
                              rules={[{ required: true, whitespace: true, message: '请输入步骤名称' }]}
                            >
                              <Input
                                placeholder="点击输入步骤名称"
                                maxLength={120}
                                className="ui-test-case-step-title-input"
                                suffix={<EditOutlined className="ui-test-case-step-title-edit-icon" />}
                              />
                            </Form.Item>
                          </div>
                          <span>{stepSummary}</span>
                        </div>
                      </div>
                      <div className="ui-test-case-step-actions" onClick={(event) => event.stopPropagation()}>
                        <Tooltip title="删除步骤">
                          <ProjectActionButton action="write"
                            type="text"
                            size="small"
                            className="ui-test-case-step-delete-action action-btn-delete"
                            operation="delete" iconOnly
                            onClick={() => removeStep(remove, index)}
                          />
                        </Tooltip>
                      </div>
                    </div>

                    <div className="ui-test-case-step-body" hidden={!expanded} aria-hidden={!expanded}>
                      <div className="ui-test-case-step-grid ui-test-case-step-core-grid">
                        <Form.Item
                          {...fieldProps}
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
                          <Select
                            showSearch
                            placeholder="请选择关键字"
                            options={uiTestKeywordOptions}
                            optionFilterProp="label"
                          />
                        </Form.Item>
                        <Form.Item
                          {...fieldProps}
                          name={[field.name, 'locatorType']}
                          label="定位方式"
                          hidden={!showLocatorTypeField}
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
                          <Select
                            showSearch
                            placeholder={stepRequiresLocator ? '请选择定位方式' : '按需选择定位方式'}
                            options={uiTestLocatorTypeOptions}
                            optionFilterProp="label"
                            allowClear={!stepRequiresLocator}
                          />
                        </Form.Item>
                      </div>

                      <div className="ui-test-case-step-detail-grid">
                        <div
                          className="ui-test-case-step-field-note ui-test-case-step-field-wide"
                          hidden={!showLocatorTypeField || !locatorFieldHint}
                        >
                          {locatorFieldHint}
                        </div>

                        <Form.Item
                          {...fieldProps}
                          name={[field.name, 'locatorValue']}
                          label={renderTemplatePickerLabel(field.name, 'locatorValue', '定位值')}
                          hidden={!showLocatorFields}
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
                          <Input
                            ref={bindTemplateInputRef(field.name, 'locatorValue')}
                            placeholder={stepRequiresLocator ? '例如：#username' : '按需填写'}
                            maxLength={400}
                          />
                        </Form.Item>

                        <Form.Item
                          {...fieldProps}
                          name={[field.name, 'operationValue']}
                          label={renderTemplatePickerLabel(field.name, 'operationValue', operationFieldLabel)}
                          hidden={!showOperationField}
                          className={`ui-test-case-step-field ${operationValueFieldClass}`}
                          dependencies={[['steps', field.name, 'keyword']]}
                          rules={[
                            ({ getFieldValue }) => ({
                              validator(_, value: string | undefined) {
                                const keyword = getFieldValue(['steps', field.name, 'keyword'])
                                const trimmedValue = value?.trim()

                                if (keyword === 'open') {
                                  if (!trimmedValue) {
                                    return Promise.reject(new Error('open 步骤请填写完整 URL'))
                                  }
                                  if (/^https?:\/\//i.test(trimmedValue)) {
                                    return Promise.resolve()
                                  }
                                  return Promise.reject(new Error('open 步骤请填写完整 URL'))
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

                                if (keyword === 'sleep' || keyword === 'assert_visible') {
                                  if (!trimmedValue) {
                                    return Promise.reject(new Error(`${keyword} 步骤请填写毫秒数`))
                                  }
                                  if (/^\d+$/.test(trimmedValue)) {
                                    return Promise.resolve()
                                  }
                                  return Promise.reject(new Error(`${keyword} 步骤请填写非负整数毫秒数`))
                                }

                                if (!trimmedValue) {
                                  return Promise.resolve()
                                }

                                return Promise.resolve()
                              },
                            }),
                          ]}
                        >
                          <Input
                            ref={bindTemplateInputRef(field.name, 'operationValue')}
                            placeholder={stepMeta.operationPlaceholder || '例如：tester'}
                            maxLength={400}
                          />
                        </Form.Item>

                        <div
                          className="ui-test-case-step-field-note ui-test-case-step-field-wide"
                          hidden={!showOperationField || !operationFieldHint}
                        >
                          {operationFieldHint}
                        </div>

                        <Form.Item
                          {...fieldProps}
                          name={[field.name, 'comparator']}
                          label="比较器"
                          hidden={!stepUsesComparator}
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
                          <Select placeholder="请选择比较器" options={uiTestComparatorOptions} />
                        </Form.Item>
                      </div>

                      <div className="ui-test-case-step-footer">
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
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          <div className="ui-test-case-step-add-row">
            <ProjectActionButton action="write" type="dashed" operation="create" onClick={() => addStep(add, fields.length)}>
              添加步骤
            </ProjectActionButton>
          </div>
        </>
      )}
    </Form.List>
  )
}
