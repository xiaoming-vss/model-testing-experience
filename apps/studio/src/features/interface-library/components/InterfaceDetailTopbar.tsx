import {
  ArrowLeftOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { Button, Tooltip } from 'antd'
import type { InterfaceDetailPageModel } from '../hooks/useInterfaceDetailPage'

const MOBILE_ACTION_LABEL = 'max-[760.01px]:hidden'

export function InterfaceDetailTopbar({ page }: { page: InterfaceDetailPageModel }) {
  const {
    draft,
    interfaceId,
    isCreate,
    canWrite,
    dirty,
    navigate,
    interfaceQuery,
    repositories,
    selectedRepository,
    interfaceInActiveProject,
    saveMutation,
    setImportOpen,
    confirmDelete,
  } = page
  const queryClient = useQueryClient()

  if (!draft) return null

  const repositoryName =
    draft.softwareRepositoryName || selectedRepository?.name || ''
  const firstTag = draft.tags[0] ?? ''
  const saveDisabled =
    !draft.name.trim() ||
    !draft.path.trim() ||
    !draft.softwareRepositoryId ||
    !interfaceInActiveProject ||
    (!isCreate && draft.interfaceId !== interfaceId)

  return (
    <header className="if-detail-topbar flex min-h-14 flex-none flex-wrap items-center justify-between gap-2.5 rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] px-4 py-2 max-[760.01px]:items-stretch">
      <div className="if-detail-topbar-main flex min-w-0 flex-auto items-center gap-2">
        <Tooltip title="返回接口库">
          <Button
            type="text"
            aria-label="返回接口库"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(-1)}
          />
        </Tooltip>
        <h1 className="tp-list-title m-0">接口库</h1>
        <span className="text-[var(--srf-text-muted)]" aria-hidden>/</span>
        {isCreate ? (
          <span className="text-[13px] font-semibold text-[var(--srf-text)]">新建接口</span>
        ) : (
          <span
            className="max-w-[220px] overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-semibold text-[var(--srf-text)]"
            title={repositoryName}
          >
            {repositoryName || '未选择软件仓库'}
          </span>
        )}
        {firstTag ? (
          <>
            <span className="text-[var(--srf-text-muted)]" aria-hidden>/</span>
            <span
              className="max-w-[160px] overflow-hidden text-ellipsis whitespace-nowrap text-[12px] text-[var(--srf-text-secondary)]"
              title={firstTag}
            >
              {firstTag}
            </span>
          </>
        ) : null}
      </div>

      <div className="if-detail-topbar-actions flex flex-none flex-wrap items-center justify-end gap-1.5 max-[760.01px]:w-full max-[760.01px]:justify-start">
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
            aria-label="新建接口"
            icon={<PlusOutlined />}
            onClick={() =>
              navigate(
                `/asset-library/interfaces/new?softwareRepositoryId=${encodeURIComponent(draft.softwareRepositoryId)}`,
              )
            }
          >
            <span className={MOBILE_ACTION_LABEL}>新建接口</span>
          </Button>
        ) : null}
        {canWrite ? (
          <Button
            aria-label="导入 OpenAPI"
            icon={<UploadOutlined />}
            disabled={!repositories.length}
            onClick={() => setImportOpen(true)}
          >
            <span className={MOBILE_ACTION_LABEL}>导入 OpenAPI</span>
          </Button>
        ) : null}
        {canWrite && !isCreate ? (
          <Button
            danger
            aria-label="删除接口"
            icon={<DeleteOutlined />}
            disabled={draft.interfaceId !== interfaceId}
            onClick={confirmDelete}
          >
            <span className={MOBILE_ACTION_LABEL}>删除</span>
          </Button>
        ) : null}
        {canWrite ? (
          <Button
            type="primary"
            aria-label={isCreate ? '创建接口' : '保存接口'}
            className="if-save-button"
            icon={<SaveOutlined />}
            loading={saveMutation.isPending}
            disabled={saveDisabled}
            onClick={() => saveMutation.mutate()}
          >
            <span className={MOBILE_ACTION_LABEL}>
              {isCreate ? '创建接口' : dirty ? '保存更改' : '保存'}
            </span>
          </Button>
        ) : null}
      </div>
    </header>
  )
}
