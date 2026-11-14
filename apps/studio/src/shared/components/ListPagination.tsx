import { Pagination, Typography } from 'antd'
import zhCN from 'antd/es/locale/zh_CN'
import { useEffect, useId } from 'react'
import { footerRange, PAGE_SIZE_OPTIONS } from '@/shared/utils/pagination'
import '@/shared/styles/pagination.css'

interface ListPaginationProps {
  current: number
  pageSize: number
  total: number
  loading?: boolean
  /** 窄侧栏/工具栏使用：只渲染分页控件，不渲染“显示第…条”整句。 */
  compact?: boolean
  onChange: (page: number, pageSize: number) => void
}

/** Shared list pagination. Footer mode also renders the range sentence. */
export function ListPagination({ current, pageSize, total, loading = false, compact = false, onChange }: ListPaginationProps) {
  const pageSizeControlId = useId()
  const validPage = Math.max(1, Math.min(current, Math.ceil(total / pageSize) || 1))

  useEffect(() => {
    if (!loading && current !== validPage) onChange(validPage, pageSize)
  }, [current, validPage, pageSize, loading, onChange])

  const paginationLocale = { ...zhCN.Pagination, items_per_page: '条/页', page_size: '每页条数' }
  const pagination = <Pagination
    className={compact ? 'list-pagination-compact' : undefined}
    current={validPage}
    pageSize={pageSize}
    total={total}
    size={compact ? 'small' : 'middle'}
    showSizeChanger={{ id: pageSizeControlId, 'aria-label': '每页条数' }}
    showQuickJumper={false}
    showLessItems={compact}
    hideOnSinglePage={false}
    pageSizeOptions={PAGE_SIZE_OPTIONS}
    locale={paginationLocale}
    disabled={loading}
    onChange={(page, size) => onChange(size === pageSize ? page : 1, size)}
  />

  if (compact) return pagination

  return <>
    <Typography.Text type="secondary">{footerRange(total, validPage, pageSize)}</Typography.Text>
    {pagination}
  </>
}
