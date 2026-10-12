import Image from '@tiptap/extension-image'
import { TableKit } from '@tiptap/extension-table'
import { EditorContent, useEditor, type Editor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import {
  BoldOutlined,
  CodeOutlined,
  CompressOutlined,
  ExpandOutlined,
  ItalicOutlined,
  OrderedListOutlined,
  PictureOutlined,
  StrikethroughOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Modal, Tooltip } from 'antd'
import { downloadStoredFile, uploadStoredFile } from '@/shared/api/files'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { stripImageSources } from './utils'
import '@/shared/styles/surface-tokens.css'
import './rich-text-editor.css'

/**
 * 平台统一富文本编辑器：受限工具栏 + 粘贴/选择图片上传到统一文件管线。
 *
 * 存储值里 <img> 只保留 data-file-id，不带 src（后端消毒白名单一致）；
 * 编辑态的临时 src 仅用于本地预览，不会写入 value。
 */
export function RichTextEditor({
  value = '',
  onChange,
  onUploadingChange,
  projectId,
  disabled = false,
  ariaLabel = '富文本编辑器',
}: {
  value?: string
  onChange?: (html: string) => void
  onUploadingChange?: (uploading: boolean) => void
  projectId?: string
  disabled?: boolean
  ariaLabel?: string
}) {
  const [uploadCount, setUploadCount] = useState(0)
  const [expanded, setExpanded] = useState(false)
  // 同一个 Tiptap 实例只挂载一次：放大/恢复通过把编辑器卡片 DOM 整体搬进/搬出弹框实现。
  // 不能让 EditorContent 随弹框条件卸载/挂载——antd 关闭后默认保留弹框节点，
  // EditorContent 的重挂载时机会与之互踩，二次打开就是空弹框。
  // 弹框面板晚一拍才挂载，承接槽用回调 ref 记入 state，槽就绪后自动补跑搬移。
  const inlineSlotRef = useRef<HTMLDivElement>(null)
  const editorHolderRef = useRef<HTMLDivElement>(null)
  const [expandedSlot, setExpandedSlot] = useState<HTMLDivElement | null>(null)
  useEffect(() => {
    const holder = editorHolderRef.current
    const target = expanded ? expandedSlot : inlineSlotRef.current
    if (holder && target && holder.parentElement !== target) target.appendChild(holder)
  }, [expanded, expandedSlot])
  const uploading = uploadCount > 0
  useEffect(() => { onUploadingChange?.(uploading) }, [onUploadingChange, uploading])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const editorRef = useRef<Editor | null>(null)
  const projectIdRef = useRef(projectId)
  const previewUrls = useRef<string[]>([])
  useEffect(() => () => { previewUrls.current.forEach((url) => URL.revokeObjectURL(url)) }, [])
  async function fetchImageUrl(fileId: string): Promise<string> {
    const { blob } = await downloadStoredFile(fileId)
    const url = URL.createObjectURL(blob)
    previewUrls.current.push(url)
    return url
  }
  useEffect(() => {
    projectIdRef.current = projectId
  }, [projectId])

  const extensions = useMemo(
    () => [
      StarterKit.configure({ heading: { levels: [2, 3] } }),
      TableKit.configure({ table: { resizable: false } }),
      Image.extend({
        addAttributes() {
          return {
            ...this.parent?.(),
            dataFileId: {
              default: null,
              parseHTML: (element: HTMLElement) => element.getAttribute('data-file-id'),
              renderHTML: (attributes: Record<string, string | null>) => ({
                'data-file-id': attributes.dataFileId,
              }),
            },
          }
        },
      }).extend({
        // 允许解析不带 src 的 <img>：存储值只有 data-file-id。
        parseHTML() {
          return [{ tag: 'img[data-file-id]' }, { tag: 'img[src]' }]
        },
      }),
    ],
    [],
  )

  async function insertImage(file: File) {
    const editor = editorRef.current
    if (!editor) return
    const activeProjectId = projectIdRef.current
    if (!activeProjectId) {
      message.error('请先选择项目后再插入图片')
      return
    }
    if (disabled) return
    if (!['image/png', 'image/jpeg'].includes(file.type)) {
      message.error('图片仅支持 PNG 或 JPEG')
      return
    }
    setUploadCount((count) => count + 1)
    try {
      const fileId = await uploadStoredFile(activeProjectId, file, 'attachment')
      // 下载完成后使用临时 Blob 地址；保存时剥离 src。
      const src = await fetchImageUrl(fileId)
      if (editor.isDestroyed) { URL.revokeObjectURL(src); return }
      editor
        .chain()
        .focus()
        .insertContent(`<img src="${src}" data-file-id="${fileId}" alt="截图">`)
        .run()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setUploadCount((count) => count - 1)
    }
  }

  const editor = useEditor({
    extensions,
    content: value || '',
    editable: !disabled,
    editorProps: {
      attributes: { 'aria-label': ariaLabel },
      handlePaste: (_view, event) => {
        const files = Array.from(event.clipboardData?.files ?? []).filter((file) =>
          file.type.startsWith('image/'),
        )
        if (files.length === 0) return false
        event.preventDefault()
        void Promise.all(files.map((file) => insertImage(file)))
        return true
      },
    },
    onUpdate: ({ editor: current }) => {
      onChange?.(stripImageSources(current.getHTML()))
    },
  })
  useEffect(() => {
    editorRef.current = editor
  }, [editor])

  useEffect(() => {
    if (!editor) return
    editor.setEditable(!disabled, false)
    if (stripImageSources(editor.getHTML()) !== value) {
      editor.commands.setContent(value || '', { emitUpdate: false })
    }
  }, [editor, value, disabled])

  // 已保存图片只有文件 ID，编辑回显时补齐临时地址，不重建文档或覆盖用户输入。
  useEffect(() => {
    if (!editor) return
    let cancelled = false
    const ids = new Set<string>()
    editor.state.doc.descendants((node) => {
      if (node.type.name === 'image' && node.attrs.dataFileId && !node.attrs.src) ids.add(node.attrs.dataFileId)
    })
    ids.forEach((fileId) => {
      void fetchImageUrl(fileId).then((src) => {
        if (cancelled || editor.isDestroyed) { URL.revokeObjectURL(src); return }
        const transaction = editor.state.tr
        editor.state.doc.descendants((node, position) => {
          if (node.type.name === 'image' && node.attrs.dataFileId === fileId && !node.attrs.src) {
            transaction.setNodeMarkup(position, undefined, { ...node.attrs, src })
          }
        })
        if (transaction.docChanged) editor.view.dispatch(transaction.setMeta('addToHistory', false))
      }).catch(() => { if (!cancelled) message.error('图片加载失败，请重新打开编辑窗口重试') })
    })
    return () => { cancelled = true }
  }, [editor, value])

  // 放大弹框打开后把焦点交还编辑器，避免用户再点一次才能输入。
  useEffect(() => {
    if (!expanded || !editor) return
    const timer = window.setTimeout(() => { if (!editor.isDestroyed) editor.commands.focus() }, 80)
    return () => window.clearTimeout(timer)
  }, [expanded, editor])

  if (!editor) {
    return <div className="rich-text-editor rich-text-editor-loading" aria-label={ariaLabel} />
  }

  type Command = { label: string; title: string; icon: React.ReactNode; active: boolean; run: () => void }
  const commands: Command[] = [
    { label: 'table', title: '插入表格', icon: <span className="rich-text-toolbar-text">▦</span>, active: false, run: () => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run() },
    ...(editor.isActive('table') ? [
      { label: 'row', title: '增加行', icon: <span>行+</span>, active: false, run: () => editor.chain().focus().addRowAfter().run() },
      { label: 'column', title: '增加列', icon: <span>列+</span>, active: false, run: () => editor.chain().focus().addColumnAfter().run() },
      { label: 'deleteRow', title: '删除行', icon: <span>行−</span>, active: false, run: () => editor.chain().focus().deleteRow().run() },
      { label: 'deleteColumn', title: '删除列', icon: <span>列−</span>, active: false, run: () => editor.chain().focus().deleteColumn().run() },
      { label: 'deleteTable', title: '删除表格', icon: <span>▦−</span>, active: false, run: () => editor.chain().focus().deleteTable().run() },
    ] : []),
    { label: 'bold', title: '加粗', icon: <BoldOutlined />, active: editor.isActive('bold'), run: () => editor.chain().focus().toggleBold().run() },
    { label: 'italic', title: '斜体', icon: <ItalicOutlined />, active: editor.isActive('italic'), run: () => editor.chain().focus().toggleItalic().run() },
    { label: 'strike', title: '删除线', icon: <StrikethroughOutlined />, active: editor.isActive('strike'), run: () => editor.chain().focus().toggleStrike().run() },
    { label: 'h2', title: '标题', icon: <span className="rich-text-toolbar-text">H2</span>, active: editor.isActive('heading', { level: 2 }), run: () => editor.chain().focus().toggleHeading({ level: 2 }).run() },
    { label: 'h3', title: '小标题', icon: <span className="rich-text-toolbar-text">H3</span>, active: editor.isActive('heading', { level: 3 }), run: () => editor.chain().focus().toggleHeading({ level: 3 }).run() },
    { label: 'bulletList', title: '无序列表', icon: <UnorderedListOutlined />, active: editor.isActive('bulletList'), run: () => editor.chain().focus().toggleBulletList().run() },
    { label: 'orderedList', title: '有序列表', icon: <OrderedListOutlined />, active: editor.isActive('orderedList'), run: () => editor.chain().focus().toggleOrderedList().run() },
    { label: 'blockquote', title: '引用', icon: <span className="rich-text-toolbar-text">❝</span>, active: editor.isActive('blockquote'), run: () => editor.chain().focus().toggleBlockquote().run() },
    { label: 'codeBlock', title: '代码块', icon: <CodeOutlined />, active: editor.isActive('codeBlock'), run: () => editor.chain().focus().toggleCodeBlock().run() },
  ]

  const editorSurface = (
    <div className={`tp-surface rich-text-editor${disabled ? ' is-disabled' : ''}${expanded ? ' is-expanded' : ''}`}>
      <div className="rich-text-toolbar" role="toolbar" aria-label="格式工具栏">
        {commands.map((command) => (
          <Tooltip key={command.label} title={command.title}>
            <button
              type="button"
              className={`rich-text-toolbar-button${command.active ? ' is-active' : ''}`}
              aria-label={command.title}
              aria-pressed={command.active}
              disabled={disabled}
              onClick={command.run}
            >
              {command.icon}
            </button>
          </Tooltip>
        ))}
        <Tooltip title="插入图片（支持直接粘贴截图）">
          <button
            type="button"
            className="rich-text-toolbar-button"
            aria-label="插入图片"
            disabled={disabled || uploading || !projectId}
            onClick={() => fileInputRef.current?.click()}
          >
            <PictureOutlined />
          </button>
        </Tooltip>
        {uploading ? <span className="rich-text-upload-hint">图片上传中…</span> : null}
        <Tooltip title={expanded ? '恢复内联编辑' : '放大编辑'}>
          <button
            type="button"
            className="rich-text-toolbar-button rich-text-toolbar-expand"
            aria-label={expanded ? '恢复内联编辑' : '放大编辑'}
            aria-pressed={expanded}
            disabled={disabled}
            onClick={() => setExpanded((previous) => !previous)}
          >
            {expanded ? <CompressOutlined /> : <ExpandOutlined />}
          </button>
        </Tooltip>
      </div>
      <EditorContent editor={editor} className="rich-text-content" />
      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ''
          if (file) void insertImage(file)
        }}
      />
    </div>
  )

  return (
    <div className="rich-text-editor-host">
      <div ref={inlineSlotRef} />
      <Modal
        title="放大编辑"
        open={expanded}
        onCancel={() => setExpanded(false)}
        width="min(1080px, 94vw)"
        zIndex={1050}
        footer={<Button onClick={() => setExpanded(false)}>恢复内联编辑</Button>}
      >
        <div ref={setExpandedSlot} />
      </Modal>
      <div ref={editorHolderRef}>{editorSurface}</div>
    </div>
  )
}
