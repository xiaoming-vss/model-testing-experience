import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import {
  OrderedListOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined,
  SaveOutlined
} from '@ant-design/icons'
import { Button, Form, Input, Popconfirm, Switch, Tooltip } from 'antd'

/*
 * 用例信息条：序号徽标 + 用例名 + 调试运行/保存，第二行是启用状态、步骤数与导入/删除。
 *
 * 设计稿第二行还有「前置通过率: 100%」——用例没有前置通过与率的模型（见 STRUCTURE.md），
 * 这里只保留真实的步骤数。这个组件必须渲染在 UiTestSuiteCasePage 的 <Form> 内部，
 * 它持有 `name` 与 `enabled` 两个字段。样式见 styles/detail-pipeline-v2.css。
 */

type Props = {
  /** 形如 `CASE-02`；没有 orderNo 时为空。 */
  serial: string
  isCreatingCase: boolean
  stepCount: number
  watchedEnabled: boolean
  debugging: boolean
  saving: boolean
  deleting: boolean
  importDisabled: boolean
  deleteDisabled: boolean
  onDebugRun: () => void
  onSave: () => void
  onImport: () => void
  onDelete: () => void
}

export function UiCaseMetaBar({
  serial,
  isCreatingCase,
  stepCount,
  watchedEnabled,
  debugging,
  saving,
  deleting,
  importDisabled,
  deleteDisabled,
  onDebugRun,
  onSave,
  onImport,
  onDelete,
}: Props) {
  return (
    <section className="ui-wb-case-meta">
      <div className="ui-wb-case-meta-head">
        {serial ? <span className="ui-wb-case-serial">{serial}</span> : null}
        <Form.Item
          name="name"
          className="ui-test-case-name-item ui-wb-case-name-item"
          rules={[{ required: true, whitespace: true, message: '请输入 UI测试用例名称' }]}
        >
          <Input
            maxLength={120}
            placeholder="例如：登录成功验证"
            aria-label="用例名称"
            suffix={<EditOutlined className="ui-wb-case-name-icon" aria-hidden="true" />}
          />
        </Form.Item>
        <div className="ui-wb-case-meta-actions">
          <Tooltip title={isCreatingCase ? '用例尚未保存，请先保存后再调试运行' : '对当前用例发起一次调试运行'}>
            <ProjectActionButton
              action="execute"
              className="ui-wb-case-debug action-btn-read"
              operation="run"
              icon={<PlayCircleOutlined />}
              loading={debugging}
              disabled={isCreatingCase}
              onClick={onDebugRun}
            >
              调试运行
            </ProjectActionButton>
          </Tooltip>
          <ProjectActionButton
            action="write"
            type="primary"
            className="ui-wb-case-save action-btn-save"
            operation="save"
            icon={<SaveOutlined />}
            loading={saving}
            onClick={onSave}
          >
            保存
          </ProjectActionButton>
        </div>
      </div>

      <div className="ui-wb-case-meta-sub" aria-live="polite">
        <div className="ui-wb-case-meta-flags">
          <Form.Item name="enabled" valuePropName="checked" className="ui-wb-case-enabled-item">
            <Switch size="small" aria-label="启用当前用例" />
          </Form.Item>
          <span className="ui-wb-case-enabled-text">{watchedEnabled ? '当前用例已启用' : '当前用例已停用'}</span>
          <span className="ui-wb-case-meta-sep" aria-hidden="true">·</span>
          <span className="ui-wb-case-step-count">
            <OrderedListOutlined aria-hidden="true" />
            包含 {stepCount} 个步骤
          </span>
        </div>

        <div className="ui-wb-case-meta-links">
          <Button type="text" size="small" className="ui-wb-case-link" icon={<CloudUploadOutlined />} disabled={importDisabled} onClick={onImport}>
            用例导入
          </Button>
          <Popconfirm
            title={isCreatingCase ? '确认丢弃这个未保存用例？' : '确认删除该 UI测试用例？'}
            onConfirm={onDelete}
          >
            <Button
              type="text"
              size="small"
              danger
              className="ui-wb-case-link ui-wb-case-delete action-btn-delete"
              icon={<DeleteOutlined />}
              loading={deleting}
              disabled={deleteDisabled}
            >
              删除用例
            </Button>
          </Popconfirm>
        </div>
      </div>
    </section>
  )
}
