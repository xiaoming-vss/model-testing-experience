import { Alert, Button, Table } from 'antd'
import { ListEmptyState } from '@/shared/components/ListEmptyState'
import { ListPagination } from '@/shared/components/ListPagination'
import { listItems, listTotal } from '@/shared/api/request'
import { tableFooterClass, tableScrollClass } from '@/shared/utils/surfaceClasses'
import { cx } from '@/shared/utils/cx'
import { getErrorMessage } from '@/utils/format'
import { all, type ElementWorkspaceModel } from '../hooks/useElementWorkspace'
import { buildElementListColumns } from './elementListColumns'
import {
  elementCardShellClass,
  elementCountStrongClass,
  elementMetaTextClass,
  elementQuickBarClass,
  elementQuickBarMainClass,
  elementRouteChipClass,
  elementScopeTitleClass,
  elementStatusChipsClass,
  elementTableScrollClass,
} from './elementLibraryClasses'
import type { ElementSummary } from '../types'

const statusOptions = [
  { value: 'all', label: '全部' },
  { value: 'verified', label: '已验证' },
  { value: 'pending', label: '待验证' },
] as const

/**
 * 元素库右栏：快速过滤条 + 元素表 + 固定分页。
 * 行点击打开详情抽屉；定位值不在列表契约里，只在抽屉展示。
 */
export function ElementListCard({ page, canWrite }: { page: ElementWorkspaceModel; canWrite: boolean }) {
  const {
    current, group, groups, keyword, status, setStatus, setPage, setSelected, selected,
    list, listEnabled, page: currentPage, pageSize, setPageSize, clearFilters, openEditor,
  } = page
  const columns = buildElementListColumns({ page, canWrite, showGroup: group === all.key, groups })

  return (
    <div className={elementCardShellClass}>
      <div className={elementQuickBarClass}>
        <div className={elementQuickBarMainClass}>
          <span className="flex min-w-0 items-baseline gap-2">
            <span className={elementScopeTitleClass}>{current.name}</span>
            {current.route && <code className={elementRouteChipClass}>{current.route}</code>}
          </span>
          <span aria-hidden="true" className="h-4 w-px bg-[var(--srf-divider)]" />
          <div role="group" aria-label="按验证状态筛选" className={elementStatusChipsClass}>
            {statusOptions.map(option => (
              <button
                key={option.value}
                type="button"
                className={cx('tp-chip', status === option.value && 'active')}
                aria-pressed={status === option.value}
                onClick={() => {
                  setStatus(option.value)
                  setPage(1)
                  setSelected('')
                }}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        <span className={elementMetaTextClass} aria-live="polite">
          {!listEnabled
            ? '该分组已不存在'
            : list.isPending
              ? '正在加载元素…'
              : list.isError
                ? '数量暂不可用'
                : <>共 <strong className={elementCountStrongClass}>{listTotal(list.data)}</strong> 条元素</>}
        </span>
      </div>

      <div className={cx(elementTableScrollClass, tableScrollClass)}>
        {listEnabled && list.isError ? (
          <Alert
            showIcon
            type="error"
            title="元素库加载失败"
            description={getErrorMessage(list.error)}
            action={<Button onClick={() => void list.refetch()}>重试</Button>}
          />
        ) : null}
        <Table<ElementSummary>
          rowKey="elementId"
          className="tp-list-table"
          columns={columns}
          dataSource={listEnabled ? listItems(list.data) : []}
          tableLayout="fixed"
          scroll={{ x: 880 }}
          pagination={false}
          loading={listEnabled && list.isPending}
          rowClassName={item => (item.elementId === selected ? 'cursor-pointer bg-[var(--srf-list-row-hover)]' : 'cursor-pointer')}
          onRow={item => ({ onClick: () => setSelected(item.elementId) })}
          locale={{
            emptyText: (
              <ListEmptyState description={keyword || status !== 'all' ? '没有匹配的元素' : '这个分组还没有元素'}>
                {keyword || status !== 'all' ? (
                  <Button onClick={clearFilters}>清除筛选</Button>
                ) : canWrite ? (
                  <Button onClick={() => openEditor()}>新建元素</Button>
                ) : null}
              </ListEmptyState>
            ),
          }}
        />
      </div>

      <div className={cx('table-footer', tableFooterClass)}>
        {!listEnabled ? (
          <span className={elementMetaTextClass}>该分组已不存在</span>
        ) : list.isPending ? (
          <span className={elementMetaTextClass}>正在加载元素…</span>
        ) : (
          <ListPagination
            total={listTotal(list.data)}
            current={currentPage}
            pageSize={pageSize}
            loading={list.isFetching || list.isError}
            onChange={(next, size) => {
              setPageSize(size)
              setPage(size === pageSize ? next : 1)
              setSelected('')
            }}
          />
        )}
      </div>
    </div>
  )
}
