import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { Alert, Drawer, Form, Input, InputNumber, Select } from 'antd'
import type { FormInstance } from 'antd'
import { getErrorMessage } from '@/utils/format'
import { DEFAULT_UI_TEST_SUITE_RUN_CONFIG, UI_SCREENSHOT_POLICY_OPTIONS } from '../constants/defaultRunConfig'
import type { UiScreenshotPolicy } from '../types'

export type UiTestSuiteFormValues = {
  sprintId?: string
  requirementId?: string
  name: string
  description?: string
  headless?: boolean
  slowMoMs?: number
  viewportWidth?: number
  viewportHeight?: number
  defaultStepTimeoutMs?: number
  screenshotPolicy?: UiScreenshotPolicy
}

export function UiTestSuiteDrawer({
  title,
  open,
  form,
  loading,
  error,
  onClose,
  sprintOptions,
  requirementOptions,
  onSprintChange,
  onFinish,
}: {
  title: string
  open: boolean
  form: FormInstance
  loading: boolean
  error: unknown
  onClose: () => void
  sprintOptions?: Array<{ label: string; value: string }>
  requirementOptions?: Array<{ label: string; value: string }>
  onSprintChange?: (value?: string) => void
  onFinish: (values: UiTestSuiteFormValues) => void
}) {
  const watchedViewportWidth = Form.useWatch('viewportWidth', form)
  const watchedViewportHeight = Form.useWatch('viewportHeight', form)
  const concreteRequirementOptions = requirementOptions?.filter((option) => option.value !== 'all')

  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
      size={780}
      className="ui-test-suite-drawer"
      extra={
        <ProjectActionButton operation="save" action="write" type="primary" className="action-btn-save" loading={loading} onClick={() => form.submit()}>
          保存
        </ProjectActionButton>
      }
    >
      {error ? <Alert showIcon type="error" title={getErrorMessage(error)} /> : null}
      <Form<UiTestSuiteFormValues>
        form={form}
        layout="vertical"
        onFinish={onFinish}
        requiredMark={false}
        initialValues={DEFAULT_UI_TEST_SUITE_RUN_CONFIG}
      >
        <div className="ui-test-suite-drawer-shell">
          <div className="ui-test-suite-drawer-section">
            <div className="ui-test-suite-drawer-grid ui-test-suite-drawer-grid-2">
              {sprintOptions ? (
                <Form.Item name="sprintId" label="所属迭代" rules={[{ required: true, message: '请选择所属迭代' }]}>
                  <Select placeholder="请选择迭代" options={sprintOptions} onChange={onSprintChange} />
                </Form.Item>
              ) : null}
              {requirementOptions ? (
                <Form.Item name="requirementId" label="所属需求" rules={[{ required: true, message: '请选择所属需求' }]}>
                  <Select placeholder="请选择需求" options={concreteRequirementOptions} />
                </Form.Item>
              ) : null}
            </div>
          </div>

          <div className="ui-test-suite-drawer-section">
            <div className="ui-test-suite-drawer-grid ui-test-suite-drawer-grid-1">
              <Form.Item name="name" label="测试集名称" rules={[{ required: true, message: '请输入测试集名称' }]}>
                <Input maxLength={64} placeholder="例如：登录冒烟 / 支付主流程" />
              </Form.Item>
            </div>
          </div>

          <div className="ui-test-suite-drawer-section">
            <div className="ui-test-suite-drawer-grid ui-test-suite-drawer-config-grid">
              <Form.Item name="headless" label="运行模式">
                <Select
                  allowClear
                  placeholder="按需设置"
                  options={[
                    { label: '无头模式', value: true },
                    { label: '可视模式', value: false },
                  ]}
                />
              </Form.Item>

              <Form.Item name="slowMoMs" label="慢放延迟(ms)">
                <InputNumber min={0} style={{ width: '100%' }} placeholder="例如：300" />
              </Form.Item>

              <Form.Item
                name="defaultStepTimeoutMs"
                label="默认步骤超时(ms)"
                rules={[
                  {
                    validator: async (_, value) => {
                      if (value === undefined || value === null) return Promise.resolve()
                      if (value > 0) return Promise.resolve()
                      return Promise.reject(new Error('默认步骤超时必须大于 0'))
                    },
                  },
                ]}
              >
                <InputNumber min={1} style={{ width: '100%' }} placeholder="例如：5000" />
              </Form.Item>

              <Form.Item name="screenshotPolicy" label="步骤截图策略">
                <Select placeholder="请选择截图策略" options={UI_SCREENSHOT_POLICY_OPTIONS} />
              </Form.Item>

              <Form.Item
                name="viewportWidth"
                label="视口宽度"
                rules={[
                  {
                    validator: async (_, value) => {
                      if ((value === undefined || value === null) && (watchedViewportHeight === undefined || watchedViewportHeight === null)) {
                        return Promise.resolve()
                      }
                      if (value === undefined || value === null || watchedViewportHeight === undefined || watchedViewportHeight === null) {
                        return Promise.reject(new Error('视口宽高需要同时填写'))
                      }
                      if (value <= 0 || watchedViewportHeight <= 0) {
                        return Promise.reject(new Error('视口宽高必须大于 0'))
                      }
                      return Promise.resolve()
                    },
                  },
                ]}
              >
                <InputNumber min={1} style={{ width: '100%' }} placeholder="例如：1440" />
              </Form.Item>

              <Form.Item
                name="viewportHeight"
                label="视口高度"
                rules={[
                  {
                    validator: async (_, value) => {
                      if ((value === undefined || value === null) && (watchedViewportWidth === undefined || watchedViewportWidth === null)) {
                        return Promise.resolve()
                      }
                      if (value === undefined || value === null || watchedViewportWidth === undefined || watchedViewportWidth === null) {
                        return Promise.reject(new Error('视口宽高需要同时填写'))
                      }
                      if (value <= 0 || watchedViewportWidth <= 0) {
                        return Promise.reject(new Error('视口宽高必须大于 0'))
                      }
                      return Promise.resolve()
                    },
                  },
                ]}
              >
                <InputNumber min={1} style={{ width: '100%' }} placeholder="例如：900" />
              </Form.Item>
            </div>
          </div>

          <div className="ui-test-suite-drawer-section ui-test-suite-drawer-section-last">
            <div className="ui-test-suite-drawer-grid ui-test-suite-drawer-grid-1">
              <Form.Item name="description" label="描述">
                <Input.TextArea rows={4} maxLength={200} placeholder="补充这个 UI 测试集的目标、范围或备注" />
              </Form.Item>
            </div>
          </div>
        </div>
      </Form>
    </Drawer>
  )
}
