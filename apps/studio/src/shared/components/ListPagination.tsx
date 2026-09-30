import { Pagination, Typography } from 'antd'
import zhCN from 'antd/es/locale/zh_CN'
import { useEffect } from 'react'
import { footerRange, PAGE_SIZE_OPTIONS } from '@/shared/utils/pagination'
import '@/shared/styles/pagination.css'

interface ListPaginationProps {
  current: number
  pageSize: number
  total: number
  loading?: boolean
  onChange: (page: number, pageSize: number) => void
}

/** Shared list footer contents. The owning page supplies its table-footer container. */
export function ListPagination({ current, pageSize, total, loading = false, onChange }: ListPaginationProps) {
  const validPage = Math.max(1, Math.min(current, Math.ceil(total / pageSize) || 1))

  useEffect(() => {
    if (!loading && current !== validPage) onChange(validPage, pageSize)
  }, [current, validPage, pageSize, loading, onChange])

  return <>
    <Typography.Text type="secondary">{footerRange(total, validPage, pageSize)}</Typography.Text>
    <Pagination
      current={validPage}
      pageSize={pageSize}
      total={total}
      size="middle"
      showSizeChanger
      showQuickJumper={false}
      hideOnSinglePage={false}
      pageSizeOptions={PAGE_SIZE_OPTIONS}
      locale={{ ...zhCN.Pagination, items_per_page: '条/页', page_size: '每页条数' }}
      disabled={loading}
      onChange={(page, size) => onChange(size === pageSize ? page : 1, size)}
    />
  </>
}
