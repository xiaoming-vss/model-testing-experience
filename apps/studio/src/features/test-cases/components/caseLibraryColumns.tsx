import { Popconfirm, Space, Tooltip, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useMemo } from 'react'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { formatCasePriority } from '../utils/casePriority'
import { caseTypeTone } from '../utils/caseTone'
import { priorityTone } from '@/shared/utils/priorityTone'
import { normalizeFunctionTestCaseId } from '@/utils/format'
import { formatTime, pickUpdatedAt } from '@/utils/format'
import type { FunctionCaseLibraryItem } from '@/services/api'
import type { CaseLibraryPageModel } from '../hooks/useCaseLibraryPage'

const { Text } = Typography

export function useCaseLibraryColumns(page: CaseLibraryPageModel) {
  const { deleteCaseMutation, suiteId, openEditCase } = page

  return useMemo(() => {
    const items: TableProps<FunctionCaseLibraryItem>['columns'] = [
      {
        title: '用例标题',
        key: 'title',
        render: (_, item) => {
          const caseId = normalizeFunctionTestCaseId(item)
          return (
            <Space size={8} className="tp-list-name functional-suite-list-name case-library-title-cell w-full min-w-0">
              {caseId ? (
                <span className="case-library-id-chip flex-none rounded-[4px] bg-[var(--srf-chip)] px-1.5 py-0.5 font-mono text-[11px] leading-[16px] text-[var(--srf-text-muted)]" title={caseId}>
                  {caseId.slice(0, 8)}
                </span>
              ) : null}
              <Tooltip title={item.title}>
                <Text ellipsis>{item.title}</Text>
              </Tooltip>
            </Space>
          )
        },
      },
    ]
    if (!suiteId) {
      items.push({
        title: '所属测试集',
        key: 'suiteName',
        width: 200,
        ellipsis: true,
        render: (_, item) => (
          <Tooltip title={item.suiteName}>
            <Text className="functional-suite-list-scope" ellipsis>
              {item.suiteName || '-'}
            </Text>
          </Tooltip>
        ),
      })
    }
    items.push(
      {
        title: '优先级',
        key: 'priority',
        width: 90,
        align: 'center',
        render: (_, item) =>
          item.priority !== undefined && item.priority !== null && String(item.priority).trim() !== '' ? (
            <span className={`case-library-priority inline-flex min-w-7 box-border items-center justify-center rounded-[4px] border border-[var(--srf-tone-border,transparent)] bg-[var(--srf-tone-bg,var(--srf-chip))] px-1.5 py-0.5 font-mono text-[10px] font-bold leading-[16px] text-[var(--srf-tone-text,var(--srf-chip-text))] tone-${priorityTone(item.priority)}`}>
              {formatCasePriority(item.priority)}
            </span>
          ) : (
            <Text type="secondary">-</Text>
          ),
      },
      {
        title: '用例类型',
        key: 'caseType',
        width: 156,
        ellipsis: true,
        render: (_, item) =>
          item.caseType ? (
            <span title={item.caseType} className={`tp-tone-tag case-library-type-tag inline-block align-middle max-w-full tone-${caseTypeTone(item.caseType)}`}>
              {item.caseType}
            </span>
          ) : (
            <Text type="secondary">-</Text>
          ),
      },
      {
        title: '最近更新',
        key: 'updatedAt',
        width: 180,
        render: (_, item) => (
          <Text className="functional-suite-list-time case-library-time-cell font-mono text-[11px] text-[var(--srf-text-muted)]" type="secondary">
            {formatTime(pickUpdatedAt(item))}
          </Text>
        ),
      },
      {
        title: <span className="tp-actions-col-title inline-block text-center" style={{ width: 64 }}>操作</span>,
        key: 'actions',
        width: 110,
        align: 'right',
        render: (_, item) => (
          <Space
            size={8}
            className="functional-suite-list-actions case-library-row-actions justify-end"
            onClick={(event) => event.stopPropagation()}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <Tooltip title="编辑用例">
              <ProjectActionButton
                action="write"
                type="text"
                shape="circle"
                className="action-btn-update"
                operation="edit"
                iconOnly
                aria-label="编辑用例"
                disabled={!item.caseId}
                onClick={() => openEditCase(item)}
              />
            </Tooltip>
            <Popconfirm
              title="确认删除该用例？"
              description="删除后不可恢复。"
              okText="确认删除"
              okButtonProps={{ danger: true }}
              onConfirm={() => item.caseId && deleteCaseMutation.mutate(item.caseId)}
            >
              <Tooltip title="删除用例">
                <ProjectActionButton
                  action="write"
                  type="text"
                  shape="circle"
                  danger
                  className="action-btn-delete"
                  operation="delete"
                  iconOnly
                  aria-label="删除用例"
                  disabled={!item.caseId}
                  loading={
                    deleteCaseMutation.isPending && deleteCaseMutation.variables === item.caseId
                  }
                />
              </Tooltip>
            </Popconfirm>
          </Space>
        ),
      },
    )
    return items
  }, [deleteCaseMutation, openEditCase, suiteId])
}
