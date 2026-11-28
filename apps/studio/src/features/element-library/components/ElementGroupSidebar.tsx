import {
  AppstoreOutlined,
  FolderOpenOutlined,
  FolderOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons'
import { Alert, Popconfirm } from 'antd'
import type { ReactNode } from 'react'
import { ActionButton } from '@/shared/components/ActionButton'
import { getErrorMessage } from '@/utils/format'
import { cx } from '@/shared/utils/cx'
import { all, common, type ElementWorkspaceModel } from '../hooks/useElementWorkspace'
import {
  elementNavListClass,
  elementNavSectionLabelClass,
  elementSidebarBodyClass,
  elementSidebarFootClass,
  elementSidebarHeadClass,
  elementSidebarShellClass,
  elementSidebarTitleClass,
} from './elementLibraryClasses'

/**
 * 元素库左栏：页面分组目录卡片。
 * 结构对齐用例库「测试集导航」——标题 + 计数、单行条目、底部新建 / 删除。
 */
export function ElementGroupSidebar({ page, canWrite }: { page: ElementWorkspaceModel; canWrite: boolean }) {
  const { entries, group, selectGroup, activeGroup, deleteGroup, setGroupModal, createGroup, groupsQuery } = page
  const fixed = entries.slice(0, 2)
  const pages = entries.slice(2)
  // 公共组随元素写入创建、供跨页面共享，不提供删除；只有页面分组可以删。
  const pageSelected = activeGroup?.kind === 'page'
  const blocked = (activeGroup?.elementCount ?? 0) > 0
  const canDelete = pageSelected && !blocked
  const deleteHint = !activeGroup
    ? '先在左栏选中一个页面分组'
    : !pageSelected ? '公共元素分组不能删除'
      : blocked ? '分组内还有元素，不能删除' : '删除分组'

  return (
    <aside aria-label="页面分组" className={elementSidebarShellClass}>
      <div className={elementSidebarHeadClass}>
        <FolderOpenOutlined className="text-[var(--srf-text-secondary)]" aria-hidden="true" />
        <span className={elementSidebarTitleClass}>页面分组</span>
        <span className="ml-auto rounded-[4px] bg-[var(--srf-chip)] px-1.5 py-0.5 font-mono text-[12px] leading-[16px] text-[var(--srf-text-secondary)]">
          {pages.length}
        </span>
      </div>

      <nav className={elementSidebarBodyClass} aria-label="分组列表">
        {groupsQuery.isError ? (
          <Alert
            showIcon
            type="error"
            title="分组加载失败"
            description={getErrorMessage(groupsQuery.error)}
            action={<ActionButton operation="refresh" iconOnly aria-label="重新加载分组" onClick={() => void groupsQuery.refetch()} />}
          />
        ) : (
          <div className={elementNavListClass}>
            {fixed.map(item => (
              <GroupRow
                key={item.key}
                name={item.name}
                count={item.count}
                active={group === item.key}
                icon={item.key === all.key ? <UnorderedListOutlined /> : <AppstoreOutlined />}
                onSelect={() => selectGroup(item.key)}
                hint={item.key === common.key ? '公共元素' : '全部元素'}
              />
            ))}
            <p className={elementNavSectionLabelClass}>页面</p>
            {pages.length === 0 ? (
              <p className="m-0 px-2.5 py-1 text-[12px] leading-[18px] text-[var(--srf-text-secondary)]">还没有页面分组</p>
            ) : pages.map(item => (
              <GroupRow
                key={item.key}
                name={item.name}
                count={item.count}
                active={group === item.key}
                icon={group === item.key ? <FolderOpenOutlined /> : <FolderOutlined />}
                onSelect={() => selectGroup(item.key)}
                hint={item.route ? `${item.name} · ${item.route}` : item.name}
              />
            ))}
          </div>
        )}
      </nav>

      {canWrite && (
        <div className={elementSidebarFootClass}>
          <ActionButton
            operation="create"
            type="text"
            size="small"
            className="px-0 text-xs"
            disabled={groupsQuery.isError}
            onClick={() => {
              createGroup.reset()
              setGroupModal(true)
            }}
          >
            新建分组
          </ActionButton>
          <span className="ml-auto inline-flex">
            <Popconfirm
              title="删除该页面分组？"
              description="分组下还有元素时不能删除。"
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true, loading: deleteGroup.isPending }}
              disabled={!canDelete}
              onConfirm={() => activeGroup && deleteGroup.mutate(activeGroup.groupId)}
            >
              <ActionButton
                operation="delete"
                iconOnly
                aria-label="删除分组"
                title={deleteHint}
                disabled={!canDelete}
                loading={deleteGroup.isPending}
              />
            </Popconfirm>
          </span>
        </div>
      )}
    </aside>
  )
}

function GroupRow({ name, count, active, icon, hint, onSelect }: {
  name: string
  count: number
  active: boolean
  icon: ReactNode
  hint: string
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active || undefined}
      title={hint}
      className={cx(
        // 未引入 preflight，裸 button 会保留 UA 的 ButtonFace 底色（深色下是亮灰块），必须显式透明。
        'group flex w-full cursor-pointer appearance-none items-center justify-between gap-2 rounded-[var(--srf-radius-control)] border border-transparent px-2.5 py-1.5 text-left font-[inherit] text-inherit transition-colors',
        active ? 'border-[var(--srf-accent-border)] bg-[var(--srf-accent-soft)]' : 'bg-transparent hover:bg-[var(--srf-hover)]',
      )}
    >
      <span className="flex min-w-0 items-center gap-2">
        <span
          aria-hidden="true"
          className={cx('flex-none text-[16px]', active ? 'text-[var(--srf-accent)]' : 'text-[var(--srf-folder)]')}
        >
          {icon}
        </span>
        <span
          className={cx(
            'min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[12px] leading-[18px]',
            active
              ? 'font-semibold text-[var(--srf-accent-strong)]'
              : 'font-medium text-[var(--srf-text-secondary)] group-hover:text-[var(--srf-text)]',
          )}
        >
          {name}
        </span>
      </span>
      <span
        className={cx(
          'flex-none rounded-[4px] px-1.5 py-0.5 font-mono text-[12px] leading-[16px]',
          active ? 'bg-[var(--srf-count-badge)] text-[var(--srf-accent-strong)]' : 'text-[var(--srf-text-secondary)]',
        )}
      >
        {count}
      </span>
    </button>
  )
}
