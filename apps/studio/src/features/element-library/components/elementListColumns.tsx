import { AppstoreOutlined, CodeOutlined } from '@ant-design/icons'
import { Popconfirm, Space, Tooltip } from 'antd'
import type { TableProps } from 'antd'
import { ActionButton } from '@/shared/components/ActionButton'
import { actionsColumnTitleClass } from '@/shared/utils/surfaceClasses'
import { cx } from '@/shared/utils/cx'
import type { ElementWorkspaceModel } from '../hooks/useElementWorkspace'
import { VerificationBadge } from './ElementDetails'
import {
  elementLocatorChipClass,
  elementNameButtonClass,
  elementNameIconClass,
  elementNameIconParameterizedClass,
} from './elementLibraryClasses'
import { locatorTypeLabels, type ElementGroup, type ElementSummary } from '../types'

/** 元素表列：名称（图标 + 参数标签）、分组 / 作用范围、定位方式、验证状态、行内操作。 */
export function buildElementListColumns({ page, canWrite, showGroup, groups }: {
  page: ElementWorkspaceModel
  canWrite: boolean
  showGroup: boolean
  groups: ElementGroup[]
}): TableProps<ElementSummary>['columns'] {
  const { setSelected, openEditorById, deleteElement } = page

  return [
    {
      title: '元素名称',
      key: 'name',
      width: 300,
      render: (_, item) => (
        <div className="flex min-w-0 items-center gap-2">
          <span
            aria-hidden="true"
            className={cx(elementNameIconClass, item.parameterized && elementNameIconParameterizedClass)}
          >
            {item.parameterized ? <CodeOutlined /> : <AppstoreOutlined />}
          </span>
          <button type="button" title={item.name} onClick={() => setSelected(item.elementId)} className={elementNameButtonClass}>
            {item.name}
          </button>
          {item.parameterized ? <span className="tp-tone-tag tone-blue flex-none">参数</span> : null}
        </div>
      ),
    },
    {
      title: showGroup ? '分组 / 作用范围' : '作用范围',
      key: 'scope',
      render: (_, item) => (
        <span className="[overflow-wrap:anywhere]">
          {showGroup ? (
            <span className="text-[var(--srf-text-secondary)]">
              {groups.find(candidate => candidate.groupId === item.groupId)?.name}
              <span aria-hidden="true"> · </span>
            </span>
          ) : null}
          {item.scope}
        </span>
      ),
    },
    {
      title: '定位',
      key: 'locator',
      width: 132,
      render: (_, item) => <code className={elementLocatorChipClass}>{locatorTypeLabels[item.locatorType]}</code>,
    },
    {
      title: '验证状态',
      key: 'state',
      width: 132,
      render: (_, item) => <VerificationBadge status={item.verificationStatus} />,
    },
    {
      title: <span className={actionsColumnTitleClass} style={{ width: 64 }}>操作</span>,
      key: 'actions',
      width: 110,
      align: 'right',
      render: (_, item) => (
        <Space
          size={8}
          className="justify-end"
          onClick={event => event.stopPropagation()}
          onMouseDown={event => event.stopPropagation()}
        >
          <Tooltip title="编辑元素">
            <ActionButton
              operation="edit"
              iconOnly
              aria-label={`编辑元素：${item.name}`}
              disabled={!canWrite}
              onClick={() => void openEditorById(item.elementId)}
            />
          </Tooltip>
          <Popconfirm
            title="确认删除该元素？"
            description="删除后不可恢复，引用该元素的用例需要重新选择定位。"
            okText="确认删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            disabled={!canWrite}
            onConfirm={() => deleteElement.mutate(item)}
          >
            <Tooltip title="删除元素">
              <ActionButton
                operation="delete"
                iconOnly
                aria-label={`删除元素：${item.name}`}
                disabled={!canWrite}
                loading={deleteElement.isPending && deleteElement.variables?.elementId === item.elementId}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]
}
