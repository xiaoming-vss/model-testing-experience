import { SearchOutlined } from '@ant-design/icons'
import { Empty, Input, Popconfirm, Tooltip } from 'antd'
import type { DragEvent } from 'react'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import type { ApiCase } from '@/services/api'
import { DRAFT_CASE_ID, methodTone } from '../config/collectionConfig'
import { getCaseDisplayPath, getCaseId } from '../utils/apiCaseEditor'

/*
 * API 测试集详情页左栏：用例列表。
 * 设计稿是一张独立卡片（标题 + 计数 + 新建 / 导入两个图标按钮 + 搜索框 + 用例列表），
 * 返回按钮与测试集信息已移到顶栏（ApiCollectionToolbar）。样式见 styles/detail-workbench-v2.css。
 */

type Props = {
  /** 已经排好序的用例，草稿（如果有）在最前。 */
  cases: ApiCase[]
  selectedCaseId: string
  loading: boolean
  /** 不带搜索词的用例总数，用于区分「还没有用例」与「没有匹配到用例」。 */
  totalCaseCount: number
  search: string
  canReorder: boolean
  draggingCaseId: string | null
  onSearchChange: (value: string) => void
  onSelectCase: (caseId: string) => void
  onCreateCase: () => void
  onImportCases: () => void
  onDeleteCase: (caseId: string) => void
  onDiscardDraft: () => void
  onDragStart: (event: DragEvent<HTMLDivElement>, caseId: string) => void
  onDrop: (caseId: string) => void
  onDragEnd: () => void
}

export function ApiCaseExplorer({
  cases,
  selectedCaseId,
  loading,
  totalCaseCount,
  search,
  canReorder,
  draggingCaseId,
  onSearchChange,
  onSelectCase,
  onCreateCase,
  onImportCases,
  onDeleteCase,
  onDiscardDraft,
  onDragStart,
  onDrop,
  onDragEnd,
}: Props) {
  return (
    <section className="api-wb-explorer" aria-label="用例列表">
      <div className="api-wb-explorer-head">
        <span className="api-wb-explorer-title">
          用例列表
          <span className="api-wb-explorer-count">{cases.length}</span>
        </span>
        <span className="api-wb-explorer-actions">
          <ProjectActionButton
            action="write"
            type="text"
            className="api-wb-explorer-action"
            operation="create"
            iconOnly
            aria-label="新建用例"
            title="新建用例"
            onClick={onCreateCase}
          />
          <ProjectActionButton
            action="execute"
            type="text"
            className="api-wb-explorer-action"
            operation="upload"
            iconOnly
            aria-label="用例导入"
            title="从 YAML 导入用例"
            onClick={onImportCases}
          />
        </span>
      </div>

      <div className="api-wb-explorer-search">
        <Input
          allowClear
          value={search}
          prefix={<SearchOutlined />}
          placeholder="搜索用例名称 / 接口路径"
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </div>

      <div className="api-wb-explorer-scroll">
        {loading ? (
          <div className="api-wb-explorer-placeholder">
            <Empty description="用例加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </div>
        ) : cases.length === 0 ? (
          <div className="api-wb-explorer-placeholder">
            <Empty description={totalCaseCount === 0 ? '当前还没有用例' : '没有匹配到用例'}>
              <ProjectActionButton
                action="write"
                type="primary"
                className="action-btn-create"
                operation="create"
                onClick={onCreateCase}
              >
                新建用例
              </ProjectActionButton>
            </Empty>
          </div>
        ) : (
          <div className="api-wb-case-list">
            {cases.map((item) => {
              const caseId = getCaseId(item)
              const isDraft = caseId === DRAFT_CASE_ID
              const selected = caseId === selectedCaseId
              const path = getCaseDisplayPath(item.urlTemplate)
              const tone = methodTone(item.method)

              return (
                <div
                  key={caseId}
                  className={`api-wb-case-item tone-${tone}${selected ? ' selected' : ''}${draggingCaseId === caseId ? ' dragging' : ''}${canReorder ? ' can-drag' : ''}`}
                  role="button"
                  tabIndex={0}
                  aria-current={selected ? 'true' : undefined}
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
                  onClick={() => onSelectCase(caseId)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      onSelectCase(caseId)
                    }
                  }}
                >
                  <span className="api-wb-case-item-main">
                    <span className="api-wb-case-item-head">
                      <span className="api-wb-case-method">{item.method}</span>
                      <span className="api-wb-case-item-name">{item.name}</span>
                      {isDraft ? <span className="api-wb-case-draft">草稿</span> : null}
                    </span>
                    <span className="api-wb-case-item-path">{path}</span>
                  </span>
                  <span className="api-wb-case-item-actions">
                    <Popconfirm
                      title={isDraft ? '确认丢弃这个未保存用例？' : '确认删除该用例？'}
                      onConfirm={() => {
                        if (isDraft) {
                          onDiscardDraft()
                          return
                        }
                        onDeleteCase(caseId)
                      }}
                    >
                      <Tooltip title={isDraft ? '丢弃草稿' : '删除用例'}>
                        <ProjectActionButton
                          action="write"
                          danger
                          type="text"
                          size="small"
                          operation="delete"
                          iconOnly
                          className="api-wb-case-delete"
                          aria-label={isDraft ? '丢弃草稿' : '删除用例'}
                          onClick={(event) => event.stopPropagation()}
                          onMouseDown={(event) => event.stopPropagation()}
                        />
                      </Tooltip>
                    </Popconfirm>
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </section>
  )
}
