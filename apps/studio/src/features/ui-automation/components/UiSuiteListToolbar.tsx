import { SearchOutlined } from '@ant-design/icons'
import { Input, Select, Space, Tooltip } from 'antd'
import type { InputRef } from 'antd'
import { useEffect, useRef } from 'react'

import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'

/**
 * UI 测试集的筛选工具栏卡片（设计稿的 filter toolbar）：左侧迭代 / 需求 / 搜索，右侧刷新与新建。
 *
 * 设计稿里还有「批量删除」和「导出测试配置」两个按钮，都没有对应接口，不做（见 STRUCTURE.md 的未实现清单）。
 * 搜索是前端过滤，实际执行在 UiTestSuiteSection 里，这里只持有输入框。
 */
export function UiSuiteListToolbar({
  showScopeFilters,
  sprintValue,
  sprintOptions,
  sprintLoading,
  onSprintChange,
  requirementValue,
  requirementOptions,
  requirementLoading,
  requirementDisabled,
  onRequirementChange,
  keyword,
  onKeywordChange,
  createDisabled,
  onCreate,
  refreshing,
  onRefresh,
}: {
  showScopeFilters: boolean
  sprintValue: string
  sprintOptions: Array<{ label: string; value: string }>
  sprintLoading: boolean
  onSprintChange: (value: string) => void
  requirementValue: string
  requirementOptions: Array<{ label: string; value: string }>
  requirementLoading: boolean
  requirementDisabled: boolean
  onRequirementChange: (value: string) => void
  keyword: string
  onKeywordChange: (value: string) => void
  createDisabled: boolean
  onCreate: () => void
  refreshing: boolean
  onRefresh: () => void
}) {
  const keywordInputRef = useRef<InputRef>(null)

  // 搜索框右侧标了 ⌘K，那就得真的能按：Mac 用 ⌘，其他平台用 Ctrl。
  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if (event.key.toLowerCase() !== 'k' || !(event.metaKey || event.ctrlKey)) return
      event.preventDefault()
      keywordInputRef.current?.focus()
    }

    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [])

  return (
    <div className="panel-header api-panel-header ui-suite-list-toolbar tp-list-toolbar">
      <div className="ui-suite-list-toolbar-filters">
              <h1 className="tp-list-title">UI测试</h1>
        {showScopeFilters ? (
          <div className="api-filter-group">
            <div className="api-filter-field">
              <span className="api-filter-field-label">迭代</span>
              <Select
                className="api-filter-select business-filter-select"
                value={sprintValue}
                options={sprintOptions}
                loading={sprintLoading}
                placeholder="请选择迭代"
                onChange={onSprintChange}
              />
            </div>
            <div className="api-filter-field">
              <span className="api-filter-field-label">需求</span>
              <Select
                className="api-filter-select business-filter-select"
                value={requirementValue}
                options={requirementOptions}
                loading={requirementLoading}
                placeholder="请选择需求"
                disabled={requirementDisabled}
                onChange={onRequirementChange}
              />
            </div>
          </div>
        ) : null}

        <div className="api-filter-field ui-suite-list-search-field">
          <Input
            ref={keywordInputRef}
            className="api-filter-input ui-suite-list-search-input"
            allowClear
            prefix={<SearchOutlined />}
            suffix={<span className="ui-suite-list-search-hint">⌘K</span>}
            placeholder="搜索UI测试集名称 / 描述"
            value={keyword}
            onChange={(event) => onKeywordChange(event.target.value)}
          />
        </div>
      </div>

      <Space size={8} className="ui-suite-list-toolbar-actions">
        <Tooltip title="刷新测试集列表">
          <ProjectActionButton
            action="read"
            type="text"
            shape="circle"
            className="action-btn-read ui-suite-list-refresh"
            operation="refresh"
            iconOnly
            aria-label="刷新测试集列表"
            loading={refreshing}
            onClick={onRefresh}
          />
        </Tooltip>
        <ProjectActionButton
          action="write"
          type="primary"
          className="action-btn-create"
          operation="create"
          disabled={createDisabled}
          onClick={onCreate}
        >
          新建测试集
        </ProjectActionButton>
      </Space>
    </div>
  )
}
