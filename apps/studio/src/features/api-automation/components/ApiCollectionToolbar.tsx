import { ArrowLeftOutlined, HistoryOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { Button } from 'antd'

/*
 * API 测试集详情页顶栏：返回 / 测试集名 + 需求 + 迭代 / 当前环境 / 运行记录 / 运行测试集。
 * 设计稿把这几项画在同一行；测试集与需求的层级信息原来在侧栏头部和「Collection 详情」卡片里，
 * 这里合到顶栏后那两块就不再需要。样式见 styles/detail-workbench-v2.css。
 */

type Props = {
  collectionName: string
  requirementName: string
  sprintName: string
  /** 最近更新时间，取自测试集自身。 */
  updatedAt: string
  /** 当前启用环境的 Base URL，没有环境时为空。 */
  environmentBaseUrl: string
  runHistoryCount: number
  runningCollection: boolean
  runDisabled: boolean
  onBack: () => void
  onOpenRunHistory: () => void
  onRunCollection: () => void
}

export function ApiCollectionToolbar({
  collectionName,
  requirementName,
  sprintName,
  updatedAt,
  environmentBaseUrl,
  runHistoryCount,
  runningCollection,
  runDisabled,
  onBack,
  onOpenRunHistory,
  onRunCollection,
}: Props) {
  return (
    <div className="api-wb-toolbar">
      <div className="api-wb-toolbar-main">
        <Button
          type="text"
          className="api-wb-toolbar-back"
          icon={<ArrowLeftOutlined />}
          aria-label="返回API测试集列表"
          title="返回API测试集列表"
          onClick={onBack}
        />
        <h1 className="api-wb-toolbar-title">
          <span className="api-wb-toolbar-label">Collection 详情:</span>
          <span className="api-wb-toolbar-name">{collectionName}</span>
          <span className="api-wb-toolbar-path">/ {requirementName} / {sprintName}</span>
        </h1>
        <span
          className={`api-wb-toolbar-env${environmentBaseUrl ? '' : ' empty'}`}
          title={environmentBaseUrl || '当前项目还没有可用环境'}
        >
          <span className="api-wb-toolbar-env-dot" aria-hidden="true" />
          {environmentBaseUrl || '未选择环境'}
        </span>
        <span className="api-wb-toolbar-updated">更新 {updatedAt}</span>
      </div>

      <div className="api-wb-toolbar-actions">
        <Button className="api-wb-toolbar-history" icon={<HistoryOutlined />} onClick={onOpenRunHistory}>
          运行记录{runHistoryCount > 0 ? ` (${runHistoryCount})` : ''}
        </Button>
        <Button
          type="primary"
          className="api-wb-toolbar-run"
          icon={<PlayCircleOutlined />}
          loading={runningCollection}
          disabled={runDisabled}
          onClick={onRunCollection}
        >
          运行测试集
        </Button>
      </div>
    </div>
  )
}
