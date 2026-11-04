import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import {
  EditOutlined,
  SaveOutlined
} from '@ant-design/icons'
import { Form, Input, Switch, Tooltip } from 'antd'

/*
 * 用例信息与运行操作放在步骤流程工具栏。
 * 导入与删除属于外层测试集流程：导入在测试集顶栏，删除在用例卡片菜单里，
 * 这里只保留当前用例的启用状态、调试运行与保存。
 */

type Props = {
  /** 形如 `CASE-02`；没有 orderNo 时为空。 */
  serial: string
  isCreatingCase: boolean
  stepCount: number
  watchedEnabled: boolean
  debugging: boolean
  saving: boolean
  onDebugRun: () => void
  onSave: () => void
}

export function UiCaseMetaBar({
  serial,
  isCreatingCase,
  stepCount,
  watchedEnabled,
  debugging,
  saving,
  onDebugRun,
  onSave,
}: Props) {
  return (
    <div className="ui-wb-case-meta ui-flow-case-meta">
      {serial ? <span className="ui-wb-case-serial">{serial}</span> : null}
      <Form.Item name="name" className="ui-test-case-name-item ui-wb-case-name-item" rules={[{ required: true, whitespace: true, message: '请输入 UI测试用例名称' }]}>
        <Input maxLength={120} placeholder="例如：登录成功验证" aria-label="用例名称" suffix={<EditOutlined className="ui-wb-case-name-icon" aria-hidden="true" />} />
      </Form.Item>
      <label className="ui-flow-case-enabled">
        <Form.Item name="enabled" valuePropName="checked" noStyle>
          <Switch size="small" aria-label="启用当前用例" />
        </Form.Item>
        <span className={`ui-flow-case-status${watchedEnabled ? ' tone-green' : ''}`}>{watchedEnabled ? '● 已启用' : '已停用'}</span>
      </label>
      <span className="ui-flow-case-count">{stepCount} 个步骤</span>
      <div className="ui-flow-case-actions">
        <Tooltip title={isCreatingCase ? '用例尚未保存，请先保存后再调试运行' : '对当前用例发起一次调试运行'}>
          <ProjectActionButton action="execute" operation="run" loading={debugging} disabled={isCreatingCase} onClick={onDebugRun}>调试运行</ProjectActionButton>
        </Tooltip>
        <ProjectActionButton action="write" type="primary" operation="save" icon={<SaveOutlined />} loading={saving} onClick={onSave}>保存</ProjectActionButton>
      </div>
    </div>
  )
}
