import '@/features/ai-testing/styles/functional-import-confirm.css'
import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/case-name-tree.css'
import type { CaseNameTreeNode } from '@/features/ai-testing/utils/caseNameTree'
import { CASE_NAME_TREE_CONNECTOR_WIDTH, CASE_NAME_TREE_NODE_HEIGHT, buildCaseNameTree, countCaseNameTree, deleteCaseNameTreeNode, getModelHeight, getModelTargetYs, getPointTargetYs, getTestModelHeight, getTestModelTargetYs, getTreeHeight, renameCaseNameTreeNode, serializeCaseNameTree, updateCategoryCaseNamesContent } from '@/features/ai-testing/utils/caseNameTree'
import { isJsonText } from '@/features/ai-testing/utils/functionalOutput'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { JsonEditor } from '@/shared/components/JsonEditor/JsonEditor'
import { message } from '@/shared/utils/feedback'
import { PictureOutlined } from '@ant-design/icons'
import { Input, Popconfirm, Tabs, Tag } from 'antd'
import { toBlob } from 'html-to-image'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

export type CaseNamesViewMode = 'json' | 'tree'

const CURVE_STROKE_META = {
  green: { color: 'rgba(124, 195, 163, 0.68)', width: 2 },
  blue: { color: 'rgba(70, 166, 210, 0.58)', width: 2 },
  slate: { color: 'rgba(100, 116, 139, 0.46)', width: 1.8 },
} as const

function CaseNameTreeCurves({ height, targetYs, layoutKey, tone = 'green' }: { height: number; targetYs: number[]; layoutKey: string; tone?: 'green' | 'blue' | 'slate' }) {
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [layout, setLayout] = useState<{ height: number; targetYs: number[] } | null>(null)
  const targetKey = targetYs.join(',')

  useLayoutEffect(() => {
    const svg = svgRef.current
    const source = svg?.previousElementSibling
    const targets = svg?.nextElementSibling
    if (!source || !targets) return

    // 换行后的节点高度各不相同，连接线使用实际布局中的节点中心。
    const measure = () => {
      const bounds = targets.getBoundingClientRect()
      if (!bounds.height) return
      const measuredHeight = Math.max(bounds.height, source.getBoundingClientRect().height)
      const next = {
        height: measuredHeight,
        targetYs: Array.from(targets.children, (child) => {
          const rect = child.getBoundingClientRect()
          return rect.top - bounds.top + rect.height / 2 + (measuredHeight - bounds.height) / 2
        }),
      }
      setLayout((current) => current?.height === next.height
        && current.targetYs.length === next.targetYs.length
        && current.targetYs.every((y, index) => y === next.targetYs[index]) ? current : next)
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(source)
    observer.observe(targets)
    Array.from(targets.children).forEach((child) => observer.observe(child))
    return () => observer.disconnect()
  }, [height, targetKey, layoutKey])

  const safeHeight = Math.max(layout?.height ?? height, CASE_NAME_TREE_NODE_HEIGHT)
  const sourceY = safeHeight / 2
  const width = CASE_NAME_TREE_CONNECTOR_WIDTH
  // 描边同时写成 presentation attributes，保证 html-to-image 导出图片时曲线样式不丢失
  const stroke = CURVE_STROKE_META[tone]

  return (
    <svg
      ref={svgRef}
      className={`ai-case-name-tree-curves ${tone}`}
      width={width}
      height={safeHeight}
      viewBox={`0 0 ${width} ${safeHeight}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {(layout?.targetYs ?? targetYs).map((targetY, index) => {
        const controlOffset = Math.min(42, Math.max(24, Math.abs(targetY - sourceY) * 0.42 + 18))
        const d = `M 2 ${sourceY} C ${controlOffset} ${sourceY}, ${width - controlOffset} ${targetY}, ${width - 2} ${targetY}`
        return (
          <path
            key={`${targetY}-${index}`}
            d={d}
            fill="none"
            stroke={stroke.color}
            strokeWidth={stroke.width}
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        )
      })}
    </svg>
  )
}

function CaseNameTreeNodeView({
  node,
  className,
  editable,
  onRename,
  onDelete,
}: {
  node: CaseNameTreeNode
  className: string
  editable?: boolean
  onRename?: (nodeId: string, title: string) => void
  onDelete?: (nodeId: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draftTitle, setDraftTitle] = useState(node.title)
  const canEdit = Boolean(editable && node.kind !== 'root')

  useEffect(() => {
    setDraftTitle(node.title)
  }, [node.title])

  function commitEdit() {
    const nextTitle = draftTitle.trim()
    if (!nextTitle) {
      message.warning('节点名称不能为空')
      setDraftTitle(node.title)
      setEditing(false)
      return
    }

    if (nextTitle !== node.title) {
      onRename?.(node.id, nextTitle)
    }
    setEditing(false)
  }

  return (
    <div className={`${className}${canEdit ? ' editable' : ''}`} title={node.title}>
      {editing ? (
        <Input
          className="ai-case-name-tree-node-input"
          size="small"
          value={draftTitle}
          autoFocus
          onChange={(event) => setDraftTitle(event.target.value)}
          onBlur={commitEdit}
          onPressEnter={commitEdit}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              setDraftTitle(node.title)
              setEditing(false)
            }
          }}
        />
      ) : (
        <span className="ai-case-name-tree-node-label">{node.title}</span>
      )}
      {canEdit && !editing ? (
        <span className="ai-case-name-tree-node-actions">
          <ProjectActionButton action="write"
            type="text"
            size="small"
            operation="edit" iconOnly
            aria-label="编辑节点"
            onClick={(event) => {
              event.stopPropagation()
              setEditing(true)
            }}
          />
          <Popconfirm
            title="确认删除该节点？"
            onConfirm={() => onDelete?.(node.id)}
          >
            <ProjectActionButton action="write"
              danger
              type="text"
              size="small"
              operation="delete" iconOnly
              aria-label="删除节点"
              onClick={(event) => event.stopPropagation()}
            />
          </Popconfirm>
        </span>
      ) : null}
    </div>
  )
}

export function CaseNameTreeView({
  content,
  rootTitle,
  expanded = false,
  editable = false,
  onTreeChange,
}: {
  content: string
  rootTitle: string
  expanded?: boolean
  editable?: boolean
  onTreeChange?: (content: string) => void
}) {
  const tree = buildCaseNameTree(content, rootTitle)
  const counts = countCaseNameTree(tree)
  const canvasRef = useRef<HTMLDivElement | null>(null)
  const [exportingImage, setExportingImage] = useState(false)

  async function handleSaveTreeImage() {
    const canvas = canvasRef.current
    if (!canvas) return
    setExportingImage(true)
    try {
      // 页面上的树卡片带有边框、圆角和渐变背景，导出时在克隆节点上补齐，保证图片与页面显示一致
      const cardVisualStyle = {
        background: 'radial-gradient(circle at 24px 24px, rgba(124, 195, 163, 0.08), transparent 26px), #ffffff',
        border: '1px solid rgba(148, 163, 184, 0.14)',
        borderRadius: '14px',
      }
      const blob = await toBlob(canvas, {
        pixelRatio: 2,
        skipFonts: true,
        style: cardVisualStyle,
      })
      if (!blob) throw new Error('导出内容为空')
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${rootTitle}-测试点树图.png`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
      message.success('图片已保存')
    } catch {
      message.error('图片导出失败，请重试')
    } finally {
      setExportingImage(false)
    }
  }

  if (!tree) {
    return <JsonEditor value={content} readOnly foldable minHeight={expanded ? 560 : 260} />
  }

  const treeHeight = getTreeHeight(tree)
  const handleRename = (nodeId: string, title: string) => {
    onTreeChange?.(updateCategoryCaseNamesContent(content, nodeId, 'rename', title) ?? serializeCaseNameTree(renameCaseNameTreeNode(tree, nodeId, title)))
  }
  const handleDelete = (nodeId: string) => {
    onTreeChange?.(updateCategoryCaseNamesContent(content, nodeId, 'delete') ?? serializeCaseNameTree(deleteCaseNameTreeNode(tree, nodeId)))
  }

  return (
    <div className={`ai-case-name-tree${expanded ? ' expanded' : ''}${editable ? ' editable' : ''}`}>
      <div className="ai-case-name-tree-stats">
        <Tag color="green">model {counts.models}</Tag>
        <Tag color="cyan">test_model {counts.testModels}</Tag>
        <Tag color="blue">test_points {counts.testPoints}</Tag>
        <ProjectActionButton action="write"
          className="ai-case-name-tree-export"
          size="small"
          icon={<PictureOutlined />}
          loading={exportingImage}
          onClick={handleSaveTreeImage}
        >
          保存图片
        </ProjectActionButton>
      </div>
      <div className="ai-case-name-tree-canvas" ref={canvasRef}>
        <CaseNameTreeNodeView
          node={tree}
          className="ai-case-name-tree-root"
          editable={editable}
          onRename={handleRename}
          onDelete={handleDelete}
        />
        <CaseNameTreeCurves layoutKey={content} height={treeHeight} targetYs={getModelTargetYs(tree)} tone="green" />
        <div className="ai-case-name-tree-branches">
          {tree.children.map((model) => (
            <div key={model.id} className="ai-case-name-tree-row">
              <CaseNameTreeNodeView
                node={model}
                className="ai-case-name-tree-node model"
                editable={editable}
                onRename={handleRename}
                onDelete={handleDelete}
              />
              <CaseNameTreeCurves layoutKey={content} height={getModelHeight(model)} targetYs={getTestModelTargetYs(model)} tone="blue" />
              <div className="ai-case-name-tree-children">
                {model.children.map((testModel) => (
                  <div key={testModel.id} className="ai-case-name-tree-row nested">
                    <CaseNameTreeNodeView
                      node={testModel}
                      className="ai-case-name-tree-node test-model"
                      editable={editable}
                      onRename={handleRename}
                      onDelete={handleDelete}
                    />
                    <CaseNameTreeCurves layoutKey={content} height={getTestModelHeight(testModel)} targetYs={getPointTargetYs(testModel)} tone="slate" />
                    <div className="ai-case-name-tree-children point-list">
                      {testModel.children.map((point) => (
                        <CaseNameTreeNodeView
                          key={point.id}
                          node={point}
                          className="ai-case-name-tree-node point"
                          editable={editable}
                          onRename={handleRename}
                          onDelete={handleDelete}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export function CaseNamesResultView({
  content,
  rootTitle,
  expanded = false,
  activeView,
  onViewChange,
}: {
  content: string
  rootTitle: string
  expanded?: boolean
  activeView?: CaseNamesViewMode
  onViewChange?: (view: CaseNamesViewMode) => void
}) {
  return (
    <Tabs
      className={`ai-case-names-inner-tabs${expanded ? ' expanded' : ''}`}
      size="small"
      activeKey={activeView}
      onChange={(key) => onViewChange?.(key as CaseNamesViewMode)}
      items={[
        {
          key: 'tree',
          label: '可视化',
          children: <CaseNameTreeView content={content} rootTitle={rootTitle} expanded={expanded} />,
        },
        {
          key: 'json',
          label: 'json',
          children: isJsonText(content) ? (
            <JsonEditor value={content} readOnly foldable minHeight={expanded ? 520 : 240} />
          ) : (
            <pre className="ai-task-code-block">{content}</pre>
          ),
        },
      ]}
    />
  )
}
