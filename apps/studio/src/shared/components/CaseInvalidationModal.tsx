import { SearchOutlined } from '@ant-design/icons'
import { Button, Checkbox, Empty, Input, Modal } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { CaseInvalidatedTag } from '@/shared/components/CaseInvalidatedTag'
import { invalidatedAtText, isCaseInvalidated } from '@/shared/utils/caseInvalidation'

export type CaseInvalidationItem = {
  id: string
  name: string
  invalidatedAt?: string | null
}

type Props = {
  open: boolean
  /** 当前范围，例如“登录接口集 · 12 条用例”。 */
  scopeLabel: string
  cases: CaseInvalidationItem[]
  canWrite: boolean
  pending?: boolean
  onClose: () => void
  onSubmit: (caseIds: string[], invalidated: boolean) => void
}

/**
 * API / UI / 性能共用的用例状态管理弹窗。
 * 只处理失效与恢复，不承载编辑、删除或排序，避免和各自页面的编辑器职责重叠。
 */
export function CaseInvalidationModal({
  open,
  scopeLabel,
  cases,
  canWrite,
  pending = false,
  onClose,
  onSubmit,
}: Props) {
  const [keyword, setKeyword] = useState('')
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  useEffect(() => {
    if (!open) return
    setKeyword('')
    setSelectedIds([])
  }, [open])

  const filteredCases = useMemo(() => {
    const text = keyword.trim().toLowerCase()
    if (!text) return cases
    return cases.filter((item) => item.name.toLowerCase().includes(text))
  }, [cases, keyword])

  const visibleIds = filteredCases.map((item) => item.id)
  const selectedSet = new Set(selectedIds)
  const allVisibleSelected =
    visibleIds.length > 0 && visibleIds.every((caseId) => selectedSet.has(caseId))
  const someVisibleSelected = visibleIds.some((caseId) => selectedSet.has(caseId))

  function toggleCase(caseId: string) {
    setSelectedIds((current) =>
      current.includes(caseId) ? current.filter((item) => item !== caseId) : [...current, caseId],
    )
  }

  function toggleAllVisible() {
    if (allVisibleSelected) {
      setSelectedIds((current) => current.filter((caseId) => !visibleIds.includes(caseId)))
      return
    }
    setSelectedIds((current) => [...new Set([...current, ...visibleIds])])
  }

  function submit(invalidated: boolean) {
    if (selectedIds.length === 0 || !canWrite) return
    onSubmit(selectedIds, invalidated)
  }

  return (
    <Modal
      open={open}
      title="管理用例状态"
      width={600}
      footer={null}
      onCancel={onClose}
    >
      <div className="flex min-h-0 flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2 justify-between">
          <span className="text-[12px] text-[var(--srf-text-secondary)]">当前范围：{scopeLabel}</span>
          <Input
            allowClear
            value={keyword}
            prefix={<SearchOutlined />}
            placeholder="搜索用例名称"
            aria-label="搜索用例名称"
            className="max-w-[240px]"
            onChange={(event) => setKeyword(event.target.value)}
          />
        </div>

        <div className="rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)]">
          <div className="border-b border-[var(--srf-divider)] px-3 py-2">
            <Checkbox
              checked={allVisibleSelected}
              indeterminate={someVisibleSelected && !allVisibleSelected}
              disabled={visibleIds.length === 0}
              onChange={toggleAllVisible}
            >
              全选（当前筛选 {visibleIds.length} 条）
            </Checkbox>
          </div>
          <div className="max-h-[360px] overflow-auto p-1">
            {filteredCases.length === 0 ? (
              <Empty
                description={cases.length === 0 ? '当前范围还没有用例' : '没有匹配到用例'}
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                className="py-6"
              />
            ) : (
              filteredCases.map((item) => (
                <label
                  key={item.id}
                  className="flex min-w-0 cursor-pointer items-center gap-2 rounded-[var(--srf-radius-control)] px-2 py-1.5 hover:bg-[var(--srf-hover)]"
                >
                  <Checkbox
                    checked={selectedSet.has(item.id)}
                    onChange={() => toggleCase(item.id)}
                  />
                  <span className="min-w-0 flex-1 truncate text-[13px] text-[var(--srf-text)]" title={item.name}>
                    {item.name}
                  </span>
                  {isCaseInvalidated(item) ? (
                    <CaseInvalidatedTag invalidatedAt={item.invalidatedAt} className="flex-none" />
                  ) : (
                    <span className="tp-tone-tag tone-green flex-none">有效</span>
                  )}
                  {item.invalidatedAt ? (
                    <span className="flex-none text-[11px] text-[var(--srf-text-secondary)]">
                      {invalidatedAtText(item.invalidatedAt)}
                    </span>
                  ) : null}
                </label>
              ))
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 justify-between">
          <span className="text-[12px] text-[var(--srf-text-secondary)]">
            已选 {selectedIds.length} 条
          </span>
          <div className="gap-2 flex items-center">
            <Button danger disabled={!canWrite || selectedIds.length === 0} loading={pending} onClick={() => submit(true)}>
              标记失效
            </Button>
            <Button disabled={!canWrite || selectedIds.length === 0} loading={pending} onClick={() => submit(false)}>
              恢复有效
            </Button>
            <Button onClick={onClose}>取消</Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
