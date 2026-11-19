import {
  ArrowLeftOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { Button, Tag, Tooltip } from 'antd'
import { MethodBadge } from '@/shared/components/MethodBadge'
import { formatTime } from '@/utils/format'
import type { InterfaceDetailPageModel } from '../hooks/useInterfaceDetailPage'

export function InterfaceDetailTopbar({ page }: { page: InterfaceDetailPageModel }) {
  const {
    draft,
    interfaceId,
    isCreate,
    canWrite,
    navigate,
    interfaceQuery,
    repositories,
    selectedRepository,
    setImportOpen,
    confirmDelete,
  } = page
  const queryClient = useQueryClient()

  if (!draft) return null

  return (
    <header className="if-detail-topbar flex min-h-[60px] flex-none items-center justify-between gap-3 rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] px-3.5 py-2 max-[760.01px]:flex-col max-[760.01px]:items-start">
      <div className="if-detail-topbar-main flex min-w-0 items-center gap-2">
        <Tooltip title="返回接口库">
          <Button
            type="text"
            aria-label="返回接口库"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(-1)}
          />
        </Tooltip>
        <div className="if-detail-heading flex min-w-0 flex-col gap-0.5">
          <div className="if-detail-title-row flex min-w-0 items-center gap-2">
            <h1 className="m-0 max-w-[520px] overflow-hidden text-ellipsis whitespace-nowrap text-[16px] font-[650] leading-6 text-[var(--srf-text)] max-[760.01px]:max-w-[70vw]">{draft.name.trim() || (isCreate ? '新建接口' : '未命名接口')}</h1>
            {isCreate ? <Tag>草稿</Tag> : null}
            {!canWrite ? <Tag>只读成员 · 不可编辑</Tag> : null}
          </div>
          <div className="if-detail-meta flex min-w-0 items-center gap-1.5 text-[11px] leading-[18px] text-[var(--srf-text-muted)]">
            <MethodBadge method={draft.method} />
            <code className="text-[11px] text-[var(--srf-text-secondary)]">{draft.path || '未填写路径'}</code>
            <span className="if-meta-dot text-[var(--srf-text-muted)]">·</span>
            <span>{draft.softwareRepositoryName || selectedRepository?.name || '未选择软件仓库'}</span>
            <span className="if-meta-dot">·</span>
            <span>{draft.updatedAt ? `更新于 ${formatTime(draft.updatedAt)}` : '尚未保存'}</span>
          </div>
        </div>
      </div>
      <div className="if-detail-topbar-actions flex flex-none items-center gap-2">
        <Tooltip title="刷新">
          <Button
            aria-label="刷新接口"
            icon={<ReloadOutlined />}
            onClick={() => {
              if (interfaceId) void interfaceQuery.refetch()
              void queryClient.invalidateQueries({ queryKey: ['apiInterfaces'] })
            }}
          />
        </Tooltip>
        {canWrite && !isCreate ? (
          <Button
            icon={<PlusOutlined />}
            onClick={() =>
              navigate(`/asset-library/interfaces/new?softwareRepositoryId=${encodeURIComponent(draft.softwareRepositoryId)}`)
            }
          >
            新建接口
          </Button>
        ) : null}
        {canWrite ? (
          <Button
            icon={<UploadOutlined />}
            disabled={!repositories.length}
            onClick={() => setImportOpen(true)}
          >
            导入 OpenAPI
          </Button>
        ) : null}
        {canWrite && !isCreate ? (
          <Button
            danger
            icon={<DeleteOutlined />}
            disabled={draft.interfaceId !== interfaceId}
            onClick={confirmDelete}
          >
            删除
          </Button>
        ) : null}
      </div>
    </header>
  )
}
