import { FlagOutlined, ProfileOutlined } from '@ant-design/icons'
import { AutoComplete, Form, Input, Select, Tag, Typography } from 'antd'
import type { FormInstance } from 'antd'
import { formatTime, pickCreatedAt, pickUpdatedAt } from '@/utils/format'
import type { FunctionCaseLibraryItem } from '../types'
import type { FunctionCaseFormValues } from '../utils/caseForm'
import { FunctionCaseContentEditor } from './FunctionCaseContentEditor'

const { Text } = Typography

const priorityOptions = ['P0', 'P1', 'P2', 'P3'].map((value) => ({ label: value, value }))
const caseTypeOptions = ['功能测试', '异常测试', '边界测试', '流程测试', '兼容测试', '安全测试'].map((value) => ({
  label: value,
  value,
}))

/**
 * 功能用例正文表单。点开用例直接就是它，没有只读态、没有抽屉。
 * 表单实例与保存动作由调用方持有，保存 / 删除按钮放在页面头部。
 */
export function FunctionCaseEditor({
  form,
  isCreate,
  item,
  onSubmit,
}: {
  form: FormInstance<FunctionCaseFormValues>
  isCreate: boolean
  item?: FunctionCaseLibraryItem | null
  onSubmit: (values: FunctionCaseFormValues) => void
}) {
  return (
    <Form<FunctionCaseFormValues>
      form={form}
      layout="vertical"
      requiredMark={false}
      className="functional-case-editor-form"
      onFinish={onSubmit}
    >
      <div className="functional-case-editor-body">
        <div className="functional-case-editor-hero">
          <div className="functional-case-title-row">
            <Text className="functional-case-inline-label">用例名称</Text>
            {isCreate ? <Tag color="processing">未保存</Tag> : null}
          </div>
          <Form.Item
            name="title"
            className="functional-case-name-item"
            rules={[{ required: true, message: '请输入用例标题' }]}
          >
            <Input
              className="functional-case-title-input"
              placeholder="例如：用户使用正确账号密码登录成功"
            />
          </Form.Item>
          {isCreate ? null : (
            <div className="functional-case-title-meta">
              <Text type="secondary">
                创建时间：{formatTime(pickCreatedAt(item ?? undefined)) || '-'}
              </Text>
              <Text type="secondary">
                更新时间：{formatTime(pickUpdatedAt(item ?? undefined)) || '-'}
              </Text>
            </div>
          )}
        </div>

        <div className="functional-case-form-grid functional-case-editor-grid functional-case-meta-panel">
          <Form.Item
            name="priority"
            label={
              <span className="functional-case-meta-label">
                <FlagOutlined />
                优先级
              </span>
            }
          >
            <Select allowClear options={priorityOptions} placeholder="请选择优先级" />
          </Form.Item>
          <Form.Item
            name="caseType"
            label={
              <span className="functional-case-meta-label">
                <ProfileOutlined />
                用例类型
              </span>
            }
          >
            <AutoComplete allowClear options={caseTypeOptions} placeholder="请选择或输入用例类型" />
          </Form.Item>
        </div>

        <FunctionCaseContentEditor />
      </div>
    </Form>
  )
}
