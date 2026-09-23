import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import type { UiTestCase } from '@/services/api'
import { normalizeUiTestCaseId } from '@/utils/format'
import { HolderOutlined } from '@ant-design/icons'
import { Empty, Popconfirm } from 'antd'
import type { DragEvent } from 'react'

import { DRAFT_CASE_ID, getUiTestCaseStepCount } from '../utils/uiTestCaseEditor'
import { formatUiCaseSerial } from '../utils/detailRunView'

/*
 * 用例顺序弹层：设计稿把用例列表收成了工具栏上的一个下拉，但顺序调整（拖拽重排）是既有能力，
 * 不能随列表一起消失，于是收进这个弹层——列表本身仍可拖拽重排、点选切换、逐条删除。
 * 弹层挂在 UiCaseControlRibbon 的「用例顺序」按钮上。
 */

type Props = {
  cases: UiTestCase[]
  selectedCaseId: string
  canReorder: boolean
  draggingCaseId: string | null
  deletingCaseId: string
  onSelect: (caseId: string) => void
  onDragStart: (event: DragEvent<HTMLDivElement>, caseId: string) => void
  onDragEnd: () => void
  onDrop: (caseId: string) => void
  onDelete: (caseId: string) => void
  onDiscardDraft: () => void
}

export function UiCaseOrderPopover({
  cases,
  selectedCaseId,
  canReorder,
  draggingCaseId,
  deletingCaseId,
  onSelect,
  onDragStart,
  onDragEnd,
  onDrop,
  onDelete,
  onDiscardDraft,
}: Props) {
  if (cases.length === 0) {
    return <Empty className="ui-wb-order-empty" description="当前测试集还没有用例" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  }

  return (
    <div className="ui-wb-order-panel tp-surface">
      <div className="ui-wb-order-head">
        <span className="ui-wb-order-title">用例顺序</span>
        <span className="ui-wb-order-hint">{canReorder ? '拖拽调整执行顺序' : '只读'}</span>
      </div>
      <div className="ui-wb-order-list">
        {cases.map((item, index) => {
          const caseId = normalizeUiTestCaseId(item)
          const isDraft = caseId === DRAFT_CASE_ID

          return (
            <div
              key={caseId}
              className={`ui-wb-order-item${caseId === selectedCaseId ? ' selected' : ''}${draggingCaseId === caseId ? ' dragging' : ''}${canReorder && !isDraft ? ' can-drag' : ''}`}
              role="button"
              tabIndex={0}
              draggable={canReorder && !isDraft}
              onDragStart={(event) => onDragStart(event, caseId)}
              onDragOver={(event) => {
                if (!canReorder || isDraft) return
                event.preventDefault()
              }}
              onDrop={(event) => {
                event.preventDefault()
                onDrop(caseId)
              }}
              onDragEnd={onDragEnd}
              onClick={() => onSelect(caseId)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onSelect(caseId)
                }
              }}
            >
              <span className="ui-wb-order-grip" aria-hidden="true">
                <HolderOutlined />
              </span>
              <span className="ui-wb-order-serial">{formatUiCaseSerial(item.orderNo ?? index + 1) || `#${index + 1}`}</span>
              <span className="ui-wb-order-name" title={item.name}>
                {item.name}
              </span>
              <span className="ui-wb-order-meta">
                {isDraft ? '草稿' : item.enabled === false ? '停用' : '启用'} · {getUiTestCaseStepCount(item)} 步
              </span>
              <span className="ui-wb-order-actions" onClick={(event) => event.stopPropagation()} onMouseDown={(event) => event.stopPropagation()}>
                <Popconfirm
                  title={isDraft ? '确认丢弃这个未保存用例？' : '确认删除该 UI测试用例？'}
                  onConfirm={() => (isDraft ? onDiscardDraft() : onDelete(caseId))}
                >
                  <ProjectActionButton
                    action="write"
                    type="text"
                    size="small"
                    className="ui-wb-order-delete action-btn-delete"
                    operation="delete"
                    iconOnly
                    loading={deletingCaseId === caseId}
                    aria-label="删除 UI测试用例"
                  />
                </Popconfirm>
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
